﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Database,
  Download,
  Eye,
  File,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Filter,
  FolderOpen,
  FolderPlus,
  GitGraph,
  Home,
  Image as ImageIcon,
  Loader2,
  LayoutGrid,
  MessageSquare,
  PencilLine,
  RotateCw,
  Search,
  Sparkles,
  Star,
  Trash2,
  UploadCloud,
  Wand2,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

import { cn } from '../../lib/utils';
import type { AuthUser } from '../../shared/api/auth';
import { buildModule1ApiUrl } from '../../shared/api/module1';
import { PdfJsViewer, type PdfViewMode } from '../../components/PdfJsViewer';
import { LuckysheetPreview } from '../../components/LuckysheetPreview';
import {
  HOME_WORKBENCH_ROOT_FOLDER_ID,
  type HomeWorkbenchFolder,
  type HomeWorkbenchItem,
  type HomeWorkbenchSession,
  type HomeWorkbenchView,
  clearModule4DraftFromHomeWorkbench,
  createDefaultHomeWorkbenchSession,
  deleteHomeWorkbenchFile,
  ensureHomeWorkbenchPersistenceReady,
  getHomeWorkbenchConvertedPdf,
  getHomeWorkbenchFile,
  isHomeWorkbenchPersistenceReady,
  readHomeWorkbenchSession,
  readModule4DraftFromHomeWorkbench,
  registerHomeWorkbenchConvertedPdf,
  registerHomeWorkbenchFiles,
  resolveHomeWorkbenchFile,
  subscribeHomeWorkbenchBinaryStore,
  writeHomeWorkbenchSession,
  writeModule1DraftFromHomeWorkbench,
  writeModule2DraftFromHomeWorkbench,
  writeModule4DraftFromHomeWorkbench,
} from '../../shared/state/homeWorkbench';
import {
  readFusionGridState,
  type FusionGridDocsetRecord,
  type FusionGridState,
  type FusionGridTemplateRecord,
  writeFusionGridState,
} from '../../lib/fusionGridStore';
import { uploadModule3Docset, uploadModule3Template } from '../../lib/module3Api';

import pdfIcon from '../../assets/pdf.png';
import wordIcon from '../../assets/WORD.png';
import xlsxIcon from '../../assets/xlsx.png';
import txtIcon from '../../assets/txt.png';
import mdIcon from '../../assets/md.png';
import customDocIcon from '../../assets/文档.png';

type DashboardProps = {
  onNavigate?: (tab: string) => void;
  user?: AuthUser;
};

type PreviewMode = 'pdf' | 'text' | 'image' | 'spreadsheet' | 'unsupported';

type ToastState = {
  tone: 'info' | 'good' | 'warn' | 'error';
  text: string;
};

type ModuleTarget = 'module2' | 'module3-template' | 'module3-source' | 'module4';

type WordToPdfConversionResult =
  | {
      ok: true;
      pdfBlob: Blob;
    }
  | {
      ok: false;
      errorMessage: string;
    };

type OfficePreviewJobPayload = {
  ok?: boolean;
  job_id?: string;
  status?: string;
  artifact_url?: string;
  error?: string;
  message?: string;
};

const MODULE1_QUICK_PROMPTS = [
  '请先总结这份文档的核心内容，再给出可执行建议',
  '请帮我提炼这份文件里的关键事实、时间点和结论',
  '请检查这份材料是否存在风险点、歧义点或表述遗漏',
  '请把这份文档改写成更适合正式汇报的版本',
];

const queueShellClassName =
  'rounded-[28px] border border-[#dbe6f2] bg-white/92 shadow-[0_26px_80px_-44px_rgba(77,99,132,0.22)] backdrop-blur-xl';

const createId = (prefix: string): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;
};

const fileExt = (name: string): string => {
  const raw = String(name || '').trim().split('.').pop() || '';
  return raw.toLowerCase();
};

const formatBytes = (value: number): string => {
  if (!Number.isFinite(value) || value <= 0) return '0 B';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
};

const formatTimestamp = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatRelativeTime = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '刚刚';
  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.max(0, Math.round(diffMs / 60000));
  if (diffMinutes < 1) return '刚刚';
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} 小时前`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} 天前`;
};

const detectMime = (file: File): string => {
  if (file.type) return file.type;
  const ext = fileExt(file.name);
  if (ext === 'pdf') return 'application/pdf';
  if (ext === 'docx') return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  if (ext === 'doc') return 'application/msword';
  if (ext === 'xlsx') return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  if (ext === 'xls') return 'application/vnd.ms-excel';
  if (['txt', 'md', 'markdown', 'csv', 'json'].includes(ext)) return 'text/plain';
  if (['jpg', 'jpeg'].includes(ext)) return 'image/jpeg';
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  if (ext === 'gif') return 'image/gif';
  return 'application/octet-stream';
};

const isPdfFile = (item: Pick<HomeWorkbenchItem, 'ext' | 'mime'>): boolean =>
  item.ext === 'pdf' || item.mime.includes('pdf');

const isWordFile = (item: Pick<HomeWorkbenchItem, 'ext' | 'mime'>): boolean =>
  item.ext === 'docx' || item.ext === 'doc' || item.mime.includes('word');

const isSpreadsheetFile = (item: Pick<HomeWorkbenchItem, 'ext' | 'mime'>): boolean =>
  item.ext === 'xlsx' || item.ext === 'xls' || item.mime.includes('sheet') || item.mime.includes('excel');

const isTextFile = (item: Pick<HomeWorkbenchItem, 'ext' | 'mime'>): boolean =>
  ['txt', 'md', 'markdown', 'csv', 'json'].includes(item.ext) || item.mime.startsWith('text/');

const isImageFile = (item: Pick<HomeWorkbenchItem, 'ext' | 'mime'>): boolean =>
  ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(item.ext) || item.mime.startsWith('image/');

const resolvePreviewMode = (item: HomeWorkbenchItem | null | undefined): PreviewMode => {
  if (!item) return 'unsupported';
  if (isPdfFile(item) || isWordFile(item)) return 'pdf';
  if (isTextFile(item)) return 'text';
  if (isImageFile(item)) return 'image';
  if (isSpreadsheetFile(item)) return 'spreadsheet';
  return 'unsupported';
};

const parseApiErrorMessage = async (response: Response): Promise<string> => {
  try {
    const bodyText = (await response.text()).trim();
    if (!bodyText) return `HTTP ${response.status}`;
    try {
      const payload = JSON.parse(bodyText) as { error?: string; detail?: string; message?: string };
      return String(payload.error || payload.detail || payload.message || bodyText).trim();
    } catch {
      return bodyText;
    }
  } catch {
    return `HTTP ${response.status}`;
  }
};

const isLikelyPdfBlob = async (blob: Blob): Promise<boolean> => {
  if (!blob || blob.size < 5) return false;
  try {
    const header = await blob.slice(0, 5).text();
    return header === '%PDF-';
  } catch {
    return false;
  }
};

const buildItemFromFile = (file: File, folderId: string | null): HomeWorkbenchItem => {
  const now = new Date().toISOString();
  return {
    id: createId('home-file'),
    name: file.name,
    originalName: file.name,
    ext: fileExt(file.name),
    mime: detectMime(file),
    size: file.size,
    folderId,
    createdAt: now,
    updatedAt: now,
    starred: false,
    trashed: false,
    source: 'upload',
    status: 'ready',
    errorMessage: null,
    convertedPdfReady: false,
  };
};

const getFolderChildren = (folders: HomeWorkbenchFolder[], parentId: string | null) =>
  folders.filter((folder) => folder.parentId === parentId);

const collectDescendantFolderIds = (
  folders: HomeWorkbenchFolder[],
  folderId: string
): string[] => {
  const descendantIds: string[] = [];
  const queue = [folderId];

  while (queue.length > 0) {
    const currentId = queue.shift();
    if (!currentId) continue;
    const children = getFolderChildren(folders, currentId);
    children.forEach((child) => {
      descendantIds.push(child.id);
      queue.push(child.id);
    });
  }

  return descendantIds;
};

const getItemAvailabilityLabel = (
  item: HomeWorkbenchItem,
  options?: { persistenceReady?: boolean }
): string => {
  if (options?.persistenceReady === false) return '恢复中';
  if (item.status === 'converting') return '转换中';
  if (item.status === 'error') return '预览异常';
  if (!getHomeWorkbenchFile(item.id) && !getHomeWorkbenchConvertedPdf(item.id)) return '需重传';
  if (isWordFile(item) && item.convertedPdfReady) return 'PDF 就绪';
  return '已就绪';
};

const getItemIcon = (item: HomeWorkbenchItem, className = 'h-5 w-5') => {
  if (isPdfFile(item)) {
    return <img src={pdfIcon} alt="PDF" className={cn(className, 'object-contain drop-shadow-sm')} />;
  }
  if (isWordFile(item)) {
    return <img src={wordIcon} alt="Word" className={cn(className, 'object-contain drop-shadow-sm')} />;
  }
  if (isSpreadsheetFile(item)) {
    return <img src={xlsxIcon} alt="Excel" className={cn(className, 'object-contain drop-shadow-sm')} />;
  }
  if (isTextFile(item)) {
    if (item.ext === 'md' || item.ext === 'markdown') {
      return <img src={mdIcon} alt="Markdown" className={cn(className, 'object-contain drop-shadow-sm')} />;
    }
    return <img src={txtIcon} alt="Text" className={cn(className, 'object-contain drop-shadow-sm')} />;
  }
  if (isImageFile(item)) {
    return <ImageIcon className={cn(className, 'text-[#9f6b32]')} />;
  }
  return <img src={customDocIcon} alt="Document" className={cn(className, 'object-contain drop-shadow-sm')} />;
};

const getFolderPathLabel = (folders: HomeWorkbenchFolder[], folderId: string | null): string => {
  if (!folderId) return '未分组';
  const folder = folders.find((entry) => entry.id === folderId);
  return folder?.name || '未分组';
};

const readInitialModule3Requirements = (): string => {
  try {
    return readFusionGridState().draftRequirements || '';
  } catch {
    return '';
  }
};

const OFFICE_PREVIEW_POLL_INTERVAL_MS = 1200;
const OFFICE_PREVIEW_MAX_WAIT_MS = 180000;

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => window.setTimeout(resolve, ms));

const parseOfficePreviewPayload = async (response: Response): Promise<OfficePreviewJobPayload> => {
  const raw = await response.text();
  if (!raw.trim()) return {};
  try {
    const parsed = JSON.parse(raw) as OfficePreviewJobPayload;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const getOfficePreviewErrorMessage = (payload: OfficePreviewJobPayload, fallback: string): string => {
  const message = String(payload.error || payload.message || '').trim();
  return message || fallback;
};

const startWordPreviewJob = async (file: File): Promise<OfficePreviewJobPayload> => {
  const formData = new FormData();
  formData.append('file', file, file.name || 'document.docx');

  const response = await fetch(buildModule1ApiUrl('/convert/office/start'), {
    method: 'POST',
    body: formData,
    credentials: 'include',
  });

  const payload = await parseOfficePreviewPayload(response);
  if (!response.ok) {
    throw new Error(`Word 转 PDF 失败：${getOfficePreviewErrorMessage(payload, await parseApiErrorMessage(response))}`);
  }

  const jobId = String(payload.job_id || '').trim();
  if (!jobId) {
    throw new Error('Word 预览任务创建失败：后端未返回 job_id。');
  }
  return payload;
};

const fetchWordPreviewJobStatus = async (jobId: string): Promise<OfficePreviewJobPayload> => {
  const response = await fetch(
    buildModule1ApiUrl(`/convert/office/status/${encodeURIComponent(jobId)}`),
    {
      method: 'GET',
      credentials: 'include',
    }
  );

  const payload = await parseOfficePreviewPayload(response);
  if (!response.ok) {
    throw new Error(`Word 转 PDF 失败：${getOfficePreviewErrorMessage(payload, await parseApiErrorMessage(response))}`);
  }
  return payload;
};

const fetchWordPreviewArtifact = async (jobId: string): Promise<Blob> => {
  const response = await fetch(
    buildModule1ApiUrl(`/convert/office/artifact/${encodeURIComponent(jobId)}`),
    {
      method: 'GET',
      credentials: 'include',
    }
  );

  if (!response.ok) {
    const errorMessage = await parseApiErrorMessage(response);
    throw new Error(`Word 转 PDF 失败：${errorMessage}`);
  }

  const contentType = response.headers.get('content-type');
  if (!contentType?.includes('application/pdf')) {
    throw new Error(`返回内容不是 PDF：${contentType || 'unknown'}`);
  }

  const pdfBlob = await response.blob();
  if (pdfBlob.size === 0) {
    throw new Error('返回的 PDF 内容为空。');
  }

  const looksLikePdf = await isLikelyPdfBlob(pdfBlob);
  if (!looksLikePdf) {
    throw new Error('返回内容不是有效 PDF。');
  }

  return pdfBlob;
};

const convertWordToPdf = async (file: File): Promise<WordToPdfConversionResult> => {
  try {
    const startedPayload = await startWordPreviewJob(file);
    const jobId = String(startedPayload.job_id || '').trim();
    let statusPayload = startedPayload;
    const deadline = Date.now() + OFFICE_PREVIEW_MAX_WAIT_MS;

    while (Date.now() <= deadline) {
      const status = String(statusPayload.status || '').trim().toLowerCase();

      if (status === 'completed') {
        const pdfBlob = await fetchWordPreviewArtifact(jobId);
        return { ok: true, pdfBlob };
      }

      if (status === 'failed') {
        return {
          ok: false,
          errorMessage: `Word 转 PDF 失败：${getOfficePreviewErrorMessage(statusPayload, '预览转换失败。')}`,
        };
      }

      await sleep(OFFICE_PREVIEW_POLL_INTERVAL_MS);
      statusPayload = await fetchWordPreviewJobStatus(jobId);
    }

    return { ok: false, errorMessage: 'Word 转 PDF 失败：预览转换超时。' };
  } catch (error) {
    const rawMessage = error instanceof Error ? error.message : 'Word 转 PDF 失败。';
    const normalizedMessage = /Failed to fetch|NetworkError|Load failed/i.test(rawMessage)
      ? 'Word 转 PDF 失败：后端服务不可用或请求被代理中断。'
      : rawMessage;
    return {
      ok: false,
      errorMessage: normalizedMessage,
    };
  }
};

const QueueToolbar: React.FC<{
  searchValue: string;
  onSearchChange: (value: string) => void;
  isToolboxOpen: boolean;
}> = ({ searchValue, onSearchChange, isToolboxOpen }) => (
  <div className="flex flex-col gap-4 border-b border-slate-100 dark:border-white/[0.05] bg-white dark:bg-[#0B1120] px-6 py-4 lg:px-7">
    <div className={cn("flex flex-col gap-4 xl:flex-row xl:items-center", !isToolboxOpen && "xl:justify-center")}>
      <label className="flex flex-1 max-w-2xl items-center gap-2 rounded-md bg-[#F2F3F5] dark:bg-white/[0.02] px-3 py-2 transition-colors focus-within:bg-white dark:focus-within:bg-[#0B1120] focus-within:ring-1 focus-within:ring-blue-500 dark:focus-within:ring-blue-400">
        <Search size={16} className="text-slate-400 dark:text-slate-500" />
        <input
          value={searchValue}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="搜索文档、文件夹或最近处理内容"
          className="min-w-0 flex-1 bg-transparent text-[13px] text-slate-800 dark:text-slate-200 outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500"
        />
      </label>
    </div>
  </div>
);

const SidebarNavItem: React.FC<{
  label: string;
  active?: boolean;
  icon: React.ReactNode;
  detail?: string;
  onClick: () => void;
}> = ({ label, active = false, icon, detail, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'group relative flex w-full items-center justify-between rounded-md px-3 py-2 text-left transition-colors',
      active
        ? 'bg-slate-100/60 dark:bg-white/[0.05] font-semibold text-slate-900 dark:text-slate-100'
        : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/[0.02] hover:text-slate-900 dark:hover:text-slate-200 font-medium'
    )}
  >
    {active && <div className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-sm bg-blue-600 dark:bg-blue-500" />}
    <span className="flex items-center gap-3">
      <span className={cn('flex items-center justify-center', active ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 dark:text-slate-500 group-hover:text-slate-500 dark:group-hover:text-slate-400')}>
        {icon}
      </span>
      <span>
        <span className="block text-[14px]">{label}</span>
      </span>
    </span>
  </button>
);

const FileRow: React.FC<{
  item: HomeWorkbenchItem;
  folderLabel: string;
  selected: boolean;
  persistenceReady: boolean;
  onOpen: () => void;
  onSelect: () => void;
  onToggleStar: () => void;
  onRename: () => void;
  onTrash: () => void;
  onDownload: () => void;
  onDragStart: (event: React.DragEvent<HTMLDivElement>) => void;
}> = ({
  item,
  folderLabel,
  selected,
  persistenceReady,
  onOpen,
  onSelect,
  onToggleStar,
  onRename,
  onTrash,
  onDownload,
  onDragStart,
}) => (
  <div
    role="button"
    tabIndex={0}
    draggable
    onDragStart={onDragStart}
    onClick={onOpen}
    onFocus={onSelect}
    onKeyDown={(event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        onOpen();
      }
    }}
    className={cn(
      'group grid w-full grid-cols-[minmax(0,2.2fr)_140px_120px_140px_180px] items-center gap-3 border-b border-slate-100 dark:border-white/[0.05] px-6 py-3 text-left transition-colors',
      selected
        ? 'bg-blue-50/50 dark:bg-blue-500/10'
        : 'bg-transparent hover:bg-slate-50 dark:hover:bg-white/[0.02]'
    )}
  >
    <div className="flex min-w-0 items-center gap-3">
      <div className="flex shrink-0 items-center justify-center bg-transparent">
        {getItemIcon(item, 'h-5 w-5 opacity-90')}
      </div>
      <div className="min-w-0">
        <div className="truncate text-[14px] font-medium text-slate-800 dark:text-slate-200">{item.name}</div>
      </div>
    </div>

    <div className="text-[13px] text-slate-500 dark:text-slate-400">{folderLabel}</div>
    <div className="text-[13px] text-slate-500 dark:text-slate-400">本地上传</div>
    <div className="text-[13px] text-slate-500 dark:text-slate-400">{formatRelativeTime(item.updatedAt)}</div>

    <div className="flex items-center justify-between gap-2">
      <span className="text-[13px] text-slate-500 dark:text-slate-400 shrink-0">
        {getItemAvailabilityLabel(item, { persistenceReady })}
      </span>

      <div
        className={cn("flex shrink-0 items-center gap-1 opacity-0 transition", selected ? "opacity-100" : "group-hover:opacity-100")}
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onToggleStar}
          className={cn('rounded-md p-1.5 transition hover:bg-slate-200 dark:hover:bg-white/[0.05]', item.starred ? 'text-yellow-500 dark:text-amber-500' : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300')}
          title={item.starred ? '取消收藏' : '加入收藏'}
        >
          <Star size={15} className={item.starred ? 'fill-current' : ''} />
        </button>
        <button
          type="button"
          onClick={onRename}
          className="rounded-md p-1.5 text-slate-400 dark:text-slate-500 transition hover:bg-slate-200 dark:hover:bg-white/[0.05] hover:text-slate-700 dark:hover:text-slate-300"
          title="重命名"
        >
          <PencilLine size={15} />
        </button>
        <button
          type="button"
          onClick={onDownload}
          className="rounded-md p-1.5 text-slate-400 dark:text-slate-500 transition hover:bg-slate-200 dark:hover:bg-white/[0.05] hover:text-slate-700 dark:hover:text-slate-300"
          title="下载"
        >
          <Download size={15} />
        </button>
        <button
          type="button"
          onClick={onTrash}
          className="rounded-md p-1.5 text-slate-400 dark:text-slate-500 transition hover:bg-red-50 dark:hover:bg-red-500/10 hover:text-red-600 dark:hover:text-red-400"
          title="移入回收站"
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  </div>
);

const SidebarFolderFileList: React.FC<{
  items: HomeWorkbenchItem[];
  depth: number;
  selectedItemId: string | null;
  onOpen: (itemId: string) => void;
}> = ({
  items,
  depth,
  selectedItemId,
  onOpen,
}) => {
  if (items.length === 0) return null;

  return (
    <div className="space-y-1">
      {items.map((item) => {
        const isSelected = selectedItemId === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onOpen(item.id)}
            title={item.name}
            className={cn(
              'flex w-full items-center gap-2 rounded-md py-1.5 pr-2 text-left transition-colors',
              isSelected
                ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300'
                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-white/[0.03] dark:hover:text-slate-200'
            )}
            style={{ paddingLeft: `${20 + depth * 18}px` }}
          >
            <span className="flex shrink-0 items-center justify-center">
              {getItemIcon(item, 'h-4 w-4 opacity-85')}
            </span>
            <span className="min-w-0 flex-1 truncate text-[12px] font-medium">
              {item.name}
            </span>
            <span className="shrink-0 text-[11px] text-slate-400 dark:text-slate-500">
              {formatRelativeTime(item.updatedAt)}
            </span>
          </button>
        );
      })}
    </div>
  );
};

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate, user }) => {
  const [session, setSession] = useState<HomeWorkbenchSession>(() => readHomeWorkbenchSession());
  const [searchValue, setSearchValue] = useState('');
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [folderDraft, setFolderDraft] = useState('');
  const [previewItemId, setPreviewItemId] = useState<string | null>(null);
  const [previewToolboxOpen, setPreviewToolboxOpen] = useState(true);
  const [isToolboxOpen, setIsToolboxOpen] = useState(true);
  const [previewScale, setPreviewScale] = useState(1);
  const [previewRotation, setPreviewRotation] = useState(0);
  const [pdfViewMode, setPdfViewMode] = useState<PdfViewMode>('fit-width');
  const [previewTextMap, setPreviewTextMap] = useState<Record<string, string>>({});
  const [toast, setToast] = useState<ToastState | null>(null);
  const [dragTarget, setDragTarget] = useState<ModuleTarget | null>(null);
  const [module3Requirements, setModule3Requirements] = useState(() => readInitialModule3Requirements());
  const [module3Busy, setModule3Busy] = useState<'template' | 'source' | null>(null);
  const [editingFolderId, setEditingFolderId] = useState<string | null>(null);
  const [folderRenameDraft, setFolderRenameDraft] = useState('');
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [itemRenameDraft, setItemRenameDraft] = useState('');
  const [module4BannerVisible, setModule4BannerVisible] = useState(() => Boolean(readModule4DraftFromHomeWorkbench()));
  const homepageUploadInputRef = useRef<HTMLInputElement>(null);
  const module2UploadInputRef = useRef<HTMLInputElement>(null);
  const module4UploadInputRef = useRef<HTMLInputElement>(null);
  const module3TemplateInputRef = useRef<HTMLInputElement>(null);
  const module3SourceInputRef = useRef<HTMLInputElement>(null);
  const objectUrlMapRef = useRef<Map<string, string>>(new Map());
  const activePreviewConversionIdsRef = useRef<Set<string>>(new Set());
  const [binaryStoreReady, setBinaryStoreReady] = useState(() => isHomeWorkbenchPersistenceReady());
  const [binaryStoreRevision, setBinaryStoreRevision] = useState(0);
  const [filterType, setFilterType] = useState<string | null>(null);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number, y: number, folderId: string } | null>(null);
  const [uploadDialogFiles, setUploadDialogFiles] = useState<File[] | null>(null);
  const [uploadTargetFolderId, setUploadTargetFolderId] = useState<string | null>(null);
  const [uploadNewFolderDraft, setUploadNewFolderDraft] = useState('');
  const [isCreatingFolderInUpload, setIsCreatingFolderInUpload] = useState(false);
  const [expandedFolderIds, setExpandedFolderIds] = useState<string[]>([]);

  useEffect(() => {
    writeHomeWorkbenchSession(session);
  }, [session]);

  useEffect(() => {
    let cancelled = false;

    const syncBinaryStoreState = () => {
      if (cancelled) return;
      setBinaryStoreReady(isHomeWorkbenchPersistenceReady());
      setBinaryStoreRevision((current) => current + 1);
    };

    const unsubscribe = subscribeHomeWorkbenchBinaryStore(syncBinaryStoreState);

    void ensureHomeWorkbenchPersistenceReady().then(() => {
      syncBinaryStoreState();
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 2800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    return () => {
      objectUrlMapRef.current.forEach((url) => URL.revokeObjectURL(url));
      objectUrlMapRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const validFolderIds = new Set(session.folders.map((folder) => folder.id));
    setExpandedFolderIds((current) => current.filter((folderId) => validFolderIds.has(folderId)));
  }, [session.folders]);

  useEffect(() => {
    if (session.activeView.kind !== 'folder') return;
    const activeFolderViewId = session.activeView.folderId;
    setExpandedFolderIds((current) => (
      current.includes(activeFolderViewId)
        ? current
        : [...current, activeFolderViewId]
    ));
  }, [session.activeView]);

  const pushToast = useCallback((tone: ToastState['tone'], text: string) => {
    setToast({ tone, text });
  }, []);

  const selectedItem = useMemo(
    () => session.items.find((item) => item.id === session.selectedItemId) ?? null,
    [session.items, session.selectedItemId]
  );

  const previewItem = useMemo(
    () => session.items.find((item) => item.id === previewItemId) ?? null,
    [previewItemId, session.items]
  );

  const rootFolder = useMemo(
    () => session.folders.find((folder) => folder.id === HOME_WORKBENCH_ROOT_FOLDER_ID) ?? session.folders[0] ?? null,
    [session.folders]
  );

  const activeFolderId = session.activeView.kind === 'folder'
    ? session.activeView.folderId
    : HOME_WORKBENCH_ROOT_FOLDER_ID;
  const normalizedSearchValue = searchValue.trim().toLowerCase();
  const expandedFolderIdSet = useMemo(() => new Set(expandedFolderIds), [expandedFolderIds]);

  const visibleItems = useMemo(() => {
    const baseItems = session.items.filter((item) => {
      if (session.activeView.kind === 'recycle') return item.trashed;
      if (item.trashed) return false;
      if (session.activeView.kind === 'favorites') return item.starred;
      if (session.activeView.kind === 'folder') return item.folderId === session.activeView.folderId;
      return true;
    });

    let filtered = normalizedSearchValue
      ? baseItems.filter((item) => item.name.toLowerCase().includes(normalizedSearchValue))
      : baseItems;

    if (filterType) {
      filtered = filtered.filter((item) => {
        if (filterType === 'pdf') return isPdfFile(item);
        if (filterType === 'word') return isWordFile(item);
        if (filterType === 'xlsx') return isSpreadsheetFile(item);
        if (filterType === 'md') return isTextFile(item) && item.name.toLowerCase().endsWith('.md');
        if (filterType === 'txt') return isTextFile(item) && item.name.toLowerCase().endsWith('.txt');
        return true;
      });
    }

    return [...filtered].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  }, [normalizedSearchValue, session.activeView, session.items, filterType]);

  const folderItemsByFolderId = useMemo(() => {
    const grouped = new Map<string, HomeWorkbenchItem[]>();
    const eligibleItems = session.items
      .filter((item) => !item.trashed)
      .filter((item) => (
        normalizedSearchValue
          ? item.name.toLowerCase().includes(normalizedSearchValue)
          : true
      ))
      .sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime());

    eligibleItems.forEach((item) => {
      const key = item.folderId ?? HOME_WORKBENCH_ROOT_FOLDER_ID;
      const currentItems = grouped.get(key);
      if (currentItems) {
        currentItems.push(item);
        return;
      }
      grouped.set(key, [item]);
    });

    return grouped;
  }, [normalizedSearchValue, session.items]);

  const getOrCreateObjectUrl = useCallback((cacheKey: string, blob: Blob): string => {
    const existing = objectUrlMapRef.current.get(cacheKey);
    if (existing) return existing;
    const next = URL.createObjectURL(blob);
    objectUrlMapRef.current.set(cacheKey, next);
    return next;
  }, []);

  const updateSession = useCallback((updater: (current: HomeWorkbenchSession) => HomeWorkbenchSession) => {
    setSession((current) => updater(current));
  }, []);

  const updateItem = useCallback((itemId: string, updater: (item: HomeWorkbenchItem) => HomeWorkbenchItem) => {
    updateSession((current) => ({
      ...current,
      items: current.items.map((item) => (item.id === itemId ? updater(item) : item)),
    }));
  }, [updateSession]);

  const ensureFolderExpanded = useCallback((folderId: string) => {
    setExpandedFolderIds((current) => (
      current.includes(folderId) ? current : [...current, folderId]
    ));
  }, []);

  const toggleFolderExpanded = useCallback((folderId: string) => {
    setExpandedFolderIds((current) => (
      current.includes(folderId)
        ? current.filter((id) => id !== folderId)
        : [...current, folderId]
    ));
  }, []);

  const activateFolder = useCallback((folderId: string) => {
    ensureFolderExpanded(folderId);
    updateSession((current) => ({ ...current, activeView: { kind: 'folder', folderId } }));
  }, [ensureFolderExpanded, updateSession]);

  const appendFilesToWorkbench = useCallback((files: File[], options?: {
    folderId?: string | null;
    selectFirst?: boolean;
  }) => {
    const folderId = options?.folderId ?? activeFolderId ?? HOME_WORKBENCH_ROOT_FOLDER_ID;
    const accepted = files.filter((file) => file instanceof globalThis.File);
    if (accepted.length === 0) return [] as HomeWorkbenchItem[];

    const entries = accepted.map((file) => {
      const item = buildItemFromFile(file, folderId);
      return { item, file };
    });

    registerHomeWorkbenchFiles(entries.map((entry) => ({ itemId: entry.item.id, file: entry.file })));

    updateSession((current) => ({
      ...current,
      items: [...entries.map((entry) => entry.item), ...current.items],
      selectedItemId: options?.selectFirst === false ? current.selectedItemId : entries[0]?.item.id ?? current.selectedItemId,
      activeView: current.activeView.kind === 'recycle'
        ? { kind: 'home' }
        : current.activeView,
    }));

    return entries.map((entry) => entry.item);
  }, [activeFolderId, updateSession]);

  const handleHomepageUpload = useCallback((files: FileList | File[] | null) => {
    if (!files || files.length === 0) return;
    const normalized = Array.from(files);
    setUploadDialogFiles(normalized);
    setUploadTargetFolderId(activeFolderId || HOME_WORKBENCH_ROOT_FOLDER_ID);
    setUploadNewFolderDraft('');
    setIsCreatingFolderInUpload(false);
  }, [activeFolderId]);

  const confirmUpload = useCallback(() => {
    if (!uploadDialogFiles) return;
    let finalFolderId = uploadTargetFolderId || HOME_WORKBENCH_ROOT_FOLDER_ID;

    if (isCreatingFolderInUpload) {
      const name = uploadNewFolderDraft.trim();
      if (!name) {
        pushToast('warn', '请输入新文件夹名称。');
        return;
      }
      const now = new Date().toISOString();
      const nextFolder: HomeWorkbenchFolder = {
        id: createId('home-folder'),
        name,
        parentId: HOME_WORKBENCH_ROOT_FOLDER_ID,
        createdAt: now,
        updatedAt: now,
      };
      updateSession((current) => ({
        ...current,
        folders: [...current.folders, nextFolder],
      }));
      finalFolderId = nextFolder.id;
    }

    const items = appendFilesToWorkbench(uploadDialogFiles, { folderId: finalFolderId });
    if (items.length > 0) {
      pushToast('good', `已加入 ${items.length} 个文件到指定文件夹。`);
      updateSession((current) => ({ ...current, activeView: { kind: 'folder', folderId: finalFolderId } }));
    }
    setUploadDialogFiles(null);
  }, [uploadDialogFiles, uploadTargetFolderId, isCreatingFolderInUpload, uploadNewFolderDraft, appendFilesToWorkbench, pushToast, updateSession]);

  const cancelUpload = useCallback(() => {
    setUploadDialogFiles(null);
  }, []);

  const handleCreateFolder = useCallback(() => {
    const name = folderDraft.trim();
    if (!name) {
      pushToast('warn', '请输入文件夹名称。');
      return;
    }

    const now = new Date().toISOString();
    const nextFolder: HomeWorkbenchFolder = {
      id: createId('home-folder'),
      name,
      parentId: activeFolderId || HOME_WORKBENCH_ROOT_FOLDER_ID,
      createdAt: now,
      updatedAt: now,
    };

    updateSession((current) => ({
      ...current,
      folders: [...current.folders, nextFolder],
      activeView: { kind: 'folder', folderId: nextFolder.id },
    }));
    setCreatingFolder(false);
    setFolderDraft('');
    pushToast('good', `文件夹“${name}”已创建。`);
  }, [activeFolderId, folderDraft, pushToast, updateSession]);

  useEffect(() => {
    if (!import.meta.env.DEV || typeof window === 'undefined') return undefined;

    const debugHost = window as Window & {
      __homeWorkbenchDebug?: {
        injectTextFile: (name?: string, text?: string) => string | null;
        injectSvgFile: (name?: string, label?: string) => string | null;
        reset: () => void;
      };
    };

    debugHost.__homeWorkbenchDebug = {
      injectTextFile: (name = '首页调试说明.txt', text = '这是首页调试注入的文本文件，用于验证全屏预览、右侧工具箱和跨模块投递。') => {
        const file = new globalThis.File([text], name, { type: 'text/plain' });
        const [item] = appendFilesToWorkbench([file]);
        return item?.id ?? null;
      },
      injectSvgFile: (name = '首页示意图.svg', label = 'Workbench Preview') => {
        const svg = `
          <svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
            <defs>
              <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#f7fbff" />
                <stop offset="100%" stop-color="#dcecff" />
              </linearGradient>
            </defs>
            <rect width="1600" height="900" rx="48" fill="url(#bg)" />
            <rect x="88" y="92" width="1424" height="108" rx="28" fill="#ffffff" stroke="#d8e5f3" />
            <rect x="88" y="240" width="420" height="540" rx="32" fill="#ffffff" stroke="#d8e5f3" />
            <rect x="548" y="240" width="964" height="540" rx="32" fill="#ffffff" stroke="#d8e5f3" />
            <text x="132" y="158" font-size="34" font-family="Microsoft YaHei, PingFang SC, sans-serif" fill="#26446b">首页调试图像</text>
            <text x="132" y="330" font-size="52" font-weight="700" font-family="Microsoft YaHei, PingFang SC, sans-serif" fill="#1c2b42">${label}</text>
            <text x="132" y="400" font-size="26" font-family="Microsoft YaHei, PingFang SC, sans-serif" fill="#5f748d">用于验证首页预览、图片渲染和布局层级。</text>
            <circle cx="1310" cy="370" r="118" fill="#2a65f4" opacity="0.12" />
            <circle cx="1380" cy="430" r="86" fill="#7cb7ff" opacity="0.24" />
          </svg>
        `.trim();
        const file = new globalThis.File([svg], name, { type: 'image/svg+xml' });
        const [item] = appendFilesToWorkbench([file]);
        return item?.id ?? null;
      },
      reset: () => setSession(createDefaultHomeWorkbenchSession()),
    };

    return () => {
      delete debugHost.__homeWorkbenchDebug;
    };
  }, [appendFilesToWorkbench]);

  const handleRenameFolder = useCallback((folderId: string) => {
    const nextName = folderRenameDraft.trim();
    if (!nextName) {
      pushToast('warn', '文件夹名称不能为空。');
      return;
    }
    updateSession((current) => ({
      ...current,
      folders: current.folders.map((folder) => (
        folder.id === folderId
          ? { ...folder, name: nextName, updatedAt: new Date().toISOString() }
          : folder
      )),
    }));
    setEditingFolderId(null);
    setFolderRenameDraft('');
    pushToast('good', '文件夹名称已更新。');
  }, [folderRenameDraft, pushToast, updateSession]);

  const handleRenameItem = useCallback((itemId: string) => {
    const nextName = itemRenameDraft.trim();
    if (!nextName) {
      pushToast('warn', '文件名不能为空。');
      return;
    }
    updateItem(itemId, (item) => ({
      ...item,
      name: nextName,
      updatedAt: new Date().toISOString(),
    }));
    setEditingItemId(null);
    setItemRenameDraft('');
    pushToast('good', '文件名称已更新。');
  }, [itemRenameDraft, pushToast, updateItem]);

  const openPreview = useCallback((itemId: string) => {
    updateSession((current) => ({ ...current, selectedItemId: itemId }));
    setPreviewItemId(itemId);
    setPreviewToolboxOpen(true);
    setPreviewScale(1);
    setPreviewRotation(0);
    setPdfViewMode('fit-width');
  }, [updateSession]);

  const handleRetryPreviewConversion = useCallback(() => {
    if (!previewItem || !isWordFile(previewItem)) return;
    updateItem(previewItem.id, (item) => ({
      ...item,
      status: 'ready',
      convertedPdfReady: Boolean(getHomeWorkbenchConvertedPdf(item.id)),
      errorMessage: null,
      updatedAt: new Date().toISOString(),
    }));
  }, [previewItem, updateItem]);

  useEffect(() => {
    if (!previewItem || !isTextFile(previewItem)) return;
    if (previewTextMap[previewItem.id]) return;
    let cancelled = false;
    void resolveHomeWorkbenchFile(previewItem.id)
      .then((file) => (file ? file.text() : null))
      .then((text) => {
        if (cancelled || typeof text !== 'string') return;
        setPreviewTextMap((current) => ({ ...current, [previewItem.id]: text }));
      })
      .catch(() => {
        if (cancelled) return;
        setPreviewTextMap((current) => ({ ...current, [previewItem.id]: '文本预览加载失败。' }));
      });

    return () => {
      cancelled = true;
    };
  }, [binaryStoreRevision, previewItem, previewTextMap]);

  useEffect(() => {
    if (!previewItem || !isWordFile(previewItem)) return;
    const targetItemId = previewItem.id;
    if (getHomeWorkbenchConvertedPdf(targetItemId)) return;
    const file = getHomeWorkbenchFile(targetItemId);
    if (!file) return;
    const activePreviewConversions = activePreviewConversionIdsRef.current;
    if (previewItem.status === 'error') return;
    if (previewItem.status === 'converting' && activePreviewConversions.has(targetItemId)) return;

    activePreviewConversions.add(targetItemId);
    if (previewItem.status !== 'converting') {
      updateItem(targetItemId, (item) => ({
        ...item,
        status: 'converting',
        convertedPdfReady: false,
        updatedAt: new Date().toISOString(),
        errorMessage: null,
      }));
    }

    void convertWordToPdf(file)
      .then((result) => {
        if (result.ok) {
          registerHomeWorkbenchConvertedPdf(targetItemId, result.pdfBlob);
          updateItem(targetItemId, (item) => ({
            ...item,
            status: 'converted',
            convertedPdfReady: true,
            updatedAt: new Date().toISOString(),
            errorMessage: null,
          }));
          return;
        }
        updateItem(targetItemId, (item) => ({
          ...item,
          status: 'error',
          convertedPdfReady: false,
          updatedAt: new Date().toISOString(),
          errorMessage: result.errorMessage || 'Word 转 PDF 失败，请稍后重试。',
        }));
      })
      .finally(() => {
        activePreviewConversionIdsRef.current.delete(targetItemId);
      });
  }, [previewItem, updateItem]);

  const previewSource = useMemo(() => {
    if (!previewItem) return null;
    if (isPdfFile(previewItem)) {
      const file = getHomeWorkbenchFile(previewItem.id);
      return file ? getOrCreateObjectUrl(`file:${previewItem.id}`, file) : null;
    }
    if (isWordFile(previewItem)) {
      const converted = getHomeWorkbenchConvertedPdf(previewItem.id);
      return converted ? getOrCreateObjectUrl(`converted:${previewItem.id}`, converted) : null;
    }
    if (isImageFile(previewItem)) {
      const file = getHomeWorkbenchFile(previewItem.id);
      return file ? getOrCreateObjectUrl(`file:${previewItem.id}`, file) : null;
    }
    return null;
  }, [getOrCreateObjectUrl, previewItem]);

  const handleDownloadItem = useCallback((item: HomeWorkbenchItem) => {
    const converted = isWordFile(item) ? getHomeWorkbenchConvertedPdf(item.id) : null;
    const file = getHomeWorkbenchFile(item.id);
    const blob = converted || file;
    if (!blob) {
      pushToast('warn', '当前会话中已找不到这个文件，请重新上传后再下载。');
      return;
    }
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = converted ? item.name.replace(/\.[^.]+$/, '.pdf') : item.name;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.setTimeout(() => URL.revokeObjectURL(url), 120);
  }, [pushToast]);

  const stageForModule2 = useCallback((itemIds: string[]) => {
    const availableIds = itemIds.filter((itemId) => Boolean(getHomeWorkbenchFile(itemId)));
    if (availableIds.length === 0) {
      pushToast('warn', '这些文件当前只保留了元数据，请重新上传后再送入模块二。');
      return;
    }
    writeModule2DraftFromHomeWorkbench(availableIds);
    pushToast('good', `已把 ${availableIds.length} 个文件送入模块二待处理区。`);
  }, [pushToast]);

  const stageForModule4 = useCallback((itemIds: string[]) => {
    if (itemIds.length === 0) {
      pushToast('warn', '请先选择一个文件。');
      return;
    }
    writeModule4DraftFromHomeWorkbench(itemIds);
    setModule4BannerVisible(true);
    pushToast('good', '已把文件加入图谱候选清单，建议先在模块二完成抽取再进入模块四。');
  }, [pushToast]);

  const syncTemplateToModule3 = useCallback(async (file: File) => {
    setModule3Busy('template');
    try {
      const response = await uploadModule3Template(file);
      const record: FusionGridTemplateRecord = {
        id: response.template_id,
        name: file.name,
        backendFilename: response.filename,
        size: formatBytes(file.size),
        uploadTime: new Date().toLocaleString('zh-CN', { hour12: false }),
        fields: response.fields,
      };

      const state = readFusionGridState();
      const nextTemplates = [
        record,
        ...state.templates.filter((item) => item.id !== record.id),
      ];
      writeFusionGridState({
        ...state,
        templates: nextTemplates,
        selectedTemplateId: record.id,
        draftRequirements: module3Requirements,
      });
      pushToast('good', `模板“${file.name}”已同步到模块三。`);
    } catch (error) {
      pushToast('error', error instanceof Error ? error.message : '模板上传失败。');
    } finally {
      setModule3Busy(null);
    }
  }, [module3Requirements, pushToast]);

  const syncSourceToModule3 = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    setModule3Busy('source');
    try {
      const response = await uploadModule3Docset(files);
      const record: FusionGridDocsetRecord = {
        id: response.doc_set_id,
        count: response.count,
        uploadTime: new Date().toLocaleString('zh-CN', { hour12: false }),
        files: response.files.map((item, index) => {
          const original = files[index];
          const ext = fileExt(item.filename);
          return {
            filename: item.filename,
            fileId: item.file_id ?? null,
            size: original ? formatBytes(original.size) : '鏈煡澶у皬',
            type: ext === 'xlsx' ? 'xlsx' : ext === 'docx' ? 'docx' : ext === 'txt' ? 'txt' : ext === 'md' ? 'md' : 'other',
          };
        }),
      };
      const state = readFusionGridState();
      const nextDocsets = [
        record,
        ...state.docsets.filter((item) => item.id !== record.id),
      ];
      writeFusionGridState({
        ...state,
        docsets: nextDocsets,
        selectedDocsetId: record.id,
        draftRequirements: module3Requirements,
      });
      pushToast('good', `已把 ${files.length} 个源文件同步到模块三。`);
    } catch (error) {
      pushToast('error', error instanceof Error ? error.message : '源文件同步失败。');
    } finally {
      setModule3Busy(null);
    }
  }, [module3Requirements, pushToast]);

  const handleModule1Prompt = useCallback((prompt: string) => {
    if (!selectedItem) {
      pushToast('warn', '请先选中文件，再把它带入模块一。');
      return;
    }
    if (!getHomeWorkbenchFile(selectedItem.id)) {
      pushToast('warn', '当前文件在这次会话里已不可用，请重新上传后再带入模块一。');
      return;
    }
    writeModule1DraftFromHomeWorkbench({
      prompt,
      itemIds: [selectedItem.id],
    });
    onNavigate?.('doc-processing');
  }, [onNavigate, pushToast, selectedItem]);

  const handleItemDropToTarget = useCallback(async (target: ModuleTarget, itemId: string) => {
    const item = session.items.find((entry) => entry.id === itemId);
    if (!item) return;

    if (target === 'module2') {
      stageForModule2([item.id]);
      return;
    }

    if (target === 'module4') {
      stageForModule4([item.id]);
      return;
    }

    const file = getHomeWorkbenchFile(item.id);
    if (!file) {
      pushToast('warn', '这个文件当前已没有可用的原始内容，请重新上传后再拖入工具箱。');
      return;
    }

    if (target === 'module3-template') {
      await syncTemplateToModule3(file);
      return;
    }

    await syncSourceToModule3([file]);
  }, [pushToast, session.items, stageForModule2, stageForModule4, syncSourceToModule3, syncTemplateToModule3]);

  const handleDragStart = useCallback((itemId: string, event: React.DragEvent<HTMLDivElement>) => {
    event.dataTransfer.effectAllowed = 'copyMove';
    event.dataTransfer.setData('application/x-smart-doc-home-item', itemId);
  }, []);

  const bindDropTarget = useCallback((target: ModuleTarget) => ({
    onDragOver: (event: React.DragEvent<HTMLElement>) => {
      event.preventDefault();
      setDragTarget(target);
    },
    onDragLeave: () => setDragTarget((current) => (current === target ? null : current)),
    onDrop: (event: React.DragEvent<HTMLElement>) => {
      event.preventDefault();
      const itemId = event.dataTransfer.getData('application/x-smart-doc-home-item');
      setDragTarget(null);
      if (!itemId) return;
      void handleItemDropToTarget(target, itemId);
    },
  }), [handleItemDropToTarget]);

  const contextFolder = useMemo(
    () => (contextMenu ? session.folders.find((folder) => folder.id === contextMenu.folderId) ?? null : null),
    [contextMenu, session.folders]
  );

  const renderFolderNode = (folder: HomeWorkbenchFolder, depth = 0): React.ReactNode => {
    const isEditing = editingFolderId === folder.id;
    const isActive = session.activeView.kind === 'folder' && session.activeView.folderId === folder.id;
    const isExpanded = expandedFolderIdSet.has(folder.id);
    const directFiles = folderItemsByFolderId.get(folder.id) ?? [];
    const childFolders = getFolderChildren(session.folders, folder.id);

    return (
      <div key={folder.id} className="space-y-1">
        <div
          className={cn(
            'group rounded-md transition-colors',
            isActive ? 'bg-slate-100/60 dark:bg-white/[0.05]' : 'hover:bg-slate-100 dark:hover:bg-white/[0.05]'
          )}
          style={{ marginLeft: `${depth * 14}px` }}
        >
          {isEditing ? (
            <div className="rounded border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] p-2 shadow-sm">
              <input
                value={folderRenameDraft}
                onChange={(event) => setFolderRenameDraft(event.target.value)}
                className="w-full rounded bg-slate-50 dark:bg-black/20 px-2 py-1 text-[13px] outline-none dark:text-slate-200"
              />
              <div className="mt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setEditingFolderId(null);
                    setFolderRenameDraft('');
                  }}
                  className="rounded px-2 py-1 text-[12px] font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/[0.05]"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => handleRenameFolder(folder.id)}
                  className="rounded bg-blue-600 px-2 py-1 text-[12px] font-medium text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600"
                >
                  保存
                </button>
              </div>
            </div>
          ) : (
            <div
              className="flex items-center gap-1.5 px-2 py-1.5"
              onDoubleClick={() => {
                setEditingFolderId(folder.id);
                setFolderRenameDraft(folder.name);
              }}
              onContextMenu={(event) => {
                event.preventDefault();
                setContextMenu({ x: event.clientX, y: event.clientY, folderId: folder.id });
              }}
            >
              <button
                type="button"
                onClick={() => toggleFolderExpanded(folder.id)}
                className="rounded p-0.5 text-slate-400 transition hover:bg-slate-200/70 hover:text-slate-600 dark:text-slate-500 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                aria-label={isExpanded ? `收起${folder.name}` : `展开${folder.name}`}
              >
                {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              </button>
              <button
                type="button"
                onClick={() => activateFolder(folder.id)}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
              >
                <FolderOpen
                  size={16}
                  className={isActive ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 dark:text-slate-500 group-hover:text-slate-500 dark:group-hover:text-slate-400'}
                />
                <span className={cn(
                  'min-w-0 flex-1 truncate text-[13px] font-medium',
                  isActive ? 'text-blue-600 dark:text-blue-400' : 'text-slate-700 dark:text-slate-300'
                )}>
                  {folder.name}
                </span>
                {directFiles.length > 0 ? (
                  <span className="shrink-0 text-[11px] font-medium text-slate-400 dark:text-slate-500">
                    {directFiles.length}
                  </span>
                ) : null}
              </button>
            </div>
          )}
        </div>

        {isExpanded ? (
          <div className="space-y-1">
            <SidebarFolderFileList
              items={directFiles}
              depth={depth + 1}
              selectedItemId={session.selectedItemId}
              onOpen={openPreview}
            />
            {childFolders.map((childFolder) => renderFolderNode(childFolder, depth + 1))}
            {directFiles.length === 0 && childFolders.length === 0 ? (
              <div
                className="rounded-md px-2 py-1 text-[12px] text-slate-400 dark:text-slate-500"
                style={{ marginLeft: `${(depth + 1) * 14 + 24}px` }}
              >
                当前文件夹暂无文件
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  };

  const previewMode = resolvePreviewMode(previewItem);
  const previewHasLiveSource = previewItem
    ? Boolean(getHomeWorkbenchFile(previewItem.id) || getHomeWorkbenchConvertedPdf(previewItem.id))
    : false;

  const renderToolbox = (mode: 'dock' | 'drawer') => {
    const cardClassName = cn(
      'group flex items-center justify-start gap-3 rounded-[8px] bg-[#F7F8FA] dark:bg-white/[0.02] px-3 py-2.5 transition-all duration-200',
      'hover:bg-[#EFF3F9] dark:hover:bg-white/[0.05]',
      mode === 'drawer' ? '' : ''
    );
    
    return (
      <div className={cn('flex h-full flex-col gap-5', mode === 'drawer' ? 'w-[320px] px-6 py-6' : 'w-[280px] px-5 py-5')}>
        <div className="flex items-center justify-between">
          <div className="text-[15px] font-bold text-slate-800 dark:text-slate-200 tracking-wide">工具箱</div>
          {mode === 'drawer' ? (
            <button
              type="button"
              onClick={() => setPreviewToolboxOpen(false)}
              className="rounded-full p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-200/50 dark:hover:bg-white/[0.05] hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
            >
              <X size={16} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setIsToolboxOpen(false)}
              className="rounded-full p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-200/50 dark:hover:bg-white/[0.05] hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
            >
              <X size={16} />
            </button>
          )}
        </div>

        <section className="pb-5 border-b border-slate-200/60 dark:border-white/[0.05]">
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center gap-2">
              <div className="flex shrink-0 items-center justify-center">
                {selectedItem ? (
                  getItemIcon(selectedItem, 'h-7 w-7 object-contain')
                ) : (
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50/50 dark:bg-blue-500/10">
                    <img src={customDocIcon} alt="Document" className="h-5 w-5 object-contain opacity-60 dark:opacity-40" />
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-semibold text-slate-800 dark:text-slate-200">
                  {selectedItem?.name || '未选中文件'}
                </div>
                <div className="mt-0.5 truncate text-[12px] font-medium text-slate-500 dark:text-slate-400">
                  {selectedItem
                    ? `${formatBytes(selectedItem.size)} · ${getFolderPathLabel(session.folders, selectedItem.folderId)}`
                    : '选择文件后即可同步到对应模块'}
                </div>
              </div>
            </div>
          </div>
        </section>

        <div className="flex flex-col gap-3">
          <div className="text-[13px] font-bold text-slate-800 dark:text-slate-200">推荐功能</div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => onNavigate?.('doc-processing')}
              className={cardClassName}
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-blue-500 text-white transition-colors group-hover:bg-blue-600 dark:bg-blue-600 dark:group-hover:bg-blue-500">
                <Wand2 size={16} />
              </div>
              <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">文档处理</span>
            </button>

            <button
              type="button"
              onClick={() => onNavigate?.('deepread')}
              className={cardClassName}
              {...bindDropTarget('module2')}
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-emerald-500 text-white transition-colors group-hover:bg-emerald-600 dark:bg-emerald-600 dark:group-hover:bg-emerald-500">
                <FileSearch size={16} />
              </div>
              <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">信息提取</span>
            </button>

            <button
              type="button"
              onClick={() => onNavigate?.('fusion')}
              className={cardClassName}
              {...bindDropTarget('module3-template')}
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-amber-500 text-white transition-colors group-hover:bg-amber-600 dark:bg-amber-600 dark:group-hover:bg-amber-500">
                <Database size={16} />
              </div>
              <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">智能填表</span>
            </button>

            <button
              type="button"
              onClick={() => onNavigate?.('nexus')}
              className={cardClassName}
              {...bindDropTarget('module4')}
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-violet-500 text-white transition-colors group-hover:bg-violet-600 dark:bg-violet-600 dark:group-hover:bg-violet-500">
                <GitGraph size={16} />
              </div>
              <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">知识图谱</span>
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="h-[100dvh] w-full overflow-hidden bg-[#F2F3F5] text-[#1a273a] dark:bg-[#0B1120] dark:text-slate-300 relative">
      <div className="flex h-full w-full flex-col">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-transparent">
          <div className={cn(
            "grid min-h-0 flex-1 overflow-hidden",
            isToolboxOpen ? "grid-cols-[240px_minmax(0,1fr)_300px]" : "grid-cols-[240px_minmax(0,1fr)]"
          )}>
            <aside className="border-r border-slate-200 dark:border-white/[0.05] bg-[#F9FAFB] dark:bg-[#0B1120] px-4 py-5 flex flex-col">
              <div className="flex flex-col gap-3 mb-6">
                <button
                  type="button"
                  onClick={() => setCreatingFolder(true)}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#1E6FFF] dark:bg-blue-600 px-4 py-2 text-[14px] font-medium text-white transition hover:bg-[#165DFF] dark:hover:bg-blue-500"
                >
                  <FolderPlus size={16} />
                  新建文件夹
                </button>
                <button
                  type="button"
                  onClick={() => homepageUploadInputRef.current?.click()}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] px-4 py-2 text-[14px] font-medium text-slate-700 dark:text-slate-300 transition hover:bg-slate-50 dark:hover:bg-white/[0.05]"
                >
                  <UploadCloud size={16} />
                  上传文件
                </button>
              </div>

              <div className="space-y-2 mt-2">
                <SidebarNavItem
                  icon={<Home size={18} strokeWidth={2.5} />}
                  label="首页"
                  detail={`${session.items.filter((item) => !item.trashed).length} 份文档`}
                  active={session.activeView.kind === 'home'}
                  onClick={() => updateSession((current) => ({ ...current, activeView: { kind: 'home' } }))}
                />
                <SidebarNavItem
                  icon={<Trash2 size={18} strokeWidth={2.5} />}
                  label="回收站"
                  active={session.activeView.kind === 'recycle'}
                  onClick={() => updateSession((current) => ({ ...current, activeView: { kind: 'recycle' } }))}
                />
              </div>

              <div className="space-y-2 mt-2">
                <SidebarNavItem
                  icon={<LayoutGrid size={18} strokeWidth={2.5} />}
                  label="工具箱"
                  active={isToolboxOpen}
                  onClick={() => setIsToolboxOpen((current) => !current)}
                />
              </div>

              <div className="mt-6">
                <div className="mb-2 flex items-center justify-between gap-3 px-2">
                  <div className="text-[12px] font-semibold text-slate-500 dark:text-slate-400">我的文件夹</div>
                </div>

                {creatingFolder ? (
                  <div className="mb-2 rounded-md border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] px-2 py-2 shadow-sm">
                    <input
                      value={folderDraft}
                      onChange={(event) => setFolderDraft(event.target.value)}
                      placeholder="新建文件夹"
                      className="w-full rounded bg-slate-50 dark:bg-black/20 px-2 py-1.5 text-[13px] outline-none placeholder:text-slate-400 dark:text-slate-200"
                    />
                    <div className="mt-2 flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setCreatingFolder(false);
                          setFolderDraft('');
                        }}
                        className="rounded px-2 py-1 text-[12px] font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/[0.05]"
                      >
                        取消
                      </button>
                      <button
                        type="button"
                        onClick={handleCreateFolder}
                        className="rounded bg-blue-600 px-2 py-1 text-[12px] font-medium text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600"
                      >
                        创建
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="space-y-1">
                  {rootFolder ? renderFolderNode(rootFolder) : null}
                </div>
              </div>
            </aside>

            <section className="flex min-h-0 flex-col overflow-hidden bg-white dark:bg-[#0B1120]">
              <QueueToolbar
                searchValue={searchValue}
                onSearchChange={setSearchValue}
                isToolboxOpen={isToolboxOpen}
              />

              <div className="flex items-center gap-6 border-b border-slate-100 dark:border-white/[0.05] px-6 pt-4">
                <button 
                  onClick={() => updateSession((current) => ({ ...current, activeView: { kind: 'recent' } }))}
                  className={cn(
                    "border-b-2 pb-3 text-[14px] font-medium transition-colors",
                    session.activeView.kind === 'recent' 
                      ? "border-blue-600 text-slate-900 dark:border-blue-500 dark:text-slate-100" 
                      : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300"
                  )}
                >
                  最近                </button>
                <button 
                  onClick={() => updateSession((current) => ({ ...current, activeView: { kind: 'favorites' } }))}
                  className={cn(
                    "border-b-2 pb-3 text-[14px] font-medium transition-colors",
                    session.activeView.kind === 'favorites' 
                      ? "border-blue-600 text-slate-900 dark:border-blue-500 dark:text-slate-100" 
                      : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300"
                  )}
                >
                  收藏
                </button>
                <div className="ml-auto pb-3 relative">
                  <button 
                    onClick={() => setIsFilterOpen(!isFilterOpen)}
                    className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[13px] text-slate-500 hover:bg-slate-50 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                  >
                    <Filter size={14} />
                    筛选                  </button>

                  {isFilterOpen ? (
                    <div className="absolute right-0 top-full z-10 mt-1 w-36 rounded-lg border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-slate-900 py-1.5 shadow-lg">
                      <button
                        onClick={() => { setFilterType(null); setIsFilterOpen(false); }}
                        className="flex w-full items-center gap-3 px-3 py-1.5 text-left text-[13px] hover:bg-slate-50 dark:hover:bg-white/[0.05]"
                      >
                        <div className="flex h-5 w-5 items-center justify-center" />
                        <span className={cn(filterType === null ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-slate-700 dark:text-slate-300')}>全部类型</span>
                      </button>
                      <button
                        onClick={() => { setFilterType('pdf'); setIsFilterOpen(false); }}
                        className="flex w-full items-center gap-3 px-3 py-1.5 text-left text-[13px] hover:bg-slate-50 dark:hover:bg-white/[0.05]"
                      >
                        <img src={pdfIcon} alt="PDF" className="h-5 w-5 object-contain" />
                        <span className={cn(filterType === 'pdf' ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-slate-700 dark:text-slate-300')}>PDF 文档</span>
                      </button>
                      <button
                        onClick={() => { setFilterType('word'); setIsFilterOpen(false); }}
                        className="flex w-full items-center gap-3 px-3 py-1.5 text-left text-[13px] hover:bg-slate-50 dark:hover:bg-white/[0.05]"
                      >
                        <img src={wordIcon} alt="Word" className="h-5 w-5 object-contain" />
                        <span className={cn(filterType === 'word' ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-slate-700 dark:text-slate-300')}>Word 文档</span>
                      </button>
                      <button
                        onClick={() => { setFilterType('xlsx'); setIsFilterOpen(false); }}
                        className="flex w-full items-center gap-3 px-3 py-1.5 text-left text-[13px] hover:bg-slate-50 dark:hover:bg-white/[0.05]"
                      >
                        <img src={xlsxIcon} alt="Excel" className="h-5 w-5 object-contain" />
                        <span className={cn(filterType === 'xlsx' ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-slate-700 dark:text-slate-300')}>Excel 表格</span>
                      </button>
                      <button
                        onClick={() => { setFilterType('txt'); setIsFilterOpen(false); }}
                        className="flex w-full items-center gap-3 px-3 py-1.5 text-left text-[13px] hover:bg-slate-50 dark:hover:bg-white/[0.05]"
                      >
                        <img src={txtIcon} alt="TXT" className="h-5 w-5 object-contain" />
                        <span className={cn(filterType === 'txt' ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-slate-700 dark:text-slate-300')}>纯文本 (TXT)</span>
                      </button>
                      <button
                        onClick={() => { setFilterType('md'); setIsFilterOpen(false); }}
                        className="flex w-full items-center gap-3 px-3 py-1.5 text-left text-[13px] hover:bg-slate-50 dark:hover:bg-white/[0.05]"
                      >
                        <img src={mdIcon} alt="Markdown" className="h-5 w-5 object-contain" />
                        <span className={cn(filterType === 'md' ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-slate-700 dark:text-slate-300')}>Markdown</span>
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="flex-1 min-h-0 overflow-hidden flex flex-col relative">
                <div className="absolute inset-0 overflow-auto custom-scrollbar bg-white dark:bg-[#0B1120]">
                  <div className="min-w-[800px] flex flex-col min-h-full relative">
                    <div className="sticky top-0 z-30 grid grid-cols-[minmax(0,2.2fr)_140px_120px_140px_180px] gap-3 border-b border-slate-100 dark:border-white/[0.05] bg-white/95 dark:bg-[#0B1120]/95 backdrop-blur-sm px-6 py-2.5 text-[12px] font-medium text-slate-500 dark:text-slate-400">
                      <span>名称</span>
                      <span>文件夹</span>
                      <span>来源</span>
                      <span>更新时间</span>
                      <span>状态</span>
                    </div>

                    <div className="flex-1 flex flex-col relative py-2">
                      {visibleItems.length === 0 ? (
                        searchValue ? (
                          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                            <div className="flex h-16 w-16 items-center justify-center rounded-[24px] bg-slate-50 dark:bg-white/[0.02] text-slate-400 dark:text-slate-500">
                              <Search size={28} />
                            </div>
                            <div className="mt-5 text-[14px] font-medium text-slate-500 dark:text-slate-400">
                              没有找到匹配的文件
                            </div>
                          </div>
                        ) : null
                      ) : (
                        <div className="space-y-0">
                          {visibleItems.map((item) => {
                            const isEditing = editingItemId === item.id;
                            const folderLabel = getFolderPathLabel(session.folders, item.folderId);
                            return (
                              <div key={item.id}>
                                {isEditing ? (
                                  <div className="rounded-lg border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] px-4 py-3 shadow-sm">
                                    <input
                                      value={itemRenameDraft}
                                      onChange={(event) => setItemRenameDraft(event.target.value)}
                                      className="w-full rounded border border-slate-200 dark:border-white/[0.05] bg-slate-50 dark:bg-black/20 px-3 py-2 text-[14px] outline-none dark:text-slate-200"
                                    />
                                    <div className="mt-2 flex items-center justify-end gap-2">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setEditingItemId(null);
                                          setItemRenameDraft('');
                                        }}
                                        className="rounded px-3 py-1.5 text-[13px] font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/[0.05]"
                                      >
                                        取消
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => handleRenameItem(item.id)}
                                        className="rounded bg-blue-600 px-3 py-1.5 text-[13px] font-medium text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600"
                                      >
                                        保存
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <FileRow
                                    item={item}
                                    folderLabel={folderLabel}
                                    selected={session.selectedItemId === item.id}
                                    persistenceReady={binaryStoreReady}
                                    onOpen={() => openPreview(item.id)}
                                    onSelect={() => updateSession((current) => ({ ...current, selectedItemId: item.id }))}
                                    onToggleStar={() => updateItem(item.id, (current) => ({ ...current, starred: !current.starred, updatedAt: new Date().toISOString() }))}
                                    onRename={() => {
                                      setEditingItemId(item.id);
                                      setItemRenameDraft(item.name);
                                    }}
                                    onTrash={() => {
                                      updateItem(item.id, (current) => ({
                                        ...current,
                                        trashed: !current.trashed,
                                        updatedAt: new Date().toISOString(),
                                      }));
                                      if (session.selectedItemId === item.id) {
                                        updateSession((current) => ({ ...current, selectedItemId: null }));
                                      }
                                    }}
                                    onDownload={() => handleDownloadItem(item)}
                                    onDragStart={(event) => handleDragStart(item.id, event)}
                                  />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {isToolboxOpen ? (
              <aside className="border-l border-slate-200 dark:border-white/[0.05] bg-white dark:bg-[#0B1120] min-h-0 overflow-y-auto custom-scrollbar">
                {renderToolbox('dock')}
              </aside>
            ) : null}
          </div>
        </div>
      </div>

      <input
        ref={homepageUploadInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          handleHomepageUpload(event.target.files);
          event.currentTarget.value = '';
        }}
      />
      <input
        ref={module2UploadInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          const files = Array.from(event.target.files || []);
          const items = appendFilesToWorkbench(files);
          if (items.length > 0) {
            stageForModule2(items.map((item) => item.id));
          }
          event.currentTarget.value = '';
        }}
      />
      <input
        ref={module4UploadInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          const files = Array.from(event.target.files || []);
          const items = appendFilesToWorkbench(files);
          if (items.length > 0) {
            stageForModule4(items.map((item) => item.id));
          }
          event.currentTarget.value = '';
        }}
      />
      <input
        ref={module3TemplateInputRef}
        type="file"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (!file) return;
          appendFilesToWorkbench([file], { selectFirst: false });
          void syncTemplateToModule3(file);
          event.currentTarget.value = '';
        }}
      />
      <input
        ref={module3SourceInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          const files = Array.from(event.target.files || []);
          if (files.length === 0) return;
          appendFilesToWorkbench(files, { selectFirst: false });
          void syncSourceToModule3(files);
          event.currentTarget.value = '';
        }}
      />

      <AnimatePresence>
        {contextMenu ? (
          <div
            className="fixed inset-0 z-50"
            onClick={() => setContextMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault();
              setContextMenu(null);
            }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.1 }}
              className="absolute w-40 rounded-lg border border-slate-200 bg-white py-1.5 shadow-lg"
              style={{ left: contextMenu.x, top: contextMenu.y }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                onClick={() => {
                  setEditingFolderId(contextMenu.folderId);
                  setFolderRenameDraft(contextFolder?.name || '');
                  setContextMenu(null);
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-[13px] text-slate-700 hover:bg-slate-100"
              >
                <PencilLine size={14} />
                重命名
              </button>
              {contextFolder?.parentId ? (
                <button
                  type="button"
                  onClick={() => {
                    const removedFolderIds = new Set([
                      contextMenu.folderId,
                      ...collectDescendantFolderIds(session.folders, contextMenu.folderId),
                    ]);
                    const nextUpdatedAt = new Date().toISOString();

                    updateSession((current) => ({
                      ...current,
                      folders: current.folders.filter((folder) => !removedFolderIds.has(folder.id)),
                      items: current.items.map((item) => (
                        item.folderId && removedFolderIds.has(item.folderId)
                          ? { ...item, folderId: HOME_WORKBENCH_ROOT_FOLDER_ID, updatedAt: nextUpdatedAt }
                          : item
                      )),
                      activeView: current.activeView.kind === 'folder' && removedFolderIds.has(current.activeView.folderId)
                        ? { kind: 'folder', folderId: HOME_WORKBENCH_ROOT_FOLDER_ID }
                        : current.activeView,
                    }));
                    setExpandedFolderIds((current) => current.filter((folderId) => !removedFolderIds.has(folderId)));
                    setContextMenu(null);
                    pushToast('good', '文件夹已删除，内部文件已归入“我的文件”。');
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-[13px] text-red-600 hover:bg-red-50"
                >
                  <Trash2 size={14} />
                  删除文件夹
                </button>
              ) : null}
            </motion.div>
          </div>
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {toast ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="absolute bottom-6 right-6 z-[80]"
          >
            <div
              className={cn(
                'rounded-2xl border px-4 py-3 text-sm shadow-[0_20px_50px_-30px_rgba(57,75,105,0.42)] backdrop-blur-xl',
                toast.tone === 'good' && 'border-[#cfe8db] bg-white/96 text-[#24593f]',
                toast.tone === 'warn' && 'border-[#f0e0bf] bg-white/96 text-[#8f641f]',
                toast.tone === 'error' && 'border-[#f2d3ce] bg-white/96 text-[#a24f45]',
                toast.tone === 'info' && 'border-[#d6e2f1] bg-white/96 text-[#31557f]'
              )}
            >
              <div className="flex items-center gap-2">
                {toast.tone === 'good' ? <CheckCircle2 size={16} /> : toast.tone === 'warn' || toast.tone === 'error' ? <AlertTriangle size={16} /> : <BrainCircuit size={16} />}
                <span>{toast.text}</span>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {module4BannerVisible ? (
          <motion.div
            initial={{ opacity: 0, y: -16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            className="absolute left-1/2 top-5 z-[72] -translate-x-1/2"
          >
            <div className="flex items-center gap-3 rounded-full border border-[#d9e4f2] bg-white/96 px-4 py-2 text-sm text-[#325178] shadow-[0_18px_42px_-28px_rgba(76,97,128,0.34)] backdrop-blur-xl">
              <GitGraph size={16} />
              <span>已有文件从首页加入模块四候选清单。模块四会优先显示图谱工作台，建议先在模块二完成抽取再继续。</span>
              <button
                type="button"
                onClick={() => {
                  clearModule4DraftFromHomeWorkbench();
                  setModule4BannerVisible(false);
                }}
                className="rounded-full p-1 text-[#7f93ab] transition hover:bg-[#eef4fb] hover:text-[#34567f]"
              >
                <X size={14} />
              </button>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {previewItem ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-[70] bg-[#F2F3F5] dark:bg-[#0B1120]"
          >
            <div className="flex h-full flex-col">
              <header className="flex items-center justify-between border-b border-slate-200 dark:border-white/[0.05] bg-white dark:bg-[#0B1120] px-5 py-3 shadow-sm dark:shadow-none">
                <div className="flex min-w-0 items-center gap-4">
                  <button
                    type="button"
                    onClick={() => setPreviewItemId(null)}
                    className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[14px] font-medium text-slate-600 dark:text-slate-400 transition hover:bg-slate-100 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                  >
                    <ChevronLeft size={16} />
                    返回
                  </button>
                  <div className="h-4 w-px bg-slate-200 dark:bg-white/[0.05]" />
                  <div className="min-w-0">
                    <div className="truncate text-[14px] font-semibold text-slate-800 dark:text-slate-200">{previewItem.name}</div>
                    <div className="mt-0.5 text-[12px] text-slate-500 dark:text-slate-400">
                      {formatBytes(previewItem.size)}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {previewMode === 'pdf' ? (
                    <>
                      <button
                        type="button"
                        onClick={() => setPdfViewMode((current) => (current === 'fit-width' ? 'fit-page' : current === 'fit-page' ? 'actual' : 'fit-width'))}
                        className="rounded-md border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] px-3 py-1.5 text-[13px] font-medium text-slate-600 dark:text-slate-400 transition hover:bg-slate-50 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                      >
                        {pdfViewMode === 'fit-width' ? '适应宽度' : pdfViewMode === 'fit-page' ? '适应页面' : '实际大小'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setPreviewScale((current) => Math.min(current + 0.1, 2.2))}
                        className="rounded-md border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] p-1.5 text-slate-600 dark:text-slate-400 transition hover:bg-slate-50 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                      >
                        <ZoomIn size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setPreviewScale((current) => Math.max(current - 0.1, 0.6))}
                        className="rounded-md border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] p-1.5 text-slate-600 dark:text-slate-400 transition hover:bg-slate-50 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                      >
                        <ZoomOut size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setPreviewRotation((current) => (current + 90) % 360)}
                        className="rounded-md border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] p-1.5 text-slate-600 dark:text-slate-400 transition hover:bg-slate-50 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                      >
                        <RotateCw size={16} />
                      </button>
                    </>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setPreviewToolboxOpen((value) => !value)}
                    className="rounded-md border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] px-3 py-1.5 text-[13px] font-medium text-slate-600 dark:text-slate-400 transition hover:bg-slate-50 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                  >
                    {previewToolboxOpen ? '隐藏工具箱' : '显示工具箱'}
                  </button>
                </div>
              </header>

              <div className="relative flex min-h-0 flex-1 overflow-hidden bg-[#F2F3F5] dark:bg-[#0B1120]">
                <div className="min-h-0 flex-1 overflow-hidden relative">
                  {!previewHasLiveSource ? (
                    <div className="flex h-full flex-col items-center justify-center rounded-none border-0 bg-white dark:bg-[#0B1120] px-8 text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-[24px] border border-[#dbe5f0] dark:border-white/[0.05] bg-[#f7fbff] dark:bg-white/[0.02] text-[#2d64aa] dark:text-slate-400">
                        <AlertTriangle size={28} />
                      </div>
                      <div className="mt-5 text-xl font-semibold text-[#1d2d43] dark:text-slate-200">当前会话里已缺少文件原文</div>
                      <div className="mt-2 max-w-xl text-sm leading-7 text-[#6c7d92] dark:text-slate-400">
                        这个队列条目仍保留元数据，但用于预览和拖入模块的原始文件已经不在当前浏览器会话中。请重新上传它，以恢复完整操作能力。
                      </div>
                    </div>
                  ) : previewMode === 'pdf' ? (
                    previewItem.status === 'converting' && !previewSource ? (
                      <div className="flex h-full flex-col items-center justify-center rounded-none border-0 bg-white dark:bg-[#0B1120]">
                        <Loader2 size={34} className="animate-spin text-[#3267ad] dark:text-blue-400" />
                        <div className="mt-4 text-xl font-semibold text-[#1f3047] dark:text-slate-200">正在把 Word 转为 PDF 预览</div>
                        <div className="mt-2 text-sm text-[#6b7d92] dark:text-slate-400">转换完成后会直接进入全屏 PDF 预览。</div>
                      </div>
                    ) : previewItem.status === 'error' && !previewSource ? (
                      <div className="flex h-full flex-col items-center justify-center rounded-none border-0 bg-white dark:bg-[#0B1120] px-8 text-center">
                        <AlertTriangle size={32} className="text-[#bb5b4f] dark:text-red-400" />
                        <div className="mt-4 text-xl font-semibold text-[#1f3047] dark:text-slate-200">PDF 预览准备失败</div>
                        <div className="mt-2 max-w-lg text-sm leading-7 text-[#6b7d92] dark:text-slate-400">
                          {previewItem.errorMessage || 'Word 转 PDF 失败，请稍后重试。'}
                        </div>
                        <button
                          type="button"
                          onClick={handleRetryPreviewConversion}
                          className="mt-5 inline-flex items-center rounded-md border border-slate-200 dark:border-white/[0.05] bg-white dark:bg-white/[0.02] px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 transition hover:bg-slate-50 dark:hover:bg-white/[0.05]"
                        >
                          重新尝试
                        </button>
                      </div>
                    ) : previewSource ? (
                      <div className="h-full w-full overflow-hidden bg-white dark:bg-[#0B1120]">
                        <PdfJsViewer
                          src={previewSource}
                          scale={previewScale}
                          rotation={previewRotation}
                          viewMode={pdfViewMode}
                        />
                      </div>
                    ) : null
                  ) : previewMode === 'image' && previewSource ? (
                    <div className="flex h-full items-center justify-center overflow-auto rounded-none border-0 bg-white dark:bg-[#0B1120]">
                      <img
                        src={previewSource}
                        alt={previewItem.name}
                        className="max-h-full max-w-full object-contain"
                        style={{ transform: `scale(${previewScale}) rotate(${previewRotation}deg)` }}
                      />
                    </div>
                  ) : previewMode === 'text' ? (
                    <div className="h-full overflow-auto rounded-none border-0 bg-white dark:bg-[#0B1120] px-8 py-7 custom-scrollbar">
                      <pre className="whitespace-pre-wrap break-words text-[15px] leading-8 text-[#26384f] dark:text-slate-300">
                        {previewTextMap[previewItem.id] || '正在加载文本预览...'}
                      </pre>
                    </div>
                  ) : previewMode === 'spreadsheet' && getHomeWorkbenchFile(previewItem.id) ? (
                    <div className="h-full overflow-hidden rounded-none border-0 bg-white dark:bg-[#0B1120]">
                      <LuckysheetPreview file={getHomeWorkbenchFile(previewItem.id)} />
                    </div>
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center rounded-none border-0 bg-white dark:bg-[#0B1120] px-8 text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-[24px] border border-[#dbe5f0] dark:border-white/[0.05] bg-[#f7fbff] dark:bg-white/[0.02]">
                        {getItemIcon(previewItem, 'h-8 w-8 object-contain drop-shadow-sm opacity-80')}
                      </div>
                      <div className="mt-5 text-xl font-semibold text-[#1d2d43] dark:text-slate-200">当前格式暂不支持浏览器内预览</div>
                      <div className="mt-2 max-w-xl text-sm leading-7 text-[#6c7d92] dark:text-slate-400">
                        你可以先下载原文件，或者直接把它送入右侧工具箱中的对应模块继续处理。
                      </div>
                    </div>
                  )}
                </div>

                <AnimatePresence>
                  {previewToolboxOpen ? (
                    <motion.aside
                      initial={{ opacity: 0, x: 32 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 32 }}
                      transition={{ duration: 0.22 }}
                      className="shrink-0 w-[300px] lg:w-[320px] border-l border-slate-200 dark:border-white/[0.05] bg-[#F2F3F5] dark:bg-[#0B1120] shadow-[-4px_0_12px_rgba(0,0,0,0.03)] dark:shadow-none z-10"
                    >
                      <div className="h-full overflow-y-auto custom-scrollbar">
                        {renderToolbox('drawer')}
                      </div>
                    </motion.aside>
                  ) : null}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {uploadDialogFiles ? (
          <div className="absolute inset-0 z-[100] flex items-center justify-center bg-slate-900/20 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md rounded-xl bg-white shadow-xl"
            >
              <div className="border-b border-slate-100 px-6 py-4">
                <h3 className="text-lg font-semibold text-slate-800">上传 {uploadDialogFiles.length} 个文件</h3>
              </div>
              <div className="px-6 py-5">
                <div className="mb-3 text-[13px] font-medium text-slate-700">选择目标文件夹</div>
                <div className="space-y-2">
                  <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-200 p-3 hover:bg-slate-50">
                    <input
                      type="radio"
                      name="upload-folder"
                      checked={!isCreatingFolderInUpload}
                      onChange={() => setIsCreatingFolderInUpload(false)}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <select
                      value={uploadTargetFolderId || HOME_WORKBENCH_ROOT_FOLDER_ID}
                      onChange={(e) => setUploadTargetFolderId(e.target.value)}
                      disabled={isCreatingFolderInUpload}
                      className="flex-1 bg-transparent text-[14px] outline-none disabled:opacity-50"
                    >
                      {session.folders.map(f => (
                        <option key={f.id} value={f.id}>{f.name}</option>
                      ))}
                    </select>
                  </label>

                  <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-200 p-3 hover:bg-slate-50">
                    <input
                      type="radio"
                      name="upload-folder"
                      checked={isCreatingFolderInUpload}
                      onChange={() => setIsCreatingFolderInUpload(true)}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <div className="flex flex-1 items-center gap-2">
                      <span className="text-[14px] text-slate-700 disabled:opacity-50">新建文件夹</span>
                      <input
                        value={uploadNewFolderDraft}
                        onChange={(e) => setUploadNewFolderDraft(e.target.value)}
                        disabled={!isCreatingFolderInUpload}
                        placeholder="输入文件夹名称"
                        className="flex-1 rounded border border-slate-200 px-2 py-1 text-[13px] outline-none focus:border-blue-500 disabled:opacity-50"
                      />
                    </div>
                  </label>
                </div>
              </div>
              <div className="flex items-center justify-end gap-3 border-t border-slate-100 bg-slate-50 px-6 py-4 rounded-b-xl">
                <button
                  type="button"
                  onClick={cancelUpload}
                  className="rounded-lg px-4 py-2 text-[14px] font-medium text-slate-600 hover:bg-slate-200 transition-colors"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={confirmUpload}
                  className="rounded-lg bg-blue-600 px-5 py-2 text-[14px] font-medium text-white hover:bg-blue-700 transition-colors"
                >
                  确认上传
                </button>
              </div>
            </motion.div>
          </div>
        ) : null}
      </AnimatePresence>
    </div>
  );
};

