import React, { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, RefreshCw, Save, ArrowLeft } from "lucide-react";
import {
  parseModule3ExcelJson,
  saveModule3RunOutput,
  type Module3ExcelSheet,
} from "../../lib/module3Api";
import { cn } from "../../lib/utils";

type ExcelPreviewDocument = {
  id: string;
  name: string;
};

type Module3ExcelPreviewProps = {
  document: ExcelPreviewDocument;
  fallbackContent: string;
  onBack?: () => void;
};

type LuckysheetCell = {
  v?: string | number | boolean | null;
  m?: string | number | boolean | null;
};

type LuckysheetSheet = {
  name?: string;
  data?: Array<Array<LuckysheetCell | null | undefined>>;
};

type LuckysheetApi = {
  create: (config: Record<string, unknown>) => void;
  destroy: () => void;
  getAllSheets: () => LuckysheetSheet[];
};

declare global {
  interface Window {
    luckysheet?: LuckysheetApi;
    __luckysheetLoaderPromise?: Promise<void>;
  }
}

const MIN_DISPLAY_ROWS = 36;
const MIN_DISPLAY_COLUMNS = 8;

const normalizeRows = (rows: Module3ExcelSheet["rows"], columnCount: number) =>
  rows.map((row) =>
    Array.from({ length: columnCount }, (_, index) => row[index] ?? null),
  );

const LUCKYSHEET_STYLE_URLS = [
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/plugins/css/pluginsCss.css",
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/plugins/plugins.css",
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/css/luckysheet.css",
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/assets/iconfont/iconfont.css",
];

const LUCKYSHEET_SCRIPT_URLS = [
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/plugins/js/plugin.js",
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/luckysheet.umd.js",
];

const ensureLuckysheetStyles = () => {
  if (typeof document === "undefined") return;
  LUCKYSHEET_STYLE_URLS.forEach((href) => {
    if (
      document.querySelector(`link[data-luckysheet-style="${href}"]`) instanceof
      HTMLLinkElement
    ) {
      return;
    }
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.setAttribute("data-luckysheet-style", href);
    document.head.appendChild(link);
  });
};

const loadScript = (src: string) =>
  new Promise<void>((resolve, reject) => {
    if (typeof document === "undefined") {
      reject(new Error("当前环境不支持 Luckysheet。"));
      return;
    }
    const existing = document.querySelector(
      `script[data-luckysheet-script="${src}"]`,
    ) as HTMLScriptElement | null;
    if (existing) {
      if (existing.dataset.loaded === "true") {
        resolve();
        return;
      }
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("Luckysheet 脚本加载失败。")),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.setAttribute("data-luckysheet-script", src);
    script.addEventListener(
      "load",
      () => {
        script.dataset.loaded = "true";
        resolve();
      },
      { once: true },
    );
    script.addEventListener(
      "error",
      () => reject(new Error("Luckysheet 脚本加载失败。")),
      { once: true },
    );
    document.body.appendChild(script);
  });

const ensureLuckysheetLoaded = async () => {
  if (typeof window === "undefined") return;
  if (window.luckysheet) return;
  if (!window.__luckysheetLoaderPromise) {
    window.__luckysheetLoaderPromise = (async () => {
      ensureLuckysheetStyles();
      for (const src of LUCKYSHEET_SCRIPT_URLS) {
        await loadScript(src);
      }
      if (!window.luckysheet) {
        throw new Error("Luckysheet 初始化失败。");
      }
    })().catch((error) => {
      window.__luckysheetLoaderPromise = undefined;
      throw error;
    });
  }
  await window.__luckysheetLoaderPromise;
};

const toLuckysheetData = (sheets: Module3ExcelSheet[]) =>
  sheets.map((sheet, index) => {
    const celldata: Array<{
      r: number;
      c: number;
      v: { v: string | number | boolean | null; m: string };
    }> = [];

    sheet.rows.forEach((row, rowIndex) => {
      row.forEach((cell, colIndex) => {
        if (cell === undefined || cell === null || cell === "") return;
        celldata.push({
          r: rowIndex,
          c: colIndex,
          v: {
            v: cell,
            m: String(cell),
          },
        });
      });
    });

    return {
      name: sheet.name,
      index: index.toString(),
      order: index,
      status: index === 0 ? 1 : 0,
      row: Math.max(sheet.row_count, sheet.rows.length, MIN_DISPLAY_ROWS),
      column: Math.max(sheet.column_count, MIN_DISPLAY_COLUMNS),
      celldata,
    };
  });

const toSavePayload = (sheets: LuckysheetSheet[]) =>
  sheets.map((sheet) => {
    const rows: Array<Array<string | number | boolean | null>> = [];
    const sheetData = Array.isArray(sheet.data) ? sheet.data : [];

    for (let rowIndex = 0; rowIndex < sheetData.length; rowIndex += 1) {
      const sourceRow = Array.isArray(sheetData[rowIndex])
        ? sheetData[rowIndex]
        : [];
      const rowData: Array<string | number | boolean | null> = [];
      for (let colIndex = 0; colIndex < sourceRow.length; colIndex += 1) {
        const cell = sourceRow[colIndex];
        rowData.push(
          cell && cell.v !== undefined && cell.v !== null ? cell.v : "",
        );
      }
      rows.push(rowData);
    }

    let lastNonEmptyRow = -1;
    for (let rowIndex = rows.length - 1; rowIndex >= 0; rowIndex -= 1) {
      if (rows[rowIndex].some((value) => value !== "")) {
        lastNonEmptyRow = rowIndex;
        break;
      }
    }

    return {
      name: sheet.name ?? "Sheet1",
      rows: rows.slice(0, lastNonEmptyRow + 1),
    };
  });

export const Module3ExcelPreview: React.FC<Module3ExcelPreviewProps> = ({
  document,
  fallbackContent,
  onBack,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const containerIdRef = useRef(
    `luckysheet-mobile-${document.id.replace(/[^a-z0-9_-]/gi, "-")}`,
  );
  const [sheets, setSheets] = useState<Module3ExcelSheet[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isBootingSheet, setIsBootingSheet] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const workbookTitle = useMemo(
    () => document.name.replace(/\.[^.]+$/, "") || document.name,
    [document.name],
  );

  const loadWorkbook = async () => {
    setIsLoading(true);
    setError("");
    setMessage("");
    try {
      const response = await parseModule3ExcelJson(document.id);
      const nextSheets = response.sheets.map((sheet) => ({
        ...sheet,
        rows: normalizeRows(sheet.rows, sheet.column_count),
      }));
      setSheets(nextSheets);
    } catch (loadError) {
      setSheets([]);
      setError(
        loadError instanceof Error ? loadError.message : fallbackContent,
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadWorkbook();
  }, [document.id]);

  useEffect(() => {
    if (!containerRef.current || isLoading || sheets.length === 0) return;

    let cancelled = false;
    setIsBootingSheet(true);

    const mountLuckysheet = async () => {
      try {
        await ensureLuckysheetLoaded();
        if (cancelled || !window.luckysheet) return;

        try {
          window.luckysheet.destroy();
        } catch {
          // Ignore stale instance cleanup failures.
        }

        window.luckysheet.create({
          container: containerIdRef.current,
          data: toLuckysheetData(sheets),
          showinfobar: false,
          showtoolbar: true,
          showsheetbar: true,
          showstatisticBar: true,
          enableAddRow: true,
          enableAddBackTop: true,
          lang: "zh",
        });

        if (!cancelled) {
          setError("");
        }
      } catch (mountError) {
        if (!cancelled) {
          setError(
            mountError instanceof Error
              ? mountError.message
              : "Luckysheet 加载失败。",
          );
        }
      } finally {
        if (!cancelled) {
          setIsBootingSheet(false);
        }
      }
    };

    void mountLuckysheet();

    return () => {
      cancelled = true;
      try {
        window.luckysheet?.destroy();
      } catch {
        // Ignore cleanup failures from the global singleton.
      }
    };
  }, [isLoading, sheets]);

  const handleSave = async () => {
    const luckysheet = window.luckysheet;
    if (!luckysheet) {
      setError("Luckysheet 尚未完成初始化。");
      return;
    }

    setIsSaving(true);
    setError("");
    setMessage("");
    try {
      const payloadSheets = toSavePayload(luckysheet.getAllSheets());
      await saveModule3RunOutput(document.id, { sheets: payloadSheets });
      setMessage("Excel 已保存。");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存失败。");
    } finally {
      setIsSaving(false);
    }
  };

  const showLoadingMask = isLoading || isBootingSheet;
  const hasRenderableSheet = sheets.length > 0;

  return (
    <div className="relative flex h-full min-h-full w-full min-w-0 flex-col overflow-hidden bg-white">
      <div className="relative z-10 flex items-center justify-between gap-3 border-b border-slate-100 bg-white/80 px-4 pb-3 pt-[max(12px,env(safe-area-inset-top))] backdrop-blur-md shadow-sm">
        {onBack ? (
          <button
            type="button"
            onClick={onBack}
            className="group relative flex h-9 items-center justify-center gap-1.5 overflow-hidden rounded-full bg-slate-50 px-3.5 text-[14px] font-bold text-slate-700 shadow-[0_2px_8px_rgba(15,23,42,0.04)] ring-1 ring-slate-900/5 transition-all active:scale-95"
          >
            <div className="absolute inset-0 bg-slate-900/0 transition-colors group-hover:bg-slate-900/5 group-active:bg-slate-900/10" />
            <ArrowLeft size={16} className="relative z-10" />
            <span className="relative z-10">返回</span>
          </button>
        ) : (
          <div className="h-9 min-w-[76px] shrink-0" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1 text-center">
          <p className="truncate text-[16px] font-bold text-slate-900">
            表格预览
          </p>
        </div>
        <div className="flex shrink-0 items-center justify-end gap-2 min-w-[76px]">
          <button
            type="button"
            onClick={() => void loadWorkbook()}
            disabled={showLoadingMask}
            className="group relative flex h-8 items-center justify-center gap-1.5 overflow-hidden rounded-full bg-slate-50 px-3 text-[13px] font-bold text-slate-600 shadow-[0_2px_8px_rgba(15,23,42,0.04)] ring-1 ring-slate-900/5 transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <div className="absolute inset-0 bg-slate-900/0 transition-colors group-hover:bg-slate-900/5 group-active:bg-slate-900/10" />
            <RefreshCw
              size={13}
              className={cn("relative z-10", showLoadingMask && "animate-spin")}
            />
            <span className="relative z-10">刷新</span>
          </button>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={showLoadingMask || isSaving || !hasRenderableSheet}
            className="group relative flex h-8 items-center justify-center gap-1.5 overflow-hidden rounded-full bg-emerald-50 px-3 text-[13px] font-bold text-emerald-600 shadow-[0_2px_8px_rgba(15,23,42,0.04)] ring-1 ring-slate-900/5 transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <div className="absolute inset-0 bg-emerald-500/0 transition-colors group-hover:bg-emerald-500/5 group-active:bg-emerald-500/10" />
            {isSaving ? (
              <Loader2 size={13} className="relative z-10 animate-spin" />
            ) : (
              <Save size={13} className="relative z-10" />
            )}
            <span className="relative z-10">保存</span>
          </button>
        </div>
      </div>

      {message ? (
        <div className="border-b border-slate-200 bg-white px-4 py-2 text-xs text-emerald-600">
          {message}
        </div>
      ) : null}

      {error && hasRenderableSheet ? (
        <div className="border-b border-slate-200 bg-white px-4 py-2 text-xs text-red-600">
          {error}
        </div>
      ) : null}

      <div className="relative min-h-0 flex-1 bg-white">
        {!hasRenderableSheet && !showLoadingMask ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-500">
            {error || fallbackContent}
          </div>
        ) : null}

        <div
          id={containerIdRef.current}
          ref={containerRef}
          className={cn(
            "absolute inset-0",
            !hasRenderableSheet ? "pointer-events-none opacity-0" : "",
          )}
        />

        {showLoadingMask ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/90">
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 size={18} className="animate-spin" />
              {isLoading ? "正在解析 Excel..." : "正在加载 Luckysheet..."}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
