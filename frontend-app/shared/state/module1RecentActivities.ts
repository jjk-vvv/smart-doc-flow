export type Module1RecentActivityStatus =
  | "running"
  | "completed"
  | "review"
  | "failed"
  | "ready";

export type Module1RecentActivityRecord = {
  id: string;
  conversationId?: string | null;
  fileId?: string | null;
  fileName: string;
  updatedAt: string;
  status: Module1RecentActivityStatus;
  summary: string;
  progressPercent?: number | null;
};

const STORAGE_KEY = "module1_recent_activities";
export const MODULE1_RECENT_ACTIVITIES_UPDATED_EVENT =
  "module1-recent-activities-updated";

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isStatus = (value: unknown): value is Module1RecentActivityStatus =>
  value === "running"
  || value === "completed"
  || value === "review"
  || value === "failed"
  || value === "ready";

const isFiniteProgress = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

const normalizeProgress = (value: unknown): number | null => {
  if (!isFiniteProgress(value)) return null;
  return Math.max(0, Math.min(100, Math.round(value)));
};

const isRecentActivityRecord = (
  value: unknown,
): value is Module1RecentActivityRecord => {
  if (!isObjectRecord(value)) return false;
  if (typeof value.id !== "string" || !value.id.trim()) return false;
  if (typeof value.fileName !== "string" || !value.fileName.trim()) return false;
  if (typeof value.updatedAt !== "string" || !value.updatedAt.trim()) return false;
  if (!isStatus(value.status)) return false;
  if (typeof value.summary !== "string") return false;
  if (value.conversationId != null && typeof value.conversationId !== "string") {
    return false;
  }
  if (value.fileId != null && typeof value.fileId !== "string") return false;
  if (value.progressPercent != null && !isFiniteProgress(value.progressPercent)) {
    return false;
  }
  return true;
};

const sanitizeRecord = (
  value: Module1RecentActivityRecord,
): Module1RecentActivityRecord => ({
  id: value.id,
  conversationId: value.conversationId?.trim() || null,
  fileId: value.fileId?.trim() || null,
  fileName: value.fileName.trim(),
  updatedAt: value.updatedAt.trim(),
  status: value.status,
  summary: value.summary.trim(),
  progressPercent: normalizeProgress(value.progressPercent),
});

export const readModule1RecentActivities = (): Module1RecentActivityRecord[] => {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isRecentActivityRecord).map(sanitizeRecord);
  } catch {
    return [];
  }
};

export const writeModule1RecentActivities = (
  records: Module1RecentActivityRecord[],
): void => {
  if (typeof window === "undefined") return;
  const safeRecords = Array.isArray(records)
    ? records.filter(isRecentActivityRecord).map(sanitizeRecord)
    : [];
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(safeRecords));
  window.dispatchEvent(new Event(MODULE1_RECENT_ACTIVITIES_UPDATED_EVENT));
};

export const clearModule1RecentActivities = (): void => {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(MODULE1_RECENT_ACTIVITIES_UPDATED_EVENT));
};

export const subscribeModule1RecentActivities = (
  handler: () => void,
): (() => void) => {
  if (typeof window === "undefined") return () => undefined;
  const onCustom = () => handler();
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      handler();
    }
  };
  window.addEventListener(MODULE1_RECENT_ACTIVITIES_UPDATED_EVENT, onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(MODULE1_RECENT_ACTIVITIES_UPDATED_EVENT, onCustom);
    window.removeEventListener("storage", onStorage);
  };
};
