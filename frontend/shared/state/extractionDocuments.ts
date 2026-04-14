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
  artifact_file_id?: string | null;
  artifact_download_url?: string | null;
  artifact_by_file_url?: string | null;
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

const toWarningText = (value: unknown): string => String(value ?? "").trim();

const toRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
);

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

export const countExtractionDocumentFields = (
  document: Pick<ExtractionDocument, "result"> | null | undefined,
): number => {
  if (!document || !document.result || typeof document.result !== "object") return 0;
  return Object.values(document.result).filter(isEntity).length;
};

export const getExtractionDocumentQualityStatus = (
  document: ExtractionDocument | null | undefined,
): string => {
  const diagnostics = toRecord(document?.diagnostics);
  return String(diagnostics.quality_status ?? "").trim().toLowerCase();
};

const toPositiveInt = (value: unknown): number => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  const rounded = Math.round(parsed);
  return rounded > 0 ? rounded : 0;
};

const getExtractionDocumentTargetFieldCount = (
  document: ExtractionDocument | null | undefined,
): number => {
  const diagnostics = toRecord(document?.diagnostics);
  const directTargetCount = [
    diagnostics.schema_field_count,
    diagnostics.quality_target_field_count,
    diagnostics.target_field_count,
  ]
    .map(toPositiveInt)
    .find((count) => count > 0);
  if (directTargetCount) return directTargetCount;

  const quality = toRecord(diagnostics.quality);
  const qualityTargetCount = toPositiveInt(
    quality.target_field_count ?? quality.quality_target_field_count,
  );
  if (qualityTargetCount > 0) return qualityTargetCount;

  const schema = toRecord(diagnostics.schema);
  return toPositiveInt(schema.field_count ?? schema.schema_field_count);
};

export const isRetryableExtractionWarning = (warningRaw: unknown): boolean => {
  const warning = toWarningText(warningRaw).toLowerCase();
  if (!warning) return false;
  const quotaLimited = warning.includes("quota") && (warning.includes("exceed") || warning.includes("limit"));
  return (
    warning.includes("rate_limited_retryable")
    || warning.includes("timeout_retryable")
    || warning.includes("upstream_retryable")
    || warning.includes("connection_retryable")
    || warning.includes("table_extract_timeout")
    || warning.includes("field_extract_timeout")
    || warning.includes("429")
    || warning.includes("http error 429")
    || warning.includes("too many requests")
    || warning.includes("rate limit")
    || quotaLimited
    || warning.includes("connection error")
  );
};

export const isStaleRetryableExtractionDocument = (
  document: ExtractionDocument | null | undefined,
): boolean => {
  if (!document) return false;
  const softWarnings = Array.isArray(document.soft_warnings) ? document.soft_warnings : [];
  const hasRetryableWarning = softWarnings.some(isRetryableExtractionWarning);
  if (!hasRetryableWarning) return false;

  const fieldCount = countExtractionDocumentFields(document);
  const targetFieldCount = getExtractionDocumentTargetFieldCount(document);
  if (targetFieldCount > 0 && fieldCount < targetFieldCount) return true;

  if (getExtractionDocumentQualityStatus(document) !== "degraded") return false;
  return fieldCount <= 3;
};

export const filterAutoRestorableExtractionDocuments = (
  documents: ExtractionDocument[],
): ExtractionDocument[] => {
  if (!Array.isArray(documents) || documents.length === 0) return [];
  return documents.filter(isDocument).filter((document) => !isStaleRetryableExtractionDocument(document));
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

export const clearExtractionDocuments = (): void => {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem(UPDATED_AT_KEY);
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
