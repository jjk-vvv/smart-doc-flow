import type { Module3TaskStatus, Module3TemplateField } from "./module3Api";

export type FusionDocumentType = "xlsx" | "docx" | "txt" | "md" | "other";

export type FusionGridTemplateRecord = {
  id: string;
  name: string;
  backendFilename: string;
  size: string;
  uploadTime: string;
  fields: Module3TemplateField[];
};

export type FusionGridDocsetFileRecord = {
  filename: string;
  path: string;
  size: string;
  type: FusionDocumentType;
};

export type FusionGridDocsetRecord = {
  id: string;
  count: number;
  uploadTime: string;
  files: FusionGridDocsetFileRecord[];
};

export type FusionGridTaskRecord = {
  id: string;
  createdAt: string;
  status: Module3TaskStatus;
  fillRate: number;
  filled: number;
  total: number;
  templateId: string;
  templateName: string;
  docsetId: string;
  docsetLabel: string;
  outputFilename?: string | null;
  error?: string | null;
};

export type FusionGridState = {
  templates: FusionGridTemplateRecord[];
  docsets: FusionGridDocsetRecord[];
  tasks: FusionGridTaskRecord[];
  selectedTemplateId: string | null;
  selectedDocsetId: string | null;
  selectedTaskId: string | null;
  draftRequirements: string;
};

const STORAGE_KEY = "module3_fusion_grid_state";

const EMPTY_STATE: FusionGridState = {
  templates: [],
  docsets: [],
  tasks: [],
  selectedTemplateId: null,
  selectedDocsetId: null,
  selectedTaskId: null,
  draftRequirements: "",
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");

const isTaskStatus = (value: unknown): value is Module3TaskStatus =>
  value === "running" ||
  value === "done" ||
  value === "failed" ||
  value === "pending" ||
  value === "cancel_requested";

const isTemplateField = (value: unknown): value is Module3TemplateField => {
  if (!isRecord(value)) return false;
  if (typeof value.key !== "string" || typeof value.header !== "string") {
    return false;
  }
  if (value.sheet != null && typeof value.sheet !== "string") return false;
  if (value.cell != null && typeof value.cell !== "string") return false;
  if (value.write_cell != null && typeof value.write_cell !== "string") {
    return false;
  }
  if (value.unit != null && typeof value.unit !== "string") return false;
  if (value.aliases != null && !isStringArray(value.aliases)) return false;
  return true;
};

const isDocumentType = (value: unknown): value is FusionDocumentType =>
  value === "xlsx" ||
  value === "docx" ||
  value === "txt" ||
  value === "md" ||
  value === "other";

const isTemplateRecord = (value: unknown): value is FusionGridTemplateRecord => {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.backendFilename === "string" &&
    typeof value.size === "string" &&
    typeof value.uploadTime === "string" &&
    Array.isArray(value.fields) &&
    value.fields.every(isTemplateField)
  );
};

const isDocsetFileRecord = (
  value: unknown,
): value is FusionGridDocsetFileRecord => {
  if (!isRecord(value)) return false;
  return (
    typeof value.filename === "string" &&
    typeof value.path === "string" &&
    typeof value.size === "string" &&
    isDocumentType(value.type)
  );
};

const isDocsetRecord = (value: unknown): value is FusionGridDocsetRecord => {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    typeof value.count === "number" &&
    typeof value.uploadTime === "string" &&
    Array.isArray(value.files) &&
    value.files.every(isDocsetFileRecord)
  );
};

const isTaskRecord = (value: unknown): value is FusionGridTaskRecord => {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    typeof value.createdAt === "string" &&
    isTaskStatus(value.status) &&
    typeof value.fillRate === "number" &&
    typeof value.filled === "number" &&
    typeof value.total === "number" &&
    typeof value.templateId === "string" &&
    typeof value.templateName === "string" &&
    typeof value.docsetId === "string" &&
    typeof value.docsetLabel === "string" &&
    (value.outputFilename == null || typeof value.outputFilename === "string") &&
    (value.error == null || typeof value.error === "string")
  );
};

export const readFusionGridState = (): FusionGridState => {
  if (typeof window === "undefined") return EMPTY_STATE;

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY_STATE;

    const parsed = JSON.parse(raw);
    if (!isRecord(parsed)) return EMPTY_STATE;

    return {
      templates: Array.isArray(parsed.templates)
        ? parsed.templates.filter(isTemplateRecord)
        : [],
      docsets: Array.isArray(parsed.docsets)
        ? parsed.docsets.filter(isDocsetRecord)
        : [],
      tasks: Array.isArray(parsed.tasks)
        ? parsed.tasks.filter(isTaskRecord)
        : [],
      selectedTemplateId:
        typeof parsed.selectedTemplateId === "string"
          ? parsed.selectedTemplateId
          : null,
      selectedDocsetId:
        typeof parsed.selectedDocsetId === "string"
          ? parsed.selectedDocsetId
          : null,
      selectedTaskId:
        typeof parsed.selectedTaskId === "string"
          ? parsed.selectedTaskId
          : null,
      draftRequirements:
        typeof parsed.draftRequirements === "string"
          ? parsed.draftRequirements
          : "",
    };
  } catch {
    return EMPTY_STATE;
  }
};

export const writeFusionGridState = (state: FusionGridState): void => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
};
