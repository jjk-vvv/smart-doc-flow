import { parseErrorMessage } from "./api/client";
import { Capacitor } from "@capacitor/core";
import { Directory, Filesystem } from "@capacitor/filesystem";

export type MobileDownloadModule =
  | "module1"
  | "module2"
  | "module3"
  | "module4"
  | "general";

export type MobileDownloadMode = "native" | "browser";

export type MobileDownloadResult = {
  mode: MobileDownloadMode;
  fileName: string;
  relativePath: string;
  savedPath?: string | null;
};

type NativeSaveRequest = {
  fileName: string;
  mimeType: string;
  base64Data: string;
  relativePath: string;
  directory: "documents";
  conflictPolicy: "uniquify";
};

type NativeSaveResponse =
  | string
  | {
      ok?: boolean;
      savedPath?: string | null;
      relativePath?: string | null;
      error?: string | null;
    };

type NativeFileBridge = {
  saveFile: (
    request: NativeSaveRequest,
  ) => Promise<NativeSaveResponse> | NativeSaveResponse;
};

declare global {
  interface Window {
    smartDocFlowNative?: {
      files?: Partial<NativeFileBridge>;
    };
    SmartDocFlowNative?: {
      files?: Partial<NativeFileBridge>;
    };
  }
}

const MODULE_RELATIVE_DIRECTORY: Record<MobileDownloadModule, string> = {
  module1: "SmartDocFlow/Module1/Exports",
  module2: "SmartDocFlow/Module2/Artifacts",
  module3: "SmartDocFlow/Module3/Outputs",
  module4: "SmartDocFlow/Module4/Exports",
  general: "SmartDocFlow/Downloads",
};

const normalizeFileName = (value: string): string => {
  const trimmed = String(value || "").trim();
  const fallback = "download.bin";
  if (!trimmed) return fallback;
  const normalized = trimmed
    .replace(/[<>:"/\\|?*\u0000-\u001F]+/g, "_")
    .replace(/\s+/g, " ")
    .trim();
  return normalized || fallback;
};

const extractFileNameFromUrl = (url: string): string | null => {
  try {
    const pathname = new URL(url, window.location.origin).pathname;
    const candidate = pathname.split("/").pop();
    return candidate ? decodeURIComponent(candidate) : null;
  } catch {
    return null;
  }
};

const parseContentDispositionFileName = (headerValue: string | null): string | null => {
  if (!headerValue) return null;

  const utf8Match = headerValue.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const asciiMatch = headerValue.match(/filename="?([^";]+)"?/i);
  return asciiMatch?.[1] ? asciiMatch[1].trim() : null;
};

const triggerBrowserDownload = (blob: Blob, fileName: string): void => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 120);
};

const resolveNativeFileBridge = (): NativeFileBridge | null => {
  const bridge =
    window.smartDocFlowNative?.files?.saveFile
      ? window.smartDocFlowNative.files
      : window.SmartDocFlowNative?.files?.saveFile
        ? window.SmartDocFlowNative.files
        : null;

  return bridge && typeof bridge.saveFile === "function"
    ? { saveFile: bridge.saveFile.bind(bridge) }
    : null;
};

const isCapacitorNativeRuntime = (): boolean => {
  try {
    return Boolean(Capacitor.isNativePlatform());
  } catch {
    return false;
  }
};

const saveFileViaCapacitorFilesystem = async ({
  base64Data,
  relativePath,
}: {
  base64Data: string;
  relativePath: string;
}): Promise<MobileDownloadResult | null> => {
  if (!isCapacitorNativeRuntime()) return null;
  try {
    const writeResult = await Filesystem.writeFile({
      path: relativePath,
      data: base64Data,
      directory: Directory.Documents,
      recursive: true,
    });
    return {
      mode: "native",
      fileName: normalizeFileName(relativePath.split("/").pop() || "download.bin"),
      relativePath,
      savedPath: String(writeResult?.uri || "").trim() || null,
    };
  } catch {
    return null;
  }
};

const blobToBase64 = async (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("读取下载文件失败"));
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      const base64 = result.includes(",") ? result.split(",").pop() || "" : result;
      if (!base64) {
        reject(new Error("下载文件编码失败"));
        return;
      }
      resolve(base64);
    };
    reader.readAsDataURL(blob);
  });

const buildRelativePath = (
  moduleName: MobileDownloadModule,
  fileName: string,
): string => `${MODULE_RELATIVE_DIRECTORY[moduleName]}/${normalizeFileName(fileName)}`;

const normalizeNativeSaveResponse = (
  response: NativeSaveResponse,
  fallbackRelativePath: string,
): { ok: boolean; savedPath?: string | null; relativePath: string; error?: string | null } => {
  if (typeof response === "string") {
    return {
      ok: Boolean(response.trim()),
      savedPath: response.trim() || null,
      relativePath: fallbackRelativePath,
    };
  }

  return {
    ok: response?.ok !== false,
    savedPath: response?.savedPath ?? null,
    relativePath: String(response?.relativePath || fallbackRelativePath).trim() || fallbackRelativePath,
    error: response?.error ?? null,
  };
};

export const describeMobileDownloadResult = (
  result: MobileDownloadResult,
): string => (
  result.mode === "native"
    ? `已保存到应用文件：${result.relativePath}`
    : "当前运行环境未接入应用内文件存储，已回退为系统下载"
);

export const saveBlobToMobileDevice = async ({
  blob,
  fileName,
  moduleName,
  mimeType,
}: {
  blob: Blob;
  fileName: string;
  moduleName: MobileDownloadModule;
  mimeType?: string | null;
}): Promise<MobileDownloadResult> => {
  const normalizedFileName = normalizeFileName(fileName);
  const relativePath = buildRelativePath(moduleName, normalizedFileName);
  const bridge = resolveNativeFileBridge();
  const base64Data = await blobToBase64(blob).catch(() => "");

  if (bridge && base64Data) {
    try {
      const nativeResponse = await bridge.saveFile({
        fileName: normalizedFileName,
        mimeType: String(mimeType || blob.type || "application/octet-stream"),
        base64Data,
        relativePath,
        directory: "documents",
        conflictPolicy: "uniquify",
      });
      const normalized = normalizeNativeSaveResponse(nativeResponse, relativePath);
      if (normalized.ok) {
        return {
          mode: "native",
          fileName: normalizedFileName,
          relativePath: normalized.relativePath,
          savedPath: normalized.savedPath ?? null,
        };
      }
    } catch {
      // Fall through to browser download to preserve current functionality.
    }
  }

  if (base64Data) {
    const capacitorSaved = await saveFileViaCapacitorFilesystem({
      base64Data,
      relativePath,
    });
    if (capacitorSaved) {
      return capacitorSaved;
    }
  }

  triggerBrowserDownload(blob, normalizedFileName);
  return {
    mode: "browser",
    fileName: normalizedFileName,
    relativePath,
    savedPath: null,
  };
};

export const downloadUrlToMobileDevice = async ({
  url,
  fileName,
  moduleName,
  init,
}: {
  url: string;
  fileName?: string | null;
  moduleName: MobileDownloadModule;
  init?: RequestInit;
}): Promise<MobileDownloadResult> => {
  const response = await fetch(url, {
    credentials: "include",
    ...init,
  });
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  const responseBlob = await response.blob();
  const responseFileName =
    normalizeFileName(
      String(
        fileName
          || parseContentDispositionFileName(response.headers.get("Content-Disposition"))
          || extractFileNameFromUrl(response.url)
          || "download.bin",
      ),
    );

  return saveBlobToMobileDevice({
    blob: responseBlob,
    fileName: responseFileName,
    moduleName,
    mimeType: responseBlob.type || response.headers.get("Content-Type"),
  });
};
