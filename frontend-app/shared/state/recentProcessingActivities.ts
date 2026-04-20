import {
  countExtractionDocumentFields,
  getExtractionDocumentQualityStatus,
  readExtractionDocuments,
  readExtractionUpdatedAt,
  subscribeExtractionUpdates,
  type ExtractionDocument,
} from "./extractionDocuments";
import {
  readFusionGridState,
  subscribeFusionGridStateUpdates,
  type FusionGridDocsetRecord,
  type FusionGridTaskRecord,
} from "../../lib/fusionGridStore";
import {
  readModule1RecentActivities,
  subscribeModule1RecentActivities,
  type Module1RecentActivityRecord,
} from "./module1RecentActivities";

export type RecentProcessingActivityModule = "module1" | "module2" | "module3";
export type RecentProcessingActivityStatus =
  | "running"
  | "completed"
  | "review"
  | "failed"
  | "ready";
export type RecentProcessingActivityTarget =
  | "doc-processing"
  | "deepread_extraction"
  | "fusion";
export type RecentProcessingActivityIconKind =
  | "word"
  | "excel"
  | "pdf"
  | "text"
  | "image"
  | "other";

export type RecentProcessingActivity = {
  id: string;
  module: RecentProcessingActivityModule;
  moduleLabel: string;
  fileName: string;
  updatedAt: string;
  status: RecentProcessingActivityStatus;
  summary: string;
  targetTab: RecentProcessingActivityTarget;
  iconKind: RecentProcessingActivityIconKind;
  progressPercent?: number | null;
};

const MAX_RECENT_ACTIVITY_COUNT = 30;

const clampProgress = (value: unknown): number | null => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, Math.min(100, Math.round(parsed)));
};

const toTimestamp = (value: string | null | undefined): number => {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const toIsoString = (value: number): string => {
  const safeValue = Number.isFinite(value) && value > 0 ? value : Date.now();
  return new Date(safeValue).toISOString();
};

const normalizeText = (value: unknown, fallback: string): string => {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text || fallback;
};

const truncateText = (value: string, maxLength = 44): string => (
  value.length > maxLength ? `${value.slice(0, maxLength)}...` : value
);

const getFileExtension = (fileName: string): string =>
  fileName.split(".").pop()?.toLowerCase() ?? "";

const getIconKind = (fileName: string): RecentProcessingActivityIconKind => {
  const ext = getFileExtension(fileName);
  if (["doc", "docx"].includes(ext)) return "word";
  if (["xls", "xlsx"].includes(ext)) return "excel";
  if (ext === "pdf") return "pdf";
  if (["txt", "md", "markdown", "csv"].includes(ext)) return "text";
  if (["jpg", "jpeg", "png", "gif", "bmp", "webp", "svg"].includes(ext)) {
    return "image";
  }
  return "other";
};

const buildModule1Summary = (record: Module1RecentActivityRecord): string => {
  const baseSummary = truncateText(normalizeText(record.summary, "已更新文档处理进度"));
  if (record.progressPercent == null) return baseSummary;
  return `${baseSummary} · ${record.progressPercent}%`;
};

const mapModule1Activities = (): RecentProcessingActivity[] =>
  readModule1RecentActivities().map((record) => ({
    id: `module1:${record.id}`,
    module: "module1",
    moduleLabel: "模块一",
    fileName: record.fileName,
    updatedAt: record.updatedAt,
    status: record.status,
    summary: buildModule1Summary(record),
    targetTab: "doc-processing",
    iconKind: getIconKind(record.fileName),
    progressPercent: clampProgress(record.progressPercent),
  }));

const getModule2Status = (
  document: ExtractionDocument,
): RecentProcessingActivityStatus => {
  const fieldCount = countExtractionDocumentFields(document);
  const qualityStatus = getExtractionDocumentQualityStatus(document);
  if (document.errors.length > 0 && fieldCount === 0) return "failed";
  if (document.errors.length > 0) return "review";
  if (qualityStatus === "degraded") return "review";
  if (fieldCount > 0) return "completed";
  return "ready";
};

const getModule2Summary = (document: ExtractionDocument): string => {
  const fieldCount = countExtractionDocumentFields(document);
  if (document.errors.length > 0 && fieldCount === 0) {
    return truncateText(
      normalizeText(document.errors[0], "抽取失败，请重新检查文件"),
    );
  }
  if (document.errors.length > 0) {
    return `已抽取 ${fieldCount} 个字段，存在异常待复核`;
  }
  if (document.cached) {
    return `已抽取 ${fieldCount} 个字段，命中缓存`;
  }
  return `已抽取 ${fieldCount} 个字段`;
};

const mapModule2Activities = (): RecentProcessingActivity[] => {
  const documents = readExtractionDocuments();
  const updatedAt = readExtractionUpdatedAt();
  const baseTimestamp = toTimestamp(updatedAt) || Date.now();

  return documents.map((document, index) => ({
    id: `module2:${document.file_hash}`,
    module: "module2",
    moduleLabel: "模块二",
    fileName: document.file_name,
    updatedAt: toIsoString(baseTimestamp - index),
    status: getModule2Status(document),
    summary: getModule2Summary(document),
    targetTab: "deepread_extraction",
    iconKind: getIconKind(document.file_name),
    progressPercent: null,
  }));
};

const buildModule3FileName = (
  task: FusionGridTaskRecord,
  docset: FusionGridDocsetRecord | undefined,
): string => {
  if (!docset || docset.files.length === 0) {
    return task.docsetLabel || task.outputName || task.templateName;
  }
  if (docset.files.length === 1) {
    return docset.files[0].filename;
  }
  return `${docset.files[0].filename} 等 ${docset.files.length} 份文件`;
};

const getModule3Status = (
  task: FusionGridTaskRecord,
): RecentProcessingActivityStatus => {
  const statusText = String(task.status);
  if (statusText === "failed") return "failed";
  if (statusText === "cancelled" || statusText === "cancel_requested") {
    return "review";
  }
  if (statusText === "done") return "completed";
  if (statusText === "running" || statusText === "pending") return "running";
  return "ready";
};

const getModule3Summary = (task: FusionGridTaskRecord): string => {
  const statusText = String(task.status);
  const progress = clampProgress(task.fillRate);
  if (statusText === "failed") {
    return truncateText(
      normalizeText(task.error, `模板“${task.templateName}”处理失败`),
    );
  }
  if (statusText === "done") {
    return `模板“${task.templateName}”已完成 (${task.filled}/${task.total})`;
  }
  if (statusText === "cancelled" || statusText === "cancel_requested") {
    return `模板“${task.templateName}”已取消`;
  }
  if (progress != null && progress > 0) {
    return `模板“${task.templateName}”处理中 (${progress}%)`;
  }
  return `模板“${task.templateName}”等待处理`;
};

const mapModule3Activities = (): RecentProcessingActivity[] => {
  const state = readFusionGridState();
  const docsetMap = new Map(state.docsets.map((docset) => [docset.id, docset]));

  return state.tasks.map((task) => {
    const progressPercent = clampProgress(task.fillRate);
    const updatedAt = toIsoString(
      toTimestamp(task.completedAt) || toTimestamp(task.createdAt),
    );
    const fileName = buildModule3FileName(task, docsetMap.get(task.docsetId));
    return {
      id: `module3:${task.id}`,
      module: "module3",
      moduleLabel: "模块三",
      fileName,
      updatedAt,
      status: getModule3Status(task),
      summary: getModule3Summary(task),
      targetTab: "fusion",
      iconKind: getIconKind(fileName),
      progressPercent,
    };
  });
};

export const readRecentProcessingActivities = (): RecentProcessingActivity[] =>
  [
    ...mapModule1Activities(),
    ...mapModule2Activities(),
    ...mapModule3Activities(),
  ]
    .sort((left, right) => toTimestamp(right.updatedAt) - toTimestamp(left.updatedAt))
    .slice(0, MAX_RECENT_ACTIVITY_COUNT);

export const subscribeRecentProcessingActivities = (
  handler: () => void,
): (() => void) => {
  const unsubscribeModule1 = subscribeModule1RecentActivities(handler);
  const unsubscribeModule2 = subscribeExtractionUpdates(handler);
  const unsubscribeModule3 = subscribeFusionGridStateUpdates(handler);
  return () => {
    unsubscribeModule1();
    unsubscribeModule2();
    unsubscribeModule3();
  };
};
