import React, { useEffect, useMemo, useRef, useState } from "react";
import "luckysheet/dist/plugins/css/pluginsCss.css";
import "luckysheet/dist/plugins/plugins.css";
import "luckysheet/dist/css/luckysheet.css";
import "luckysheet/dist/assets/iconfont/iconfont.css";

type LocatorHint = {
  sheet_index?: number;
  row_index?: number;
  col_index?: number;
  sheet_name?: string;
};

type LuckysheetPreviewProps = {
  file: File | null;
  locator?: LocatorHint | null;
  className?: string;
};

type LuckysheetLike = {
  create: (options: Record<string, unknown>) => void;
  destroy?: () => void;
  setSheetActive?: (order: number) => void;
  setSheetActiveByIndex?: (index: number) => void;
  setRangeShow?: (ranges: Array<{ row: [number, number]; column: [number, number] }>, order?: number) => void;
  scrollToCell?: (row: number, col: number) => void;
  getluckysheetfile?: () => Array<Record<string, unknown>>;
};

type LuckyExcelLike = {
  transformExcelToLucky: (
    file: File,
    callback: (exportJson: { sheets?: unknown[]; info?: Record<string, unknown> }) => void
  ) => void;
};

type RuntimeRef = {
  luckysheet: LuckysheetLike;
  luckyExcel: LuckyExcelLike;
};

let runtimePromise: Promise<RuntimeRef> | null = null;

function readRuntimeFromWindow(): RuntimeRef | null {
  const win = window as Window & {
    luckysheet?: LuckysheetLike;
    LuckyExcel?: LuckyExcelLike;
  };
  if (!win.luckysheet || !win.LuckyExcel) return null;
  if (typeof win.luckysheet.create !== "function") return null;
  if (typeof win.LuckyExcel.transformExcelToLucky !== "function") return null;
  return {
    luckysheet: win.luckysheet,
    luckyExcel: win.LuckyExcel,
  };
}

async function ensureRuntime(): Promise<RuntimeRef> {
  const cached = readRuntimeFromWindow();
  if (cached) return cached;
  if (runtimePromise) return runtimePromise;
  runtimePromise = (async () => {
    const jqMod = await import("jquery");
    const jqValue = (jqMod as { default?: unknown }).default ?? jqMod;
    const win = window as Window & {
      $?: unknown;
      jQuery?: unknown;
      LuckyExcel?: LuckyExcelLike;
      luckysheet?: LuckysheetLike;
    };
    win.$ = jqValue;
    win.jQuery = jqValue;

    await import("luckysheet/dist/plugins/js/plugin.js");
    await import("luckysheet/dist/luckysheet.umd.js");

    const luckyExcelMod = await import("luckyexcel");
    const luckyExcelValue =
      (luckyExcelMod as { default?: LuckyExcelLike }).default ?? (luckyExcelMod as unknown as LuckyExcelLike);
    if (!win.LuckyExcel && luckyExcelValue) {
      win.LuckyExcel = luckyExcelValue;
    }

    const runtime = readRuntimeFromWindow();
    if (!runtime) {
      throw new Error("Luckysheet 运行时加载失败");
    }
    return runtime;
  })().catch((error) => {
    runtimePromise = null;
    throw error;
  });
  return runtimePromise;
}

async function convertXlsx(runtime: RuntimeRef, file: File): Promise<{ sheets: unknown[]; info: Record<string, unknown> }> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new Error("Excel 转换超时"));
    }, 30_000);

    try {
      runtime.luckyExcel.transformExcelToLucky(file, (exportJson) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        const sheets = Array.isArray(exportJson?.sheets) ? exportJson.sheets : [];
        if (sheets.length === 0) {
          reject(new Error("未检测到可预览的工作表"));
          return;
        }
        resolve({
          sheets,
          info: (exportJson?.info ?? {}) as Record<string, unknown>,
        });
      });
    } catch (error) {
      window.clearTimeout(timer);
      if (settled) return;
      settled = true;
      reject(error);
    }
  });
}

function applyLocator(luckysheet: LuckysheetLike, locator?: LocatorHint | null) {
  if (!locator || typeof locator !== "object") return;

  const rowIndex = Number(locator.row_index || 0);
  const colIndex = Number(locator.col_index || 0);
  const sheetIndex = Number(locator.sheet_index || 0);
  const sheetName = String(locator.sheet_name || "").trim();

  let orderHint: number | undefined;
  const sheets = typeof luckysheet.getluckysheetfile === "function" ? luckysheet.getluckysheetfile() : [];
  if (Array.isArray(sheets) && sheets.length > 0) {
    const matched = sheets.find((sheet) => {
      const idx = Number(sheet.index ?? -1);
      const order = Number(sheet.order ?? -1);
      const name = String(sheet.name ?? "").trim();
      if (sheetName && name === sheetName) return true;
      if (sheetIndex > 0 && idx + 1 === sheetIndex) return true;
      if (sheetIndex > 0 && order + 1 === sheetIndex) return true;
      return false;
    });
    if (matched) {
      const order = Number(matched.order ?? matched.index ?? -1);
      if (Number.isFinite(order) && order >= 0) {
        orderHint = order;
      }
    } else if (sheetIndex > 0) {
      orderHint = Math.max(0, Math.round(sheetIndex) - 1);
    }
  } else if (sheetIndex > 0) {
    orderHint = Math.max(0, Math.round(sheetIndex) - 1);
  }

  if (orderHint !== undefined) {
    try {
      if (typeof luckysheet.setSheetActive === "function") {
        luckysheet.setSheetActive(orderHint);
      } else if (typeof luckysheet.setSheetActiveByIndex === "function") {
        luckysheet.setSheetActiveByIndex(orderHint);
      }
    } catch {
      // Best-effort jump.
    }
  }

  if (!(Number.isFinite(rowIndex) && rowIndex > 0 && Number.isFinite(colIndex) && colIndex > 0)) {
    return;
  }

  const row = Math.max(0, Math.round(rowIndex) - 1);
  const col = Math.max(0, Math.round(colIndex) - 1);
  try {
    if (typeof luckysheet.setRangeShow === "function") {
      luckysheet.setRangeShow([{ row: [row, row], column: [col, col] }], orderHint);
    }
  } catch {
    // Best-effort jump.
  }
  try {
    if (typeof luckysheet.scrollToCell === "function") {
      luckysheet.scrollToCell(row, col);
    }
  } catch {
    // Best-effort jump.
  }
}

export const LuckysheetPreview: React.FC<LuckysheetPreviewProps> = ({ file, locator, className = "" }) => {
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<RuntimeRef | null>(null);
  const containerId = useMemo(() => `module2-luckysheet-${Math.random().toString(36).slice(2, 11)}`, []);

  useEffect(() => {
    const runtime = runtimeRef.current?.luckysheet;
    if (!runtime || status !== "ready") return;
    applyLocator(runtime, locator);
  }, [locator, status]);

  useEffect(() => {
    let disposed = false;
    async function run() {
      if (!file) {
        setStatus("idle");
        setError("");
        return;
      }

      setStatus("loading");
      setError("");
      try {
        const runtime = await ensureRuntime();
        if (disposed) return;
        runtimeRef.current = runtime;
        const payload = await convertXlsx(runtime, file);
        if (disposed) return;
        runtime.luckysheet.destroy?.();

        runtime.luckysheet.create({
          container: containerId,
          data: payload.sheets,
          title: String(payload.info?.name || file.name || "工作簿"),
          userInfo: false,
          lang: "zh",
          showtoolbar: false,
          showinfobar: false,
          showstatisticBar: false,
          showsheetbar: true,
          allowCopy: true,
          enableAddRow: false,
          enableAddBackTop: false,
          enablePage: false,
          editMode: false,
        });

        applyLocator(runtime.luckysheet, locator);
        setStatus("ready");
      } catch (err) {
        if (disposed) return;
        const msg = err instanceof Error ? err.message : "Excel 预览加载失败";
        setError(msg || "Excel 预览加载失败");
        setStatus("error");
      }
    }

    void run();
    return () => {
      disposed = true;
    };
  }, [containerId, file, locator]);

  useEffect(() => {
    return () => {
      try {
        runtimeRef.current?.luckysheet.destroy?.();
      } catch {
        // Ignore.
      }
    };
  }, []);

  return (
    <div className={`relative h-full w-full overflow-hidden ${className}`}>
      {status === "loading" && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-slate-50/80 text-xs text-slate-600 dark:bg-slate-900/80 dark:text-slate-300">
          Excel 预览加载中...
        </div>
      )}
      {status === "error" && (
        <div className="absolute inset-0 z-20 flex items-center justify-center p-4">
          <p className="max-w-md rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-center text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            {error || "Excel 预览加载失败"}
          </p>
        </div>
      )}
      <div
        id={containerId}
        ref={containerRef}
        className="h-full w-full"
        style={{ visibility: status === "ready" ? "visible" : "hidden" }}
      />
    </div>
  );
};
