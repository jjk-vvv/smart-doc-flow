﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
} from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle,
  ChevronDown,
  Download,
  Eye,
  File as FileIcon,
  FileSpreadsheet,
  FolderOpen,
  HelpCircle,
  Loader2,
  RefreshCw,
  Table,
  Trash2,
  UploadCloud,
  X,
  Save,
} from "lucide-react";
import { motion } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  cancelModule3Run,
  createModule3Run,
  fetchModule3RunStatus,
  fetchModule3DocumentPreviewText,
  module3RunDownloadUrl,
  parseModule3ExcelJson,
  parseModule3MissingResource,
  saveModule3RunOutput,
  normalizeModule3Status,
  uploadModule3Docset,
  uploadModule3Template,
  type Module3WorkbookSheet,
  type Module3RunStatusResponse,
  type Module3TaskStatus,
  type Module3TemplateField,
} from "../../lib/module3Api";
import {
  clearFusionGridStateStorage,
  createEmptyFusionGridState,
  readFusionGridState,
  readFusionGridOwnerScope,
  writeFusionGridOwnerScope,
  writeFusionGridState,
  type FusionDocumentType,
  type FusionGridDocsetRecord,
  type FusionGridState,
  type FusionGridTaskRecord,
  type FusionGridTemplateRecord,
} from "../../lib/fusionGridStore";
import { getCurrentUser } from "../../shared/api/auth";
import { Module3WordPreview } from "./Module3WordPreview";
import "luckysheet/dist/plugins/css/pluginsCss.css";
import "luckysheet/dist/plugins/plugins.css";
import "luckysheet/dist/css/luckysheet.css";
import "luckysheet/dist/assets/iconfont/iconfont.css";

import wordIconUrl from "../../assets/WORD.png";
import excelIconUrl from "../../assets/xlsx.png";
import mdIconUrl from "../../assets/md.png";
import txtIconUrl from "../../assets/txt.png";
import fusionLogoUrl from "../../assets/fusion_logo.svg";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const resolveModule3OwnerScope = async (): Promise<string> => {
  try {
    const payload = await getCurrentUser();
    const user = payload?.user;
    const candidate = String(user?.tenantId || user?.id || "anonymous").trim();
    return candidate || "anonymous";
  } catch {
    return "anonymous";
  }
};

type TaskStatus = Module3TaskStatus;
type DocumentType = "xlsx" | "docx" | "txt" | "md" | "other";

type TemplateItem = {
  id: string;
  name: string;
  size: string;
  uploadTime: string;
  fields: Module3TemplateField[];
  backendFilename: string;
};

type DocumentItem = {
  id: string;
  name: string;
  type: DocumentType;
  size: string;
  uploadTime: string;
  fileId: string | null;
  docsetId: string;
};

type TaskItem = {
  id: string;
  name: string;
  createdAt: string;
  completedAt?: string | null;
  status: TaskStatus;
  fillRate: number;
  templateName: string;
  docsetId: string;
  docsetLabel: string;
  filled: number;
  total: number;
  outputFileId?: string | null;
  outputName?: string | null;
  error?: string | null;
};

type SegmentedOption = {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  compactLabel?: string;
  onClick: () => void;
  disabled?: boolean;
  dropdownContent?: React.ReactNode;
  dropdownAlign?: "left" | "right";
};

const MODULE3_TASK_DRAWER_BREAKPOINT = 1320;
const MODULE3_TOPBAR_DENSE_BREAKPOINT = 1180;
const MODULE3_TOPBAR_ULTRA_DENSE_BREAKPOINT = 980;

type PreviewSheet = {
  id: string;
  name: string;
  rows: string[][];
  kind: "sheet" | "table" | "text";
};

const toPreviewTextCell = (
  value: string | number | boolean | null | undefined,
): string => {
  if (value === null || value === undefined) return "";
  return String(value);
};

const workbookSheetsToPreviewSheets = (
  sheets: Module3WorkbookSheet[],
): PreviewSheet[] =>
  sheets.map((sheet, index) => ({
    id: sheet.id || `sheet-${index}`,
    name: sheet.name || `Sheet ${index + 1}`,
    kind: "sheet",
    rows: (sheet.rows || []).map((row) =>
      (row || []).map((cell) => toPreviewTextCell(cell)),
    ),
  }));

const formatBytes = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes <= 0) return "未知大小";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** index;
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
};

const nowText = (): string =>
  new Date().toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

const normalizeProgress = (value: number): number => {
  if (!Number.isFinite(value)) return 0;
  if (value <= 1)
    return Math.max(0, Math.min(100, Math.round(value * 1000) / 10));
  return Math.max(0, Math.min(100, Math.round(value * 10) / 10));
};

const getDocumentType = (filename: string): DocumentType => {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "xlsx") return "xlsx";
  if (ext === "docx") return "docx";
  if (ext === "txt") return "txt";
  if (ext === "md") return "md";
  return "other";
};

const TemplateUploadIcon = ({
  size = 24,
  className = "",
}: {
  size?: number;
  className?: string;
}) => (
  <svg
    viewBox="0 0 1024 1024"
    version="1.1"
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    className={className}
    fill="currentColor"
  >
    <path d="M882.2272 275.2L691.2 93.0304a69.5296 69.5296 0 0 0-48.1792-19.3024H263.5776a137.1136 137.1136 0 0 0-136.9088 136.9088v602.3168a137.0624 137.0624 0 0 0 136.9088 136.9088h503.4496a137.0624 137.0624 0 0 0 136.9088-136.9088V325.7344a70.144 70.144 0 0 0-21.7088-50.5344z m-50.432 36.7616h-177.152a6.8608 6.8608 0 0 1-6.912-6.912V136.704l0.9728 0.8192z m-64.768 576.4608H263.5776a75.52 75.52 0 0 1-75.4688-75.4688V210.6368A75.5712 75.5712 0 0 1 263.5776 135.168h322.56v169.8816a68.4544 68.4544 0 0 0 68.352 68.352h187.8528v439.552a75.5712 75.5712 0 0 1-75.3152 75.4688z" />
    <path d="M686.6432 477.1328h-378.88a30.72 30.72 0 0 0 0 61.44h378.88a30.72 30.72 0 0 0 0-61.44zM686.6432 661.4528h-378.88a30.72 30.72 0 0 0 0 61.44h378.88a30.72 30.72 0 0 0 0-61.44z" />
  </svg>
);

const NeedIcon = ({
  size = 24,
  className = "",
}: {
  size?: number;
  className?: string;
}) => (
  <svg
    viewBox="0 0 1024 1024"
    version="1.1"
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    className={className}
    fill="currentColor"
  >
    <path d="M512 83.2c-108.8 0-192 83.2-192 192s83.2 192 192 192 192-83.2 192-192c0-102.4-83.2-192-192-192z m-108.8 192c0-57.6 44.8-108.8 108.8-108.8s108.8 44.8 108.8 108.8S569.6 384 512 384s-108.8-44.8-108.8-108.8z m224 281.6H281.6c-25.6 0-57.6 6.4-76.8 19.2-44.8 19.2-76.8 57.6-96 96-12.8 25.6-19.2 51.2-19.2 83.2V896c0 25.6 19.2 44.8 44.8 44.8h768c25.6 0 44.8-19.2 44.8-44.8v-25.6-115.2c0-32-6.4-57.6-19.2-83.2-32-38.4-64-76.8-108.8-96-25.6-12.8-51.2-19.2-83.2-19.2H627.2z m-441.6 153.6c12.8-25.6 32-44.8 57.6-57.6 12.8-6.4 25.6-12.8 51.2-12.8h441.6c25.6 0 38.4 6.4 51.2 12.8 25.6 12.8 44.8 32 57.6 57.6 6.4 12.8 12.8 25.6 12.8 51.2v89.6H172.8v-89.6c0-25.6 6.4-38.4 12.8-51.2z" />
  </svg>
);

const HistoryIcon = ({
  size = 24,
  className = "",
}: {
  size?: number;
  className?: string;
}) => (
  <svg
    viewBox="0 0 1024 1024"
    version="1.1"
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    className={className}
    fill="currentColor"
  >
    <path d="M782.7968 239.36c-6.0416 0-12.0832-2.0992-16.9472-6.4a368.70144 368.70144 0 0 0-24.6784-19.968 25.6 25.6 0 0 1-5.3248-35.7888 25.6512 25.6512 0 0 1 35.84-5.3248c9.6256 7.168 19.0464 14.7968 28.0576 22.7328a25.60512 25.60512 0 0 1 2.2528 36.1472 25.8048 25.8048 0 0 1-19.2 8.6016z" />
    <path d="M519.68 935.3216c-196.864 0-366.1824-133.5296-411.8016-324.7616a25.58464 25.58464 0 0 1 18.944-30.8224c13.7728-3.328 27.5456 5.2224 30.8224 18.944 40.0896 168.0896 188.928 285.44 361.984 285.44 205.2096 0 372.1216-166.912 372.1216-372.1216 0-85.0432-27.904-165.0688-80.6912-231.424-8.8064-11.0592-6.9632-27.1872 4.096-35.9936s27.1872-6.9632 35.9936 4.096c60.0576 75.52 91.8528 166.6048 91.8528 263.3216 0 233.4208-189.9008 423.3216-423.3216 423.3216zM683.264 121.4464c-51.8656-21.76-106.9056-32.768-163.584-32.768-152.064 0-290.2528 80.7424-365.4656 209.6128V233.6768c0-14.1312-11.4688-25.6-25.6-25.6s-25.6 11.4688-25.6 25.6v126.464c0 14.1312 11.4688 25.6 25.6 25.6h129.6384c14.1312 0 25.6-11.4688 25.6-25.6s-11.4688-25.6-25.6-25.6H192.5632a371.51744 371.51744 0 0 1 327.1168-194.6624c49.8688 0 98.2016 9.6768 143.7696 28.7744a25.53856 25.53856 0 0 0 33.4848-13.7216c5.5296-13.0048-0.6144-28.0064-13.6704-33.4848z" />
    <path d="M704.6656 547.84H487.0144c-14.1312 0-25.6-11.4688-25.6-25.6V254.9248c0-14.1312 11.4688-25.6 25.6-25.6s25.6 11.4688 25.6 25.6V496.64h192.0512c14.1312 0 25.6 11.4688 25.6 25.6s-11.4688 25.6-25.6 25.6z" />
  </svg>
);

const LookIcon = ({
  size = 24,
  className = "",
}: {
  size?: number;
  className?: string;
}) => (
  <svg
    viewBox="0 0 1024 1024"
    version="1.1"
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    className={className}
    fill="currentColor"
  >
    <path d="M581.53 895.71v-0.952H163.873c-2.867 0-5.255-0.958-6.69-3.345l-0.478-0.479c-1.91-1.913-3.346-4.78-3.346-7.646V140.68c0-1.43 0-2.388 0.958-3.823 1.435-2.866 3.823-5.255 7.168-7.169 0.958-0.474 1.91-0.952 3.345-0.952h695.297c1.91 0 4.298 0.478 7.169 3.823 1.909 1.91 3.345 4.776 3.345 7.643v436.292c0 18.16 14.811 32.976 32.972 32.976h0.478c17.677 0 32.493-14.337 32.493-32.497V139.729c0-20.55-7.646-38.71-22.458-53.047-14.337-14.333-33.45-22.458-53.999-22.458H163.395c-9.078 0-19.113 1.91-29.148 6.211-9.079 3.824-17.683 9.557-24.851 16.725-6.691 7.169-12.424 15.295-15.769 23.895-4.302 9.556-6.211 19.112-6.211 29.148v744.515c0 21.028 7.647 39.188 22.458 53.999 14.815 14.337 33.451 21.506 53.521 21.506h411.446c18.156 0 32.972-14.815 32.972-32.972-0.478-15.294-11.471-28.675-26.283-31.541z m0 0" />
    <path d="M380.736 419.291c0-8.599-3.346-16.725-9.557-22.937s-14.337-9.557-22.937-9.557h-156.26c-8.604 0-16.725 3.345-22.941 9.557-6.213 6.211-9.557 14.337-9.557 22.937v0.478c0 18.635 14.337 32.972 32.972 32.972h155.786c17.682-0.479 32.494-15.29 32.494-33.45z m301.533-129.5c8.604 0 16.73-3.345 22.941-9.083 6.211-6.212 9.556-14.334 10.034-22.938v-0.478c0-18.156-14.337-32.971-32.019-32.971H191.982c-17.683 0-32.499 14.337-32.499 32.493v0.478c0 18.64 14.337 32.977 32.972 32.977l489.814-0.478z m-490.287 259c-9.084 0-17.205 3.345-22.941 9.561-6.213 6.211-9.557 14.333-9.557 22.937v0.478c0 18.635 14.337 32.972 32.972 32.972h73.117c8.6 0 16.725-3.345 22.937-9.078 6.211-6.216 9.556-14.337 10.035-22.941v-0.474c0-18.161-14.337-32.977-32.019-32.977h-74.543v-0.478z m662.798 342.63L734.358 774.345c27.718-36.796 42.529-82.19 42.529-128.543 0-46.353-14.811-91.747-42.529-128.543-30.106-39.66-72.158-63.553-118.028-66.898-13.859-0.957-27.718-0.957-41.577-0.957-13.859 0-27.718 0-41.577 0.957-45.874 3.345-87.922 27.238-118.028 66.898-27.718 36.796-42.529 82.19-42.529 128.543 0 46.353 14.811 91.747 42.529 128.543 30.106 39.664 72.154 63.557 118.028 66.902 13.859 0.958 27.718 0.958 41.577 0.958s27.718 0 41.577-0.958c45.87-3.345 87.922-27.238 118.028-66.902z m-159.605-181.107c33.929 0 61.647 27.718 61.647 61.647 0 33.925-27.718 61.643-61.647 61.643-33.925 0-61.643-27.718-61.643-61.643 0-33.929 27.718-61.647 61.643-61.647z" />
  </svg>
);

const basename = (value?: string | null): string => {
  if (!value) return "";
  let name = value.split(/[\\/]/).pop() ?? value;
  // 去除形如 tpl_123456789abc__ 的前缀
  if (name.startsWith("tpl_")) {
    name = name.replace(/^tpl_[a-f0-9a-z]+__/, "");
  }
  return name;
};

const getTaskOutputName = (task: {
  outputName?: string | null;
  templateName: string;
}): string => {
  const outputName = String(task.outputName || "").trim();
  if (outputName) return outputName;
  return basename(task.templateName);
};

const getTaskName = (index: number, total: number): string =>
  `填充任务${total - index}`;

const getTaskStatusDot = (status: TaskStatus) => {
  switch (status) {
    case "done":
      return "bg-emerald-500";
    case "running":
      return "bg-blue-500";
    case "cancelled":
      return "bg-amber-500";
    case "failed":
      return "bg-red-500";
    default:
      return "bg-slate-400";
  }
};


const getStatusText = (status: TaskStatus) => {
  switch (status) {
    case "done":
      return "已完成";
    case "running":
      return "执行中";
    case "cancelled":
      return "已取消";
    case "failed":
      return "失败";
    default:
      return "待执行";
  }
};

const getFileIcon = (type: DocumentType) => {
  switch (type) {
    case "xlsx":
      return (
        <img
          src={excelIconUrl}
          alt="Excel"
          className="w-[18px] h-[18px] object-contain"
        />
      );
    case "docx":
      return (
        <img
          src={wordIconUrl}
          alt="Word"
          className="w-[18px] h-[18px] object-contain"
        />
      );
    case "txt":
      return (
        <img
          src={txtIconUrl}
          alt="TXT"
          className="w-[18px] h-[18px] object-contain"
        />
      );
    case "md":
      return (
        <img
          src={mdIconUrl}
          alt="Markdown"
          className="w-[18px] h-[18px] object-contain"
        />
      );
    case "other":
    default:
      return <FileIcon size={18} className="text-slate-600" />;
  }
};

const UnifiedFileListItem = ({
  file,
  icon,
  isSelected,
  onClick,
  onRemove,
  onReupload,
  children
}: {
  file: { id: string; name: string; size?: string };
  icon: React.ReactNode;
  isSelected: boolean;
  onClick: () => void;
  onRemove: () => void;
  onReupload?: () => void;
  children?: React.ReactNode;
}) => {
  return (
    <div
      onClick={onClick}
      className={cn(
        "group relative flex flex-col gap-2 rounded-[12px] p-2.5 transition-all cursor-pointer border",
        isSelected
          ? "bg-white dark:bg-white/[0.04] shadow-sm border-slate-200/60 dark:border-white/[0.05]"
          : "bg-transparent border-transparent hover:bg-white dark:hover:bg-white/[0.02] hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:hover:shadow-none hover:border-slate-200/40 dark:hover:border-white/[0.02]"
      )}
    >
      <div className="flex items-center justify-between min-w-0 gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-lg bg-slate-50 dark:bg-white/[0.04]">
            {icon}
          </div>
          <div className="flex flex-col min-w-0 gap-0.5">
            <p className={cn(
              "truncate text-[13px] font-medium leading-none",
              isSelected ? "text-slate-800 dark:text-slate-200" : "text-slate-700 dark:text-slate-300"
            )}>
              {file.name}
            </p>
            <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-none">
              {file.size || "未知大小"}
            </p>
          </div>
        </div>
        
        <div
          className={cn(
            "shrink-0 flex items-center gap-1 transition-opacity",
            isSelected ? "opacity-100" : "opacity-0 group-hover:opacity-100"
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {onReupload && (
            <button
              type="button"
              onClick={onReupload}
              className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700/50 rounded-lg text-slate-400 hover:text-slate-600 transition-colors"
              title="替换文件"
            >
              <UploadCloud size={14} />
            </button>
          )}
          <button
            type="button"
            onClick={onRemove}
            className="p-1.5 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg text-slate-400 hover:text-red-500 transition-colors"
            title="删除"
          >
            <X size={14} />
          </button>
        </div>
      </div>
      {children}
    </div>
  );
};

const spreadsheetColumnLabel = (index: number): string => {
  let current = index + 1;
  let label = "";
  while (current > 0) {
    const remainder = (current - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    current = Math.floor((current - 1) / 26);
  }
  return label;
};

const parsePreviewCells = (line: string): string[] => {
  const trimmed = line.trim();
  if (!trimmed) return [];
  if (trimmed.includes("\t")) {
    return trimmed.split("\t").map((cell) => cell.trim());
  }
  if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
    const cells = trimmed
      .split("|")
      .slice(1, -1)
      .map((cell) => cell.trim());
    if (cells.some((cell) => cell)) return cells;
  }
  return [trimmed];
};

const isWordDocumentMarker = (line: string): string | null => {
  const match = line.match(/^\[(?:Word\s*文档|Word\s*Document)\]\s*(.*)$/i);
  if (!match) return null;
  return match[1]?.trim() ?? "";
};

const parseWordTableHeader = (
  line: string,
): {
  indexText: string;
  label: string;
} | null => {
  const match = line.match(/^\[(?:表格|Table)\s+(\d+)\]\s*(.*)?$/i);
  if (!match) return null;
  return {
    indexText: match[1] ?? "",
    label: match[2]?.trim() || "",
  };
};

const parsePreviewSheets = (
  content: string,
  type: DocumentType,
  fallbackName: string,
): PreviewSheet[] => {
  const normalized = content.replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");

  if (type === "xlsx") {
    const sheets: PreviewSheet[] = [];
    let currentSheet: PreviewSheet | null = null;

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      const sheetMatch = line.match(/^\[工作表\s+\d+\]\s*(.+)?$/);
      if (sheetMatch) {
        currentSheet = {
          id: `sheet-${sheets.length}`,
          name: sheetMatch[1]?.trim() || `Sheet ${sheets.length + 1}`,
          rows: [],
          kind: "sheet",
        };
        sheets.push(currentSheet);
        continue;
      }
      if (!line.trim()) continue;
      if (!currentSheet) {
        currentSheet = {
          id: "sheet-0",
          name: fallbackName,
          rows: [],
          kind: "sheet",
        };
        sheets.push(currentSheet);
      }
      const cells = parsePreviewCells(line);
      if (cells.length > 0) {
        currentSheet.rows.push(cells);
      }
    }

    return sheets;
  }

  if (type === "docx") {
    const sheets: PreviewSheet[] = [];
    const proseRows: string[][] = [];
    let currentTable: PreviewSheet | null = null;
    let implicitTableCount = 0;

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      const documentTitle = isWordDocumentMarker(line);
      if (documentTitle !== null) {
        proseRows.push([documentTitle || fallbackName]);
        currentTable = null;
        continue;
      }

      const tableHeader = parseWordTableHeader(line);
      if (tableHeader) {
        currentTable = {
          id: `table-${sheets.length}`,
          name:
            tableHeader.label ||
            `表格 ${tableHeader.indexText || sheets.length + 1}`,
          rows: [],
          kind: "table",
        };
        sheets.push(currentTable);
        continue;
      }

      if (!line.trim()) {
        if (currentTable?.kind === "table") {
          currentTable = null;
        }
        continue;
      }

      const cells = parsePreviewCells(line);
      const looksLikeTableRow = cells.length > 1;

      if (looksLikeTableRow) {
        if (!currentTable) {
          implicitTableCount += 1;
          currentTable = {
            id: `table-${sheets.length}`,
            name: `表格 ${implicitTableCount}`,
            rows: [],
            kind: "table",
          };
          sheets.push(currentTable);
        }
        currentTable.rows.push(cells);
        continue;
      }

      currentTable = null;
      if (cells.length > 0) {
        proseRows.push([line.trim()]);
      }
    }

    if (proseRows.length > 0) {
      sheets.unshift({
        id: "doc-text",
        name: "文档内容",
        rows: proseRows,
        kind: "text",
      });
    }

    return sheets;
  }

  const textRows = lines
    .map((line) => line.trimEnd())
    .filter((line) => line.trim())
    .map((line) => parsePreviewCells(line))
    .filter((cells) => cells.length > 0);

  return [
    {
      id: "text-preview",
      name: fallbackName,
      rows: textRows,
      kind: "text",
    },
  ];
};

type LuckysheetRuntime = {
  create: (config: Record<string, unknown>) => void;
  destroy: () => void;
  getAllSheets: () => Array<{
    name?: string;
    data?: Array<Array<{ v?: string | number | boolean | null } | null>>;
  }>;
};

type LuckysheetRuntimeWindow = Window & {
  luckysheet?: LuckysheetRuntime;
  __luckysheetLoaderPromise?: Promise<void>;
};

const LUCKYSHEET_CDN_STYLE_URLS = [
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/plugins/css/pluginsCss.css",
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/plugins/plugins.css",
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/css/luckysheet.css",
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/assets/iconfont/iconfont.css",
];

const LUCKYSHEET_CDN_SCRIPT_URLS = [
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/plugins/js/plugin.js",
  "https://cdn.jsdelivr.net/npm/luckysheet@2.1.13/dist/luckysheet.umd.js",
];

const ensureLuckysheetStyles = () => {
  if (typeof document === "undefined") return;
  LUCKYSHEET_CDN_STYLE_URLS.forEach((href) => {
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

const loadLuckysheetFromLocalBundle = async (
  hostWindow: LuckysheetRuntimeWindow,
) => {
  await import("luckysheet/dist/plugins/js/plugin.js");
  const module = await import("luckysheet/dist/luckysheet.umd.js");
  const maybeRuntime =
    (module as { default?: LuckysheetRuntime; luckysheet?: LuckysheetRuntime })
      .default ??
    (module as { default?: LuckysheetRuntime; luckysheet?: LuckysheetRuntime })
      .luckysheet ??
    hostWindow.luckysheet;
  if (maybeRuntime && !hostWindow.luckysheet) {
    hostWindow.luckysheet = maybeRuntime;
  }
  if (!hostWindow.luckysheet) {
    throw new Error("Luckysheet 初始化失败");
  }
};

const loadLuckysheetScript = (src: string) =>
  new Promise<void>((resolve, reject) => {
    if (typeof document === "undefined") {
      reject(new Error("当前环境不支持 Luckysheet"));
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
        () => reject(new Error("Luckysheet 脚本加载失败")),
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
      () => reject(new Error("Luckysheet 脚本加载失败")),
      { once: true },
    );
    document.body.appendChild(script);
  });

const loadLuckysheetFromCdn = async (hostWindow: LuckysheetRuntimeWindow) => {
  ensureLuckysheetStyles();
  for (const src of LUCKYSHEET_CDN_SCRIPT_URLS) {
    await loadLuckysheetScript(src);
  }
  if (!hostWindow.luckysheet) {
    throw new Error("Luckysheet 初始化失败");
  }
};

const ensureLuckysheetLoaded = async (): Promise<LuckysheetRuntime> => {
  if (typeof window === "undefined") {
    throw new Error("当前环境不支持 Luckysheet");
  }

  const hostWindow = window as LuckysheetRuntimeWindow;

  if (hostWindow.luckysheet) return hostWindow.luckysheet;

  if (!hostWindow.__luckysheetLoaderPromise) {
    hostWindow.__luckysheetLoaderPromise = (async () => {
      try {
        await loadLuckysheetFromLocalBundle(hostWindow);
      } catch {
        // 兜底到 CDN，避免历史部署环境中本地包未命中的场景。
        await loadLuckysheetFromCdn(hostWindow);
      }
    })().catch((error) => {
      hostWindow.__luckysheetLoaderPromise = undefined;
      throw error;
    });
  }

  await hostWindow.__luckysheetLoaderPromise;
  if (!hostWindow.luckysheet) {
    throw new Error("Luckysheet 初始化失败");
  }
  return hostWindow.luckysheet;
};

const LuckysheetPreview = ({
  document,
  content,
  sheets: structuredSheets,
}: {
  document: DocumentItem;
  content: string;
  sheets?: PreviewSheet[] | null;
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const containerIdRef = useRef(
    `luckysheet-web-${document.id.replace(/[^a-z0-9_-]/gi, "-")}`,
  );
  const [isSaving, setIsSaving] = useState(false);
  const [isBootingSheet, setIsBootingSheet] = useState(false);
  const [engineError, setEngineError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const [toastMessage, setToastMessage] = useState<{
    text: string;
    type: "success" | "error";
  } | null>(null);
  const [headerActionsContainer, setHeaderActionsContainer] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const el = window.document.getElementById("preview-header-actions");
    if (el) {
      setHeaderActionsContainer(el);
    }
  }, []);

  const sheets = useMemo(
    () =>
      structuredSheets && structuredSheets.length > 0
        ? structuredSheets
        : parsePreviewSheets(content, document.type, document.name),
    [content, document.name, document.type, structuredSheets],
  );

  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;
    setIsBootingSheet(true);
    setEngineError("");

    const mountLuckysheet = async () => {
      let luckysheet: any;
      try {
        luckysheet = await ensureLuckysheetLoaded();
        if (cancelled || !luckysheet) return;

        luckysheet.destroy();
      } catch {
        // Ignore stale instance cleanup failures.
      }

      try {
        if (!luckysheet) return;
        const luckysheetData = sheets.map((sheet, index) => {
          const celldata: any[] = [];
          sheet.rows.forEach((row, rIndex) => {
            row.forEach((cell, cIndex) => {
              if (cell !== undefined && cell !== null && cell !== "") {
                celldata.push({
                  r: rIndex,
                  c: cIndex,
                  v: { v: cell, m: String(cell) },
                });
              }
            });
          });

          return {
            name: sheet.name,
            index: index.toString(),
            order: index,
            status: index === 0 ? 1 : 0,
            celldata,
          };
        });

        luckysheet.create({
          container: containerIdRef.current,
          data: luckysheetData,
          showinfobar: false,
          showtoolbar: true,
          showsheetbar: true,
          showstatisticBar: true,
          enableAddRow: true,
          enableAddBackTop: true,
          lang: "zh",
        });
      } catch (error) {
        if (!cancelled) {
          setEngineError(
            error instanceof Error ? error.message : "Luckysheet 加载失败",
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
        (window as any).luckysheet?.destroy();
      } catch {
        // Ignore cleanup failures from the global singleton.
      }
    };
  }, [document.id, sheets, reloadToken]);

  const handleSave = async () => {
    const luckysheet = (window as any).luckysheet;
    if (!luckysheet) {
      setToastMessage({ text: "表格引擎尚未加载完成", type: "error" });
      setTimeout(() => setToastMessage(null), 3000);
      return;
    }

    setIsSaving(true);
    try {
      const allSheets = luckysheet.getAllSheets();
      const payloadSheets = allSheets.map((sheet: any) => {
        const rows: any[][] = [];
        const sheetData = sheet.data || [];
        for (let r = 0; r < sheetData.length; r++) {
          const rowData: any[] = [];
          for (let c = 0; c < sheetData[r].length; c++) {
            const cell = sheetData[r][c];
            const val =
              cell && cell.v !== undefined && cell.v !== null ? cell.v : "";
            rowData.push(val);
          }
          rows.push(rowData);
        }

        let lastNonEmptyRow = -1;
        for (let r = rows.length - 1; r >= 0; r--) {
          if (rows[r].some((val) => val !== "")) {
            lastNonEmptyRow = r;
            break;
          }
        }
        const trimmedRows = rows.slice(0, lastNonEmptyRow + 1);

        return {
          name: sheet.name,
          rows: trimmedRows,
        };
      });

      await saveModule3RunOutput(document.id, { sheets: payloadSheets });
      setToastMessage({ text: "保存成功！", type: "success" });
    } catch (err) {
      console.error(err);
      setToastMessage({ text: "保存失败", type: "error" });
    } finally {
      setIsSaving(false);
      setTimeout(() => setToastMessage(null), 3000);
    }
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 max-w-full flex-col relative overflow-hidden bg-slate-50 dark:bg-[#0B1120]">
      {toastMessage && (
        <div
          className={cn(
            "absolute top-4 left-1/2 -translate-x-1/2 z-[2000] px-4 py-2 rounded-[12px] shadow-lg text-[13px] font-medium text-white transition-opacity",
            toastMessage.type === "success" ? "bg-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400" : "bg-red-600 dark:bg-red-500/20 dark:text-red-400",
          )}
        >
          {toastMessage.text}
        </div>
      )}
      {headerActionsContainer && createPortal(
        <button
          onClick={handleSave}
          disabled={isSaving}
          title="保存修改"
          className="flex items-center justify-center w-[22px] h-[22px] bg-white dark:bg-white/[0.02] border border-slate-200 dark:border-transparent dark:ring-1 dark:ring-white/[0.05] text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/[0.05] hover:text-slate-900 dark:hover:text-slate-200 rounded-[4px] shadow-sm transition-all active:scale-95 disabled:opacity-50"
        >
          {isSaving ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Save size={12} />
          )}
        </button>,
        headerActionsContainer
      )}
      <div
        id={containerIdRef.current}
        ref={containerRef}
        className="flex-1 w-full h-full relative"
      />
      {isBootingSheet ? (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/85 text-sm text-slate-500 dark:bg-[#0B1120]/85 dark:text-slate-300">
          <div className="flex items-center gap-2">
            <Loader2 size={16} className="animate-spin" />
            正在加载 Excel 预览引擎...
          </div>
        </div>
      ) : null}
      {engineError ? (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/92 p-6 dark:bg-[#0B1120]/92">
          <div className="flex max-w-md flex-col items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-6 py-5 text-center shadow-sm dark:border-amber-900/50 dark:bg-amber-500/10">
            <AlertCircle size={24} className="text-amber-600 dark:text-amber-400" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                Excel 预览引擎初始化失败
              </p>
              <p className="text-xs leading-6 text-amber-700 dark:text-amber-300">
                当前文件仍会坚持走 Luckysheet 预览链路，不再降级为普通表格视图。请重试初始化，若仍失败请检查文件内容或转换结果。
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setReloadToken((value) => value + 1)}
                className="inline-flex items-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-amber-700 dark:bg-amber-500 dark:text-slate-950 dark:hover:bg-amber-400"
              >
                <RefreshCw size={14} />
                重新加载 Luckysheet
              </button>
            </div>
            <p className="text-[11px] text-amber-700/80 dark:text-amber-200/70">
              {engineError}
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
};

const SpreadsheetPreview = ({
  document,
  content,
  sheets: structuredSheets,
}: {
  document: DocumentItem;
  content: string;
  sheets?: PreviewSheet[] | null;
}) => {
  const sheets = useMemo(
    () =>
      structuredSheets && structuredSheets.length > 0
        ? structuredSheets
        : parsePreviewSheets(content, document.type, document.name),
    [content, document.name, document.type, structuredSheets],
  );
  const [activeSheetId, setActiveSheetId] = useState<string | null>(null);

  useEffect(() => {
    const preferredSheet =
      document.type === "docx"
        ? (sheets.find((sheet) => sheet.kind === "table") ?? sheets[0] ?? null)
        : (sheets[0] ?? null);
    setActiveSheetId(preferredSheet?.id ?? null);
  }, [document.type, sheets]);

  const activeSheet = useMemo(
    () =>
      sheets.find((sheet) => sheet.id === activeSheetId) ?? sheets[0] ?? null,
    [activeSheetId, sheets],
  );

  const normalizedRows = useMemo(() => {
    if (!activeSheet) return [];
    const columnCount = Math.max(
      1,
      ...activeSheet.rows.map((row) => row.length),
    );
    return activeSheet.rows.map((row) => {
      const nextRow = [...row];
      while (nextRow.length < columnCount) {
        nextRow.push("");
      }
      return nextRow;
    });
  }, [activeSheet]);

  const columnLabels = useMemo(() => {
    const columnCount = normalizedRows[0]?.length ?? 1;
    return Array.from({ length: columnCount }, (_, index) =>
      spreadsheetColumnLabel(index),
    );
  }, [normalizedRows]);

  if (!activeSheet || normalizedRows.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-50/60 text-sm text-slate-500 dark:bg-slate-900/40 dark:text-slate-400">
        当前文件暂无可展示的预览内容
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 max-w-full flex-col overflow-hidden bg-[#f8fafc] dark:bg-slate-950">
      <div className="min-w-0 border-b border-slate-200 bg-white/90 px-4 py-3 dark:border-slate-700 dark:bg-slate-900/95">
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <Table
              size={16}
              className="text-emerald-600 dark:text-emerald-400"
            />
            <span className="truncate font-medium text-slate-900 dark:text-white">
              表格预览
            </span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs dark:bg-slate-800">
              {activeSheet.kind === "sheet"
                ? "Excel"
                : activeSheet.kind === "table"
                  ? "表格"
                  : "文本"}
            </span>
          </div>
          <div className="shrink-0 text-xs text-slate-500 dark:text-slate-400">
            {normalizedRows.length} 行 · {columnLabels.length} 列
          </div>
        </div>
        <div className="mt-3 flex min-w-0 flex-wrap gap-2">
          {sheets.map((sheet) => (
            <button
              key={sheet.id}
              type="button"
              onClick={() => setActiveSheetId(sheet.id)}
              className={cn(
                "rounded-lg border px-3 py-1.5 text-xs transition-colors",
                sheet.id === activeSheet.id
                  ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-300"
                  : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800",
              )}
            >
              {sheet.name}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 min-w-0 max-w-full flex-1 overflow-x-auto overflow-y-auto overscroll-contain scrollbar-thin scrollbar-thumb-slate-200 dark:scrollbar-thumb-white/10">
        <div className="min-w-full w-full max-w-full">
          <table className="w-max min-w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="bg-[#eef2f7] dark:bg-slate-900">
                <th className="w-14 border border-slate-200 px-3 py-2 text-center text-xs font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  #
                </th>
                {columnLabels.map((label) => (
                  <th
                    key={label}
                    className="min-w-[140px] border border-slate-200 px-3 py-2 text-center text-xs font-semibold text-slate-600 dark:border-slate-700 dark:text-slate-300"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {normalizedRows.map((row, rowIndex) => (
                <tr
                  key={`${activeSheet.id}-${rowIndex}`}
                  className={cn(
                    "transition-colors",
                    rowIndex === 0
                      ? "bg-emerald-50/70 dark:bg-emerald-500/5"
                      : rowIndex % 2 === 0
                        ? "bg-white dark:bg-slate-950"
                        : "bg-slate-50/60 dark:bg-slate-900/40",
                  )}
                >
                  <th className="border border-slate-200 px-3 py-2 text-center text-xs font-medium text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    {rowIndex + 1}
                  </th>
                  {row.map((cell, columnIndex) => (
                    <td
                      key={`${activeSheet.id}-${rowIndex}-${columnIndex}`}
                      className={cn(
                        "max-w-[320px] border border-slate-200 px-3 py-2 align-top text-slate-700 dark:border-slate-700 dark:text-slate-200",
                        rowIndex === 0 &&
                          "font-semibold text-slate-900 dark:text-white",
                      )}
                    >
                      <div className="whitespace-pre-wrap break-words">
                        {cell || "—"}
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

const updateTaskFromStatus = (
  task: FusionGridTaskRecord,
  status: Module3RunStatusResponse,
): FusionGridTaskRecord => ({
  ...task,
  status: normalizeModule3Status(status.status, status.error),
  filled: Number.isFinite(status.filled) ? status.filled : task.filled,
  total: Number.isFinite(status.total) ? status.total : task.total,
  fillRate: Number.isFinite(status.fill_rate)
    ? normalizeProgress(status.fill_rate)
    : task.fillRate,
  outputFileId: status.output_file_id ?? task.outputFileId ?? null,
  outputName: status.output_name ?? task.outputName ?? null,
  error: status.error ?? task.error ?? null,
  completedAt:
    status.completed_at ?? status.finished_at ?? task.completedAt ?? null,
});

const SegmentedControl = ({
  options,
  denseMode = false,
  ultraDenseMode = false,
}: {
  options: SegmentedOption[];
  denseMode?: boolean;
  ultraDenseMode?: boolean;
}) => {
  const [openDropdownIndex, setOpenDropdownIndex] = useState<number | null>(
    null,
  );
  const [lockedDropdownIndex, setLockedDropdownIndex] = useState<number | null>(
    null,
  );
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [dropdownPositions, setDropdownPositions] = useState<
    { left: number; right: number; top: number; width: number }[]
  >([]);
  const closeTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 计算下拉菜单位置

  useEffect(() => {
    const positions = buttonRefs.current.map((btn) => {
      if (!btn) return { left: 0, right: 0, top: 0, width: 0 };
      const rect = btn.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        top: rect.bottom + 8,
        width: rect.width,
      };
    });
    setDropdownPositions(positions);
  }, [openDropdownIndex, lockedDropdownIndex]);

  // 清理 timeout
  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) clearTimeout(closeTimeoutRef.current);
    };
  }, []);

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (lockedDropdownIndex !== null) {
        const btnRef = buttonRefs.current[lockedDropdownIndex];
        if (btnRef && !btnRef.contains(event.target as Node)) {
          // 检查是否点击了下拉菜单内部
          const dropdownEl = document.querySelector(
            `[data-dropdown-index="${lockedDropdownIndex}"]`,
          );
          if (dropdownEl && !dropdownEl.contains(event.target as Node)) {
            setLockedDropdownIndex(null);
            setOpenDropdownIndex(null);
          }
        }
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [lockedDropdownIndex]);

  // 处理按钮点击 - 切换下拉菜单锁定状态
  const handleButtonClick = (
    index: number,
    hasDropdown: boolean,
    onClick: () => void,
  ) => {
    if (hasDropdown) {
      // 如果点击的是已锁定的下拉菜单，则关闭它
      if (lockedDropdownIndex === index) {
        setLockedDropdownIndex(null);
        setOpenDropdownIndex(null);
      } else {
        // 否则锁定这个下拉菜单
        setLockedDropdownIndex(index);
        setOpenDropdownIndex(index);
      }
    } else {
      // 没有下拉菜单的按钮，执行原有点击逻辑
      onClick();
    }
  };

  // 处理鼠标进入 - 显示下拉菜单（但不锁定）
  const handleMouseEnter = (index: number, hasDropdown: boolean) => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
    if (hasDropdown && lockedDropdownIndex === null) {
      setOpenDropdownIndex(index);
    }
  };

  // 处理鼠标离开
  const handleMouseLeave = () => {
    // 只有在没有锁定的情况下才延迟关闭下拉菜单，以便鼠标可以移动到下拉菜单上
    if (lockedDropdownIndex === null) {
      closeTimeoutRef.current = setTimeout(() => {
        setOpenDropdownIndex(null);
      }, 150);
    }
  };

  // 处理下拉菜单内部的鼠标进入
  const handleDropdownMouseEnter = () => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
  };

  // 确定当前应该显示哪个下拉菜单
  const currentOpenIndex =
    lockedDropdownIndex !== null ? lockedDropdownIndex : openDropdownIndex;

  return (
    <>
      <div
        className={cn(
          "relative flex w-full max-w-full overflow-x-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none] justify-start sm:justify-end items-center lg:ml-auto pb-1 sm:pb-0",
          ultraDenseMode
            ? "gap-0.5 sm:gap-1 lg:max-w-[620px]"
            : denseMode
              ? "gap-0.5 sm:gap-1.5 lg:max-w-[700px]"
              : "gap-1 sm:gap-2 lg:max-w-[800px]",
        )}
      >
        {options.map((option, index) => {
          const Icon = option.icon;
          const hasDropdown = !!option.dropdownContent;
          const isDropdownOpen = currentOpenIndex === index;
          const displayLabel =
            denseMode || ultraDenseMode
              ? option.compactLabel || option.label
              : option.label;

          return (
            <motion.button
              key={option.label}
              ref={(el) => {
                buttonRefs.current[index] = el;
              }}
              type="button"
              onClick={() => {
                if (option.disabled) return;
                handleButtonClick(index, hasDropdown, option.onClick);
              }}
              onMouseEnter={() => handleMouseEnter(index, hasDropdown)}
              onMouseLeave={handleMouseLeave}
              className={cn(
                "relative flex shrink-0 items-center justify-center whitespace-nowrap font-medium transition-colors duration-200",
                ultraDenseMode
                  ? "gap-1 rounded-md px-2 h-[24px] text-[11px]"
                  : denseMode
                    ? "gap-1 rounded-md px-2.25 h-[25px] text-[11px]"
                    : "gap-1.5 rounded-md px-2.5 h-[26px] text-[12px]",
                "text-slate-600 hover:text-slate-900 hover:bg-slate-100/80 dark:text-slate-300 dark:hover:text-white dark:hover:bg-white/[0.05]",
                isDropdownOpen
                  ? "bg-slate-100/80 text-slate-900 dark:bg-white/[0.05] dark:text-white"
                  : "",
                option.disabled
                  ? "cursor-not-allowed opacity-50 hover:bg-transparent dark:hover:bg-transparent"
                  : "",
              )}
              whileTap={{ scale: option.disabled ? 1 : 0.98 }}
            >
              <div className="relative z-10 flex items-center justify-center gap-1.5">
                <Icon
                  size={ultraDenseMode ? 13 : 14}
                  className={cn(ultraDenseMode ? "w-[13px] h-[13px]" : "w-3.5 h-3.5")}
                />
                <span className={cn("font-medium", ultraDenseMode ? "hidden md:inline" : "hidden sm:inline")}>
                  {displayLabel}
                </span>
                {hasDropdown && (
                  <ChevronDown
                    size={ultraDenseMode ? 10 : 12}
                    className={cn(
                      ultraDenseMode ? "transition-transform duration-200 w-2.5 h-2.5" : "transition-transform duration-200 w-3 h-3",
                      isDropdownOpen ? "rotate-180" : "",
                    )}
                  />
                )}
              </div>
            </motion.button>
          );
        })}
      </div>

      {/* 真正挂到 body，避免受主内容区偏移影响 */}
      {typeof document !== "undefined"
        ? createPortal(
            <>
              {options.map((option, index) => {
                const hasDropdown = !!option.dropdownContent;
                const isDropdownOpen = currentOpenIndex === index;
                const position = dropdownPositions[index];
                const alignRight = option.dropdownAlign === "right";

                if (!hasDropdown || !isDropdownOpen || !position) return null;

                return (
                  <div
                    key={`dropdown-${index}`}
                    data-dropdown-index={index}
                    style={{
                      position: "fixed",
                      left: alignRight ? undefined : position.left,
                      right: alignRight
                        ? window.innerWidth - position.right
                        : undefined,
                      top: position.top,
                      zIndex: 9999,
                    }}
                    onMouseEnter={handleDropdownMouseEnter}
                    onMouseLeave={handleMouseLeave}
                  >
                    <motion.div
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.15 }}
                    >
                      <div className="rounded-xl border border-slate-200/60 bg-white/95 backdrop-blur-xl shadow-[0_8px_30px_rgb(0,0,0,0.08)] dark:border-white/[0.1] dark:bg-[#0B1120]/95 dark:shadow-[0_8px_30px_rgb(0,0,0,0.4)] overflow-hidden">
                        {option.dropdownContent}
                      </div>
                    </motion.div>
                  </div>
                );
              })}
            </>,
            document.body,
          )
        : null}
    </>
  );
};

export const FusionGrid: React.FC = () => {
  const [leftPanelWidth, setLeftPanelWidth] = useState(25); // Percentage width of the left panel
  const [workbenchWidth, setWorkbenchWidth] = useState<number>(() =>
    typeof window !== "undefined" ? window.innerWidth : 1440,
  );
  const [isTaskDrawerOpen, setIsTaskDrawerOpen] = useState(false);
  const isResizingRef = useRef(false);
  const dragOffsetRef = useRef(0);
  const splitLayoutRef = useRef<HTMLDivElement>(null);

  const getSplitLayoutWidth = useCallback(() => {
    return (
      splitLayoutRef.current?.getBoundingClientRect().width ?? window.innerWidth
    );
  }, []);

  // Resize handler
  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isResizingRef.current) return;

      // Calculate new width against the actual split container, not the full window.
      const newWidth =
        ((e.clientX - dragOffsetRef.current) / getSplitLayoutWidth()) * 100;

      // Constrain width between 15% and 50%
      if (newWidth >= 15 && newWidth <= 50) {
        setLeftPanelWidth(newWidth);
      }
    },
    [getSplitLayoutWidth],
  );

  const handleMouseUp = useCallback(() => {
    isResizingRef.current = false;
    document.body.style.cursor = "default";
    document.body.style.userSelect = "auto"; // Re-enable text selection
  }, []);

  useEffect(() => {
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  useEffect(() => {
    const target = splitLayoutRef.current;

    const syncWidth = () => {
      const nextWidth = Math.round(
        target?.getBoundingClientRect().width || window.innerWidth || 1440,
      );
      setWorkbenchWidth((prev) => (prev === nextWidth ? prev : nextWidth));
    };

    syncWidth();

    if (typeof ResizeObserver === "undefined" || !target) {
      window.addEventListener("resize", syncWidth);
      return () => window.removeEventListener("resize", syncWidth);
    }

    const observer = new ResizeObserver(() => syncWidth());
    observer.observe(target);
    window.addEventListener("resize", syncWidth);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", syncWidth);
    };
  }, []);

  const [gridState, setGridState] = useState<FusionGridState>(() =>
    readFusionGridState(),
  );
  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
  const [previewDocument, setPreviewDocument] = useState<DocumentItem | null>(
    null,
  );
  const [previewContent, setPreviewContent] = useState<string>("");
  const [previewSheets, setPreviewSheets] = useState<PreviewSheet[] | null>(
    null,
  );
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [, setInfoMessage] = useState(
    "请先上传模板，再上传文档，最后点击开始填充。",
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [isUploadingTemplate, setIsUploadingTemplate] = useState(false);
  const [isUploadingDocset, setIsUploadingDocset] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [cancellingTaskIds, setCancellingTaskIds] = useState<string[]>([]);

  const templateInputRef = useRef<HTMLInputElement>(null);
  const docsetInputRef = useRef<HTMLInputElement>(null);

  const templates = gridState.templates;
  const docsets = gridState.docsets;
  const tasks = gridState.tasks;
  const selectedTemplateId = gridState.selectedTemplateId;
  const selectedDocsetId = gridState.selectedDocsetId;
  const selectedTaskId = gridState.selectedTaskId;
  const draftRequirements = gridState.draftRequirements;

  const selectedTemplateRecord = useMemo(
    () => templates.find((item) => item.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  );
  const selectedDocsetRecord = useMemo(
    () => docsets.find((item) => item.id === selectedDocsetId) ?? null,
    [docsets, selectedDocsetId],
  );
  const selectedTaskRecord = useMemo(
    () => tasks.find((item) => item.id === selectedTaskId) ?? null,
    [tasks, selectedTaskId],
  );

  const templateItems: TemplateItem[] = templates;
  const documentItems: DocumentItem[] = useMemo(() => {
    if (!selectedDocsetRecord) return [];
    return selectedDocsetRecord.files.map((file, index) => ({
      id: `${selectedDocsetRecord.id}:${file.fileId || `${file.filename}:${index}`}`,
      name: file.filename,
      type: file.type as DocumentType,
      size: file.size,
      uploadTime: selectedDocsetRecord.uploadTime,
      fileId: file.fileId ?? null,
      docsetId: selectedDocsetRecord.id,
    }));
  }, [selectedDocsetRecord]);

  const taskItems: TaskItem[] = useMemo(
    () =>
      tasks.map((task, index) => ({
        id: task.id,
        name: getTaskName(index, tasks.length),
        createdAt: task.createdAt,
        completedAt: task.completedAt,
        status: task.status,
        fillRate: normalizeProgress(task.fillRate),
        templateName: task.templateName,
        docsetId: task.docsetId,
        docsetLabel: task.docsetLabel,
        filled: task.filled,
        total: task.total,
        outputFileId: task.outputFileId,
        outputName: task.outputName,
        error: task.error,
      })),
    [tasks],
  );

  const normalizedDraftRequirements = draftRequirements.trim();
  const canStartRun =
    !isRunning &&
    !isUploadingTemplate &&
    !isUploadingDocset &&
    templates.length > 0 &&
    docsets.length > 0;
  const shouldUseTaskDrawer = workbenchWidth > 0 && workbenchWidth <= MODULE3_TASK_DRAWER_BREAKPOINT;
  const useDenseTopBar = workbenchWidth > 0 && workbenchWidth <= MODULE3_TOPBAR_DENSE_BREAKPOINT;
  const useUltraDenseTopBar =
    workbenchWidth > 0 && workbenchWidth <= MODULE3_TOPBAR_ULTRA_DENSE_BREAKPOINT;
  const useDenseRightPanel = workbenchWidth > 0 && workbenchWidth <= 1180;
  const useUltraDenseRightPanel = workbenchWidth > 0 && workbenchWidth <= 940;
  const showDockedTaskPanel = !shouldUseTaskDrawer;
  const showTaskDrawer = shouldUseTaskDrawer && isTaskDrawerOpen;

  const closeTaskDrawer = useCallback(() => setIsTaskDrawerOpen(false), []);
  const toggleTaskDrawer = useCallback(() => {
    if (!shouldUseTaskDrawer) return;
    setIsTaskDrawerOpen((prev) => !prev);
  }, [shouldUseTaskDrawer]);
  const handleSelectTask = useCallback(
    (taskId: string) => {
      setGridState((current) => ({
        ...current,
        selectedTaskId: taskId,
      }));
      if (showTaskDrawer) {
        setIsTaskDrawerOpen(false);
      }
    },
    [showTaskDrawer],
  );

  useEffect(() => {
    writeFusionGridState(gridState);
  }, [gridState]);

  useEffect(() => {
    if (!shouldUseTaskDrawer && isTaskDrawerOpen) {
      setIsTaskDrawerOpen(false);
    }
  }, [isTaskDrawerOpen, shouldUseTaskDrawer]);

  useEffect(() => {
    let active = true;

    resolveModule3OwnerScope().then((ownerScope) => {
      if (!active) return;
      const previousOwnerScope = readFusionGridOwnerScope();
      if (previousOwnerScope && previousOwnerScope !== ownerScope) {
        clearFusionGridStateStorage();
        setGridState(createEmptyFusionGridState());
        setErrorMessage("");
        setInfoMessage("已切换到当前账号对应的填表工作区。");
      }
      writeFusionGridOwnerScope(ownerScope);
    });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setGridState((current) => {
      let changed = false;
      let nextSelectedTemplateId = current.selectedTemplateId;
      let nextSelectedDocsetId = current.selectedDocsetId;
      let nextSelectedTaskId = current.selectedTaskId;

      if (current.templates.length === 0) {
        if (nextSelectedTemplateId !== null) {
          nextSelectedTemplateId = null;
          changed = true;
        }
      } else if (
        !nextSelectedTemplateId ||
        !current.templates.some((item) => item.id === nextSelectedTemplateId)
      ) {
        nextSelectedTemplateId = current.templates[0].id;
        changed = true;
      }

      if (current.docsets.length === 0) {
        if (nextSelectedDocsetId !== null) {
          nextSelectedDocsetId = null;
          changed = true;
        }
      } else if (
        !nextSelectedDocsetId ||
        !current.docsets.some((item) => item.id === nextSelectedDocsetId)
      ) {
        nextSelectedDocsetId = current.docsets[0].id;
        changed = true;
      }

      if (current.tasks.length === 0) {
        if (nextSelectedTaskId !== null) {
          nextSelectedTaskId = null;
          changed = true;
        }
      } else if (
        !nextSelectedTaskId ||
        !current.tasks.some((item) => item.id === nextSelectedTaskId)
      ) {
        nextSelectedTaskId = current.tasks[0].id;
        changed = true;
      }

      if (!changed) return current;
      return {
        ...current,
        selectedTemplateId: nextSelectedTemplateId,
        selectedDocsetId: nextSelectedDocsetId,
        selectedTaskId: nextSelectedTaskId,
      };
    });
  }, [templates, docsets, tasks]);

  useEffect(() => {
    if (documentItems.length === 0) {
      setSelectedDocument(null);
      return;
    }
    if (
      !selectedDocument ||
      !documentItems.some((item) => item.id === selectedDocument)
    ) {
      setSelectedDocument(documentItems[0].id);
    }
  }, [documentItems, selectedDocument]);

  useEffect(() => {
    const runningTaskIds = tasks
      .filter((item) => item.status === "running")
      .map((item) => item.id);
    if (runningTaskIds.length === 0) return;

    const timer = window.setInterval(() => {
      runningTaskIds.forEach((taskId) => {
        fetchModule3RunStatus(taskId)
          .then((status) => {
            setGridState((current) => ({
              ...current,
              tasks: current.tasks.map((item) =>
                item.id === taskId ? updateTaskFromStatus(item, status) : item,
              ),
            }));
          })
          .catch(() => undefined);
      });
    }, 3000);

    return () => window.clearInterval(timer);
  }, [tasks]);

  useEffect(() => {
    setCancellingTaskIds((current) =>
      current.filter((taskId) =>
        tasks.some((task) => task.id === taskId && task.status === "running"),
      ),
    );
  }, [tasks]);

  const dropMissingRunDependency = useCallback(
    (kind: "template" | "docset", missingId: string) => {
      setGridState((current) => {
        if (kind === "template") {
          const templates = current.templates.filter((item) => item.id !== missingId);
          return {
            ...current,
            templates,
            selectedTemplateId:
              current.selectedTemplateId === missingId
                ? (templates[0]?.id ?? null)
                : current.selectedTemplateId,
          };
        }

        const docsets = current.docsets.filter((item) => item.id !== missingId);
        return {
          ...current,
          docsets,
          selectedDocsetId:
            current.selectedDocsetId === missingId
              ? (docsets[0]?.id ?? null)
              : current.selectedDocsetId,
        };
      });
    },
    [],
  );

  const stats = useMemo(() => {
    const total = taskItems.length;
    const done = taskItems.filter((item) => item.status === "done").length;
    const running = taskItems.filter(
      (item) => item.status === "running",
    ).length;
    const failed = taskItems.filter((item) => item.status === "failed").length;
    const avgFillRate =
      taskItems.length > 0
        ? Math.round(
            taskItems.reduce((acc, item) => acc + item.fillRate, 0) /
              taskItems.length,
          )
        : 0;
    return { total, done, running, failed, avgFillRate };
  }, [taskItems]);

  const handleTemplateUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setErrorMessage("");
    setInfoMessage("正在上传模板并解析表头...");
    setIsUploadingTemplate(true);

    try {
      const response = await uploadModule3Template(file);
      const record: FusionGridTemplateRecord = {
        id: response.template_id,
        name: file.name,
        backendFilename: response.filename,
        size: formatBytes(file.size),
        uploadTime: nowText(),
        fields: response.fields,
      };

      setGridState((current) => ({
        ...current,
        templates: [
          record,
          ...current.templates.filter((item) => item.id !== record.id),
        ],
        selectedTemplateId: record.id,
      }));
      setInfoMessage(`模板上传成功，已识别 ${response.fields.length} 个字段。`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "模板上传失败");
    } finally {
      setIsUploadingTemplate(false);
    }
  };

  const handleDocsetUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const files: File[] = event.target.files
      ? Array.from(event.target.files)
      : [];
    event.target.value = "";
    if (files.length === 0) return;

    setErrorMessage("");
    setInfoMessage(`正在上传 ${files.length} 个文档...`);
    setIsUploadingDocset(true);

    try {
      const response = await uploadModule3Docset(files);
      const sizeByName = new Map(
        files.map((file) => [file.name, formatBytes(file.size)] as const),
      );
      const record: FusionGridDocsetRecord = {
        id: response.doc_set_id,
        count: response.count,
        uploadTime: nowText(),
        files: response.files.map((file) => ({
          filename: file.filename,
          fileId: file.file_id ?? null,
          size: sizeByName.get(file.filename) ?? "未知大小",
          type: getDocumentType(file.filename) as FusionDocumentType,
        })),
      };

      setGridState((current) => ({
        ...current,
        docsets: [
          record,
          ...current.docsets.filter((item) => item.id !== record.id),
        ],
        selectedDocsetId: record.id,
      }));
      setInfoMessage(`文档集上传成功，当前批次共 ${response.count} 个文件。`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "文档上传失败");
    } finally {
      setIsUploadingDocset(false);
    }
  };

  const handleRequirementsChange = (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const nextValue = event.target.value;
    setGridState((current) => ({ ...current, draftRequirements: nextValue }));
  };

  const handleStartRun = async () => {
    const templateForRun = selectedTemplateRecord ?? templates[0] ?? null;
    const docsetForRun = selectedDocsetRecord ?? docsets[0] ?? null;

    if (!templateForRun) {
      setErrorMessage("请先上传并选择模板。");
      return;
    }
    if (!docsetForRun) {
      setErrorMessage("请先上传并选择文档集。");
      return;
    }

    if (
      selectedTemplateRecord?.id !== templateForRun.id ||
      selectedDocsetRecord?.id !== docsetForRun.id
    ) {
      setGridState((current) => ({
        ...current,
        selectedTemplateId: templateForRun.id,
        selectedDocsetId: docsetForRun.id,
      }));
    }

    setErrorMessage("");
    setInfoMessage("正在启动填充任务...");
    setIsRunning(true);
    const userRequirements = normalizedDraftRequirements;

    try {
      const payload = {
        template_id: templateForRun.id,
        doc_set_id: docsetForRun.id,
        ...(userRequirements ? { prompt: userRequirements } : {}),
      };
      const run = await createModule3Run(payload);

      let status: Module3RunStatusResponse;
      try {
        status = await fetchModule3RunStatus(run.run_id);
      } catch {
        status = {
          run_id: run.run_id,
          status: run.status,
          filled: 0,
          total: templateForRun.fields.length,
          fill_rate: 0,
          output_file_id: null,
          output_name: null,
          error: null,
        };
      }

      const record: FusionGridTaskRecord = {
        id: run.run_id,
        createdAt: nowText(),
        status: normalizeModule3Status(status.status, status.error),
        fillRate: normalizeProgress(status.fill_rate),
        filled: Number.isFinite(status.filled) ? status.filled : 0,
        total: Number.isFinite(status.total)
          ? status.total
          : templateForRun.fields.length,
        templateId: templateForRun.id,
        templateName: templateForRun.name,
        docsetId: docsetForRun.id,
        docsetLabel: `${docsetForRun.count} 个文件`,
        outputFileId: status.output_file_id ?? null,
        outputName: status.output_name ?? null,
        error: status.error ?? null,
      };

      setGridState((current) => ({
        ...current,
        tasks: [
          record,
          ...current.tasks.filter((item) => item.id !== record.id),
        ],
        selectedTaskId: record.id,
      }));

      setInfoMessage(
        record.status === "done"
          ? "任务已完成，可以下载结果文件。"
          : userRequirements
            ? `任务已创建：${record.id}，运行要求已提交。`
            : `任务已创建：${record.id}`,
      );
    } catch (error) {
      const missingResource = parseModule3MissingResource(error);
      if (missingResource?.kind === "template") {
        dropMissingRunDependency("template", missingResource.id);
        setInfoMessage("检测到失效模板缓存，已自动从当前列表中移除。");
        setErrorMessage("当前模板已失效或不属于当前登录账号，请重新上传模板后再试。");
      } else if (missingResource?.kind === "docset") {
        dropMissingRunDependency("docset", missingResource.id);
        setInfoMessage("检测到失效文档集缓存，已自动从当前列表中移除。");
        setErrorMessage("当前文档集已失效或不属于当前登录账号，请重新上传文档后再试。");
      } else {
        setErrorMessage(error instanceof Error ? error.message : "启动任务失败");
      }
    } finally {
      setIsRunning(false);
    }
  };

  const handleRefreshAll = async () => {
    if (tasks.length === 0) {
      setInfoMessage("当前还没有任务记录。");
      return;
    }

    setErrorMessage("");
    setInfoMessage("正在刷新任务状态...");
    setIsRefreshing(true);

    try {
      const results = await Promise.all(
        tasks.map(async (task) => {
          const status = await fetchModule3RunStatus(task.id);
          return { taskId: task.id, status };
        }),
      );
      const statusMap = new Map<string, Module3RunStatusResponse>(
        results.map(
          (item) =>
            [item.taskId, item.status] as [string, Module3RunStatusResponse],
        ),
      );

      setGridState((current) => ({
        ...current,
        tasks: current.tasks.map((task) => {
          const status = statusMap.get(task.id);
          return status ? updateTaskFromStatus(task, status) : task;
        }),
      }));
      setInfoMessage("任务状态已刷新。");
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "刷新任务状态失败",
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleDownloadSelected = () => {
    if (!selectedTaskRecord || selectedTaskRecord.status !== "done") {
      setErrorMessage("请选择一个已完成的任务后再下载结果。");
      return;
    }
    window.location.assign(module3RunDownloadUrl(selectedTaskRecord.id));
  };

  const handleClearTaskHistory = () => {
    setGridState((current) => ({
      ...current,
      tasks: [],
      selectedTaskId: null,
    }));
    setInfoMessage("已清空当前页面缓存的任务记录。");
  };

  const [isHelpModalOpen, setIsHelpModalOpen] = useState(false);

  const handleHelp = () => {
    setIsHelpModalOpen(true);
  };

  const handleRemoveTemplate = (templateId: string) => {
    setGridState((current) => ({
      ...current,
      templates: current.templates.filter((item) => item.id !== templateId),
      selectedTemplateId:
        current.selectedTemplateId === templateId
          ? null
          : current.selectedTemplateId,
    }));
    setInfoMessage("模板已从当前页面缓存中移除，后端文件不会删除。");
  };

  const handleRemoveDocument = (docsetId: string, documentId: string) => {
    setGridState((current) => ({
      ...current,
      docsets: current.docsets.map((docset) => {
        if (docset.id === docsetId) {
          return {
            ...docset,
            files: docset.files.filter((file, index) => {
              const fileCompositeId = `${docsetId}:${file.fileId || `${file.filename}:${index}`}`;
              return fileCompositeId !== documentId;
            }),
          };
        }
        return docset;
      }),
    }));
    setInfoMessage("文档已从当前页面缓存中移除。");
  };

  const handleRemoveTask = (taskId: string) => {
    setGridState((current) => ({
      ...current,
      tasks: current.tasks.filter((item) => item.id !== taskId),
      selectedTaskId:
        current.selectedTaskId === taskId ? null : current.selectedTaskId,
    }));
    setInfoMessage("任务记录已从当前页面缓存中移除。");
  };

  const handleCancelTask = async (task: TaskItem) => {
    if (task.status !== "running") return;

    setErrorMessage("");
    setInfoMessage(`正在请求取消任务 ${task.id}...`);
    setCancellingTaskIds((current) =>
      current.includes(task.id) ? current : [...current, task.id],
    );

    try {
      const response = await cancelModule3Run(task.id);
      if (!response.cancel_requested) {
        setInfoMessage("当前任务未处于可取消状态。");
        setCancellingTaskIds((current) =>
          current.filter((item) => item !== task.id),
        );
        return;
      }

      setInfoMessage(`已提交取消请求：${task.id}，等待后端停止任务。`);

      try {
        const status = await fetchModule3RunStatus(task.id);
        setGridState((current) => ({
          ...current,
          tasks: current.tasks.map((item) =>
            item.id === task.id ? updateTaskFromStatus(item, status) : item,
          ),
        }));
      } catch {
        // Keep the existing polling loop to pick up the final status.
      }
    } catch (error) {
      setCancellingTaskIds((current) =>
        current.filter((item) => item !== task.id),
      );
      setErrorMessage(error instanceof Error ? error.message : "取消任务失败");
    }
  };

  const loadTextPreview = async (fileId: string, fallbackContent: string) => {
    const content = await fetchModule3DocumentPreviewText(fileId);
    setPreviewSheets(null);
    setPreviewContent(content || fallbackContent);
  };

  const loadPreviewContent = async ({
    runId,
    fileId,
    type,
    fallbackContent,
  }: {
    runId: string;
    fileId: string;
    type: DocumentType;
    fallbackContent: string;
  }) => {
    if (type === "xlsx") {
      try {
        const workbookPreview = await parseModule3ExcelJson(runId);
        const structuredSheets = workbookSheetsToPreviewSheets(
          workbookPreview.sheets || [],
        );
        if (structuredSheets.length > 0) {
          setPreviewSheets(structuredSheets);
          setPreviewContent("");
          return;
        }
      } catch {
        // Fallback to text preview when parse-json is unavailable.
      }
    }

    if (type === "docx") {
      setPreviewSheets(null);
      setPreviewContent("");
      return;
    }
    await loadTextPreview(fileId, fallbackContent);
  };

  const handlePreviewTaskOutput = async (task: TaskItem) => {
    if (showTaskDrawer) {
      setIsTaskDrawerOpen(false);
    }
    if (previewDocument?.id === task.id) {
      setPreviewDocument(null);
      setPreviewContent("");
      setPreviewSheets(null);
      return;
    }

    let outputFileId = task.outputFileId ?? null;
    let outputNameFromStatus = task.outputName ?? null;

    if (!outputFileId) {
      try {
        const latestStatus = await fetchModule3RunStatus(task.id);
        outputFileId = latestStatus.output_file_id ?? null;
        outputNameFromStatus = latestStatus.output_name ?? outputNameFromStatus;
        setGridState((current) => ({
          ...current,
          tasks: current.tasks.map((item) =>
            item.id === task.id ? updateTaskFromStatus(item, latestStatus) : item,
          ),
        }));
      } catch {
        // Keep local values and show explicit error below if file_id remains missing.
      }
    }

    if (!outputFileId) {
      setErrorMessage("该任务暂无可预览输出（缺少 file_id，请先刷新任务）");
      return;
    }

    const outputName =
      String(outputNameFromStatus || "").trim() ||
      getTaskOutputName(task);
    const outputType = getDocumentType(outputName);
    setPreviewDocument({
      id: task.id,
      name: outputName,
      type: outputType,
      size: "未知",
      uploadTime: task.createdAt,
      fileId: outputFileId,
      docsetId: task.docsetId,
    });
    setIsPreviewLoading(true);
    setPreviewContent("");
    setPreviewSheets(null);

    const fallbackContent =
      `file_id: ${outputFileId}\n文件名: ${outputName}\n\n` +
      "（预览功能需要后端支持文件内容读取接口）";

    try {
      await loadPreviewContent({
        runId: task.id,
        fileId: outputFileId,
        type: outputType,
        fallbackContent,
      });
    } catch {
      setPreviewSheets(null);
      setPreviewContent(fallbackContent);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const fusionDropdownPanelClass = cn(
    "flex flex-col gap-2 max-h-[400px] overflow-y-auto scrollbar-thin scrollbar-thumb-slate-200 dark:scrollbar-thumb-white/10",
    useUltraDenseTopBar
      ? "w-[min(300px,calc(100vw-24px))] p-2.5"
      : useDenseTopBar
        ? "w-[min(320px,calc(100vw-28px))] p-3"
        : "w-[340px] p-3",
  );
  const fusionUploadCardClass = cn(
    "group w-full rounded-[16px] border border-dashed border-slate-300 text-center transition-all dark:border-white/[0.1] dark:bg-white/[0.02] dark:hover:border-blue-500 dark:hover:bg-blue-500/10",
    useUltraDenseTopBar
      ? "px-3 py-5"
      : "py-6 px-4",
  );
  const fusionCompactRecordClass = cn(
    "flex items-center justify-between gap-1 rounded-[12px] border border-slate-200 text-[11px] text-slate-600 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-300 shadow-sm bg-white dark:bg-[#0B1120] shrink-0",
    useUltraDenseTopBar ? "px-2 py-1.5" : "px-2.5 py-2",
  );

  // 模板上传下拉内容
  const templateDropdownContent = (
    <div className={fusionDropdownPanelClass}>
      {templateItems.length === 0 ? (
        <button
          type="button"
          onClick={() => templateInputRef.current?.click()}
          className={cn(
            fusionUploadCardClass,
            "hover:border-blue-500 hover:bg-blue-50/30",
          )}
        >
          <div className={cn(
            "mx-auto mb-3 flex items-center justify-center rounded-full bg-white shadow-sm border border-slate-200/50 transition-colors group-hover:border-blue-200 dark:bg-white/[0.04] dark:border-white/[0.05] dark:group-hover:border-blue-500/30",
            useUltraDenseTopBar ? "h-9 w-9" : "h-10 w-10",
          )}>
            {isUploadingTemplate ? (
              <Loader2
                size={useUltraDenseTopBar ? 20 : 22}
                className="animate-spin text-slate-400 transition-colors group-hover:text-blue-500 dark:text-slate-500 dark:group-hover:text-blue-400"
              />
            ) : (
              <UploadCloud
                size={useUltraDenseTopBar ? 20 : 22}
                className="text-slate-400 transition-colors group-hover:text-blue-500 dark:text-slate-500 dark:group-hover:text-blue-400"
              />
            )}
          </div>
          <p className={cn(
            "font-medium text-slate-700 transition-colors group-hover:text-blue-600 dark:text-slate-300 dark:group-hover:text-blue-400 mb-1",
            useUltraDenseTopBar ? "text-[12px]" : "text-[13px]",
          )}>
            {isUploadingTemplate ? "上传中..." : "点击或拖拽上传模板"}
          </p>
          <p className={cn("text-slate-400", useUltraDenseTopBar ? "text-[10px]" : "text-[11px]")}>支持 XLSX, DOCX</p>
        </button>
      ) : (
        <div className={fusionCompactRecordClass}>
          <div className="flex min-w-0 items-center gap-1.5">
            <FileSpreadsheet size={14} className="shrink-0 text-blue-500" />
            <span className="truncate font-medium">模板文件</span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                templateInputRef.current?.click();
              }}
              className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700/50 rounded-[6px] text-blue-500 hover:text-blue-600 transition-colors flex items-center gap-1 bg-blue-50 dark:bg-blue-500/10"
              title="上传新模板"
            >
              <UploadCloud size={12} />
              <span className="text-[10px] font-medium pr-0.5">重传</span>
            </button>
          </div>
        </div>
      )}

      {/* 模板列表 */}
      {templateItems.length > 0 && (
        <div className="flex flex-col gap-1 min-h-0 bg-slate-50/30 dark:bg-white/[0.01] rounded-[16px] p-1.5 border border-transparent dark:border-white/[0.02]">
          {templateItems.map((tpl) => (
            <UnifiedFileListItem
              key={tpl.id}
              file={tpl}
              icon={
                tpl.name.toLowerCase().endsWith(".docx") || tpl.name.toLowerCase().endsWith(".doc") ? (
                  <img src={wordIconUrl} alt="Word" className="w-6 h-6 object-contain" />
                ) : (
                  <img src={excelIconUrl} alt="Excel" className="w-6 h-6 object-contain" />
                )
              }
              isSelected={selectedTemplateId === tpl.id}
              onClick={() => setGridState((current) => ({ ...current, selectedTemplateId: tpl.id }))}
              onRemove={() => handleRemoveTemplate(tpl.id)}
            >
              {selectedTemplateRecord && selectedTemplateRecord.id === tpl.id && (
                <div className="mt-1 pt-2 border-t border-slate-100 dark:border-white/[0.05]">
                  <div className="flex flex-wrap gap-1.5">
                    {selectedTemplateRecord.fields.map((field, idx) => (
                      <span
                        key={`${field.key}-${idx}`}
                        className="inline-flex items-center rounded-[6px] bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:bg-blue-500/10 dark:text-blue-400"
                      >
                        {field.header}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </UnifiedFileListItem>
          ))}
        </div>
      )}
    </div>
  );

  // 文档集管理下拉内容
  const [isDraggingDocset, setIsDraggingDocset] = useState(false);

  const handleDocsetDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingDocset(true);
  };

  const handleDocsetDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingDocset(false);
  };

  const handleDocsetDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingDocset(false);
    const files: File[] = Array.from(e.dataTransfer.files);
    if (files.length > 0 && docsetInputRef.current) {
      const dataTransfer = new DataTransfer();
      files.forEach((file) => {
        dataTransfer.items.add(file);
      });
      docsetInputRef.current.files = dataTransfer.files;
      docsetInputRef.current.dispatchEvent(
        new Event("change", { bubbles: true }),
      );
    }
  };

  const docsetDropdownContent = (
    <div className={fusionDropdownPanelClass}>
      {documentItems.length === 0 ? (
        <div
          onClick={() => docsetInputRef.current?.click()}
          onDragOver={handleDocsetDragOver}
          onDragLeave={handleDocsetDragLeave}
          onDrop={handleDocsetDrop}
          className={cn(
            fusionUploadCardClass,
            "cursor-pointer",
            isDraggingDocset
              ? "border-blue-500 bg-blue-50/50 dark:border-blue-400 dark:bg-blue-500/10"
              : "border-slate-300 hover:border-blue-500 hover:bg-blue-50/30 dark:border-white/[0.1] dark:bg-white/[0.02] dark:hover:border-blue-500 dark:hover:bg-blue-500/10"
          )}
        >
          <div
            className={cn(
              "mx-auto mb-3 flex items-center justify-center rounded-full bg-white shadow-sm border border-slate-200/50 transition-colors dark:bg-white/[0.04] dark:border-white/[0.05]",
              useUltraDenseTopBar ? "h-9 w-9" : "h-10 w-10",
              isDraggingDocset
                ? "border-blue-200 dark:border-blue-500/30"
                : "group-hover:border-blue-200 dark:group-hover:border-blue-500/30"
            )}
          >
            {isUploadingDocset ? (
              <Loader2
                size={useUltraDenseTopBar ? 20 : 22}
                className={cn(
                  "animate-spin transition-colors",
                  isDraggingDocset
                    ? "text-blue-500 dark:text-blue-400"
                    : "text-slate-400 group-hover:text-blue-500 dark:text-slate-500 dark:group-hover:text-blue-400"
                )}
              />
            ) : (
              <UploadCloud
                size={useUltraDenseTopBar ? 20 : 22}
                className={cn(
                  "transition-colors",
                  isDraggingDocset
                    ? "text-blue-500 dark:text-blue-400"
                    : "text-slate-400 group-hover:text-blue-500 dark:text-slate-500 dark:group-hover:text-blue-400"
                )}
              />
            )}
          </div>
          <p
            className={cn(
              "font-medium transition-colors mb-1",
              useUltraDenseTopBar ? "text-[12px]" : "text-[13px]",
              isDraggingDocset
                ? "text-blue-600 dark:text-blue-400"
                : "text-slate-700 group-hover:text-blue-600 dark:text-slate-300 dark:group-hover:text-blue-400"
            )}
          >
            {isUploadingDocset
              ? "上传中..."
              : isDraggingDocset
                ? "松开以上传"
                : "点击或拖入上传文档"}
          </p>
          <p className={cn("text-slate-400", useUltraDenseTopBar ? "text-[10px]" : "text-[11px]")}>支持 DOCX, XLSX, TXT, MD</p>
          <p className={cn("text-slate-400/80 mt-0.5", useUltraDenseTopBar ? "text-[9px]" : "text-[10px]")}>每次最多 5 个文件</p>
        </div>
      ) : null}

      {/* 当有文档时，显示紧凑的头部控制区 */}
      {documentItems.length > 0 && (
        <div className={fusionCompactRecordClass}>
          <div className="flex min-w-0 items-center gap-1.5">
            <FolderOpen size={14} className="shrink-0 text-blue-500" />
            <span className="truncate font-medium">
              {selectedDocsetRecord
                ? `文档集${docsets.length - docsets.findIndex((d) => d.id === selectedDocsetRecord.id)}(${selectedDocsetRecord.count}个)`
                : "未上传"}
            </span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {docsets.length > 1 ? (
              <div className="relative shrink-0">
                <select
                  value={selectedDocsetId ?? ""}
                  onChange={(event) =>
                    setGridState((current) => ({
                      ...current,
                      selectedDocsetId: event.target.value || null,
                    }))
                  }
                  className="appearance-none rounded-[6px] border border-slate-200 bg-slate-50 px-2 py-0.5 pr-5 text-[10px] font-medium text-slate-700 dark:border-white/[0.1] dark:bg-white/[0.05] dark:text-slate-200 transition-colors hover:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                >
                  {docsets.map((docset, index) => (
                    <option key={docset.id} value={docset.id}>
                      文档集{docsets.length - index}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  size={10}
                  className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 text-slate-400"
                />
              </div>
            ) : null}
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                docsetInputRef.current?.click();
              }}
              className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700/50 rounded-[6px] text-blue-500 hover:text-blue-600 transition-colors flex items-center gap-1 bg-blue-50 dark:bg-blue-500/10"
              title="追加文档"
            >
              <UploadCloud size={12} />
              <span className="text-[10px] font-medium pr-0.5">追加</span>
            </button>
          </div>
        </div>
      )}

      {documentItems.length > 0 && (
        <div className="flex flex-col gap-1 min-h-0 bg-slate-50/30 dark:bg-white/[0.01] rounded-[16px] p-1.5 border border-transparent dark:border-white/[0.02]">
          {documentItems.map((doc) => (
            <UnifiedFileListItem
              key={doc.id}
              file={doc}
              icon={getFileIcon(doc.type)}
              isSelected={selectedDocument === doc.id}
              onClick={() => setSelectedDocument(doc.id)}
              onRemove={() => {
                if (selectedDocsetId) {
                  handleRemoveDocument(selectedDocsetId, doc.id);
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );

  const prepareDropdownContent = (
    <div
      className={cn(
        "flex max-h-[420px] flex-col gap-3 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-200 dark:scrollbar-thumb-white/10",
        useUltraDenseTopBar
          ? "w-[min(320px,calc(100vw-24px))] p-2.5"
          : useDenseTopBar
            ? "w-[min(360px,calc(100vw-32px))] p-3"
            : "w-[380px] p-3",
      )}
    >
      <div className="rounded-[16px] border border-slate-200/70 bg-white/90 p-3 shadow-sm dark:border-white/[0.08] dark:bg-white/[0.03]">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <TemplateUploadIcon size={14} className="shrink-0 text-blue-500" />
            <span className="truncate text-[12px] font-semibold text-slate-800 dark:text-slate-200">模板上传</span>
          </div>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              templateInputRef.current?.click();
            }}
            className="inline-flex items-center gap-1 rounded-[6px] bg-blue-50 px-2 py-1 text-[10px] font-medium text-blue-600 transition-colors hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20"
            title="上传模板"
          >
            <UploadCloud size={11} />
            <span>{templateItems.length > 0 ? '重传' : '上传'}</span>
          </button>
        </div>
        {templateItems.length === 0 ? (
          <div className="rounded-[12px] border border-dashed border-slate-300 px-3 py-4 text-center text-[11px] text-slate-500 dark:border-white/[0.12] dark:text-slate-400">
            还没有模板，点击右上角上传 XLSX / DOCX 模板。
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {templateItems.map((tpl) => (
              <UnifiedFileListItem
                key={tpl.id}
                file={tpl}
                icon={
                  tpl.name.toLowerCase().endsWith(".docx") || tpl.name.toLowerCase().endsWith(".doc") ? (
                    <img src={wordIconUrl} alt="Word" className="w-6 h-6 object-contain" />
                  ) : (
                    <img src={excelIconUrl} alt="Excel" className="w-6 h-6 object-contain" />
                  )
                }
                isSelected={selectedTemplateId === tpl.id}
                onClick={() => setGridState((current) => ({ ...current, selectedTemplateId: tpl.id }))}
                onRemove={() => handleRemoveTemplate(tpl.id)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="rounded-[16px] border border-slate-200/70 bg-white/90 p-3 shadow-sm dark:border-white/[0.08] dark:bg-white/[0.03]">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <FolderOpen size={14} className="shrink-0 text-blue-500" />
            <span className="truncate text-[12px] font-semibold text-slate-800 dark:text-slate-200">文档集管理</span>
          </div>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              docsetInputRef.current?.click();
            }}
            className="inline-flex items-center gap-1 rounded-[6px] bg-blue-50 px-2 py-1 text-[10px] font-medium text-blue-600 transition-colors hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20"
            title="上传文档"
          >
            <UploadCloud size={11} />
            <span>{documentItems.length > 0 ? '追加' : '上传'}</span>
          </button>
        </div>
        {documentItems.length === 0 ? (
          <div className="rounded-[12px] border border-dashed border-slate-300 px-3 py-4 text-center text-[11px] text-slate-500 dark:border-white/[0.12] dark:text-slate-400">
            还没有文档集，点击右上角上传 DOCX / XLSX / TXT / MD 文件。
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {documentItems.map((doc) => (
              <UnifiedFileListItem
                key={doc.id}
                file={doc}
                icon={getFileIcon(doc.type)}
                isSelected={selectedDocument === doc.id}
                onClick={() => setSelectedDocument(doc.id)}
                onRemove={() => {
                  if (selectedDocsetId) {
                    handleRemoveDocument(selectedDocsetId, doc.id);
                  }
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );

  const segmentedOptions: SegmentedOption[] = [
    ...(useDenseTopBar
      ? [{
          icon: FolderOpen,
          label: "准备区",
          compactLabel: "准备区",
          onClick: () => templateInputRef.current?.click(),
          dropdownContent: prepareDropdownContent,
          dropdownAlign: "right" as const,
        }]
      : [
          {
            icon: TemplateUploadIcon,
            label: "模板上传",
            compactLabel: "模板",
            onClick: () => templateInputRef.current?.click(),
            dropdownContent: templateDropdownContent,
            dropdownAlign: "right" as const,
          },
          {
            icon: FolderOpen,
            label: "文档集管理",
            compactLabel: "文档",
            onClick: () => docsetInputRef.current?.click(),
            dropdownContent: docsetDropdownContent,
            dropdownAlign: "right" as const,
          },
        ]),
    {
      icon: Download,
      label: "下载结果",
      compactLabel: "下载",
      onClick: handleDownloadSelected,
      disabled: !selectedTaskRecord || selectedTaskRecord.status !== "done",
    },
    {
      icon: Trash2,
      label: "清空任务",
      compactLabel: "清空",
      onClick: handleClearTaskHistory,
      disabled: tasks.length === 0,
    },
    {
      icon: RefreshCw,
      label: "刷新任务",
      compactLabel: "刷新",
      onClick: handleRefreshAll,
      disabled: isRefreshing || tasks.length === 0,
    },
    {
      icon: HelpCircle,
      label: "使用说明",
      compactLabel: "说明",
      onClick: handleHelp,
    },
  ];

  return (
    <div className="h-screen w-full max-w-full min-w-0 flex flex-col overflow-x-hidden overflow-y-hidden bg-white dark:bg-[#0B1120]">
      {/* 帮助说明模态框 */}
      {isHelpModalOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div className="fixed inset-0 z-[99999] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="relative w-full max-w-lg rounded-2xl bg-white shadow-[0_12px_40px_rgba(0,0,0,0.12)] dark:bg-[#0B1120] border border-slate-200/60 dark:border-white/[0.1] dark:shadow-[0_12px_40px_rgba(0,0,0,0.4)] flex flex-col overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-white/[0.05] px-6 py-4 bg-transparent">
                <h3 className="font-medium text-slate-800 dark:text-slate-200 flex items-center gap-2 text-[14px]">
                  <HelpCircle size={16} className="text-slate-500" />
                  自定义智能填表 - 使用说明
                </h3>
                <button
                  onClick={() => setIsHelpModalOpen(false)}
                  className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-white/[0.05] dark:hover:text-slate-300 transition-colors"
                >
                  <X size={16} />
                </button>
              </div>
              <div className="px-6 py-6 overflow-y-auto">
                <ol className="space-y-5 text-[14px] leading-relaxed text-slate-600 dark:text-slate-300">
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full border border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 font-bold text-xs shadow-sm">
                      1
                    </span>
                    <div>
                      <strong className="text-slate-900 dark:text-white">
                        模板上传：
                      </strong>
                      点击顶部“模板上传”，选择 XLSX 或 DOCX
                      模板，系统将自动解析字段。
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full border border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 font-bold text-xs shadow-sm">
                      2
                    </span>
                    <div>
                      <strong className="text-slate-900 dark:text-white">
                        文档集管理：
                      </strong>
                      点击“文档集管理”，上传资料文档（支持
                      DOCX/XLSX/TXT/MD），可选择当前文档集。
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full border border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 font-bold text-xs shadow-sm">
                      3
                    </span>
                    <div>
                      <strong className="text-slate-900 dark:text-white">
                        用户要求：
                      </strong>
                      在右侧“用户要求”框中填写本次数据回填的具体提示或要求（可选）。
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full border border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 font-bold text-xs shadow-sm">
                      4
                    </span>
                    <div>
                      <strong className="text-slate-900 dark:text-white">
                        运行任务：
                      </strong>
                      点击“开始填充”，系统开始工作返回填充好的文件。
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full border border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 font-bold text-xs shadow-sm">
                      5
                    </span>
                    <div>
                      <strong className="text-slate-900 dark:text-white">
                        预览结果：
                      </strong>
                      右侧“文件预览”展示结果，可滚动查看表格或在线编辑文本。
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full border border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 font-bold text-xs shadow-sm">
                      6
                    </span>
                    <div>
                      <strong className="text-slate-900 dark:text-white">
                        下载与管理：
                      </strong>
                      顶部可导出结果、刷新或清空任务记录。
                    </div>
                  </li>
                </ol>
              </div>
              <div className="border-t border-slate-200 dark:border-white/[0.05] px-6 py-4 bg-slate-50/50 dark:bg-[#0B1120] flex justify-end">
                  <button
                    onClick={() => setIsHelpModalOpen(false)}
                    className="px-5 py-2 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-700 hover:to-blue-600 text-white text-[13px] font-medium rounded-lg shadow-sm hover:shadow transition-all"
                  >
                    我知道了
                  </button>
                </div>
            </div>
          </div>,
          document.body,
        )}

      <input
        ref={templateInputRef}
        type="file"
        accept=".xlsx,.docx"
        className="hidden"
        onChange={handleTemplateUpload}
      />
      <input
        ref={docsetInputRef}
        type="file"
        multiple
        accept=".xlsx,.docx,.txt,.md"
        className="hidden"
        onChange={handleDocsetUpload}
      />

      <motion.section
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className={cn(
          "relative z-10 shrink-0 bg-[#fbfcfd]/90 backdrop-blur-xl border-b border-slate-200/40 shadow-[0_2px_12px_rgba(0,0,0,0.03)] dark:bg-slate-950/95 dark:border-white/5 dark:shadow-[0_4px_16px_rgba(0,0,0,0.4)]",
          useUltraDenseTopBar
            ? "pl-3 pr-0 py-1.5"
            : useDenseTopBar
              ? "pl-4 pr-0 py-2"
              : "pl-4 pr-0 py-2.5",
        )}
      >
        <div
          className={cn(
            "flex flex-wrap items-center justify-between gap-x-4 gap-y-2",
            useUltraDenseTopBar ? "gap-x-2.5 gap-y-1" : useDenseTopBar && "gap-x-3 gap-y-1.5",
          )}
        >
          <div className={cn("flex-1", useUltraDenseTopBar ? "min-w-[150px]" : "min-w-[210px]")}>
            <div className={cn("flex shrink-0 items-center translate-y-[2px]", useUltraDenseTopBar ? "-ml-2.5" : "-ml-5")}>
              <img 
                  src={fusionLogoUrl} 
                  alt="Fusion" 
                  className={cn(
                    "w-auto origin-left scale-[3.0] translate-y-1 object-contain transition-all duration-300",
                    useUltraDenseTopBar ? "h-[24px] mr-[72px]" : useDenseTopBar ? "h-[28px] mr-[96px]" : "h-[32px] mr-[110px]",
                  )}
              />
              <h1 className={cn(
                "flex shrink-0 items-center space-x-[1px] font-['Microsoft_YaHei'] font-bold tracking-widest translate-y-[2px] whitespace-nowrap",
                useUltraDenseTopBar ? "text-[15px] -ml-0.5" : useDenseTopBar ? "text-[18px] -ml-0.5" : "text-[20px] -ml-0.5",
              )}>
                <span className="text-[#334155] dark:text-slate-200">自定义</span>
                <span className="text-[#3b82f6] dark:text-blue-400">智能填表</span>
              </h1>
            </div>
          </div>
          <div className={cn(
            "flex min-w-0 items-center justify-end overflow-hidden",
            useUltraDenseTopBar ? "gap-1 pr-3" : "gap-1.5 pr-4 sm:pr-5 lg:pr-6",
          )}>
            {shouldUseTaskDrawer && (
              <button
                type="button"
                onClick={toggleTaskDrawer}
                className={cn(
                  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border font-medium transition-colors duration-200",
                  useUltraDenseTopBar ? "h-[24px] px-2 text-[11px]" : "h-[26px] px-2.5 text-[12px]",
                  showTaskDrawer
                    ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300"
                    : "border-slate-200/70 bg-white/90 text-slate-600 hover:bg-slate-100/80 hover:text-slate-900 dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-slate-300 dark:hover:bg-white/[0.06] dark:hover:text-white",
                )}
                title={showTaskDrawer ? "收起任务记录" : "打开任务记录"}
                aria-label={showTaskDrawer ? "收起任务记录" : "打开任务记录"}
              >
                <HistoryIcon size={useUltraDenseTopBar ? 12 : 14} />
                <span className={cn(useUltraDenseTopBar ? "hidden md:inline" : "hidden sm:inline")}>
                  {useUltraDenseTopBar ? "任务" : "任务记录"}
                </span>
              </button>
            )}
            <SegmentedControl
              options={segmentedOptions}
              denseMode={useDenseTopBar}
              ultraDenseMode={useUltraDenseTopBar}
            />
          </div>
        </div>
      </motion.section>

      {errorMessage ? (
        <div className="shrink-0 border-b border-red-200 bg-red-50 px-6 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300">
          <div className="flex items-start gap-3">
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        </div>
      ) : null}

      <div
        ref={splitLayoutRef}
        className="relative grid w-full max-w-full flex-1 min-h-0 min-w-0 overflow-x-hidden overflow-y-hidden bg-white dark:bg-[#0B1120]"
        style={{ gridTemplateColumns: showDockedTaskPanel ? `${leftPanelWidth}% minmax(0, 1fr)` : `minmax(0, 1fr)` }}
      >
        {showTaskDrawer && (
          <button
            type="button"
            onClick={closeTaskDrawer}
            className="absolute inset-0 z-30 bg-slate-950/16 backdrop-blur-[2px]"
            aria-label="关闭任务记录抽屉"
          />
        )}
        {/* 左侧：任务记录 */}
        {(showDockedTaskPanel || showTaskDrawer) && (
        <div
          className={cn(
            "box-border flex flex-col min-h-0 min-w-0 bg-white dark:bg-[#0B1120]",
            showTaskDrawer
              ? "absolute inset-y-3 left-3 z-40 h-auto w-[min(360px,calc(100%-24px))] overflow-hidden rounded-[24px] border border-slate-200/70 shadow-[0_24px_60px_-28px_rgba(15,23,42,0.32)] dark:border-white/[0.08] dark:shadow-[0_28px_72px_-34px_rgba(2,6,23,0.9)]"
              : "relative h-full border-r border-slate-200 dark:border-white/[0.05]",
          )}
        >
          {/* 拖拽手柄 */}
          {showDockedTaskPanel && (
            <div
              className="absolute -right-1 top-0 bottom-0 w-2 cursor-ew-resize z-10 group"
              onMouseDown={(e) => {
                e.preventDefault();
                isResizingRef.current = true;

                // 计算当前鼠标位置与侧边栏实际像素宽度的差值作为 offset
                // 左侧面板的实际宽度 = 分栏容器宽度 * (leftPanelWidth / 100)
                const currentPixelWidth =
                  getSplitLayoutWidth() * (leftPanelWidth / 100);
                dragOffsetRef.current = e.clientX - currentPixelWidth;

                document.body.style.cursor = "ew-resize";
                document.body.style.userSelect = "none"; // Prevent text selection while dragging
              }}
            >
              {/* 仅高亮的分割线 */}
              <div className="absolute right-[3px] top-0 bottom-0 w-[1px] bg-transparent group-hover:bg-blue-400 dark:group-hover:bg-blue-500 transition-colors" />
            </div>
          )}
          <div className="flex flex-col h-full min-h-0 w-full">
            {/* 任务记录 */}
            <div className="flex flex-col flex-1 min-h-0 bg-transparent w-full">
              <div className="flex items-center justify-between shrink-0 px-4 py-2 border-b border-slate-200 dark:border-white/[0.05] z-10 w-full bg-slate-50/30 dark:bg-[#0B1120]">
                <h3 className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5 text-[12px] uppercase tracking-wider">
                  <HistoryIcon size={14} className="text-blue-500" />
                  任务记录
                </h3>
                {showTaskDrawer && (
                  <button
                    type="button"
                    onClick={closeTaskDrawer}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-white/[0.08] dark:hover:text-slate-200"
                    title="关闭任务记录"
                    aria-label="关闭任务记录"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
              <div className="flex flex-col flex-1 min-h-0">
                <div className="px-4 py-3 shrink-0 border-b border-slate-200 dark:border-white/[0.05]">
                  <div className="grid grid-cols-2 gap-1.5 p-1 bg-slate-100 dark:bg-white/[0.04] rounded-lg">
                    <div className="rounded-md bg-white shadow-sm dark:bg-white/[0.06] p-1.5 text-center flex items-baseline justify-center gap-1 transition-all">
                      <div className="text-[13px] font-bold text-slate-700 dark:text-slate-200">
                        {stats.total}
                      </div>
                      <div className="text-[10px] font-medium text-slate-500 dark:text-slate-400">
                        总任务
                      </div>
                    </div>
                    <div className="rounded-md hover:bg-white/50 dark:hover:bg-white/[0.02] p-1.5 text-center flex items-baseline justify-center gap-1 transition-all cursor-pointer">
                      <div className="text-[13px] font-bold text-blue-600 dark:text-blue-400">
                        {stats.done}
                      </div>
                      <div className="text-[10px] font-medium text-blue-600/80 dark:text-blue-400/80">
                        已完成
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex-1 overflow-auto scrollbar-thin scrollbar-thumb-slate-200 dark:scrollbar-thumb-white/10">
                  {taskItems.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-48 bg-transparent">
                      <div className="flex items-center justify-center w-14 h-14 rounded-full bg-slate-50 dark:bg-white/[0.02] mb-3 border border-slate-100 dark:border-white/[0.05]">
                        <HistoryIcon size={24} className="text-slate-300 dark:text-slate-600" />
                      </div>
                      <span className="text-[13px] font-medium text-slate-500 dark:text-slate-400">
                        暂无任务记录
                      </span>
                    </div>
                  ) : (
                    taskItems.map((task) => (
                      <div
                        key={task.id}
                        className={cn(
                          "group p-4 transition-all duration-200 cursor-pointer border-b border-slate-200 dark:border-white/[0.05] last:border-b-0",
                          selectedTaskId === task.id
                            ? "bg-blue-50/50 dark:bg-blue-500/10"
                            : "bg-white hover:bg-slate-50 dark:bg-[#0B1120] dark:hover:bg-white/[0.02]",
                        )}
                        onClick={() => handleSelectTask(task.id)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          {/* 左侧：文件大图标 */}
                          <div className="flex-shrink-0 mt-0.5">
                            {getDocumentType(getTaskOutputName(task)) === "docx" ? (
                              <img
                                src={wordIconUrl}
                                alt="Word"
                                className="w-5 h-5 object-contain"
                              />
                            ) : (
                              <img
                                src={excelIconUrl}
                                alt="Excel"
                                className="w-5 h-5 object-contain"
                              />
                            )}
                          </div>

                          {/* 中间：标题与状态 */}
                          <div className="flex-1 min-w-0 flex flex-col justify-center">
                            <span className="truncate font-semibold text-slate-800 dark:text-slate-100 text-sm mb-1.5">
                              {getTaskOutputName(task)}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <span
                                className={cn(
                                  "w-2 h-2 rounded-full",
                                  getTaskStatusDot(task.status),
                                )}
                              />
                              <span
                                className={cn(
                                  "text-[11px] font-medium",
                                  task.status === "done"
                                    ? "text-emerald-600 dark:text-emerald-400"
                                    : task.status === "running"
                                      ? "text-blue-600 dark:text-blue-400"
                                      : task.status === "failed"
                                        ? "text-red-600 dark:text-red-400"
                                        : "text-slate-500 dark:text-slate-400",
                                )}
                              >
                                {getStatusText(task.status)}
                              </span>
                            </div>
                          </div>

                          {/* 右侧：操作按钮及时间 */}
                          <div className="flex shrink-0 items-start">
                            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                              {task.status === "running" ? (
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    void handleCancelTask(task);
                                  }}
                                  disabled={cancellingTaskIds.includes(task.id)}
                                  className={cn(
                                      "p-1.5 rounded-md transition-colors",
                                      cancellingTaskIds.includes(task.id)
                                        ? "cursor-not-allowed text-amber-500"
                                        : "text-slate-400 hover:bg-amber-100 hover:text-amber-600 dark:hover:bg-amber-500/20",
                                    )}
                                  title="取消任务"
                                >
                                  {cancellingTaskIds.includes(task.id) ? (
                                    <Loader2
                                      size={14}
                                      className="animate-spin"
                                    />
                                  ) : (
                                    <X size={14} />
                                  )}
                                </button>
                              ) : null}
                              {task.status === "done" ? (
                                <>
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      handlePreviewTaskOutput(task);
                                    }}
                                    className={cn(
                                        "p-1.5 rounded-md transition-colors",
                                        previewDocument?.id === task.id
                                          ? "bg-blue-100 text-blue-600 dark:bg-blue-500/30 dark:text-blue-400"
                                          : "text-slate-400 hover:bg-blue-100 hover:text-blue-600 dark:hover:bg-blue-500/20",
                                      )}
                                    title="预览"
                                  >
                                    <Eye size={14} />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      window.location.assign(
                                        module3RunDownloadUrl(task.id),
                                      );
                                    }}
                                    className="p-1.5 hover:bg-emerald-100 dark:hover:bg-emerald-500/20 rounded-md text-slate-400 hover:text-emerald-600 transition-colors"
                                    title="下载"
                                  >
                                    <Download size={14} />
                                  </button>
                                </>
                              ) : null}
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleRemoveTask(task.id);
                                }}
                                className="p-1.5 hover:bg-red-100 dark:hover:bg-red-500/20 rounded-md text-slate-400 hover:text-red-600 transition-colors"
                                title="删除"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
        )}

        {/* 右侧：用户要求 + 文件预览 */}
        <div className="flex-1 flex min-w-0 flex-col h-full min-h-0 bg-white dark:bg-[#0B1120]">
            {/* 顶部输入与操作区 (内联化) */}
            <div
              className={cn(
                "shrink-0 border-b border-slate-200 bg-slate-50/30 dark:border-white/[0.05] dark:bg-[#0B1120]",
                useUltraDenseRightPanel
                  ? "px-3 py-2"
                  : useDenseRightPanel
                    ? "px-3.5 py-2"
                    : "px-4 py-2",
              )}
            >
                <div
                  className={cn(
                    "flex",
                    useUltraDenseRightPanel ? "flex-col gap-2" : "items-center gap-3",
                  )}
                >
                  <div className={cn("flex items-center shrink-0", useUltraDenseRightPanel ? "gap-1" : "gap-1.5")}>
                    <NeedIcon size={14} className="text-slate-500 dark:text-slate-400" />
                    <h3
                      className={cn(
                        "font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200",
                        useUltraDenseRightPanel ? "text-[11px]" : "text-[12px]",
                      )}
                    >
                      {useUltraDenseRightPanel ? "要求" : "用户要求"}
                    </h3>
                  </div>
                  <div
                    className={cn(
                      "flex flex-1 min-w-0",
                      useUltraDenseRightPanel ? "items-stretch gap-2" : "items-center gap-3",
                    )}
                  >
                <input
                  type="text"
                  value={draftRequirements}
                  onChange={handleRequirementsChange}
                  maxLength={600}
                  placeholder="请输入你对这次填充的要求（选填）"
                  className={cn(
                    "flex-1 rounded-lg border border-slate-200 bg-slate-50/50 text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-blue-500/50 focus:bg-white focus:ring-4 focus:ring-blue-500/10 dark:border-white/[0.1] dark:bg-white/[0.02] dark:text-slate-200 dark:focus:bg-white/[0.04] dark:focus:ring-blue-500/20 shadow-sm",
                    useUltraDenseRightPanel
                      ? "h-[34px] px-2.5 text-[12px]"
                      : useDenseRightPanel
                        ? "h-[35px] px-3 text-[12.5px]"
                        : "h-[36px] px-3 text-[13px]",
                  )}
                />
                <motion.button
                  type="button"
                  whileTap={{ scale: 0.97 }}
                  onClick={handleStartRun}
                  disabled={!canStartRun}
                  className={cn(
                    "shrink-0 flex items-center justify-center gap-2 rounded-lg font-medium transition-all shadow-sm",
                    useUltraDenseRightPanel
                      ? "h-[34px] px-4 text-[12px]"
                      : useDenseRightPanel
                        ? "h-[35px] px-5 text-[12.5px]"
                        : "h-[36px] px-6 text-[13px]",
                    canStartRun
                      ? "bg-gradient-to-b from-blue-500 to-blue-600 text-white hover:from-blue-600 hover:to-blue-700 shadow-blue-500/20 ring-1 ring-inset ring-white/20"
                      : "cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-white/[0.02] dark:text-slate-500 dark:border dark:border-white/[0.05]",
                  )}
                >
                  {isRunning ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : null}
                  {useUltraDenseRightPanel ? "开始" : "开始填充"}
                </motion.button>
              </div>
            </div>
          </div>

          {/* 文件预览区 */}
          <div className="flex-1 min-h-0 flex flex-col">
            <div
              className={cn(
                "shrink-0 border-b border-slate-200 bg-slate-50/30 dark:border-white/[0.05] dark:bg-[#0B1120]",
                useUltraDenseRightPanel
                  ? "px-3 py-1.5"
                  : useDenseRightPanel
                    ? "px-3.5 py-2"
                    : "px-4 py-2",
              )}
            >
              <div className="flex items-center justify-between">
              <div className={cn("flex items-center", useUltraDenseRightPanel ? "gap-1" : "gap-1.5")}>
                <LookIcon size={14} className="text-slate-500 dark:text-slate-400" />
                <h3
                  className={cn(
                    "font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200",
                    useUltraDenseRightPanel ? "text-[11px]" : "text-[12px]",
                  )}
                >
                  {useUltraDenseRightPanel ? "预览" : "文件预览"}
                </h3>
                <div
                  id="preview-header-actions"
                  className={cn(
                    "flex items-center empty:hidden",
                    useUltraDenseRightPanel ? "ml-1" : "ml-2",
                  )}
                ></div>
              </div>
              <div className="flex items-center gap-2"></div>
              </div>
            </div>
            <div className="flex-1 min-h-0 bg-white dark:bg-[#0B1120] relative">
              {isPreviewLoading ? (
                <div className={cn(
                  "h-full flex flex-col items-center justify-center",
                  useUltraDenseRightPanel ? "space-y-3 px-4" : "space-y-4",
                )}>
                  <Loader2 size={24} className="animate-spin text-slate-400" />
                  <div className="text-center">
                    <p className={cn("font-medium text-slate-600 dark:text-slate-300", useUltraDenseRightPanel ? "text-[12px]" : "text-[13px]")}>正在加载预览</p>
                    <p className={cn("text-slate-400 mt-1", useUltraDenseRightPanel ? "text-[11px]" : "text-[12px]")}>请稍候，正在为您准备文档内容</p>
                  </div>
                </div>
              ) : previewDocument ? (
                <div className="flex h-full min-w-0 flex-col overflow-hidden bg-white dark:bg-[#0B1120]">
                  <div className="min-h-0 min-w-0 flex-1 overflow-hidden relative">
                    {previewDocument.type === "xlsx" ? (
                      <LuckysheetPreview
                        document={previewDocument}
                        content={
                          previewContent || "（文件内容为空或无法预览）"
                        }
                        sheets={previewSheets}
                      />
                    ) : previewDocument.type === "docx" ? (
                      <Module3WordPreview
                        document={previewDocument}
                        fallbackContent={
                          previewContent || "（文件内容为空或无法预览）"
                        }
                      />
                    ) : (
                      <SpreadsheetPreview
                        document={previewDocument}
                        content={
                          previewContent || "（文件内容为空或无法预览）"
                        }
                        sheets={previewSheets}
                      />
                    )}
                  </div>
                </div>
              ) : (
                <div className={cn(
                  "h-full flex flex-col items-center justify-center bg-slate-50/30 dark:bg-white/[0.01]",
                  useUltraDenseRightPanel ? "space-y-3 px-4" : "space-y-4",
                )}>
                  <div className={cn(
                    "flex items-center justify-center rounded-full bg-slate-100 dark:bg-white/[0.03] border border-slate-200/50 dark:border-white/[0.05] shadow-sm",
                    useUltraDenseRightPanel ? "w-14 h-14" : "w-16 h-16",
                  )}>
                    <Eye size={useUltraDenseRightPanel ? 28 : 32} className="text-slate-400 dark:text-slate-600" />
                  </div>
                  <div className="text-center">
                    <h4 className={cn("font-medium text-slate-600 dark:text-slate-300", useUltraDenseRightPanel ? "text-[13px]" : "text-[14px]")}>暂无预览内容</h4>
                    <p className={cn(
                      "text-slate-400 dark:text-slate-500 mt-1.5 mx-auto leading-relaxed",
                      useUltraDenseRightPanel ? "max-w-[200px] text-[11px]" : "max-w-[220px] text-[12px]",
                    )}>
                      请在左侧“任务记录”中点击已完成任务的预览按钮查看生成文件
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
