export type ExtractionEntity = {
  value: unknown;
  confidence: number;
  source_ref_id?: string | null;
  bbox: number[];
};

export type TraceHit = {
  file_name?: string;
  file_hash?: string;
  object_type?: string;
  object_id?: string;
  ref_id?: string | null;
  page?: number | null;
  snippet?: string;
  confidence?: number;
  locator?: Record<string, unknown>;
  bbox?: number[];
  artifact_path?: string | null;
  artifact_url?: string | null;
  match_reason?: string;
};

export type ExtractionDocument = {
  file_name: string;
  file_hash: string;
  track: string;
  cached: boolean;
  result: Record<string, ExtractionEntity>;
  errors: string[];
  soft_warnings?: string[];
  trace_hits?: TraceHit[];
  trace_stats?: Record<string, unknown>;
  diagnostics?: Record<string, unknown>;
};

const STORAGE_KEY = "module2_last_documents";
const UPDATED_AT_KEY = "module2_last_updated";
export const EXTRACTION_UPDATED_EVENT = "module2-data-updated";

const isEntity = (value: unknown): value is ExtractionEntity => {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return typeof obj.confidence === "number" && Array.isArray(obj.bbox);
};

const isTraceHit = (value: unknown): value is TraceHit => {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  if (obj.object_type != null && typeof obj.object_type !== "string") return false;
  if (obj.object_id != null && typeof obj.object_id !== "string") return false;
  if (obj.ref_id != null && typeof obj.ref_id !== "string") return false;
  if (obj.snippet != null && typeof obj.snippet !== "string") return false;
  if (obj.confidence != null && typeof obj.confidence !== "number") return false;
  if (obj.bbox != null && !Array.isArray(obj.bbox)) return false;
  return true;
};

const isDocument = (value: unknown): value is ExtractionDocument => {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  if (typeof obj.file_name !== "string") return false;
  if (typeof obj.file_hash !== "string") return false;
  if (typeof obj.track !== "string") return false;
  if (typeof obj.cached !== "boolean") return false;
  if (!Array.isArray(obj.errors)) return false;
  if (obj.soft_warnings != null && !Array.isArray(obj.soft_warnings)) return false;
  if (obj.trace_hits != null && (!Array.isArray(obj.trace_hits) || !(obj.trace_hits as unknown[]).every(isTraceHit))) return false;
  if (obj.trace_stats != null && typeof obj.trace_stats !== "object") return false;
  if (obj.diagnostics != null && typeof obj.diagnostics !== "object") return false;
  if (!obj.result || typeof obj.result !== "object") return false;
  const result = obj.result as Record<string, unknown>;
  return Object.values(result).every(isEntity);
};

export const readExtractionDocuments = (): ExtractionDocument[] => {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isDocument);
  } catch {
    return [];
  }
};

export const readExtractionUpdatedAt = (): string | null => {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(UPDATED_AT_KEY);
};

export const writeExtractionDocuments = (documents: ExtractionDocument[]): void => {
  if (typeof window === "undefined") return;
  const safeDocs = Array.isArray(documents) ? documents.filter(isDocument) : [];
  const now = new Date().toISOString();
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(safeDocs));
  window.localStorage.setItem(UPDATED_AT_KEY, now);
  window.dispatchEvent(new Event(EXTRACTION_UPDATED_EVENT));
};

export const subscribeExtractionUpdates = (handler: () => void): (() => void) => {
  if (typeof window === "undefined") return () => undefined;
  const onCustom = () => handler();
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY || event.key === UPDATED_AT_KEY) {
      handler();
    }
  };
  window.addEventListener(EXTRACTION_UPDATED_EVENT, onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(EXTRACTION_UPDATED_EVENT, onCustom);
    window.removeEventListener("storage", onStorage);
  };
};
