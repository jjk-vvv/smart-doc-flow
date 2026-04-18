export type Module3TaskStatus =
  | "running"
  | "done"
  | "failed"
  | "pending"
  | "cancelled";

export type Module3TemplateField = {
  key: string;
  header: string;
  sheet?: string | null;
  cell?: string | null;
  write_cell?: string | null;
  unit?: string | null;
  template_type?: string | null;
  table_index?: number | null;
  col_idx?: number | null;
  write_row?: number | null;
  aliases?: string[];
};

export type Module3TemplateUploadResponse = {
  template_id: string;
  filename: string;
  fields: Module3TemplateField[];
};

export type Module3DocsetFile = {
  filename: string;
  file_id?: string | null;
};

export type Module3DocsetUploadResponse = {
  doc_set_id: string;
  count: number;
  files: Module3DocsetFile[];
};

export type Module3RunRequest = {
  template_id: string;
  doc_set_id: string;
  prompt?: string;
  user_requirements?: string;
};

export type Module3RunResponse = {
  run_id: string;
  status: string;
};

export type Module3MissingResource = {
  kind: "template" | "docset" | "run";
  id: string;
};

export type Module3RunStatusResponse = {
  run_id: string;
  status: string;
  filled: number;
  total: number;
  fill_rate: number;
  output_file_id?: string | null;
  output_name?: string | null;
  output_download_url?: string;
  output_preview_url?: string;
  error?: string | null;
  finished_at?: string | null;
  completed_at?: string | null;
};

export type Module3WorkbookSheet = {
  name: string;
  row_count: number;
  col_count: number;
  rows: string[][];
};

export type Module3WorkbookPreviewResponse = {
  run_id?: string;
  document_name?: string;
  filename?: string;
  editable?: boolean;
  sheet_count?: number;
  sheets: Module3WorkbookSheet[];
};

export type Module3ExcelCellValue = string | number | boolean | null;

export type Module3ExcelSheet = {
  id: string;
  name: string;
  order: number;
  row_count: number;
  column_count: number;
  rows: Module3ExcelCellValue[][];
};

export type Module3ExcelParseResponse = {
  run_id: string;
  document_name: string;
  sheet_count: number;
  sheets: Module3ExcelSheet[];
};

export type Module3WordStyle = {
  style_id?: string | null;
  alignment?: string | null;
  color?: string | null;
  highlight?: string | null;
  font?: string | null;
  "w:b"?: boolean;
  "w:i"?: boolean;
  "w:u"?: boolean;
  "w:strike"?: boolean;
  "w:sz"?: number | null;
  [key: string]: unknown;
};

export type Module3WordRun = {
  text: string;
  style?: Module3WordStyle;
};

export type Module3WordParagraph = {
  index: number;
  id?: string;
  text: string;
  runs: Module3WordRun[];
  style?: Module3WordStyle;
};

export type Module3WordCell = {
  text: string;
  colspan?: number;
  rowspan?: number;
  width?: number | null;
  style?: Module3WordStyle;
};

export type Module3WordTextSection = {
  id: string;
  name: string;
  type: "text";
  order: number;
  paragraphs: Module3WordParagraph[];
};

export type Module3WordTableSection = {
  id: string;
  name: string;
  type: "table";
  order: number;
  row_count: number;
  column_count: number;
  column_widths: number[];
  virtualized?: boolean;
  rows: Module3WordCell[][];
};

export type Module3WordSection =
  | Module3WordTextSection
  | Module3WordTableSection;

export type Module3WordParseResponse = {
  run_id: string;
  document_name: string;
  sections: Module3WordSection[];
};

export type Module3WordParagraphDiff = {
  paragraph_index: number;
  text: string | null;
};

export type Module3WordCellDiff = {
  row: number;
  col: number;
  value: string | number | float | null;
};

type float = number;

export type Module3WordSectionDiff =
  | {
      section_id: string;
      type: "text";
      paragraphs: Module3WordParagraphDiff[];
    }
  | {
      section_id: string;
      type: "table";
      cells: Module3WordCellDiff[];
    };

export type Module3WordStructureAction = {
  section_id: string;
  action_type: "insert_row" | "delete_row" | "insert_col" | "delete_col";
  index: number;
  count?: number;
};

export type Module3WordApplyDiffRequest = {
  run_id: string;
  sections: Module3WordSectionDiff[];
  actions: Module3WordStructureAction[];
};

export type Module3WordApplyDiffResponse = {
  ok: boolean;
  applied: number;
  output_file_id?: string | null;
  output_name?: string | null;
};

export type Module3ExcelSaveSheet = {
  name: string;
  rows: Module3ExcelCellValue[][];
};

export type Module3ExcelSaveRequest = {
  sheets: Module3ExcelSaveSheet[];
};

const trimTrailingSlash = (value: string): string => value.replace(/\/+$/, "");

const resolveModule3BaseUrl = (): string => {
  const envBase =
    typeof import.meta !== "undefined"
      ? String(import.meta.env?.VITE_MODULE3_API_BASE ?? "").trim()
      : "";
  if (envBase) return trimTrailingSlash(envBase);
  return "/module3";
};

const MODULE3_BASE_URL = resolveModule3BaseUrl();

const module3Url = (path: string): string => `${MODULE3_BASE_URL}${path}`;

const module3Fetch = (path: string, init: RequestInit = {}): Promise<Response> =>
  fetch(module3Url(path), {
    credentials: "include",
    ...init,
  });

const describeDetailItem = (value: unknown): string => {
  if (!value || typeof value !== "object") return "请求格式错误";
  const item = value as Record<string, unknown>;
  if (typeof item.msg === "string" && item.msg.trim()) return item.msg;
  if (Array.isArray(item.loc)) return item.loc.join(".");
  return "请求格式错误";
};

const readModule3Error = async (response: Response): Promise<string> => {
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map(describeDetailItem).join("；");
    }
  } catch {
    return `请求失败（HTTP ${response.status}）`;
  }
  return `请求失败（HTTP ${response.status}）`;
};

const readJson = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    throw new Error(await readModule3Error(response));
  }
  return response.json() as Promise<T>;
};

const extractResourceId = (message: string, prefix: string): string => {
  const match = message.match(new RegExp(`${prefix}_[a-z0-9]+`, "i"));
  return match?.[0] ?? "";
};

export const parseModule3MissingResource = (
  value: unknown,
): Module3MissingResource | null => {
  const message =
    value instanceof Error
      ? value.message
      : typeof value === "string"
        ? value
        : "";
  const normalized = message.trim();
  if (!normalized) return null;

  const templateId = extractResourceId(normalized, "tpl");
  if (templateId) {
    return { kind: "template", id: templateId };
  }

  const docsetId = extractResourceId(normalized, "docset");
  if (docsetId) {
    return { kind: "docset", id: docsetId };
  }

  const runId = extractResourceId(normalized, "run");
  if (runId && normalized.toLowerCase().includes("run")) {
    return { kind: "run", id: runId };
  }

  return null;
};

export const normalizeModule3Status = (
  value: string,
  error?: string | null,
): Module3TaskStatus => {
  if (value === "cancelled") return "cancelled";
  if (value === "done" || value === "completed" || value === "success") {
    return "done";
  }
  if (value === "failed" || value === "error") return "failed";
  if (value === "running" || value === "processing" || value === "queued") {
    return "running";
  }
  if (error) return "failed";
  return "pending";
};

export const uploadModule3Template = async (
  file: File,
): Promise<Module3TemplateUploadResponse> => {
  const formData = new FormData();
  formData.append("file", file, file.name);

  const response = await module3Fetch("/template/upload", {
    method: "POST",
    body: formData,
  });

  return readJson<Module3TemplateUploadResponse>(response);
};

export const uploadModule3Docset = async (
  files: File[],
): Promise<Module3DocsetUploadResponse> => {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file, file.name);
  }

  const response = await module3Fetch("/docset/upload", {
    method: "POST",
    body: formData,
  });

  return readJson<Module3DocsetUploadResponse>(response);
};

export const createModule3Run = async (
  payload: Module3RunRequest,
): Promise<Module3RunResponse> => {
  const response = await module3Fetch("/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      template_id: payload.template_id,
      doc_set_id: payload.doc_set_id,
      prompt: payload.prompt ?? payload.user_requirements,
    }),
  });

  return readJson<Module3RunResponse>(response);
};

export const fetchModule3RunStatus = async (
  runId: string,
): Promise<Module3RunStatusResponse> => {
  const response = await module3Fetch(`/run/${encodeURIComponent(runId)}`);
  return readJson<Module3RunStatusResponse>(response);
};

export const cancelModule3Run = async (
  runId: string,
): Promise<{ cancel_requested?: boolean; status?: string }> => {
  const response = await module3Fetch(
    `/run/${encodeURIComponent(runId)}/cancel`,
    {
      method: "POST",
    },
  );
  return readJson<{ cancel_requested?: boolean; status?: string }>(response);
};

export const fetchModule3Workbook = async (
  runId: string,
): Promise<Module3WorkbookPreviewResponse> => {
  const response = await module3Fetch("/api/v1/excel/parse-json", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ run_id: runId }),
  });
  return readJson<Module3WorkbookPreviewResponse>(response);
};

export const module3RunDownloadUrl = (runId: string): string =>
  module3Url(`/run/${encodeURIComponent(runId)}/download`);

export const module3DocumentPreviewUrl = (fileId: string): string =>
  module3Url(`/documents/preview?file_id=${encodeURIComponent(fileId)}`);

export const fetchModule3DocumentPreviewText = async (
  fileId: string,
): Promise<string> => {
  const response = await module3Fetch(
    `/documents/preview?file_id=${encodeURIComponent(fileId)}`,
  );
  if (!response.ok) {
    throw new Error(await readModule3Error(response));
  }
  return response.text();
};

export const saveModule3RunOutput = async (
  runId: string,
  payload: Module3ExcelSaveRequest,
): Promise<{
  status: string;
  message?: string;
  output_file_id?: string | null;
  output_name?: string | null;
}> => {
  const response = await module3Fetch(`/run/${encodeURIComponent(runId)}/save`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return readJson<{
    status: string;
    message?: string;
    output_file_id?: string | null;
    output_name?: string | null;
  }>(response);
};

export const parseModule3ExcelJson = async (
  runId: string,
): Promise<Module3ExcelParseResponse> => {
  const response = await module3Fetch("/api/v1/excel/parse-json", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ run_id: runId }),
  });
  return readJson<Module3ExcelParseResponse>(response);
};

export const parseModule3WordJson = async (
  runId: string,
): Promise<Module3WordParseResponse> => {
  const response = await module3Fetch("/api/v1/word/parse-json", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ run_id: runId }),
  });
  return readJson<Module3WordParseResponse>(response);
};

export const applyModule3WordDiff = async (
  payload: Module3WordApplyDiffRequest,
): Promise<Module3WordApplyDiffResponse> => {
  const response = await module3Fetch("/api/v1/word/apply-diff", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return readJson<Module3WordApplyDiffResponse>(response);
};
