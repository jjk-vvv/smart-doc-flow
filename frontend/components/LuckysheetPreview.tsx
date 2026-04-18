import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
  file?: File | null;
  workbook?: WorkbookPayload | null;
  locator?: LocatorHint | null;
  className?: string;
  editable?: boolean;
  loadingLabel?: string;
};

type LuckysheetLike = {
  create: (options: Record<string, unknown>) => void;
  destroy?: () => void;
  resize?: () => void;
  refresh?: () => void;
  flowdata?: () => unknown[];
  luckysheetrefreshgrid?: () => void;
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

type JQueryCompat = Record<string, unknown> & {
  isArray?: (value: unknown) => boolean;
  isFunction?: (value: unknown) => boolean;
  isNumeric?: (value: unknown) => boolean;
  trim?: (value: unknown) => string;
  type?: (value: unknown) => string;
  fn?: Record<string, unknown>;
};

type WorkbookPayload = {
  sheets: unknown[];
  info: Record<string, unknown>;
};

export type LuckysheetWorkbookPayload = WorkbookPayload;

export type LuckysheetSaveSheet = {
  name: string;
  rows: Array<Array<string | number | boolean | null>>;
};

export type LuckysheetPreviewHandle = {
  exportSheets: () => LuckysheetSaveSheet[] | null;
  relayout: () => void;
  retry: () => void;
};

type SheetJsModule = typeof import("xlsx");

type SheetJsCellLike = {
  v?: unknown;
  w?: string;
  t?: string;
  z?: string;
  f?: string;
};

type SheetJsRangeLike = {
  s: { r: number; c: number };
  e: { r: number; c: number };
};

type SheetJsWorksheetLike = Record<string, unknown> & {
  "!ref"?: string;
  "!merges"?: SheetJsRangeLike[];
};

type LuckySheetCellDatum = {
  r?: number;
  c?: number;
  v?: unknown;
};

let runtimePromise: Promise<RuntimeRef> | null = null;
const workbookPayloadCache = new Map<string, WorkbookPayload>();
const workbookPayloadPromiseCache = new Map<string, Promise<WorkbookPayload>>();
const MAX_WORKBOOK_CACHE_ITEMS = 6;

function isKnownLuckysheetNoise(args: unknown[]): boolean {
  if (!Array.isArray(args) || args.length === 0) return false;
  if (args.some((item) => String(item ?? "").includes("缓存操作失败"))) return true;
  if (args.some((item) => String(item ?? "").includes("Merge info is null"))) return true;
  if (args.length === 2) {
    const isEmptyArrayMarker = (value: unknown) =>
      (Array.isArray(value) && value.length === 0) || String(value ?? "").trim() === "[]";
    if (isEmptyArrayMarker(args[0]) && isEmptyArrayMarker(args[1])) {
      return true;
    }
  }
  return false;
}

function installLuckysheetNoiseFilter(): void {
  const target = console as unknown as {
    __luckysheetNoiseFilterInstalled?: boolean;
    log: (...args: unknown[]) => void;
    warn: (...args: unknown[]) => void;
  };
  if (target.__luckysheetNoiseFilterInstalled) return;

  const originalLog = target.log.bind(console);
  const originalWarn = target.warn.bind(console);
  target.log = (...args: unknown[]) => {
    if (isKnownLuckysheetNoise(args)) return;
    originalLog(...args);
  };
  target.warn = (...args: unknown[]) => {
    if (isKnownLuckysheetNoise(args)) return;
    originalWarn(...args);
  };
  target.__luckysheetNoiseFilterInstalled = true;
}

async function withLuckysheetConsoleSilenced<T>(task: () => Promise<T>): Promise<T> {
  installLuckysheetNoiseFilter();
  const originalLog = console.log.bind(console);
  const originalWarn = console.warn.bind(console);
  console.log = (...args: unknown[]) => {
    if (isKnownLuckysheetNoise(args)) return;
    originalLog(...args);
  };
  console.warn = (...args: unknown[]) => {
    if (isKnownLuckysheetNoise(args)) return;
    originalWarn(...args);
  };
  try {
    return await task();
  } finally {
    console.log = originalLog;
    console.warn = originalWarn;
  }
}

installLuckysheetNoiseFilter();

function workbookCacheKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function cloneWorkbookPayload(payload: WorkbookPayload): WorkbookPayload {
  if (typeof structuredClone === "function") {
    return structuredClone(payload) as WorkbookPayload;
  }
  return JSON.parse(JSON.stringify(payload)) as WorkbookPayload;
}

function cloneValue<T>(value: T): T {
  if (typeof structuredClone === "function") {
    return structuredClone(value) as T;
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

function storeWorkbookPayload(key: string, payload: WorkbookPayload): void {
  if (workbookPayloadCache.has(key)) {
    workbookPayloadCache.delete(key);
  }
  workbookPayloadCache.set(key, cloneWorkbookPayload(payload));
  while (workbookPayloadCache.size > MAX_WORKBOOK_CACHE_ITEMS) {
    const oldestKey = workbookPayloadCache.keys().next().value;
    if (!oldestKey) break;
    workbookPayloadCache.delete(oldestKey);
  }
}

function hasLuckysheetCellValue(cell: unknown): boolean {
  if (cell === null || cell === undefined) return false;
  if (typeof cell === "number" || typeof cell === "boolean") return true;
  if (typeof cell === "string") return cell.trim().length > 0;
  if (typeof cell !== "object") return false;

  const cellLike = cell as Record<string, unknown>;
  const rawValue = cellLike.v;
  if (rawValue !== null && rawValue !== undefined && String(rawValue).trim().length > 0) {
    return true;
  }
  const formattedValue = cellLike.m;
  if (formattedValue !== null && formattedValue !== undefined && String(formattedValue).trim().length > 0) {
    return true;
  }
  const formula = cellLike.f;
  return typeof formula === "string" && formula.trim().length > 0;
}

function dropSheetCelldata(sheet: Record<string, unknown>): boolean {
  const celldata = Array.isArray(sheet.celldata) ? (sheet.celldata as unknown[]) : [];
  if (celldata.length === 0) return false;
  delete sheet.celldata;
  return true;
}

function sheetDataLooksHydrated(sheet: Record<string, unknown>): boolean {
  const data = Array.isArray(sheet.data) ? (sheet.data as unknown[]) : [];
  if (data.length === 0) return false;

  const rowProbeLimit = Math.min(data.length, 56);
  for (let rowIdx = 0; rowIdx < rowProbeLimit; rowIdx += 1) {
    const row = data[rowIdx];
    if (!Array.isArray(row) || row.length === 0) continue;
    const colProbeLimit = Math.min(row.length, 40);
    for (let colIdx = 0; colIdx < colProbeLimit; colIdx += 1) {
      if (hasLuckysheetCellValue(row[colIdx])) {
        return true;
      }
    }
  }
  return false;
}

function sheetNeedsHydration(sheet: Record<string, unknown>): boolean {
  const data = Array.isArray(sheet.data) ? (sheet.data as unknown[]) : [];
  const celldata = Array.isArray(sheet.celldata) ? (sheet.celldata as LuckySheetCellDatum[]) : [];
  if (celldata.length === 0) return false;
  if (data.length === 0) return true;
  if (sheetDataLooksHydrated(sheet)) return false;

  const sampleSize = Math.min(celldata.length, 24);
  let matched = 0;
  let missing = 0;
  for (let idx = 0; idx < sampleSize; idx += 1) {
    const item = celldata[idx];
    const row = Number(item?.r);
    const col = Number(item?.c);
    if (!Number.isFinite(row) || !Number.isFinite(col) || row < 0 || col < 0) {
      continue;
    }
    const rowData = Array.isArray(data[row]) ? (data[row] as unknown[]) : [];
    if (hasLuckysheetCellValue(rowData[col])) {
      matched += 1;
    } else {
      missing += 1;
    }
  }
  if (matched === 0 && missing > 0) return true;
  return missing >= Math.ceil(Math.max(sampleSize, 1) * 0.66);
}

function hydrateSheetGrid(sheet: Record<string, unknown>, force = false): boolean {
  const data = Array.isArray(sheet.data) ? (sheet.data as unknown[][]) : [];
  const celldata = Array.isArray(sheet.celldata) ? (sheet.celldata as LuckySheetCellDatum[]) : [];
  if ((!force && data.length > 0) || celldata.length === 0) {
    return false;
  }

  const grid: unknown[][] = [];
  let maxRow = -1;
  let maxCol = -1;
  let changed = false;

  for (const item of celldata) {
    const row = Number(item?.r);
    const col = Number(item?.c);
    if (!Number.isFinite(row) || !Number.isFinite(col) || row < 0 || col < 0) continue;
    if (!Array.isArray(grid[row])) {
      grid[row] = [];
    }
    grid[row][col] = item?.v ?? null;
    if (row > maxRow) maxRow = row;
    if (col > maxCol) maxCol = col;
  }

  if (grid.length > 0) {
    sheet.data = grid;
    changed = true;
  }

  if (maxRow >= 0) {
    const rowCount = Number(sheet.row ?? 0);
    const nextRowCount = Number.isFinite(rowCount) && rowCount > 0 ? Math.max(rowCount, maxRow + 1) : maxRow + 1;
    if (nextRowCount !== rowCount) {
      sheet.row = nextRowCount;
      changed = true;
    }
  }
  if (maxCol >= 0) {
    const colCount = Number(sheet.column ?? 0);
    const nextColCount = Number.isFinite(colCount) && colCount > 0 ? Math.max(colCount, maxCol + 1) : maxCol + 1;
    if (nextColCount !== colCount) {
      sheet.column = nextColCount;
      changed = true;
    }
  }

  return changed;
}

function hydrateLuckysheetFiles(luckysheet?: LuckysheetLike | null): boolean {
  const sheets = typeof luckysheet?.getluckysheetfile === "function" ? luckysheet.getluckysheetfile() : [];
  if (!Array.isArray(sheets) || sheets.length === 0) return false;

  let changed = false;
  let hasData = false;
  for (const sheet of sheets) {
    if (!sheet || typeof sheet !== "object") continue;
    const normalized = sheet as Record<string, unknown>;
    if (sheetDataLooksHydrated(normalized)) {
      if (dropSheetCelldata(normalized)) {
        changed = true;
      }
      hasData = true;
      continue;
    }
    if (sheetNeedsHydration(normalized) && hydrateSheetGrid(normalized, true)) {
      dropSheetCelldata(normalized);
      changed = true;
      hasData = true;
      continue;
    }
  }

  if (!changed) return hasData;
  try {
    luckysheet?.luckysheetrefreshgrid?.();
  } catch {
    // Best-effort refresh.
  }
  return true;
}

function luckysheetRuntimeHasData(luckysheet?: LuckysheetLike | null): boolean {
  const sheets = typeof luckysheet?.getluckysheetfile === "function" ? luckysheet.getluckysheetfile() : [];
  if (!Array.isArray(sheets) || sheets.length === 0) return false;
  return sheets.some((sheet) => sheet && typeof sheet === "object" && sheetDataLooksHydrated(sheet as Record<string, unknown>));
}

function syncRuntimeSheetsFromPayload(luckysheet: LuckysheetLike | null | undefined, sourceSheets: unknown[]): boolean {
  const runtimeSheets = typeof luckysheet?.getluckysheetfile === "function" ? luckysheet.getluckysheetfile() : [];
  if (!Array.isArray(runtimeSheets) || runtimeSheets.length === 0 || !Array.isArray(sourceSheets) || sourceSheets.length === 0) {
    return false;
  }

  let changed = false;
  runtimeSheets.forEach((runtimeSheet, index) => {
    if (!runtimeSheet || typeof runtimeSheet !== "object") return;
    const runtime = runtimeSheet as Record<string, unknown>;
    if (sheetDataLooksHydrated(runtime)) return;

    const runtimeName = String(runtime.name ?? "").trim();
    const source = sourceSheets.find((item, sourceIndex) => {
      if (!item || typeof item !== "object") return false;
      const normalized = item as Record<string, unknown>;
      const sourceName = String(normalized.name ?? "").trim();
      if (runtimeName && sourceName && runtimeName === sourceName) return true;
      return sourceIndex === index;
    });
    if (!source || typeof source !== "object") return;

    const normalizedSource = source as Record<string, unknown>;
    const sourceData = Array.isArray(normalizedSource.data) ? normalizedSource.data : [];
    if (sourceData.length === 0) return;

    runtime.data = cloneValue(sourceData);
    const nextRowCount = Number(normalizedSource.row ?? sourceData.length);
    const nextColCount = Number(
      normalizedSource.column
      ?? (Array.isArray(sourceData[0]) ? (sourceData[0] as unknown[]).length : 0)
    );
    if (Number.isFinite(nextRowCount) && nextRowCount > 0) {
      runtime.row = nextRowCount;
    }
    if (Number.isFinite(nextColCount) && nextColCount > 0) {
      runtime.column = nextColCount;
    }
    if (normalizedSource.config && typeof normalizedSource.config === "object") {
      runtime.config = cloneValue(normalizedSource.config as Record<string, unknown>);
    }
    changed = true;
  });

  if (!changed) return false;
  try {
    luckysheet?.luckysheetrefreshgrid?.();
  } catch {
    // Best-effort refresh.
  }
  return true;
}

function hydrateWorkbookSheets(sheets: unknown[]): boolean {
  if (!Array.isArray(sheets) || sheets.length === 0) return false;
  let hasData = false;
  for (const item of sheets) {
    if (!item || typeof item !== "object") continue;
    const normalized = item as Record<string, unknown>;
    if (!sheetDataLooksHydrated(normalized) && sheetNeedsHydration(normalized)) {
      hydrateSheetGrid(normalized, true);
    }
    if (!sheetDataLooksHydrated(normalized)) continue;
    hasData = true;
    dropSheetCelldata(normalized);
  }
  return hasData;
}

function mapSheetJsCellType(type?: string): string {
  switch ((type || "").toLowerCase()) {
    case "n":
      return "n";
    case "b":
      return "b";
    case "d":
      return "d";
    case "e":
      return "e";
    case "s":
    case "str":
    case "inlinestr":
      return "s";
    default:
      return "g";
  }
}

function toLuckysheetCellFromSheetJs(cell: SheetJsCellLike | null | undefined): Record<string, unknown> | null {
  if (!cell || typeof cell !== "object") return null;
  const hasValue = cell.v !== undefined && cell.v !== null;
  const display = cell.w ?? (hasValue ? String(cell.v) : "");
  const formula = typeof cell.f === "string" && cell.f.trim() ? `=${cell.f}` : "";
  if (!hasValue && !display && !formula) return null;

  const format = typeof cell.z === "string" && cell.z.trim() ? cell.z : (typeof cell.v === "number" ? "General" : "@");
  const out: Record<string, unknown> = {
    v: hasValue ? cell.v : display,
    m: display || (hasValue ? String(cell.v) : ""),
    ct: {
      fa: format,
      t: mapSheetJsCellType(cell.t),
    },
  };
  if (formula) {
    out.f = formula;
  }
  return out;
}

function buildWorkbookPayloadWithSheetJs(
  xlsx: SheetJsModule,
  file: File,
  workbook: { SheetNames: string[]; Sheets: Record<string, SheetJsWorksheetLike> },
): WorkbookPayload {
  const sheets = workbook.SheetNames.map((sheetName, index) => {
    const worksheet = workbook.Sheets[sheetName] as SheetJsWorksheetLike | undefined;
    const ref = typeof worksheet?.["!ref"] === "string" && worksheet["!ref"].trim() ? worksheet["!ref"] : "A1";
    const range = xlsx.utils.decode_range(ref);
    const rowCount = Math.max(1, range.e.r + 1);
    const colCount = Math.max(1, range.e.c + 1);
    const celldata: Array<{ r: number; c: number; v: Record<string, unknown> }> = [];

    for (const [address, rawCell] of Object.entries(worksheet ?? {})) {
      if (address.startsWith("!")) continue;
      const cell = toLuckysheetCellFromSheetJs(rawCell as SheetJsCellLike);
      if (!cell) continue;
      const decoded = xlsx.utils.decode_cell(address);
      if (decoded.r < 0 || decoded.c < 0) continue;
      celldata.push({
        r: decoded.r,
        c: decoded.c,
        v: cell,
      });
    }

    const mergeConfig: Record<string, { r: number; c: number; rs: number; cs: number }> = {};
    const merges = Array.isArray(worksheet?.["!merges"]) ? worksheet["!merges"] : [];
    for (const merge of merges) {
      const startRow = Number(merge?.s?.r);
      const startCol = Number(merge?.s?.c);
      const endRow = Number(merge?.e?.r);
      const endCol = Number(merge?.e?.c);
      if (!Number.isFinite(startRow) || !Number.isFinite(startCol) || !Number.isFinite(endRow) || !Number.isFinite(endCol)) {
        continue;
      }
      const rowSpan = endRow - startRow + 1;
      const colSpan = endCol - startCol + 1;
      if (rowSpan <= 1 && colSpan <= 1) continue;
      mergeConfig[`r_${startRow}_c_${startCol}`] = {
        r: startRow,
        c: startCol,
        rs: rowSpan,
        cs: colSpan,
      };
    }

    return {
      name: sheetName,
      index: String(index),
      order: index,
      status: index === 0 ? 1 : 0,
      row: rowCount,
      column: colCount,
      defaultColWidth: 84,
      defaultRowHeight: 22,
      celldata,
      config: Object.keys(mergeConfig).length > 0 ? { merge: mergeConfig } : {},
    };
  });

  return {
    sheets,
    info: {
      name: file.name,
      source: "sheetjs-fallback",
    },
  };
}

async function readWorkbookWithSheetJs(file: File): Promise<WorkbookPayload> {
  const xlsx = await import("xlsx");
  const arrayBuffer = await file.arrayBuffer();
  const workbook = xlsx.read(arrayBuffer, {
    type: "array",
    cellDates: true,
    cellFormula: true,
    cellNF: true,
    cellText: true,
  });

  if (!Array.isArray(workbook.SheetNames) || workbook.SheetNames.length === 0) {
    throw new Error("未检测到可预览的工作表");
  }

  return buildWorkbookPayloadWithSheetJs(xlsx, file, workbook as { SheetNames: string[]; Sheets: Record<string, SheetJsWorksheetLike> });
}

function installJQueryCompat(raw: unknown): void {
  const jq = raw as JQueryCompat;
  if (!jq || (typeof jq !== "function" && typeof jq !== "object")) return;
  if (typeof jq.isArray !== "function") {
    jq.isArray = (value: unknown) => Array.isArray(value);
  }
  if (typeof jq.isFunction !== "function") {
    jq.isFunction = (value: unknown) => typeof value === "function";
  }
  if (typeof jq.isNumeric !== "function") {
    jq.isNumeric = (value: unknown) => {
      if (typeof value === "number") return Number.isFinite(value);
      if (typeof value === "string" && value.trim() !== "") {
        return Number.isFinite(Number(value));
      }
      return false;
    };
  }
  if (typeof jq.trim !== "function") {
    jq.trim = (value: unknown) => String(value ?? "").trim();
  }
  if (typeof jq.type !== "function") {
    jq.type = (value: unknown) => Object.prototype.toString.call(value).slice(8, -1).toLowerCase();
  }
  const jqFn = jq.fn;
  if (jqFn && typeof jqFn.mousewheel !== "function") {
    jqFn.mousewheel = function mousewheelShim(this: unknown): unknown {
      return this;
    };
  }
}

function resolveLuckysheetExport(mod: unknown): LuckysheetLike | null {
  const obj = mod as Record<string, unknown> | null | undefined;
  if (!obj) return null;
  const direct = obj as unknown as LuckysheetLike;
  if (typeof direct.create === "function") return direct;
  const fromDefault = (obj.default ?? null) as Record<string, unknown> | null;
  if (fromDefault) {
    const d = fromDefault as unknown as LuckysheetLike;
    if (typeof d.create === "function") return d;
    const nested = (fromDefault.luckysheet ?? null) as LuckysheetLike | null;
    if (nested && typeof nested.create === "function") return nested;
  }
  const named = (obj.luckysheet ?? null) as LuckysheetLike | null;
  if (named && typeof named.create === "function") return named;
  return null;
}

function resolveLuckyExcelExport(mod: unknown): LuckyExcelLike | null {
  const obj = mod as Record<string, unknown> | null | undefined;
  if (!obj) return null;
  const direct = obj as unknown as LuckyExcelLike;
  if (typeof direct.transformExcelToLucky === "function") return direct;
  const fromDefault = (obj.default ?? null) as LuckyExcelLike | null;
  if (fromDefault && typeof fromDefault.transformExcelToLucky === "function") return fromDefault;
  const named = (obj.LuckyExcel ?? null) as LuckyExcelLike | null;
  if (named && typeof named.transformExcelToLucky === "function") return named;
  return null;
}

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
  runtimePromise = withLuckysheetConsoleSilenced(async () => {
    const jqMod = await import("jquery");
    const jqValue = (jqMod as { default?: unknown }).default ?? jqMod;
    installJQueryCompat(jqValue);
    const win = window as Window & {
      $?: unknown;
      jQuery?: unknown;
      LuckyExcel?: LuckyExcelLike;
      luckysheet?: LuckysheetLike;
    };
    win.$ = jqValue;
    win.jQuery = jqValue;

    await import("luckysheet/dist/plugins/js/plugin.js");
    const luckysheetMod = await import("luckysheet/dist/luckysheet.umd.js");
    if (!win.luckysheet) {
      const luckysheetExport = resolveLuckysheetExport(luckysheetMod);
      if (luckysheetExport) {
        win.luckysheet = luckysheetExport;
      }
    }

    const luckyExcelMod = await import("luckyexcel");
    const luckyExcelValue = resolveLuckyExcelExport(luckyExcelMod);
    if (!win.LuckyExcel && luckyExcelValue) {
      win.LuckyExcel = luckyExcelValue;
    }

    const runtime = readRuntimeFromWindow();
    if (!runtime) {
      throw new Error("表格预览运行时加载失败");
    }
    return runtime;
  }).catch((error) => {
    runtimePromise = null;
    throw error;
  });
  return runtimePromise;
}

async function convertXlsx(runtime: RuntimeRef, file: File): Promise<WorkbookPayload> {
  return withLuckysheetConsoleSilenced(
    async () =>
      new Promise((resolve, reject) => {
    let settled = false;
    const timer = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new Error("电子表格转换超时"));
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
      }),
  );
}

async function getWorkbookPayload(file: File, runtime?: RuntimeRef): Promise<WorkbookPayload> {
  const key = workbookCacheKey(file);
  const cached = workbookPayloadCache.get(key);
  if (cached) {
    storeWorkbookPayload(key, cached);
    return cloneWorkbookPayload(cached);
  }

  const pending = workbookPayloadPromiseCache.get(key);
  if (pending) {
    return cloneWorkbookPayload(await pending);
  }

  const task = (async () => {
    let payload: WorkbookPayload | null = null;

    try {
      const activeRuntime = runtime ?? (await ensureRuntime());
      payload = await convertXlsx(activeRuntime, file);
      if (!Array.isArray(payload.sheets) || payload.sheets.length === 0) {
        payload = await readWorkbookWithSheetJs(file);
      }
    } catch (error) {
      payload = await readWorkbookWithSheetJs(file);
      if (!payload || !Array.isArray(payload.sheets) || payload.sheets.length === 0) {
        throw error;
      }
    }

    if (!payload) {
      throw new Error("电子表格预览加载失败");
    }

    storeWorkbookPayload(key, payload);
    return cloneWorkbookPayload(payload);
  })().finally(() => {
    workbookPayloadPromiseCache.delete(key);
  });

  workbookPayloadPromiseCache.set(key, task);
  return cloneWorkbookPayload(await task);
}

export async function preloadLuckysheetRuntime(): Promise<void> {
  await ensureRuntime();
}

export async function warmLuckysheetPreview(file: File | null): Promise<void> {
  if (!file) return;
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (ext !== "xlsx") return;
  const runtime = await ensureRuntime();
  await getWorkbookPayload(file, runtime);
}

export function clearLuckysheetPreviewCache(): void {
  workbookPayloadCache.clear();
  workbookPayloadPromiseCache.clear();
}

function normalizeSavedCellValue(cell: unknown): string | number | boolean | null {
  if (cell === null || cell === undefined) return "";
  if (
    typeof cell === "string"
    || typeof cell === "number"
    || typeof cell === "boolean"
  ) {
    return cell;
  }
  if (typeof cell !== "object") return String(cell);

  const normalized = cell as Record<string, unknown>;
  if (
    typeof normalized.v === "string"
    || typeof normalized.v === "number"
    || typeof normalized.v === "boolean"
  ) {
    return normalized.v;
  }
  if (
    typeof normalized.m === "string"
    || typeof normalized.m === "number"
    || typeof normalized.m === "boolean"
  ) {
    return normalized.m;
  }
  if (typeof normalized.f === "string" && normalized.f.trim()) {
    return normalized.f;
  }
  return "";
}

function buildSaveSheetsFromLuckysheet(
  sheets: Array<Record<string, unknown>>,
): LuckysheetSaveSheet[] {
  return sheets.map((sheet) => {
    const rows: Array<Array<string | number | boolean | null>> = [];
    const sheetData = Array.isArray(sheet.data) ? (sheet.data as unknown[][]) : [];

    for (let rowIndex = 0; rowIndex < sheetData.length; rowIndex += 1) {
      const sourceRow = Array.isArray(sheetData[rowIndex]) ? sheetData[rowIndex] : [];
      const rowData: Array<string | number | boolean | null> = [];
      for (let colIndex = 0; colIndex < sourceRow.length; colIndex += 1) {
        rowData.push(normalizeSavedCellValue(sourceRow[colIndex]));
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
      name: String(sheet.name ?? "Sheet1"),
      rows: rows.slice(0, lastNonEmptyRow + 1),
    };
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

function requestLuckysheetRelayout(luckysheet?: LuckysheetLike | null): void {
  if (!luckysheet) return;
  const run = () => {
    try {
      luckysheet.resize?.();
    } catch {
      // Best-effort relayout.
    }
    try {
      luckysheet.refresh?.();
    } catch {
      // Best-effort relayout.
    }
    try {
      window.dispatchEvent(new Event("resize"));
    } catch {
      // Ignore.
    }
  };

  window.requestAnimationFrame(() => {
    run();
    window.requestAnimationFrame(() => {
      run();
      window.setTimeout(() => {
        window.requestAnimationFrame(run);
      }, 90);
    });
  });
}

function isLuckysheetFlowReady(luckysheet?: LuckysheetLike | null): boolean {
  if (!luckysheet || typeof luckysheet.flowdata !== "function") return false;
  try {
    const flow = luckysheet.flowdata();
    return Array.isArray(flow) && flow.length > 0;
  } catch {
    return false;
  }
}

function isLuckysheetPreviewReady(
  luckysheet?: LuckysheetLike | null,
  sourceSheets?: unknown[],
): boolean {
  if (!luckysheet) return false;
  if (isLuckysheetFlowReady(luckysheet)) return true;
  hydrateLuckysheetFiles(luckysheet);
  if (Array.isArray(sourceSheets) && sourceSheets.length > 0) {
    syncRuntimeSheetsFromPayload(luckysheet, sourceSheets);
    hydrateLuckysheetFiles(luckysheet);
  }
  return isLuckysheetFlowReady(luckysheet);
}

function syncLuckysheetViewport(
  wrapper?: HTMLDivElement | null,
  container?: HTMLDivElement | null,
): void {
  if (!wrapper || !container) return;

  const width = Math.max(0, Math.floor(wrapper.clientWidth || wrapper.getBoundingClientRect().width));
  const height = Math.max(0, Math.floor(wrapper.clientHeight || wrapper.getBoundingClientRect().height));
  if (width <= 0 || height <= 0) return;

  container.style.width = `${width}px`;
  container.style.height = `${height}px`;
  container.style.minWidth = "0px";
  container.style.minHeight = "0px";

  const root = container.querySelector<HTMLElement>(".luckysheet");
  if (!root) return;

  root.style.width = `${width}px`;
  root.style.height = `${height}px`;
  root.style.left = "0px";
  root.style.top = "0px";
}

type TableWorkbookSheet = {
  name: string;
  rows: unknown[][];
  rowCount: number;
  colCount: number;
};

const TABLE_ROW_HEIGHT = 30;
const TABLE_HEADER_HEIGHT = 34;
const TABLE_ROW_HEADER_WIDTH = 64;
const TABLE_COL_WIDTH = 152;
const TABLE_ROW_OVERSCAN = 12;

function displayCellText(cell: unknown): string {
  if (cell === null || cell === undefined) return "";
  if (typeof cell === "string") return cell;
  if (typeof cell === "number" || typeof cell === "boolean") return String(cell);
  if (typeof cell !== "object") return String(cell);

  const cellLike = cell as Record<string, unknown>;
  const formatted = cellLike.m;
  if (formatted !== null && formatted !== undefined && String(formatted).trim().length > 0) {
    return String(formatted);
  }
  const value = cellLike.v;
  if (value !== null && value !== undefined && String(value).trim().length > 0) {
    return String(value);
  }
  const formula = cellLike.f;
  if (typeof formula === "string" && formula.trim().length > 0) {
    return formula;
  }
  return "";
}

function hasWorkbookPayloadData(payload?: WorkbookPayload | null): boolean {
  return Boolean(payload && Array.isArray(payload.sheets) && payload.sheets.some((sheet) => {
    if (!sheet || typeof sheet !== "object") return false;
    return sheetDataLooksHydrated(sheet as Record<string, unknown>);
  }));
}

function estimateWorkbookPayloadComplexity(payload?: WorkbookPayload | null): {
  sheetCount: number;
  totalCells: number;
  maxSheetCells: number;
  maxRows: number;
  maxCols: number;
} {
  if (!payload || !Array.isArray(payload.sheets)) {
    return { sheetCount: 0, totalCells: 0, maxSheetCells: 0, maxRows: 0, maxCols: 0 };
  }

  let totalCells = 0;
  let maxSheetCells = 0;
  let maxRows = 0;
  let maxCols = 0;

  payload.sheets.forEach((sheet) => {
    if (!sheet || typeof sheet !== "object") return;
    const normalized = sheet as Record<string, unknown>;
    const rows = Math.max(1, Number(normalized.row ?? 0) || 0);
    const cols = Math.max(1, Number(normalized.column ?? 0) || 0);
    const sheetCells = rows * cols;
    totalCells += sheetCells;
    maxSheetCells = Math.max(maxSheetCells, sheetCells);
    maxRows = Math.max(maxRows, rows);
    maxCols = Math.max(maxCols, cols);
  });

  return {
    sheetCount: payload.sheets.length,
    totalCells,
    maxSheetCells,
    maxRows,
    maxCols,
  };
}

function shouldPreferTableModeForWorkbook(file: File | null, payload?: WorkbookPayload | null): boolean {
  if (!file || !payload) return false;
  const complexity = estimateWorkbookPayloadComplexity(payload);
  if (file.size >= 1_200_000) return true;
  if (complexity.totalCells >= 150_000) return true;
  if (complexity.maxSheetCells >= 90_000) return true;
  if (complexity.maxRows >= 4_000) return true;
  if (complexity.maxCols >= 180) return true;
  if (complexity.sheetCount >= 8) return true;
  return false;
}

function buildTableWorkbookSheets(payload?: WorkbookPayload | null): TableWorkbookSheet[] {
  if (!payload || !Array.isArray(payload.sheets)) return [];
  return payload.sheets
    .map((sheet, index) => {
      const normalized = (sheet && typeof sheet === "object") ? (sheet as Record<string, unknown>) : null;
      if (!normalized) return null;
      const rows = Array.isArray(normalized.data) ? (normalized.data as unknown[][]) : [];
      const rowCount = Math.max(rows.length, Number(normalized.row ?? 0) || 0, 1);
      const colCount = Math.max(
        Number(normalized.column ?? 0) || 0,
        rows.reduce((maxCols, row) => Math.max(maxCols, Array.isArray(row) ? row.length : 0), 0),
        1,
      );
      return {
        name: String(normalized.name ?? `工作表${index + 1}`),
        rows,
        rowCount,
        colCount,
      } satisfies TableWorkbookSheet;
    })
    .filter((sheet): sheet is TableWorkbookSheet => Boolean(sheet));
}

function resolveLocatorSheetIndex(locator: LocatorHint | null | undefined, sheets: TableWorkbookSheet[]): number {
  if (!Array.isArray(sheets) || sheets.length === 0) return 0;
  const sheetName = String(locator?.sheet_name || "").trim();
  if (sheetName) {
    const byName = sheets.findIndex((sheet) => sheet.name === sheetName);
    if (byName >= 0) return byName;
  }
  const sheetIndex = Number(locator?.sheet_index || 0);
  if (Number.isFinite(sheetIndex) && sheetIndex > 0) {
    return Math.max(0, Math.min(sheets.length - 1, Math.round(sheetIndex) - 1));
  }
  return 0;
}

function columnLabelFromIndex(index: number): string {
  let current = Math.max(0, Math.floor(index));
  let label = "";
  do {
    label = String.fromCharCode(65 + (current % 26)) + label;
    current = Math.floor(current / 26) - 1;
  } while (current >= 0);
  return label;
}

const SheetTableFallback: React.FC<{
  payload: WorkbookPayload;
  locator?: LocatorHint | null;
}> = ({ payload, locator }) => {
  const sheets = useMemo(() => buildTableWorkbookSheets(payload), [payload]);
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setActiveSheetIndex(resolveLocatorSheetIndex(locator, sheets));
  }, [locator, sheets]);

  useEffect(() => {
    const target = scrollRef.current;
    if (!target || typeof ResizeObserver === "undefined") return;
    const updateViewport = () => {
      setViewportHeight(Math.max(0, target.clientHeight - TABLE_HEADER_HEIGHT));
    };
    updateViewport();
    const observer = new ResizeObserver(() => {
      updateViewport();
    });
    observer.observe(target);
    return () => {
      observer.disconnect();
    };
  }, [activeSheetIndex]);

  const activeSheet = sheets[activeSheetIndex] || sheets[0] || null;

  useEffect(() => {
    const target = scrollRef.current;
    if (!target || !activeSheet) return;
    const rowIndex = Math.max(0, Math.round(Number(locator?.row_index || 1)) - 1);
    const colIndex = Math.max(0, Math.round(Number(locator?.col_index || 1)) - 1);
    target.scrollTop = rowIndex * TABLE_ROW_HEIGHT;
    target.scrollLeft = colIndex * TABLE_COL_WIDTH;
    setScrollTop(target.scrollTop);
    setScrollLeft(target.scrollLeft);
  }, [activeSheet, locator]);

  const visibleRowRange = useMemo(() => {
    if (!activeSheet) {
      return { start: 0, end: 0 };
    }
    const bodyHeight = Math.max(viewportHeight, TABLE_ROW_HEIGHT * 8);
    const start = Math.max(0, Math.floor(scrollTop / TABLE_ROW_HEIGHT) - TABLE_ROW_OVERSCAN);
    const visibleCount = Math.ceil(bodyHeight / TABLE_ROW_HEIGHT) + TABLE_ROW_OVERSCAN * 2;
    const end = Math.min(activeSheet.rowCount, start + visibleCount);
    return { start, end };
  }, [activeSheet, scrollTop, viewportHeight]);

  const highlightRow = Math.max(0, Math.round(Number(locator?.row_index || 0)) - 1);
  const highlightCol = Math.max(0, Math.round(Number(locator?.col_index || 0)) - 1);
  const totalWidth = activeSheet
    ? TABLE_ROW_HEADER_WIDTH + activeSheet.colCount * TABLE_COL_WIDTH
    : TABLE_ROW_HEADER_WIDTH;
  const totalHeight = activeSheet ? activeSheet.rowCount * TABLE_ROW_HEIGHT : 0;

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-white dark:bg-transparent">
      {sheets.length > 1 && (
        <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 bg-slate-50/90 px-2 py-1.5 text-[11px] dark:border-white/[0.05] dark:bg-slate-900/90">
          {sheets.map((sheet, index) => (
            <button
              key={`${sheet.name}-${index}`}
              type="button"
              onClick={() => setActiveSheetIndex(index)}
              className={`rounded-md px-2.5 py-1 font-medium transition ${
                index === activeSheetIndex
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              {sheet.name}
            </button>
          ))}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">
        <div
          ref={scrollRef}
          className="h-full overflow-auto bg-slate-50/60 text-[11px] text-slate-700 dark:bg-white/[0.01] dark:text-slate-200"
          onScroll={(event) => {
            const target = event.currentTarget;
            setScrollTop(target.scrollTop);
            setScrollLeft(target.scrollLeft);
          }}
        >
          <div className="relative" style={{ width: `${totalWidth}px`, minHeight: `${TABLE_HEADER_HEIGHT + totalHeight}px` }}>
            <div className="sticky top-0 z-20 flex border-b border-slate-200 bg-slate-100/95 text-[11px] font-semibold text-slate-600 backdrop-blur dark:border-white/[0.05] dark:bg-slate-900/95 dark:text-slate-300">
              <div
                className="sticky left-0 z-30 flex shrink-0 items-center justify-center border-r border-slate-200 bg-slate-100/95 dark:border-white/[0.05] dark:bg-slate-900/95"
                style={{ width: `${TABLE_ROW_HEADER_WIDTH}px`, height: `${TABLE_HEADER_HEIGHT}px` }}
              >
                #
              </div>
              {activeSheet && Array.from({ length: activeSheet.colCount }, (_, colIndex) => (
                <div
                  key={`header-${colIndex}`}
                  className="flex shrink-0 items-center border-r border-slate-200 px-3 dark:border-white/[0.05]"
                  style={{ width: `${TABLE_COL_WIDTH}px`, height: `${TABLE_HEADER_HEIGHT}px` }}
                >
                  {columnLabelFromIndex(colIndex)}
                </div>
              ))}
            </div>

            <div className="relative" style={{ height: `${totalHeight}px` }}>
              {activeSheet && Array.from({ length: Math.max(0, visibleRowRange.end - visibleRowRange.start) }, (_, offset) => {
                const rowIndex = visibleRowRange.start + offset;
                const row = Array.isArray(activeSheet.rows[rowIndex]) ? activeSheet.rows[rowIndex] : [];
                const isHighlightedRow = highlightRow === rowIndex;
                return (
                  <div
                    key={`row-${rowIndex}`}
                    className={`absolute left-0 flex ${isHighlightedRow ? "bg-amber-50/80 dark:bg-amber-500/10" : "bg-transparent"}`}
                    style={{
                      top: `${rowIndex * TABLE_ROW_HEIGHT}px`,
                      width: `${totalWidth}px`,
                      height: `${TABLE_ROW_HEIGHT}px`,
                    }}
                  >
                    <div
                      className={`sticky left-0 z-10 flex shrink-0 items-center justify-center border-b border-r border-slate-200 px-2 font-medium ${
                        isHighlightedRow
                          ? "bg-amber-100 text-amber-800 dark:border-white/[0.05] dark:bg-amber-500/20 dark:text-amber-200"
                          : "bg-slate-50 text-slate-500 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-400"
                      }`}
                      style={{ width: `${TABLE_ROW_HEADER_WIDTH}px`, height: `${TABLE_ROW_HEIGHT}px` }}
                    >
                      {rowIndex + 1}
                    </div>
                    {Array.from({ length: activeSheet.colCount }, (_, colIndex) => {
                      const text = displayCellText(row[colIndex]);
                      const isHighlightedCell = highlightRow === rowIndex && highlightCol === colIndex;
                      return (
                        <div
                          key={`cell-${rowIndex}-${colIndex}`}
                          className={`flex shrink-0 items-center border-b border-r px-3 ${
                            isHighlightedCell
                              ? "bg-amber-100/80 font-medium text-amber-900 ring-1 ring-inset ring-amber-300 dark:border-white/[0.05] dark:bg-amber-500/20 dark:text-amber-100 dark:ring-amber-500/60"
                              : "border-slate-200 bg-white dark:border-white/[0.05] dark:bg-transparent"
                          }`}
                          style={{ width: `${TABLE_COL_WIDTH}px`, height: `${TABLE_ROW_HEIGHT}px` }}
                          title={text}
                        >
                          <span className="truncate">{text || "\u00A0"}</span>
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const LuckysheetPreview: React.FC<LuckysheetPreviewProps> = ({ file, locator, className = "" }) => {
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState("");
  const [renderMode, setRenderMode] = useState<"grid" | "table">("grid");
  const [fallbackPayload, setFallbackPayload] = useState<WorkbookPayload | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<RuntimeRef | null>(null);
  const settleRelayoutRef = useRef<number | null>(null);
  const hydrationTimerRefs = useRef<number[]>([]);
  const lastObservedSizeRef = useRef<{ width: number; height: number } | null>(null);
  const containerId = useMemo(() => `module2-luckysheet-${Math.random().toString(36).slice(2, 11)}`, []);

  useEffect(() => {
    if (renderMode !== "grid") return;
    const runtime = runtimeRef.current?.luckysheet;
    if (!runtime || status !== "ready") return;
    applyLocator(runtime, locator);
  }, [locator, renderMode, status]);

  useEffect(() => {
    let disposed = false;

    const clearHydrationTimers = () => {
      if (hydrationTimerRefs.current.length === 0) return;
      hydrationTimerRefs.current.forEach((timerId) => {
        window.clearTimeout(timerId);
        window.clearInterval(timerId);
      });
      hydrationTimerRefs.current = [];
    };

    const scheduleReadyCheck = (
      luckysheet?: LuckysheetLike | null,
      rawSourceSheets: unknown[] = [],
      tablePayload?: WorkbookPayload | null,
    ) => {
      clearHydrationTimers();
      let settled = false;
      let sourceSheets: unknown[] | null = null;
      const finalize = () => {
        if (settled) return;
        settled = true;
        clearHydrationTimers();
      };
      const activateTableFallback = () => {
        finalize();
        try {
          luckysheet?.destroy?.();
        } catch {
          // Ignore.
        }
        runtimeRef.current = null;
        if (containerRef.current) {
          containerRef.current.innerHTML = "";
        }
        if (!disposed) {
          setError("Luckysheet 初始化失败，请稍后重试。");
          setStatus("error");
        }
      };
      const getSourceSheets = () => {
        if (sourceSheets) return sourceSheets;
        if (!Array.isArray(rawSourceSheets) || rawSourceSheets.length === 0) {
          sourceSheets = [];
          return sourceSheets;
        }
        sourceSheets = cloneValue(rawSourceSheets);
        hydrateWorkbookSheets(sourceSheets);
        return sourceSheets;
      };
      const attempt = () => {
        if (!isLuckysheetPreviewReady(luckysheet, getSourceSheets())) {
          return;
        }
        finalize();
        syncLuckysheetViewport(wrapperRef.current, containerRef.current);
        requestLuckysheetRelayout(luckysheet);
        if (!disposed) {
          setRenderMode("grid");
          setStatus("ready");
        }
      };
      attempt();
      window.requestAnimationFrame(attempt);
      hydrationTimerRefs.current.push(
        window.setInterval(() => {
          if (settled) return;
          attempt();
        }, 250)
      );
      if (hasWorkbookPayloadData(tablePayload)) {
        hydrationTimerRefs.current.push(
          window.setTimeout(() => {
            if (settled || disposed) return;
            if (isLuckysheetPreviewReady(luckysheet, getSourceSheets())) return;
            activateTableFallback();
          }, 6_500)
        );
      }
      hydrationTimerRefs.current.push(
        window.setTimeout(() => {
          if (settled || disposed) return;
          if (hasWorkbookPayloadData(tablePayload)) {
            activateTableFallback();
            return;
          }
          finalize();
          setError("电子表格预览初始化超时，请稍后重试");
          setStatus("error");
        }, 20_000)
      );
    };

    const mountWorkbook = (runtime: RuntimeRef, payload: WorkbookPayload, tablePayload?: WorkbookPayload | null) => {
      const createSheets = cloneValue(payload.sheets);
      const recoverySheets = cloneValue(payload.sheets);
      runtime.luckysheet.destroy?.();
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
      syncLuckysheetViewport(wrapperRef.current, containerRef.current);
      runtime.luckysheet.create({
        container: containerId,
        data: createSheets,
        title: String(payload.info?.name || file?.name || "工作簿"),
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
      scheduleReadyCheck(runtime.luckysheet, recoverySheets, tablePayload);
    };

    async function run() {
      if (!file) {
        try {
          runtimeRef.current?.luckysheet.destroy?.();
        } catch {
          // Ignore.
        }
        if (containerRef.current) {
          containerRef.current.innerHTML = "";
        }
        runtimeRef.current = null;
        setRenderMode("grid");
        setFallbackPayload(null);
        setStatus("idle");
        setError("");
        lastObservedSizeRef.current = null;
        return;
      }

      setRenderMode("grid");
      setFallbackPayload(null);
      setStatus("loading");
      setError("");
      try {
        const payload = await getWorkbookPayload(file);
        if (disposed) return;
        let tablePayload = cloneWorkbookPayload(payload);
        let hasTableData = hydrateWorkbookSheets(tablePayload.sheets);
        if (!hasTableData) {
          try {
            tablePayload = await readWorkbookWithSheetJs(file);
            hasTableData = hydrateWorkbookSheets(tablePayload.sheets);
          } catch {
            tablePayload = cloneWorkbookPayload(payload);
          }
        }
        setFallbackPayload(hasTableData ? tablePayload : null);
        const preferTableMode = false;
        if (preferTableMode) {
          try {
            runtimeRef.current?.luckysheet.destroy?.();
          } catch {
            // Ignore.
          }
          if (containerRef.current) {
            containerRef.current.innerHTML = "";
          }
          runtimeRef.current = null;
          setError("电子表格预览初始化失败，请稍后重试");
          setStatus("error");
          return;
        }

        try {
          const runtime = await ensureRuntime();
          if (disposed) return;
          runtimeRef.current = runtime;
          mountWorkbook(runtime, payload, hasTableData ? tablePayload : null);
        } catch (runtimeError) {
          throw runtimeError;
        }
      } catch (err) {
        if (disposed) return;
        const msg = err instanceof Error ? err.message : "电子表格预览加载失败";
        setError(msg || "电子表格预览加载失败");
        setStatus("error");
      }
    }

    void run();
    return () => {
      disposed = true;
      clearHydrationTimers();
    };
  }, [containerId, file]);

  useEffect(() => {
    if (renderMode !== "grid") return;
    if (status !== "ready") return;
    syncLuckysheetViewport(wrapperRef.current, containerRef.current);
    requestLuckysheetRelayout(runtimeRef.current?.luckysheet);

    if (settleRelayoutRef.current !== null) {
      window.clearTimeout(settleRelayoutRef.current);
    }
    settleRelayoutRef.current = window.setTimeout(() => {
      settleRelayoutRef.current = null;
      syncLuckysheetViewport(wrapperRef.current, containerRef.current);
      requestLuckysheetRelayout(runtimeRef.current?.luckysheet);
    }, 320);
  }, [file, renderMode, status]);

  useEffect(() => {
    if (renderMode !== "grid") return;
    if (!file || status !== "ready") return;
    const target = wrapperRef.current;
    if (!target || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const width = Math.round(entry.contentRect.width);
      const height = Math.round(entry.contentRect.height);
      if (width <= 0 || height <= 0) return;

      const prev = lastObservedSizeRef.current;
      lastObservedSizeRef.current = { width, height };
      syncLuckysheetViewport(wrapperRef.current, containerRef.current);
      if (!prev) {
        return;
      }

      const widthDelta = Math.abs(width - prev.width);
      const heightDelta = Math.abs(height - prev.height);
      if (widthDelta < 6 && heightDelta < 6) return;

      requestLuckysheetRelayout(runtimeRef.current?.luckysheet);

      if (settleRelayoutRef.current !== null) {
        window.clearTimeout(settleRelayoutRef.current);
      }
      settleRelayoutRef.current = window.setTimeout(() => {
        settleRelayoutRef.current = null;
        syncLuckysheetViewport(wrapperRef.current, containerRef.current);
        requestLuckysheetRelayout(runtimeRef.current?.luckysheet);
      }, 340);
    });

    observer.observe(target);
    return () => {
      observer.disconnect();
      if (settleRelayoutRef.current !== null) {
        window.clearTimeout(settleRelayoutRef.current);
        settleRelayoutRef.current = null;
      }
    };
  }, [file, renderMode, status]);

  useEffect(() => {
    return () => {
      if (settleRelayoutRef.current !== null) {
        window.clearTimeout(settleRelayoutRef.current);
        settleRelayoutRef.current = null;
      }
      if (hydrationTimerRefs.current.length > 0) {
        hydrationTimerRefs.current.forEach((timerId) => {
          window.clearTimeout(timerId);
          window.clearInterval(timerId);
        });
        hydrationTimerRefs.current = [];
      }
      try {
        runtimeRef.current?.luckysheet.destroy?.();
      } catch {
        // Ignore.
      }
    };
  }, []);

  return (
    <div ref={wrapperRef} className={`module2-luckysheet-preview relative h-full w-full min-h-0 min-w-0 overflow-hidden ${className}`}>
      {status === "loading" && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-slate-50/80 text-xs text-slate-600 dark:bg-slate-900/80 dark:text-slate-300">
          电子表格预览加载中...
        </div>
      )}
      {status === "error" && (
        <div className="absolute inset-0 z-20 flex items-center justify-center p-4">
          <p className="max-w-md rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-center text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            {error || "电子表格预览加载失败"}
          </p>
        </div>
      )}
      <div
        id={containerId}
        ref={containerRef}
        className="h-full w-full min-h-0 min-w-0"
      />
    </div>
  );
};

