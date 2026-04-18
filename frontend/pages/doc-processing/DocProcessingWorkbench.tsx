import React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { 
  Send, Paperclip, 
  FileText, X, CheckCircle, Plus, Palette, Loader,
  FileUp, Brain, Download, Eye,
  ChevronLeft, ChevronRight, Diff,
  Maximize2, Minimize2, Clock, AlertCircle,
  ZoomIn, ZoomOut, RotateCw, Layers, ScanLine, Trash2,
  UploadCloud, Sparkles
} from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { Image } from 'lucide-react';

import AppLogoImage from '../../assets/app-logo.png';
import SmartDocWordmarkImage from '../../assets/smart-doc-wordmark.svg';
import RightExpandImage from '../../assets/right-expand.svg';
import AssistantAvatarImage from '../../assets/文心智能体-copy.png';
import PdfIconImage from '../../assets/pdf.png';
import DialogIllustrationImage from '../../assets/对话框插图.png';
import WordIconImage from '../../assets/WORD.png';
import TxtIconImage from '../../assets/txt.png';
import ExcelIconImage from '../../assets/xlsx.png';
import CustomDocIconImage from '../../assets/文档.png';

import { LuckysheetPreview } from './LuckysheetPreview';
import { ReportSelectionToolbar } from './ReportSelectionToolbar';
import { prepareReportContent } from './lib/reportFormatting.js';
import { applyReportQuickEdit, type ReportQuickEditAction } from './lib/reportQuickEdit';
import {
  adjustReportFormattingAfterTextReplacement,
  applyBlockFormatPatch,
  applyInlineFormatToSelection,
  buildReportTextSegments,
  cloneReportFormatting,
  DEFAULT_REPORT_TEXT_ALIGN,
  getInlineStyleForSelection,
  type ReportBlockType,
  type ReportFormattingState,
  type ReportHistorySnapshot,
  type ReportTextAlign,
} from './lib/reportRichFormatting';
import {
  clearBrowserSelection,
  extractReportSelection,
  type ReportSelectionSnapshot,
} from './lib/reportSelection';
import { buildModule1ApiUrl } from '@/shared/api/module1';
import { consumeModule1DraftFromHomeWorkbench } from '../../shared/state/homeWorkbench';

const pdfWorkerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();
pdfjs.GlobalWorkerOptions.workerSrc = `${pdfWorkerSrc}?v=${pdfjs.version}`;
const PLATFORM_ICON_SRC = AssistantAvatarImage;
const SMART_DOC_WORDMARK_SRC = SmartDocWordmarkImage;
const SIDEBAR_TOGGLE_ICON_SRC = RightExpandImage;
const ALLOWED_UPLOAD_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt', '.xlsx', '.md', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'];
const MAX_UPLOAD_FILE_SIZE = 20 * 1024 * 1024;
const WORD_PREVIEW_FALLBACK_MESSAGE = '当前环境暂时无法把 Word 转成 PDF 预览，你仍然可以继续处理并下载原文件。';
const SAVEABLE_REPORT_EXTENSIONS = new Set(['doc', 'docx', 'txt', 'md', 'csv']);
const FILE_TYPE_ICON_MAP: Record<string, string> = {
  pdf: PdfIconImage,
  doc: WordIconImage,
  docx: WordIconImage,
  txt: TxtIconImage,
  md: TxtIconImage,
  xls: ExcelIconImage,
  xlsx: ExcelIconImage,
};
const METALLIC_PRIMARY_BUTTON_CLASS = `
  relative
  border border-[#2f62e8]
  bg-[rgb(42,100,246)]
  text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12),0_10px_24px_-16px_rgba(42,100,246,0.42)]
  hover:-translate-y-0.5 hover:border-[#2555d7] hover:bg-[rgb(32,88,232)]
  hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.16),0_14px_28px_-16px_rgba(42,100,246,0.48)]
  active:translate-y-0 active:scale-[0.98]
  transition-all duration-200
`.replace(/\s+/g, ' ').trim();

const METALLIC_SECONDARY_BUTTON_CLASS = `
  relative
  border border-[#c9dbfb]
  bg-white
  text-[#18406f] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.88),0_8px_18px_-16px_rgba(42,100,246,0.18)]
  hover:-translate-y-0.5 hover:border-[#aac6fb] hover:bg-[#f7faff]
  hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.94),0_12px_24px_-16px_rgba(42,100,246,0.22)]
  dark:border-slate-700/80
  dark:bg-slate-900/88
  dark:text-slate-100
  dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04),0_12px_28px_-18px_rgba(15,23,42,0.7)]
  dark:hover:border-slate-600
  dark:hover:bg-slate-800/92
  dark:hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06),0_16px_32px_-18px_rgba(15,23,42,0.82)]
  transition-all duration-200
`.replace(/\s+/g, ' ').trim();
const METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS = `
  relative
  border border-[#9fc0fb]
  bg-[#edf4ff]
  text-[#123d75] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.9),0_10px_22px_-18px_rgba(42,100,246,0.22)]
  dark:border-sky-500/40
  dark:bg-sky-500/12
  dark:text-sky-100
  dark:shadow-[inset_0_0_0_1px_rgba(125,211,252,0.14),0_14px_28px_-18px_rgba(14,165,233,0.22)]
`.replace(/\s+/g, ' ').trim();
const COBALT_GLASS_BUTTON_CLASS = `
  relative
  border border-[#2f62e8]
  bg-[rgb(42,100,246)]
  text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12),0_10px_24px_-16px_rgba(42,100,246,0.42)]
  transition-all duration-200
  hover:-translate-y-0.5 hover:border-[#2555d7] hover:bg-[rgb(32,88,232)]
  hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.16),0_14px_28px_-16px_rgba(42,100,246,0.48)]
  active:translate-y-0 active:scale-[0.98]
`.replace(/\s+/g, ' ').trim();
const METALLIC_PANEL_CLASS = 'border border-[#e2ebfb] bg-white shadow-[0_18px_40px_-34px_rgba(42,100,246,0.14)] dark:border-slate-800/80 dark:bg-slate-900/88 dark:shadow-[0_28px_50px_-34px_rgba(2,6,23,0.82)]';
const METALLIC_PANEL_SOFT_CLASS = 'border border-[#e8effc] bg-[#fbfdff] dark:border-slate-800/80 dark:bg-slate-950/72';
const METALLIC_EMPTY_STATE_CLASS = 'border border-dashed border-[#d7e4fb] bg-[#fbfdff] dark:border-slate-700/80 dark:bg-slate-950/48';
const METALLIC_PREVIEW_TAG_CLASS = 'border border-[#d4e3ff] bg-[#f3f8ff] text-[#1b4d8f] shadow-[0_8px_18px_-16px_rgba(42,100,246,0.16)] dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100 dark:shadow-none';
const LANDING_CORNER_BUTTON_CLASS = `
  border border-[#d7e2f7]
  bg-white/92
  text-[#4d5d74]
  shadow-[0_10px_22px_-18px_rgba(86,104,145,0.42)]
  backdrop-blur-md
  transition-all duration-200
  hover:-translate-y-0.5 hover:border-[#c7d7f3] hover:bg-white
  dark:border-slate-700/80
  dark:bg-slate-900/88
  dark:text-slate-200
  dark:shadow-[0_16px_30px_-22px_rgba(2,6,23,0.84)]
  dark:hover:border-slate-600
  dark:hover:bg-slate-800/92
`.replace(/\s+/g, ' ').trim();
const LANDING_SUGGESTION_BUTTON_CLASS = `
  inline-flex items-center gap-2 rounded-full border border-[#d7e2f7]
  bg-white/82 px-4 py-2.5 text-[13px] font-medium text-[#6f82a0]
  shadow-[0_10px_24px_-24px_rgba(75,98,150,0.32)]
  backdrop-blur-sm transition-all duration-200
  hover:-translate-y-0.5 hover:border-[#c6d6f3] hover:bg-white hover:text-[#4f6b92]
  disabled:cursor-not-allowed disabled:opacity-50
  dark:border-slate-700 dark:bg-slate-900/88 dark:text-slate-200
  dark:hover:border-slate-600 dark:hover:bg-slate-800 dark:hover:text-sky-200
`.replace(/\s+/g, ' ').trim();

const isFileDragEvent = (dataTransfer: DataTransfer | null) => (
  Array.from(dataTransfer?.types ?? []).includes('Files')
);

// ---------- 类型定义 ----------
interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system';
  content: string;
  fileIds?: string[];
  displayMode?: 'chat' | 'report';
  timestamp: Date;
}

interface FileInfo {
  id: string;
  name: string;
  size: number;
  type: string;
  content?: string;
  uploadTime: Date;
  status: 'uploading' | 'ready' | 'error' | 'processing' | 'completed' | 'converting';
  progress?: number;
  file?: File;
  preview?: string;
  previewType?: string;
  previewBlob?: Blob;
  conversionStatus?: 'idle' | 'converting' | 'ready' | 'error';
  convertedPdfBlob?: Blob;
  convertedPdfFileName?: string;
  result?: string;
  error?: string;
  originalFile?: File; // 保存原始文件用于操作
  sourceFileId?: string;
}

interface Modification {
  type: string;
  target?: string;
  changes?: any;
  old_text?: string;
  new_text?: string;
  rows?: number;
  cols?: number;
  position?: string;
  preview?: {
    before?: string;
    after?: string;
    description?: string;
  };
  [key: string]: any;
}

interface OperationResult {
  success: boolean;
  instruction: string;
  ai_explanation: string;
  modifications: Modification[];
  file_info: {
    name: string;
    type: string;
    size: number;
  };
  preview?: {
    name: string;
    content: string;
    type: string;
  };
}

interface ConversationRecord {
  id: string;
  title: string;
  titleEdited: boolean;
  createdAt: Date;
  updatedAt: Date;
  messages: Message[];
  files: Record<string, FileInfo>;
  composerFileIds: string[];
  rememberedFileBatchIds: string[];
  selectedFileId: string | null;
  inputText: string;
  previewPaneMode: PreviewPaneMode;
  previewReadingMode: PdfReadingMode;
  showPreviewPanel: boolean;
}

interface PromptSuggestionItem {
  label: string;
  prompt: string;
  icon: React.ComponentType<{ size?: number }>;
}

interface ReportBlock {
  key: string;
  type: ReportBlockType;
  text: string;
}

interface PreparedReportContent {
  text: string;
  blocks: ReportBlock[];
  visualTone: 'analysis' | 'extraction' | 'risk';
}

interface ActiveReportSelection extends ReportSelectionSnapshot {
  fileId: string;
  reportVersionKey: string;
}

type ReportProgressStatus = 'idle' | 'active' | 'completed' | 'fallback' | 'failed';

interface ReportProgressState {
  visible: boolean;
  fileId: string | null;
  stageId: string;
  label: string;
  description: string;
  progress: number;
  status: ReportProgressStatus;
}

const REPORT_TONE_STYLES: Record<PreparedReportContent['visualTone'], {
  heading1: string;
  heading2: string;
  heading3: string;
  paragraph: string;
}> = {
  analysis: {
    heading1: 'mt-10 border-b border-[#d9e6f7] pb-3 text-[1.46rem] font-extrabold tracking-[0.025em] text-[#0f172a] first:mt-0 dark:border-slate-700 dark:text-white',
    heading2: 'mt-7 text-[1.16rem] font-bold tracking-[0.015em] text-[#111827] first:mt-0 dark:text-slate-100',
    heading3: 'mt-4 text-[1rem] font-semibold tracking-[0.01em] text-[#1f2937] first:mt-0 dark:text-sky-200',
    paragraph: 'mt-3.5 text-[15.5px] leading-9 tracking-[0.012em] text-[#111827] first:mt-0 dark:text-slate-200',
  },
  extraction: {
    heading1: 'mt-9 border-b border-[#dbe6f3] pb-3 text-[1.34rem] font-extrabold tracking-[0.02em] text-[#0f172a] first:mt-0 dark:border-slate-700 dark:text-slate-50',
    heading2: 'mt-6 text-[1.08rem] font-bold tracking-[0.01em] text-[#111827] first:mt-0 dark:text-slate-100',
    heading3: 'mt-4 text-[0.96rem] font-semibold tracking-[0.01em] text-[#1f2937] first:mt-0 dark:text-slate-300',
    paragraph: 'mt-3.5 text-[14.8px] leading-9 tracking-[0.012em] text-[#111827] first:mt-0 dark:text-slate-200',
  },
  risk: {
    heading1: 'mt-9 border-b border-[#f0d7d2] pb-3 text-[1.38rem] font-extrabold tracking-[0.03em] text-[#111827] first:mt-0 dark:border-rose-900/50 dark:text-rose-100',
    heading2: 'mt-6 text-[1.12rem] font-bold tracking-[0.01em] text-[#111827] first:mt-0 dark:text-rose-200',
    heading3: 'mt-4 text-[0.98rem] font-semibold tracking-[0.01em] text-[#1f2937] first:mt-0 dark:text-amber-200',
    paragraph: 'mt-3.5 text-[15.2px] leading-9 tracking-[0.012em] text-[#111827] first:mt-0 dark:text-slate-200',
  },
};

const INITIAL_LANDING_SUGGESTIONS: PromptSuggestionItem[] = [
  {
    label: '总结重点',
    prompt: '总结这份材料的核心重点，并按条列出关键结论',
    icon: FileText
  },
  {
    label: '提取信息',
    prompt: '提取这份材料里的关键信息、字段和结构化要点',
    icon: ScanLine
  },
  {
    label: '内容优化',
    prompt: '基于当前内容生成一版更完整、更清晰的文档',
    icon: Diff
  },
  {
    label: '检查风险',
    prompt: '检查这份文档里可能存在的风险点、歧义或不严谨表达',
    icon: AlertCircle
  },
  {
    label: '优化格式',
    prompt: '优化这份文档的结构、格式和表达风格',
    icon: Palette
  },
  {
    label: '替换内容',
    prompt: '帮我把文档中的指定内容替换成新的表述，并保持整体风格一致',
    icon: Sparkles
  }
];

// 布局模式
type LayoutMode = 'default' | 'compact' | 'expanded';
type PreviewPaneMode = 'report' | 'current' | 'original' | 'compare';
type PdfReadingMode = 'scroll' | 'paged';
type PreviewCategory = 'pdf' | 'excel' | 'text' | 'image' | 'word' | 'other';

const REPORT_ACTION_FEEDBACK: Record<ReportQuickEditAction, string> = {
  rewrite: '已改写选中文本',
  expand: '已扩写选中文本',
  condense: '已精简选中文本',
  polish: '已润色选中文本',
};
const formatPreparedReportContent = (content: string): PreparedReportContent => (
  prepareReportContent(content) as PreparedReportContent
);

const createReportProgressState = (
  partial?: Partial<ReportProgressState>,
): ReportProgressState => ({
  visible: false,
  fileId: null,
  stageId: 'idle',
  label: '',
  description: '',
  progress: 0,
  status: 'idle',
  ...partial,
});

const buildReportVersionKey = (fileId: string, messageId: string): string => `${fileId}::${messageId}`;

// 辅助函数
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

const fileExt = (name: string) => name.split('.').pop()?.toLowerCase() ?? '';
const getCapabilityFileName = (file?: FileInfo | null) => file?.originalFile?.name || file?.name || '';
const getCapabilityFileExt = (file?: FileInfo | null) => fileExt(getCapabilityFileName(file));
const getFileIconUrl = (file?: FileInfo | null) => {
  const iconUrl = FILE_TYPE_ICON_MAP[getCapabilityFileExt(file)];
  if (!iconUrl) return null;
  return iconUrl;
};

const prefixModifiedFileName = (name: string) => {
  if (!name) return '(修改版)未命名文件';
  if (name.startsWith('(修改版)')) return name;
  return `(修改版)${name}`;
};

const guessMimeTypeFromName = (name: string): string => {
  const ext = fileExt(name);

  switch (ext) {
    case 'pdf':
      return 'application/pdf';
    case 'doc':
      return 'application/msword';
    case 'docx':
      return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    case 'txt':
      return 'text/plain';
    case 'md':
    case 'markdown':
      return 'text/markdown';
    case 'csv':
      return 'text/csv';
    case 'xls':
      return 'application/vnd.ms-excel';
    case 'xlsx':
      return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg';
    case 'png':
      return 'image/png';
    case 'gif':
      return 'image/gif';
    case 'bmp':
      return 'image/bmp';
    case 'webp':
      return 'image/webp';
    case 'svg':
      return 'image/svg+xml';
    default:
      return 'application/octet-stream';
  }
};

const normalizeReportSegment = (value: string): string => (
  String(value || '').replace(/\s+/g, ' ').trim()
);

const replaceSelectionInPreparedReport = (
  preparedReport: PreparedReportContent,
  selection: ReportSelectionSnapshot,
  replacementText: string,
): string | null => {
  let blockStart = 0;

  for (let index = 0; index < preparedReport.blocks.length; index += 1) {
    const block = preparedReport.blocks[index];
    const blockEnd = blockStart + block.text.length;

    if (block.key === selection.blockKey) {
      const startOffset = Math.min(Math.max(selection.startOffset, 0), block.text.length);
      const endOffset = Math.min(Math.max(selection.endOffset, startOffset), block.text.length);
      const selectedText = block.text.slice(startOffset, endOffset);

      if (
        normalizeReportSegment(selectedText)
        && normalizeReportSegment(selection.selectedText)
        && normalizeReportSegment(selectedText) !== normalizeReportSegment(selection.selectedText)
      ) {
        return null;
      }

      const reportStart = blockStart + startOffset;
      const reportEnd = blockStart + endOffset;
      return `${preparedReport.text.slice(0, reportStart)}${replacementText}${preparedReport.text.slice(reportEnd)}`;
    }

    blockStart = blockEnd + (index < preparedReport.blocks.length - 1 ? 2 : 0);
  }

  return null;
};

const downloadBlob = (blob: Blob, fileName: string): void => {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.setTimeout(() => URL.revokeObjectURL(url), 100);
};

const parseContentDispositionFilename = (headerValue: string | null): string | null => {
  if (!headerValue) return null;

  const utf8Match = headerValue.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const plainMatch = headerValue.match(/filename="?([^"]+)"?/i);
  return plainMatch?.[1] ?? null;
};

const waitForNextPaint = async (): Promise<void> => {
  if (typeof window === 'undefined') return;
  await new Promise<void>((resolve) => {
    window.requestAnimationFrame(() => resolve());
  });
};

const resolveFileMimeType = (rawMime: string | undefined, fileName: string): string => {
  const normalizedMime = String(rawMime || '').toLowerCase().trim();

  if (normalizedMime && normalizedMime !== 'application/octet-stream') {
    return normalizedMime;
  }

  return guessMimeTypeFromName(fileName);
};

const parseApiErrorMessage = async (response: Response): Promise<string> => {
  try {
    const bodyText = (await response.text()).trim();
    if (!bodyText) return `HTTP ${response.status}`;

    try {
      const payload = JSON.parse(bodyText) as { error?: string; detail?: string; message?: string };
      const fallback = String(payload.error || payload.detail || payload.message || '').trim();
      return fallback || bodyText;
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

const getPreviewCategory = (file?: FileInfo | null): PreviewCategory => {
  if (!file) return 'other';

  const ext = fileExt(file.name);
  const mime = String(file.previewType || file.type || '').toLowerCase();
  const hasSpecificMime = Boolean(mime && mime !== 'application/octet-stream');

  if (mime.includes('pdf')) return 'pdf';
  if (mime.includes('sheet') || mime.includes('excel')) return 'excel';
  if (mime.startsWith('text/')) return 'text';
  if (mime.startsWith('image/')) return 'image';
  if (mime.includes('wordprocessingml') || mime.includes('msword')) return 'word';

  if (!hasSpecificMime && ext === 'pdf') return 'pdf';
  if (!hasSpecificMime && ['xlsx', 'xls'].includes(ext)) return 'excel';
  if (!hasSpecificMime && ['txt', 'md', 'markdown', 'csv'].includes(ext)) return 'text';
  if (!hasSpecificMime && ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) return 'image';
  if (!hasSpecificMime && ['doc', 'docx'].includes(ext)) return 'word';

  return 'other';
};

const getRenderablePreviewCategory = (file?: FileInfo | null): PreviewCategory => {
  if (!file) return 'other';
  if (file.convertedPdfBlob) return 'pdf';
  return getPreviewCategory(file);
};

const getCycledItems = <T,>(items: T[], start: number, count: number): T[] => {
  if (items.length <= count) {
    return items;
  }

  return Array.from({ length: Math.min(count, items.length) }, (_, index) => items[(start + index) % items.length]);
};

const getExistingFileIds = (
  fileMap: Record<string, FileInfo>,
  candidateIds: string[] | undefined
): string[] => Array.from(new Set((candidateIds ?? []).filter((id) => Boolean(fileMap[id]))));

const getFilesByIds = (
  fileMap: Record<string, FileInfo>,
  ids: string[] | undefined
): FileInfo[] => getExistingFileIds(fileMap, ids).map((id) => fileMap[id]);

const removeFileIds = (ids: string[], idsToRemove: string[]): string[] => {
  if (ids.length === 0 || idsToRemove.length === 0) return ids;
  const idsToRemoveSet = new Set(idsToRemove);
  return ids.filter((id) => !idsToRemoveSet.has(id));
};

const buildConversationContextPayload = (conversationMessages: Message[]): string => JSON.stringify(
  conversationMessages
    .slice(-12)
    .map((message) => ({
      role: message.type === 'assistant'
        ? 'assistant'
        : message.type === 'system'
          ? 'system'
          : 'user',
      content: message.content.trim()
    }))
    .filter((message) => message.content)
);

const ANALYSIS_KEYWORDS = ['分析', '总结', '摘要', '提取', '查找', '统计', '概括', '归纳', '识别', 'ocr'];

const createEntityId = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;


const createConversationTitle = (index: number) => (index <= 1 ? '新对话' : `新对话 ${index}`);

const createConversationRecord = (index: number): ConversationRecord => ({
  id: createEntityId('conversation'),
  title: createConversationTitle(index),
  titleEdited: false,
  createdAt: new Date(),
  updatedAt: new Date(),
  messages: [],
  files: {},
  composerFileIds: [],
  rememberedFileBatchIds: [],
  selectedFileId: null,
  inputText: '',
  previewPaneMode: 'current',
  previewReadingMode: 'paged',
  showPreviewPanel: false
});

const isConversationEmpty = (conversation: Pick<ConversationRecord, 'messages' | 'files' | 'inputText'>) => (
  conversation.messages.length === 0
  && Object.keys(conversation.files).length === 0
  && !conversation.inputText.trim()
);

const deriveConversationTitle = (messages: Message[], fallbackTitle: string) => {
  const firstUserMessage = messages.find((message) => message.type === 'user' && message.content.trim());
  if (!firstUserMessage) return fallbackTitle;

  const normalizedContent = firstUserMessage.content.replace(/\s+/g, ' ').trim();
  if (!normalizedContent) return fallbackTitle;

  return normalizedContent.length > 20 ? `${normalizedContent.slice(0, 20)}...` : normalizedContent;
};

const getConversationUpdatedAt = (
  messages: Message[],
  files: Record<string, FileInfo>,
  fallbackTime: Date
) => {
  const timestamps = [
    fallbackTime.getTime(),
    ...messages.map((message) => message.timestamp.getTime()),
    ...Object.values(files).map((file) => file.uploadTime.getTime())
  ];

  return new Date(Math.max(...timestamps));
};

const getConversationPreviewText = (messages: Message[]) => {
  const lastMeaningfulMessage = [...messages].reverse().find((message) => message.content.trim());
  if (!lastMeaningfulMessage) {
    return '等待第一条指令';
  }

  const normalizedContent = lastMeaningfulMessage.content.replace(/\s+/g, ' ').trim();
  return normalizedContent.length > 34 ? `${normalizedContent.slice(0, 34)}...` : normalizedContent;
};

const formatConversationTimestamp = (timestamp: Date) => {
  const now = new Date();
  const diffMs = Math.max(0, now.getTime() - timestamp.getTime());
  const diffMinutes = Math.floor(diffMs / 60000);
  const sameDay = now.toDateString() === timestamp.toDateString();
  const sameYear = now.getFullYear() === timestamp.getFullYear();

  if (diffMinutes < 1) return '刚刚';
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`;
  if (sameDay) {
    return timestamp.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
  if (sameYear) {
    return timestamp.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
  }

  return timestamp.toLocaleDateString('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric' });
};

const toPageNumber = (bbox: number[]): number | null => {
  if (bbox.length !== 5) return null;
  const page = Number(bbox[0]);
  if (!Number.isFinite(page) || page < 1) return null;
  return Math.round(page);
};

const toPercentBox = (bbox: number[]) => {
  if (bbox.length !== 5) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }

  const [, x, y, w, h] = bbox;
  const maxVal = Math.max(x + w, y + h);

  if (maxVal <= 1.5) {
    return { x: x * 100, y: y * 100, w: w * 100, h: h * 100 };
  }

  if (maxVal <= 100) {
    return { x, y, w, h };
  }

  return { x: (x / 595) * 100, y: (y / 842) * 100, w: (w / 595) * 100, h: (h / 842) * 100 };
};

const WorkbenchAssistantAvatar: React.FC<{ size?: 'sm' | 'md' }> = ({ size = 'sm' }) => {
  const wrapperClass = size === 'md' ? 'h-10 w-10 rounded-[16px]' : 'h-9 w-9 rounded-[15px]';
  const innerClass = size === 'md' ? 'rounded-[13px] p-1.5' : 'rounded-[12px] p-1';

  return (
    <div
      className={`relative flex shrink-0 items-center justify-center overflow-hidden border border-[#dde9fb] bg-white shadow-[0_10px_24px_-20px_rgba(42,100,246,0.12)] dark:border-slate-700/80 dark:bg-slate-900 dark:shadow-[0_14px_28px_-22px_rgba(2,6,23,0.72)] ${wrapperClass}`}
    >
      <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_24%_18%,rgba(42,100,246,0.06),rgba(255,255,255,0)_46%)]" />
      <div className={`relative z-10 h-full w-full bg-white dark:bg-slate-900 ${innerClass}`}>
        <img
          src={PLATFORM_ICON_SRC}
          alt="文档智能操作平台"
          className="relative z-10 h-full w-full rounded-[inherit] object-contain saturate-[0.88] contrast-[1.04]"
        />
      </div>
    </div>
  );
};

interface FileFormatIconProps {
  file?: FileInfo | null;
  iconClassName: string;
  fallbackSize: number;
  fallbackClassName?: string;
}

const FileFormatIcon: React.FC<FileFormatIconProps> = ({
  file,
  iconClassName,
  fallbackSize,
  fallbackClassName
}) => {
  const iconUrl = getFileIconUrl(file);

  if (iconUrl) {
    return (
      <img
        src={iconUrl}
        alt=""
        aria-hidden="true"
        className={`${iconClassName} shrink-0 object-contain drop-shadow-sm`}
      />
    );
  }

  return (
    <img
      src={CustomDocIconImage}
      alt=""
      aria-hidden="true"
      className={`${iconClassName} shrink-0 object-contain drop-shadow-sm opacity-90`}
    />
  );
};

type PdfFileSource = Exclude<React.ComponentProps<typeof Document>['file'], null | undefined>;
type WordToPdfConversionResult =
  | { ok: true; pdfBlob: Blob; pdfFile: File }
  | { ok: false; errorMessage: string };

interface PdfPreviewSharedProps {
  fileSource: PdfFileSource;
  fileName: string;
  scale: number;
  rotation: number;
  maxWidth?: number;
  onLoadSuccess?: (pdf: { numPages: number }) => void;
}

type PdfScrollRequest = {
  page: number;
  nonce: number;
};

const createPdfScrollRequest = (page: number): PdfScrollRequest => ({
  page,
  nonce: Date.now() + Math.random(),
});

const useResponsivePdfWidth = (maxWidth?: number) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  const updateContainerWidth = useCallback(() => {
    const nextWidth = containerRef.current?.clientWidth ?? 0;
    setContainerWidth(prev => (Math.abs(prev - nextWidth) > 1 ? nextWidth : prev));
  }, []);

  useEffect(() => {
    updateContainerWidth();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateContainerWidth);
      return () => window.removeEventListener('resize', updateContainerWidth);
    }

    const observer = new ResizeObserver(() => updateContainerWidth());
    if (containerRef.current) {
      observer.observe(containerRef.current);
    }

    return () => observer.disconnect();
  }, [updateContainerWidth]);

  const pageWidth = useMemo(() => {
    if (!containerWidth) return undefined;
    const availableWidth = Math.max(300, Math.floor(containerWidth - 12));
    return maxWidth ? Math.min(availableWidth, maxWidth) : availableWidth;
  }, [containerWidth, maxWidth]);

  return { containerRef, pageWidth };
};

const PdfDocumentFrame: React.FC<{
  children: React.ReactNode;
  pageLabel?: string;
}> = ({ children, pageLabel }) => (
  <div className="relative overflow-hidden rounded-[28px] border border-[#d9e7fd] bg-[linear-gradient(180deg,#ffffff,#f8fbff)] shadow-[0_26px_60px_-34px_rgba(15,23,42,0.34)] dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(30,41,59,0.88))] dark:shadow-[0_30px_60px_-34px_rgba(2,6,23,0.88)]">
    <span className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-[linear-gradient(180deg,rgba(255,255,255,0.4),rgba(255,255,255,0))] dark:bg-[linear-gradient(180deg,rgba(148,163,184,0.08),rgba(148,163,184,0))]" />
    {pageLabel && (
      <div className="absolute right-4 top-4 z-10 rounded-full border border-[#dbe7fb] bg-white/92 px-3 py-1 text-[11px] font-medium tracking-[0.08em] text-[#5e7896] shadow-[0_10px_18px_-16px_rgba(42,100,246,0.28)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/92 dark:text-slate-300 dark:shadow-none">
        {pageLabel}
      </div>
    )}
    <div className="relative z-10 flex items-start justify-center p-2 sm:p-3">
      {children}
    </div>
  </div>
);

interface PdfPagedPreviewProps extends PdfPreviewSharedProps {
  pageNumber: number;
}

const PdfPagedPreview = React.memo(({
  fileSource,
  fileName,
  pageNumber,
  scale,
  rotation,
  maxWidth,
  onLoadSuccess
}: PdfPagedPreviewProps) => {
  const { containerRef, pageWidth } = useResponsivePdfWidth(maxWidth);
  const zoomedPageWidth = pageWidth
    ? Math.max(220, Math.round(pageWidth * scale))
    : undefined;

  return (
    <div ref={containerRef} className="flex h-full min-h-0 w-full min-w-0 items-start justify-center">
      <Document
        file={fileSource}
        loading={
          <div className="flex min-h-[320px] items-center justify-center text-sm text-[#6a86a3] dark:text-slate-400">
            <Loader size={18} className="mr-2 animate-spin text-[#6a86a3] dark:text-slate-400" />
            正在加载 PDF 预览…
          </div>
        }
        error={
          <div className="flex min-h-[320px] flex-col items-center justify-center rounded-[22px] border border-rose-200/50 bg-rose-50/50 p-6 text-center text-rose-600 dark:border-rose-900/30 dark:bg-rose-950/20 dark:text-rose-400">
            <AlertCircle size={32} className="mb-3 opacity-80" />
            <p className="text-[15px] font-medium">PDF 预览加载失败</p>
            <p className="mt-1 text-[13px] opacity-75">请尝试下载后在本地查看，或刷新页面重试。</p>
          </div>
        }
        onLoadSuccess={onLoadSuccess}
        className="mx-auto"
      >
        <PdfDocumentFrame pageLabel={`第 ${pageNumber} 页`}>
          <Page
            key={`${fileName}-${pageNumber}-${scale}-${rotation}`}
            pageNumber={pageNumber}
            width={zoomedPageWidth}
            scale={1}
            rotate={rotation}
            loading={
              <div className="flex min-h-[320px] items-center justify-center text-sm text-[#6a86a3] dark:text-slate-400">
                正在渲染第 {pageNumber} 页…
              </div>
            }
            className="overflow-hidden rounded-[22px] bg-white [&_canvas]:!h-auto [&_canvas]:!max-w-full dark:bg-slate-900"
            renderAnnotationLayer={false}
            renderTextLayer={false}
          />
        </PdfDocumentFrame>
      </Document>
      <span className="sr-only">{fileName}</span>
    </div>
  );
});

interface PdfScrollPreviewProps extends PdfPreviewSharedProps {
  initialPage?: number;
  scrollRequest?: PdfScrollRequest | null;
  onVisiblePageChange?: (page: number) => void;
}

const PdfScrollPreview = React.memo(({
  fileSource,
  fileName,
  scale,
  rotation,
  maxWidth,
  onLoadSuccess,
  initialPage = 1,
  scrollRequest,
  onVisiblePageChange
}: PdfScrollPreviewProps) => {
  const { containerRef, pageWidth } = useResponsivePdfWidth(maxWidth);
  const zoomedPageWidth = pageWidth
    ? Math.max(220, Math.round(pageWidth * scale))
    : undefined;
  const scrollViewportRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);
  const pendingInitialScrollRef = useRef(true);
  const handledScrollRequestNonceRef = useRef<number | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [visiblePages, setVisiblePages] = useState(2);

  useEffect(() => {
    pendingInitialScrollRef.current = true;
    handledScrollRequestNonceRef.current = null;
    setVisiblePages(Math.max(2, initialPage + 1));
  }, [fileSource]);

  const handleDocumentLoadSuccess = useCallback((pdf: { numPages: number }) => {
    setNumPages(pdf.numPages);
    setVisiblePages(prev => Math.min(pdf.numPages, Math.max(prev, initialPage + 1, 2)));
    onLoadSuccess?.(pdf);
  }, [initialPage, onLoadSuccess]);

  const syncVisiblePage = useCallback(() => {
    const viewport = scrollViewportRef.current;
    if (!viewport) return;

    const viewportRect = viewport.getBoundingClientRect();
    let closestPage = 1;
    let closestDistance = Number.POSITIVE_INFINITY;

    pageRefs.current.forEach((element, index) => {
      if (!element) return;
      const rect = element.getBoundingClientRect();
      const distance = Math.abs(rect.top - viewportRect.top - 24);
      if (distance < closestDistance) {
        closestDistance = distance;
        closestPage = index + 1;
      }
    });

    onVisiblePageChange?.(closestPage);
  }, [onVisiblePageChange]);

  const handleViewportScroll = useCallback(() => {
    const viewport = scrollViewportRef.current;
    if (!viewport) return;

    const remaining = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
    if (remaining < 1200) {
      setVisiblePages(prev => (
        numPages ? Math.min(numPages, prev + 4) : prev + 4
      ));
    }

    syncVisiblePage();
  }, [numPages, syncVisiblePage]);

  useEffect(() => {
    if (!pendingInitialScrollRef.current) return;

    const viewport = scrollViewportRef.current;
    if (!viewport) return;

    const targetPage = Math.max(1, initialPage);
    const targetNode = pageRefs.current[targetPage - 1];
    if (!targetNode) return;

    viewport.scrollTo({
      top: Math.max(0, targetNode.offsetTop - 24),
      behavior: 'auto'
    });
    pendingInitialScrollRef.current = false;
    onVisiblePageChange?.(targetPage);
  }, [fileSource, initialPage, onVisiblePageChange, visiblePages]);

  useEffect(() => {
    if (!scrollRequest?.page || typeof window === 'undefined') return;
    if (handledScrollRequestNonceRef.current === scrollRequest.nonce) return;

    const targetPage = numPages
      ? Math.min(Math.max(1, Math.round(scrollRequest.page)), numPages)
      : Math.max(1, Math.round(scrollRequest.page));

    if (visiblePages < targetPage) {
      setVisiblePages(prev => (
        numPages ? Math.min(numPages, Math.max(prev, targetPage)) : Math.max(prev, targetPage)
      ));
      return;
    }

    const viewport = scrollViewportRef.current;
    const targetNode = pageRefs.current[targetPage - 1];
    if (!viewport || !targetNode) return;

    const raf = window.requestAnimationFrame(() => {
      handledScrollRequestNonceRef.current = scrollRequest.nonce;
      viewport.scrollTo({
        top: Math.max(0, targetNode.offsetTop - 24),
        behavior: 'smooth'
      });
      onVisiblePageChange?.(targetPage);
    });

    return () => window.cancelAnimationFrame(raf);
  }, [numPages, onVisiblePageChange, scrollRequest?.nonce, scrollRequest?.page, visiblePages]);

  return (
    <div ref={containerRef} className="flex h-full min-h-0 w-full min-w-0">
      <Document
        file={fileSource}
        loading={
          <div className="flex min-h-[320px] items-center justify-center text-sm text-[#6a86a3] dark:text-slate-400">
            <Loader size={18} className="mr-2 animate-spin text-[#6a86a3] dark:text-slate-400" />
            正在加载 PDF 预览…
          </div>
        }
        error={
          <div className="flex min-h-[320px] items-center justify-center text-sm text-rose-500">
            PDF 预览加载失败，请尝试下载后查看。
          </div>
        }
        onLoadSuccess={handleDocumentLoadSuccess}
        className="flex h-full min-h-0 min-w-0 flex-1"
      >
        <div
          ref={scrollViewportRef}
          onScroll={handleViewportScroll}
          className="flex h-full min-h-0 w-full min-w-0 flex-1 overflow-auto rounded-[28px] border border-[#dde8fc] bg-[linear-gradient(180deg,#f4f8ff,#edf3ff)] p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.94),rgba(30,41,59,0.86))] sm:p-3"
        >
          <div className="flex w-full flex-col gap-2.5">
            {Array.from({ length: visiblePages }, (_, index) => index + 1).map((page) => (
              <div
                key={page}
                ref={(node) => {
                  pageRefs.current[page - 1] = node;
                }}
              >
                <PdfDocumentFrame pageLabel={`第 ${page} 页`}>
                  <Page
                    pageNumber={page}
                    width={zoomedPageWidth}
                    scale={1}
                    rotate={rotation}
                    loading={
                      <div className="flex min-h-[320px] items-center justify-center text-sm text-[#6a86a3] dark:text-slate-400">
                        正在渲染第 {page} 页…
                      </div>
                    }
                    error={
                      <div className="flex min-h-[320px] items-center justify-center rounded-[22px] border border-rose-200 bg-rose-50 px-6 text-sm text-rose-500 dark:border-rose-950/60 dark:bg-rose-950/20">
                        第 {page} 页渲染失败。
                      </div>
                    }
                    className="overflow-hidden rounded-[22px] bg-white [&_canvas]:!h-auto [&_canvas]:!max-w-full dark:bg-slate-900"
                    renderAnnotationLayer={false}
                    renderTextLayer={false}
                  />
                </PdfDocumentFrame>
              </div>
            ))}
          </div>
        </div>
      </Document>
      <span className="sr-only">{fileName}</span>
    </div>
  );
});

// ---------- 智能打字机副标题组件 (Impeccable 设计) ----------
const TypewriterSubtitle: React.FC = () => {
  const [text, setText] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [loopNum, setLoopNum] = useState(0);
  const [typingSpeed, setTypingSpeed] = useState(120);

  const phrases = ["您的AI文档处理助手", "上传你的文档，即刻开始分析"];

  useEffect(() => {
    let timer: NodeJS.Timeout;

    if (loopNum >= 2) return; // 播放完两句后永久定格

    const currentPhrase = phrases[loopNum % 2];

    if (isDeleting) {
      // 退格阶段
      timer = setTimeout(() => {
        setText(currentPhrase.substring(0, text.length - 1));
        setTypingSpeed(40); // 退格速度略快，符合直觉
      }, typingSpeed);

      if (text === '') {
        setIsDeleting(false);
        setLoopNum(loopNum + 1);
        setTypingSpeed(100);
      }
    } else {
      // 打字阶段
      timer = setTimeout(() => {
        setText(currentPhrase.substring(0, text.length + 1));
        setTypingSpeed(80 + Math.random() * 60); // 拟人化随机节奏
      }, typingSpeed);

      if (text === currentPhrase) {
        if (loopNum === 0) {
          // 第一句写完，停顿供用户阅读
          timer = setTimeout(() => setIsDeleting(true), 1800);
        } else {
          // 第二句写完，彻底定格
          setLoopNum(2);
        }
      }
    }

    return () => clearTimeout(timer);
  }, [text, isDeleting, loopNum]);

  return (
    <div className="mb-6 mt-2 flex h-8 items-center justify-center">
      <div className="flex items-center">
        <span className="text-[15px] font-medium tracking-widest text-[#7285a1] dark:text-slate-400">
          {text}
        </span>
        <span
          className={`ml-[6px] inline-block h-[15px] w-[2px] rounded-full bg-[#5282f1]/80 dark:bg-sky-400/80 ${
            loopNum >= 2 ? 'opacity-0 transition-opacity duration-1000' : 'animate-[pulse_0.8s_cubic-bezier(0.4,0,0.6,1)_infinite]'
          }`}
        />
      </div>
    </div>
  );
};

// ---------- 主组件 ----------
export const DocProcessingWorkbench: React.FC = () => {
  const initialConversation = useMemo(() => createConversationRecord(1), []);
  const hydratingConversationRef = useRef(false);
  const activeConversationIdRef = useRef(initialConversation.id);

  const [conversations, setConversations] = useState<ConversationRecord[]>(() => [initialConversation]);
  const [activeConversationId, setActiveConversationId] = useState(initialConversation.id);
  const [isConversationSidebarCollapsed, setIsConversationSidebarCollapsed] = useState(true);
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null);
  const [conversationTitleDraft, setConversationTitleDraft] = useState('');

  // 文档存储
  const [files, setFiles] = useState<Record<string, FileInfo>>(initialConversation.files);
  const [composerFileIds, setComposerFileIds] = useState<string[]>(initialConversation.composerFileIds);
  const [rememberedFileBatchIds, setRememberedFileBatchIds] = useState<string[]>(initialConversation.rememberedFileBatchIds);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(initialConversation.selectedFileId);
  
  // 聊天状态
  const [messages, setMessages] = useState<Message[]>(initialConversation.messages);
  const [inputText, setInputText] = useState(initialConversation.inputText);
  const [isLoading, setIsLoading] = useState(false);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('default');
  const [followUpSuggestionBatchIndex, setFollowUpSuggestionBatchIndex] = useState(0);
  
  // 预览控制
  const [scale, setScale] = useState(0.9);
  const [rotation, setRotation] = useState(0);
  const [pdfPage, setPdfPage] = useState(1);
  const [previewPaneMode, setPreviewPaneMode] = useState<PreviewPaneMode>(initialConversation.previewPaneMode);
  const [previewReadingMode, setPreviewReadingMode] = useState<PdfReadingMode>(initialConversation.previewReadingMode);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesViewportRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const abortControllerRef = useRef<AbortController | null>(null);
  const workbenchRootRef = useRef<HTMLDivElement>(null);
  const previewPanelRef = useRef<HTMLDivElement>(null);
  const reportPreviewScrollRef = useRef<HTMLDivElement>(null);
  const reportContentRef = useRef<HTMLDivElement>(null);
  const reportSourceByVersionKeyRef = useRef<Record<string, string>>({});
  const documentDragDepthRef = useRef(0);
  const [showPreviewPanel, setShowPreviewPanel] = useState(initialConversation.showPreviewPanel);
  const [isDocumentDragOver, setIsDocumentDragOver] = useState(false);
  const [isPreviewFullscreen, setIsPreviewFullscreen] = useState(false);
  const [primaryPdfPageCount, setPrimaryPdfPageCount] = useState<number | null>(null);
  const [comparisonPdfPageCount, setComparisonPdfPageCount] = useState<number | null>(null);
  const [pdfScrollRequest, setPdfScrollRequest] = useState<PdfScrollRequest | null>(null);
  const [isBrowsingHistory, setIsBrowsingHistory] = useState(false);
  const [isComposerHovered, setIsComposerHovered] = useState(false);
  const [isComposerFocused, setIsComposerFocused] = useState(false);
  const [editableReportByFileId, setEditableReportByFileId] = useState<Record<string, string>>({});
  const [reportFormattingByFileId, setReportFormattingByFileId] = useState<Record<string, ReportFormattingState>>({});
  const [reportHistoryByFileId, setReportHistoryByFileId] = useState<Record<string, ReportHistorySnapshot[]>>({});
  const [activeReportMessageIdByFileId, setActiveReportMessageIdByFileId] = useState<Record<string, string>>({});
  const [reportSelection, setReportSelection] = useState<ActiveReportSelection | null>(null);
  const [reportBusyAction, setReportBusyAction] = useState<ReportQuickEditAction | null>(null);
  const [reportManualEditOpen, setReportManualEditOpen] = useState(false);
  const [reportManualEditValue, setReportManualEditValue] = useState('');
  const [reportManualEditBusy, setReportManualEditBusy] = useState(false);
  const [reportToolbarFeedback, setReportToolbarFeedback] = useState('');
  const [reportDownloadBusy, setReportDownloadBusy] = useState(false);
  const [reportProgressState, setReportProgressState] = useState<ReportProgressState>(() => createReportProgressState());
  const [reportStreamHighlightNonce, setReportStreamHighlightNonce] = useState(0);
  const [animatedReportFileId, setAnimatedReportFileId] = useState<string | null>(null);
  const [animatedReportText, setAnimatedReportText] = useState('');

  const updateMessageById = useCallback((messageId: string, updater: (message: Message) => Message) => {
    setMessages(prev => prev.map(message => (
      message.id === messageId ? updater(message) : message
    )));
  }, []);

  const isReportIntent = useCallback((instruction: string) => {
    const normalizedInstruction = instruction.toLowerCase();
    return ANALYSIS_KEYWORDS.some(keyword => normalizedInstruction.includes(keyword));
  }, []);

  const resetPreviewViewport = useCallback(() => {
    setScale(0.9);
    setRotation(0);
    setPdfPage(1);
    setPdfScrollRequest(null);
  }, []);

  // 计算属性
  const fileList = useMemo(() => Object.values(files), [files]);
  const composerFiles = useMemo(() => getFilesByIds(files, composerFileIds), [composerFileIds, files]);
  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) ?? conversations[0],
    [activeConversationId, conversations]
  );
  const orderedConversations = useMemo(
    () => [...conversations].sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()),
    [conversations]
  );
  const syncConversationRecord = useCallback((conversation: ConversationRecord): ConversationRecord => ({
    ...conversation,
    title: conversation.titleEdited ? conversation.title : deriveConversationTitle(messages, conversation.title),
    updatedAt: getConversationUpdatedAt(messages, files, conversation.updatedAt),
    messages,
    files,
    composerFileIds,
    rememberedFileBatchIds,
    selectedFileId,
    inputText,
    previewPaneMode,
    previewReadingMode,
    showPreviewPanel
  }), [composerFileIds, files, inputText, messages, previewPaneMode, previewReadingMode, rememberedFileBatchIds, selectedFileId, showPreviewPanel]);
  const commitCurrentConversation = useCallback((conversationList: ConversationRecord[]) => (
    conversationList.map((conversation) => (
      conversation.id === activeConversationId ? syncConversationRecord(conversation) : conversation
    ))
  ), [activeConversationId, syncConversationRecord]);
  const selectedFile = useMemo(
    () => selectedFileId ? files[selectedFileId] : null,
    [files, selectedFileId]
  );
  const reportMessagesByFileId = useMemo(() => {
    const reportMap = new Map<string, Message[]>();

    messages.forEach((message) => {
      if (message.type !== 'assistant' || message.displayMode !== 'report' || !message.fileIds?.length) {
        return;
      }

      message.fileIds.forEach((fileId) => {
        const existing = reportMap.get(fileId) ?? [];
        existing.push(message);
        reportMap.set(fileId, existing);
      });
    });

    reportMap.forEach((reportMessages, fileId) => {
      const sortedMessages = [...reportMessages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
      reportMap.set(fileId, sortedMessages);
    });

    return reportMap;
  }, [messages]);

  const latestReportByFileId = useMemo(() => {
    const latestReportMap = new Map<string, Message>();
    reportMessagesByFileId.forEach((reportMessages, fileId) => {
      const latestMessage = reportMessages[reportMessages.length - 1];
      if (latestMessage) {
        latestReportMap.set(fileId, latestMessage);
      }
    });
    return latestReportMap;
  }, [reportMessagesByFileId]);

  const getActiveReportMessageForFile = useCallback((fileId: string): Message | null => {
    const reportMessages = reportMessagesByFileId.get(fileId) ?? [];
    if (reportMessages.length === 0) return null;

    const selectedMessageId = activeReportMessageIdByFileId[fileId];
    if (selectedMessageId) {
      const selectedMessage = reportMessages.find((message) => message.id === selectedMessageId);
      if (selectedMessage) return selectedMessage;
    }

    return reportMessages[reportMessages.length - 1] ?? null;
  }, [activeReportMessageIdByFileId, reportMessagesByFileId]);

  useEffect(() => {
    setActiveReportMessageIdByFileId((prev) => {
      let changed = false;
      const next = { ...prev };

      reportMessagesByFileId.forEach((reportMessages, fileId) => {
        if (reportMessages.length === 0) return;
        const hasSelected = Boolean(
          next[fileId] && reportMessages.some((message) => message.id === next[fileId]),
        );
        if (!hasSelected) {
          const latestMessageId = reportMessages[reportMessages.length - 1]?.id;
          if (latestMessageId && next[fileId] !== latestMessageId) {
            next[fileId] = latestMessageId;
            changed = true;
          }
        }
      });

      Object.keys(next).forEach((fileId) => {
        if (!reportMessagesByFileId.has(fileId)) {
          delete next[fileId];
          changed = true;
        }
      });

      return changed ? next : prev;
    });
  }, [reportMessagesByFileId]);

  const selectedFileReportMessages = useMemo(
    () => (selectedFile ? reportMessagesByFileId.get(selectedFile.id) ?? [] : []),
    [reportMessagesByFileId, selectedFile]
  );
  const activeReportMessageForSelectedFile = useMemo(
    () => (selectedFile ? getActiveReportMessageForFile(selectedFile.id) : null),
    [getActiveReportMessageForFile, selectedFile]
  );
  const activeReportVersionKey = useMemo(
    () => (
      selectedFile && activeReportMessageForSelectedFile
        ? buildReportVersionKey(selectedFile.id, activeReportMessageForSelectedFile.id)
        : null
    ),
    [activeReportMessageForSelectedFile, selectedFile]
  );

  
  
  const contentColumnsStyle = useMemo<React.CSSProperties | undefined>(() => {
    if (!showPreviewPanel) return undefined;

    if (layoutMode === 'compact') {
      return { gridTemplateColumns: 'minmax(0, 42%) minmax(0, 1fr)' };
    }

    if (layoutMode === 'expanded') {
      return { gridTemplateColumns: 'minmax(0, 54%) minmax(0, 1fr)' };
    }

    return { gridTemplateColumns: 'minmax(0, 48%) minmax(0, 1fr)' };
  }, [layoutMode, showPreviewPanel]);

  const canPreviewOriginal = useMemo(
    () => Boolean(selectedFile?.sourceFileId && files[selectedFile.sourceFileId]),
    [files, selectedFile]
  );

  const scrollMessagesToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    shouldAutoScrollRef.current = true;
    setIsBrowsingHistory(false);
    messagesEndRef.current?.scrollIntoView({
      behavior,
      block: 'end'
    });
  }, []);

  const updateComposerCollapseState = useCallback(() => {
    const viewport = messagesViewportRef.current;
    if (!viewport) {
      shouldAutoScrollRef.current = true;
      setIsBrowsingHistory(false);
      return;
    }

    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
    const isNearBottom = distanceFromBottom <= 72;
    shouldAutoScrollRef.current = isNearBottom;
    setIsBrowsingHistory(!isNearBottom);
  }, []);

  useEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  useEffect(() => {
    if (hydratingConversationRef.current) return;
    setConversations((prev) => commitCurrentConversation(prev));
  }, [commitCurrentConversation]);

  useEffect(() => {
    if (selectedFileId) return;
    if (fileList.length === 0) return;

    setSelectedFileId(fileList[0].id);
  }, [fileList, selectedFileId]);

  const comparisonFile = useMemo(
    () => selectedFile?.sourceFileId ? files[selectedFile.sourceFileId] ?? null : null,
    [files, selectedFile]
  );

  const previewedFile = useMemo(() => {
    if (!selectedFile) return null;
    if (previewPaneMode === 'original' && selectedFile.sourceFileId && files[selectedFile.sourceFileId]) {
      return files[selectedFile.sourceFileId];
    }
    return selectedFile;
  }, [files, previewPaneMode, selectedFile]);
  
  const activeFileExt = previewedFile ? fileExt(previewedFile.name) : '';
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [comparisonPreviewUrl, setComparisonPreviewUrl] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string>('');
  const [pdfPageInput, setPdfPageInput] = useState('1');
  const rawPreviewCategory = getPreviewCategory(previewedFile);
  const previewCategory = getRenderablePreviewCategory(previewedFile);
  const comparisonCategory = getRenderablePreviewCategory(comparisonFile);
  const previewPdfSource = useMemo<PdfFileSource | null>(() => {
    if (previewedFile?.convertedPdfBlob) return previewedFile.convertedPdfBlob;
    if (previewedFile?.previewBlob) return previewedFile.previewBlob;
    if (previewedFile && getRenderablePreviewCategory(previewedFile) === 'pdf' && previewedFile.file) {
      return previewedFile.file;
    }
    return previewUrl;
  }, [previewUrl, previewedFile]);
  const comparisonPdfSource = useMemo<PdfFileSource | null>(() => {
    if (comparisonFile?.convertedPdfBlob) return comparisonFile.convertedPdfBlob;
    if (comparisonFile?.previewBlob) return comparisonFile.previewBlob;
    if (comparisonFile && getRenderablePreviewCategory(comparisonFile) === 'pdf' && comparisonFile.file) {
      return comparisonFile.file;
    }
    return comparisonPreviewUrl;
  }, [comparisonFile, comparisonPreviewUrl]);
  const previewedFileName = previewedFile?.name ?? '预览文件';

  const syncPreviewUrl = useCallback((file: FileInfo | null, setter: React.Dispatch<React.SetStateAction<string | null>>) => {
    if (!file?.preview && !file?.file) {
      setter(null);
      return undefined;
    }

    // 预览优先使用后端或转换后的地址，缺失时才回退到本地 blob。
    let createdPreviewUrl: string | null = null;
    const nextPreviewUrl = file.preview ?? URL.createObjectURL(file.file!);

    if (!file.preview && file.file) {
      createdPreviewUrl = nextPreviewUrl;
    }

    setter(nextPreviewUrl);

    return () => {
      if (createdPreviewUrl) {
        URL.revokeObjectURL(createdPreviewUrl);
      }
    };
  }, []);

  // 预览URL管理
  React.useEffect(() => syncPreviewUrl(previewedFile, setPreviewUrl), [previewedFile, syncPreviewUrl]);
  React.useEffect(() => syncPreviewUrl(comparisonFile, setComparisonPreviewUrl), [comparisonFile, syncPreviewUrl]);

  // 文本预览 - 只处理纯文本文件
  React.useEffect(() => {
    let cancelled = false;
    // 只处理纯文本文件，不处理 Excel
    if (!previewedFile?.file || !['txt', 'md', 'csv'].includes(activeFileExt)) {
      setPreviewText('');
      return;
    }
    previewedFile.file.text().then((text) => {
      if (cancelled) return;
      const maxChars = 12000;
      setPreviewText(text.length > maxChars ? `${text.slice(0, maxChars)}\n\n... [truncated]` : text);
    }).catch(err => {
      console.error('读取文本文件失败:', err);
      setPreviewText('文件读取失败');
    });
    return () => { cancelled = true; };
  }, [previewedFile, activeFileExt]);

  // 自动滚动
  const lastMessage = useMemo(
    () => messages[messages.length - 1] ?? null,
    [messages]
  );

  const streamingAssistantMessageId = useMemo(() => (
    isLoading && lastMessage?.type === 'assistant' ? lastMessage.id : null
  ), [isLoading, lastMessage]);

  React.useEffect(() => {
    if (shouldAutoScrollRef.current) {
      scrollMessagesToBottom(isLoading ? 'auto' : 'smooth');
    }

    if (typeof window === 'undefined') return;
    const frameId = window.requestAnimationFrame(updateComposerCollapseState);
    return () => window.cancelAnimationFrame(frameId);
  }, [isLoading, messages, scrollMessagesToBottom, updateComposerCollapseState]);

  useEffect(() => {
    const textarea = composerTextareaRef.current;
    if (!textarea) return;

    const minHeight = composerFiles.length > 0 ? 68 : 48;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, minHeight), 180)}px`;
  }, [composerFiles.length, composerTextareaRef, inputText]);

  // 组件卸载时中止请求
  React.useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  useEffect(() => {
    workbenchRootRef.current?.scrollTo({ top: 0, behavior: 'auto' });
  }, []);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsPreviewFullscreen(document.fullscreenElement === previewPanelRef.current);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
  }, []);

  const loadConversation = useCallback((conversation: ConversationRecord) => {
    hydratingConversationRef.current = true;
    documentDragDepthRef.current = 0;
    shouldAutoScrollRef.current = true;
    setIsDocumentDragOver(false);
    setIsComposerHovered(false);
    setIsComposerFocused(false);
    setIsBrowsingHistory(false);

    const nextSelectedFileId = conversation.selectedFileId && conversation.files[conversation.selectedFileId]
      ? conversation.selectedFileId
      : Object.values(conversation.files)[0]?.id ?? null;
    const nextComposerFileIds = getExistingFileIds(conversation.files, conversation.composerFileIds);
    const nextRememberedFileBatchIds = getExistingFileIds(conversation.files, conversation.rememberedFileBatchIds);

    setFiles(conversation.files);
    setComposerFileIds(nextComposerFileIds);
    setRememberedFileBatchIds(nextRememberedFileBatchIds);
    setSelectedFileId(nextSelectedFileId);
    setMessages(conversation.messages);
    setInputText(conversation.inputText);
    setPreviewPaneMode(conversation.previewPaneMode);
    setPreviewReadingMode(conversation.previewReadingMode ?? 'paged');
    setShowPreviewPanel(conversation.showPreviewPanel);
    resetPreviewViewport();

    if (typeof window !== 'undefined') {
      window.setTimeout(() => {
        hydratingConversationRef.current = false;
      }, 0);
      return;
    }

    hydratingConversationRef.current = false;
  }, [resetPreviewViewport]);

  const createNewConversation = useCallback(() => {
    if (isLoading) return;

    const currentConversation = conversations.find((conversation) => conversation.id === activeConversationId);
    if (currentConversation && isConversationEmpty({
      messages,
      files,
      inputText
    })) {
      setEditingConversationId(null);
      setConversationTitleDraft('');
      return;
    }

    const nextConversation = createConversationRecord(conversations.length + 1);
    setEditingConversationId(null);
    setConversationTitleDraft('');
    setConversations((prev) => [nextConversation, ...commitCurrentConversation(prev)]);
    setActiveConversationId(nextConversation.id);
    loadConversation(nextConversation);
  }, [activeConversationId, commitCurrentConversation, conversations, files, inputText, isLoading, loadConversation, messages]);

  const activateConversation = useCallback((conversationId: string) => {
    if (conversationId === activeConversationId || isLoading) return;

    const nextConversation = conversations.find((conversation) => conversation.id === conversationId);
    if (!nextConversation) return;

    setEditingConversationId(null);
    setConversationTitleDraft('');
    setConversations((prev) => commitCurrentConversation(prev));
    setActiveConversationId(conversationId);
    loadConversation(nextConversation);
  }, [activeConversationId, commitCurrentConversation, conversations, isLoading, loadConversation]);

  const startConversationRename = useCallback((conversation: ConversationRecord) => {
    setEditingConversationId(conversation.id);
    setConversationTitleDraft(conversation.title);
  }, []);

  const commitConversationRename = useCallback((conversationId: string) => {
    const nextTitle = conversationTitleDraft.trim();

    if (!nextTitle) {
      setEditingConversationId(null);
      setConversationTitleDraft('');
      return;
    }

    setConversations((prev) => prev.map((conversation) => (
      conversation.id === conversationId
        ? {
            ...conversation,
            title: nextTitle,
            titleEdited: true,
            updatedAt: new Date()
          }
        : conversation
    )));
    setEditingConversationId(null);
    setConversationTitleDraft('');
  }, [conversationTitleDraft]);

  const cancelConversationRename = useCallback(() => {
    setEditingConversationId(null);
    setConversationTitleDraft('');
  }, []);

  const deleteConversation = useCallback((conversationId: string) => {
    if (isLoading) return;

    const syncedConversations = commitCurrentConversation(conversations);
    const remainingConversations = syncedConversations.filter((conversation) => conversation.id !== conversationId);
    const orderedRemainingConversations = [...remainingConversations]
      .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
    const fallbackConversation = remainingConversations.length === 0
      ? createConversationRecord(1)
      : null;
    const nextActiveConversation = conversationId === activeConversationId
      ? orderedRemainingConversations[0] ?? fallbackConversation
      : null;
    const nextConversations = fallbackConversation
      ? [fallbackConversation]
      : remainingConversations;

    if (editingConversationId === conversationId) {
      setEditingConversationId(null);
      setConversationTitleDraft('');
    }
    setConversations(nextConversations);

    if (conversationId !== activeConversationId) {
      return;
    }

    if (!nextActiveConversation) {
      return;
    }

    setActiveConversationId(nextActiveConversation.id);
    loadConversation(nextActiveConversation);
  }, [activeConversationId, commitCurrentConversation, conversations, editingConversationId, isLoading, loadConversation]);

  // ---------- Word转PDF转换函数 ----------
  const convertWordToPdf = async (file: File): Promise<WordToPdfConversionResult> => {
    const formData = new FormData();
    formData.append('file', file, file.name || 'document.docx');

    try {
      console.log(`开始转换Word文件: ${file.name}`);
      const response = await fetch(buildModule1ApiUrl('/convert/docx-to-pdf'), {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });

      if (!response.ok) {
        const errorMessage = await parseApiErrorMessage(response);
        console.error('服务器返回错误:', response.status, errorMessage);
        return {
          ok: false,
          errorMessage: `Word 转 PDF 失败：HTTP ${response.status} - ${errorMessage}`,
        };
      }

      const contentType = response.headers.get('content-type');
      console.log('响应内容类型:', contentType);

      if (!contentType?.includes('application/pdf')) {
        const errorMessage = await parseApiErrorMessage(response);
        console.error('返回的不是PDF文件:', errorMessage);
        return {
          ok: false,
          errorMessage: `Word 转 PDF 失败：返回了非 PDF 内容（${contentType || 'unknown'}）`,
        };
      }

      const pdfBlob = await response.blob();
      if (pdfBlob.size === 0) {
        return { ok: false, errorMessage: 'Word 转 PDF 失败：返回内容为空' };
      }

      const looksLikePdf = await isLikelyPdfBlob(pdfBlob);
      if (!looksLikePdf) {
        return { ok: false, errorMessage: 'Word 转 PDF 失败：返回内容不是有效 PDF' };
      }

      console.log('PDF Blob大小:', pdfBlob.size, 'bytes');
      const pdfFileName = file.name.replace(/\.[^/.]+$/, '') + '.pdf';

      let pdfFile: File;
      try {
        pdfFile = new File([pdfBlob], pdfFileName, { type: 'application/pdf' });
      } catch (e) {
        console.warn('File constructor not available, using fallback method');
        pdfFile = pdfBlob as File;
        Object.defineProperties(pdfFile, {
          name: { value: pdfFileName, writable: false },
          lastModified: { value: Date.now(), writable: false }
        });
      }

      console.log(`转换成功: ${pdfFileName}`);
      return { ok: true, pdfBlob, pdfFile };
    } catch (error) {
      console.error('Word转PDF失败:', error);
      return {
        ok: false,
        errorMessage: error instanceof Error ? error.message : 'Word 转 PDF 失败：未知错误',
      };
    }
  };

  // ---------- 文件上传 ----------
  const processUploadedFiles = useCallback(async (incomingFiles: File[]) => {
    if (incomingFiles.length === 0) return;

    const targetConversationId = activeConversationIdRef.current;
    const acceptedFiles: Array<{ file: File; fileId: string; ext: string; previewUrl: string }> = [];
    const stagedFiles: Record<string, FileInfo> = {};

    incomingFiles.forEach((file, index) => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();

      if (!ALLOWED_UPLOAD_EXTENSIONS.includes(ext)) {
        alert(`文件 ${file.name} 格式不支持。模块一后端当前支持 PDF、DOC、DOCX、TXT、XLSX、MD 和常见图片格式。`);
        return;
      }

      if (file.size > MAX_UPLOAD_FILE_SIZE) {
        alert(`文件 ${file.name} 大小超过20MB`);
        return;
      }

      const fileId = Date.now() + Math.random().toString(36).substr(2, 9) + index;
      const previewUrl = URL.createObjectURL(file);

      acceptedFiles.push({ file, fileId, ext, previewUrl });
      stagedFiles[fileId] = {
        id: fileId,
        name: file.name,
        size: file.size,
        type: file.type,
        uploadTime: new Date(),
        status: 'ready',
        progress: 100,
        file,
        preview: previewUrl,
        previewType: file.type,
        previewBlob: ext === '.pdf' ? file : undefined,
        conversionStatus: ext === '.doc' || ext === '.docx' ? 'converting' : 'idle',
        originalFile: file
      };
    });

    if (acceptedFiles.length === 0) {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    setFiles(prev => ({
      ...prev,
      ...stagedFiles
    }));
    setComposerFileIds(acceptedFiles.map(({ fileId }) => fileId));

    if (!selectedFileId) {
      setSelectedFileId(acceptedFiles[0].fileId);
      setPreviewPaneMode('current');
      setPreviewReadingMode('paged');
    }

    for (const { file, ext, fileId } of acceptedFiles) {
      if (ext !== '.doc' && ext !== '.docx') continue;

      const conversionResult = await convertWordToPdf(file);

      if (conversionResult.ok) {
        const pdfBlob = conversionResult.pdfBlob;
        const pdfFile = conversionResult.pdfFile;

        setConversations((prev) => prev.map((conversation) => {
          if (conversation.id !== targetConversationId || !conversation.files[fileId]) {
            return conversation;
          }

          return {
            ...conversation,
            updatedAt: new Date(),
            files: {
              ...conversation.files,
              [fileId]: {
                ...conversation.files[fileId],
                status: 'ready',
                progress: 100,
                conversionStatus: 'ready',
                convertedPdfBlob: pdfBlob,
                convertedPdfFileName: pdfFile.name,
                originalFile: file
              }
            }
          };
        }));

        if (activeConversationIdRef.current === targetConversationId) {
          setFiles(prev => {
            if (!prev[fileId]) {
              return prev;
            }

            return {
              ...prev,
              [fileId]: {
                ...prev[fileId],
                status: 'ready',
                progress: 100,
                conversionStatus: 'ready',
                convertedPdfBlob: pdfBlob,
                convertedPdfFileName: pdfFile.name,
                originalFile: file
              }
            };
          });
        }
      } else {
        const previewErrorMessage = WORD_PREVIEW_FALLBACK_MESSAGE;
        console.error(`文件 ${file.name} 转换失败`);

        setConversations((prev) => prev.map((conversation) => {
          if (conversation.id !== targetConversationId || !conversation.files[fileId]) {
            return conversation;
          }

          return {
            ...conversation,
            updatedAt: new Date(),
            files: {
              ...conversation.files,
              [fileId]: {
                ...conversation.files[fileId],
                status: 'ready',
                progress: 100,
                conversionStatus: 'error',
                error: previewErrorMessage,
                result: previewErrorMessage
              }
            }
          };
        }));

        if (activeConversationIdRef.current === targetConversationId) {
          setFiles(prev => {
            if (!prev[fileId]) {
              return prev;
            }

            return {
              ...prev,
              [fileId]: {
                ...prev[fileId],
                status: 'ready',
                progress: 100,
                conversionStatus: 'error',
                error: previewErrorMessage,
                result: previewErrorMessage
              }
            };
          });
        }
      }
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [convertWordToPdf, selectedFileId]);

  const handleFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;

    await processUploadedFiles(Array.from(fileList));
  }, [processUploadedFiles]);

  useEffect(() => {
    void consumeModule1DraftFromHomeWorkbench().then((handoff) => {
      if (!handoff) return;

      if (handoff.itemIds && handoff.itemIds.length > 0) {
        // process HomeWorkbench items ...
      }
    });
  }, [processUploadedFiles]);

  const handleDocumentDragEnter = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (!isFileDragEvent(event.dataTransfer)) return;

    event.preventDefault();
    event.stopPropagation();
    documentDragDepthRef.current += 1;
    setIsDocumentDragOver(true);
  }, []);

  const handleDocumentDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (!isFileDragEvent(event.dataTransfer)) return;

    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'copy';

    if (!isDocumentDragOver) {
      setIsDocumentDragOver(true);
    }
  }, [isDocumentDragOver]);

  const handleDocumentDragLeave = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (!isFileDragEvent(event.dataTransfer)) return;

    event.preventDefault();
    event.stopPropagation();
    documentDragDepthRef.current = Math.max(documentDragDepthRef.current - 1, 0);

    if (documentDragDepthRef.current === 0) {
      setIsDocumentDragOver(false);
    }
  }, []);

  const handleDocumentDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (!isFileDragEvent(event.dataTransfer)) return;

    event.preventDefault();
    event.stopPropagation();
    documentDragDepthRef.current = 0;
    setIsDocumentDragOver(false);

    void processUploadedFiles(Array.from(event.dataTransfer.files ?? []));
  }, [processUploadedFiles]);

  const removeComposerFile = useCallback((fileId: string) => {
    setComposerFileIds((prev) => prev.filter((id) => id !== fileId));
  }, []);

  const triggerFileInput = useCallback(() => fileInputRef.current?.click(), []);

  const handleMessagesScroll = useCallback(() => {
    updateComposerCollapseState();
  }, [updateComposerCollapseState]);

  // ---------- API 调用 ----------
  const applyModificationsToFile = useCallback(async (
    operationResult: OperationResult,
    targetFile: FileInfo
  ): Promise<void> => {
    try {
      // 获取要修改的文件
      const fileToModify = targetFile.originalFile || targetFile.file;
      if (!fileToModify) {
        throw new Error('找不到要修改的文件');
      }
      
      // 准备修改数据
      const formData = new FormData();
      formData.append('file', fileToModify, fileToModify.name || targetFile.name);
      formData.append('modifications', JSON.stringify(operationResult.modifications || []));
      formData.append('instruction', operationResult.instruction || '');
      
      console.log('正在应用修改:', {
        fileName: fileToModify.name,
        modifications: operationResult.modifications
      });
      
      // 调用应用修改的API
      const response = await fetch(buildModule1ApiUrl('/apply-modifications'), {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });
      
      console.log('API响应状态:', response.status);
      console.log('API响应头:', Object.fromEntries(response.headers.entries()));
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('API错误响应:', errorText);
        throw new Error(`应用修改失败: ${response.status} - ${errorText}`);
      }
      
      // 获取修改后的文件
      const modifiedBlob = await response.blob();
      console.log('修改后的文件大小:', modifiedBlob.size, 'bytes');
      
      // 从响应头获取修改信息（注意：这些头可能不存在）
      const modificationApplied = response.headers.get('X-Modification-Applied');
      const modificationCount = response.headers.get('X-Modification-Count') || 
                                (operationResult.modifications?.length || 0).toString();
      
      console.log('修改信息:', { modificationApplied, modificationCount });
      
      const sourceFileName = fileToModify.name || targetFile.originalFile?.name || targetFile.name;
      const fileName = prefixModifiedFileName(sourceFileName);
      const logicalFileType = resolveFileMimeType(modifiedBlob.type, sourceFileName);
      
      // 创建File对象
      let modifiedFile;
      try {
        modifiedFile = new File([modifiedBlob], fileName, { type: logicalFileType });
      } catch (e) {
        console.warn('File constructor not available, using fallback');
        modifiedFile = modifiedBlob as File;
        Object.defineProperties(modifiedFile, {
          name: { value: fileName, writable: false },
          lastModified: { value: Date.now(), writable: false }
        });
      }
      
      // 生成预览URL
      let modifiedPreviewUrl = URL.createObjectURL(modifiedBlob);
      let modifiedPreviewType = logicalFileType;
      let modifiedPreviewBlob: Blob | undefined = logicalFileType.includes('pdf') ? modifiedBlob : undefined;
      const modifiedExt = '.' + sourceFileName.split('.').pop()?.toLowerCase();
      let conversionStatus: FileInfo['conversionStatus'] = 'idle';
      let convertedPdfBlob: Blob | undefined;
      let convertedPdfFileName = '';
      let conversionErrorMessage = '';
      let previewFallbackNote = '';

      if (modifiedExt === '.doc' || modifiedExt === '.docx') {
        conversionStatus = 'converting';
        const conversionResult = await convertWordToPdf(modifiedFile as File);
        if (conversionResult.ok) {
          URL.revokeObjectURL(modifiedPreviewUrl);
          modifiedPreviewUrl = URL.createObjectURL(conversionResult.pdfBlob);
          modifiedPreviewType = 'application/pdf';
          modifiedPreviewBlob = conversionResult.pdfBlob;
          conversionStatus = 'ready';
          convertedPdfBlob = conversionResult.pdfBlob;
          convertedPdfFileName = conversionResult.pdfFile.name;
        } else {
          conversionStatus = 'error';
          previewFallbackNote = `\n\n${WORD_PREVIEW_FALLBACK_MESSAGE}`;
        }
      }
      
      // 更新文件列表，添加修改后的文件
      const newFileId = Date.now() + Math.random().toString(36).substr(2, 9);
      
      setFiles(prev => {
        const newFiles = { ...prev };
        
        // 添加修改后的文件
        newFiles[newFileId] = {
          id: newFileId,
          name: fileName,
          size: modifiedBlob.size,
          type: logicalFileType,
          uploadTime: new Date(),
          status: 'ready',
          progress: 100,
          file: modifiedFile,
          preview: modifiedPreviewUrl,
          previewType: modifiedPreviewType,
          previewBlob: modifiedPreviewBlob,
          conversionStatus,
          convertedPdfBlob,
          convertedPdfFileName: convertedPdfFileName || undefined,
          originalFile: modifiedFile,
          sourceFileId: targetFile.id,
          error: conversionStatus === 'error'
            ? `${WORD_PREVIEW_FALLBACK_MESSAGE}`
            : undefined,
          result: `已应用 ${modificationCount} 项修改${previewFallbackNote ? '，并保留原文件下载' : ''}`
        };
        
        return newFiles;
      });
      
      // 自动选中新文件
      setSelectedFileId(newFileId);
      setPreviewPaneMode('current');
      setShowPreviewPanel(true);
      resetPreviewViewport();
      
      // 添加成功消息
      const successMessage: Message = {
        id: Date.now().toString(),
        type: 'assistant',
        content: `✅ 修改已成功应用\n\n已生成修改后的文件：${fileName}\n共应用 ${modificationCount} 项修改。现在会直接切到预览，不会自动下载。${previewFallbackNote}`,
        displayMode: 'chat',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, successMessage]);

    } catch (error) {
      console.error('应用修改失败:', error);
      
      // 添加错误消息
      const errorMessage: Message = {
        id: Date.now().toString(),
        type: 'assistant',
        content: `❌ 应用修改失败\n\n${error instanceof Error ? error.message : '未知错误'}\n\n请查看控制台获取详细信息。`,
        displayMode: 'chat',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    }
  }, [convertWordToPdf, resetPreviewViewport]);

  const getStatusIcon = useCallback((file: FileInfo) => {
    if (file.conversionStatus === 'converting') {
      return <Loader size={14} className="text-yellow-500 animate-spin" />;
    }

    switch(file.status) {
      case 'ready':
        return <CheckCircle size={15} className="text-emerald-500" />;
      case 'converting':
        return <Loader size={14} className="text-yellow-500 animate-spin" />;
      case 'processing':
        return <Loader size={14} className="text-[#6a86a3] dark:text-slate-400 animate-spin" />;
      case 'completed':
        return <CheckCircle size={15} className="text-emerald-500" />;
      case 'error':
        return <AlertCircle size={14} className="text-red-500" />;
      case 'uploading':
      default:
        return <Clock size={14} className="text-[#8daad0] dark:text-slate-500" />;
    }
  }, []);

  // Excel预览组件
  const ExcelPreview: React.FC<{ file: FileInfo }> = ({ file }) => {
    const previewFile = file.file || file.originalFile || null;

    if (!previewFile) {
      return (
        <div className="flex h-full flex-col items-center justify-center text-center p-8">
          <AlertCircle size={48} className="mx-auto mb-4 text-red-500" />
          <p className="text-sm text-red-500 mb-4">Excel 文件不存在，暂时无法预览。</p>
          <button
            type="button"
            onClick={() => downloadFile(file)}
            className={`flex h-10 w-10 items-center justify-center rounded-xl ${METALLIC_PRIMARY_BUTTON_CLASS}`}
            title={`下载 ${file.name}`}
            aria-label={`下载 ${file.name}`}
          >
            <Download size={16} />
          </button>
        </div>
      );
    }

    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="mb-3 flex items-center justify-between rounded-[18px] px-3 py-2.5 text-sm text-[#6a81a0] dark:text-slate-300">
          <span className="font-medium">Excel 预览</span>
          <button
            type="button"
            onClick={() => downloadFile(file)}
            className={`flex h-9 w-9 items-center justify-center rounded-xl ${METALLIC_PRIMARY_BUTTON_CLASS}`}
            title={`下载 ${file.name}`}
            aria-label={`下载 ${file.name}`}
          >
            <Download size={14} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden rounded-[22px] border border-[#dbe7fb] bg-white dark:border-slate-700 dark:bg-slate-900">
          <LuckysheetPreview
            file={previewFile}
            className="h-full min-h-0"
          />
        </div>
      </div>
    );
  };

  // ---------- 发送消息 ----------
  const sendMessage = useCallback(async (promptOverride?: string) => {
    const instruction = String(promptOverride ?? inputText).trim();
    if (!instruction || isLoading) return;
  
    // 移除强制文件检查，允许无文件时聊天
    // if (Object.keys(files).length === 0) { alert('请先上传文档'); return; }
  
    // 中止之前的请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  
    // 创建新的 AbortController
    abortControllerRef.current = new AbortController();
    const requestedComposerFileIds = getExistingFileIds(files, composerFileIds);
    const requestedRememberedFileIds = getExistingFileIds(files, rememberedFileBatchIds);
    const effectiveRequestFileIds = requestedComposerFileIds.length > 0
      ? requestedComposerFileIds
      : requestedRememberedFileIds;
    const effectiveRequestFiles = getFilesByIds(files, effectiveRequestFileIds);
    const conversationContext = buildConversationContextPayload(messages);
    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: instruction,
      fileIds: effectiveRequestFileIds,
      timestamp: new Date()
    };
    shouldAutoScrollRef.current = true;
    setIsBrowsingHistory(false);
    setMessages(prev => [...prev, userMessage]);
    setInputText('');
    if (requestedComposerFileIds.length > 0) {
      setComposerFileIds((prev) => removeFileIds(prev, requestedComposerFileIds));
    }
    if (effectiveRequestFileIds.length > 0) {
      setFiles((prev) => {
        const next = { ...prev };
        for (const fileId of effectiveRequestFileIds) {
          if (next[fileId]) {
            next[fileId] = {
              ...next[fileId],
              status: 'processing',
              progress: 85,
            };
          }
        }
        return next;
      });
    }
    setIsLoading(true);
    let animationFrameId: number | null = null;
    let shouldRememberRequestedComposerBatch = false;
    let targetFileInfo: FileInfo | null = null;
    let shouldOpenReportPreview = false;
  
    const cancelPendingAssistantFlush = () => {
      if (animationFrameId !== null && typeof window !== 'undefined') {
        window.cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
      }
    };
  
    try {
      // 获取当前选中的文件（可能为 null）
      targetFileInfo = selectedFileId && effectiveRequestFileIds.includes(selectedFileId)
        ? files[selectedFileId]
        : effectiveRequestFiles[0] ?? null;
      const orderedRequestFiles = targetFileInfo
        ? [targetFileInfo, ...effectiveRequestFiles.filter((file) => file.id !== targetFileInfo.id)]
        : effectiveRequestFiles;
  
      // 构建 FormData
      const formData = new FormData();
      if (orderedRequestFiles.length > 0) {
        orderedRequestFiles.forEach((fileInfo, index) => {
          const fileToUse = fileInfo.originalFile || fileInfo.file;
          if (!fileToUse) return;

          const fieldName = index === 0 ? 'file' : 'files';
          formData.append(fieldName, fileToUse, getCapabilityFileName(fileInfo));
        });
      }
      formData.append('instruction', instruction);
      formData.append('conversation_context', conversationContext);
      if (targetFileInfo) {
        formData.append('selected_file_name', getCapabilityFileName(targetFileInfo));
      }
  
      // 报告预览仅在存在文件且指令为分析意图时开启
      shouldOpenReportPreview = targetFileInfo !== null && isReportIntent(instruction);
      if (shouldOpenReportPreview && targetFileInfo) {
        setSelectedFileId(targetFileInfo.id);
        setPreviewPaneMode('report');
        setShowPreviewPanel(true);
        resetPreviewViewport();
        setReportProgressState(createReportProgressState({
          visible: true,
          fileId: targetFileInfo.id,
          stageId: 'request_received',
          label: '已收到分析请求',
          description: '正在准备处理',
          progress: 10,
          status: 'active',
        }));
      } else {
        setReportProgressState(createReportProgressState());
      }
  
      // 创建占位消息（流式内容将累加至此）
      const assistantMessageId = (Date.now() + 2).toString();
      setMessages(prev => [
        ...prev,
        {
          id: assistantMessageId,
          type: 'assistant',
          content: '',
          // 有文件时关联文件ID，否则为空
          fileIds: targetFileInfo ? [targetFileInfo.id] : [],
          displayMode: shouldOpenReportPreview ? 'report' : 'chat',
          timestamp: new Date()
        }
      ]);
      if (shouldOpenReportPreview && targetFileInfo) {
        setActiveReportMessageIdByFileId((prev) => ({
          ...prev,
          [targetFileInfo.id]: assistantMessageId,
        }));
      }
  
      // 调用流式 API
      const response = await fetch(buildModule1ApiUrl('/operate-stream'), {
        method: 'POST',
        body: formData,
        credentials: 'include',
        signal: abortControllerRef.current.signal
      });
  
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`请求失败: ${response.status} - ${errorText}`);
      }
  
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('无法读取响应流');
  
      let accumulatedContent = shouldOpenReportPreview ? '' : '';
      let buffer = '';
      let receivedModifications: OperationResult | null = null;
  
      const flushAssistantMessage = (force = false) => {
        if (typeof window === 'undefined') {
          updateMessageById(assistantMessageId, message => ({
            ...message,
            content: accumulatedContent
          }));
          return;
        }
  
        if (force) {
          if (animationFrameId !== null) {
            window.cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
          }
          updateMessageById(assistantMessageId, message => ({
            ...message,
            content: accumulatedContent
          }));
          return;
        }
  
        if (animationFrameId !== null) return;
  
        animationFrameId = window.requestAnimationFrame(() => {
          animationFrameId = null;
          updateMessageById(assistantMessageId, message => ({
            ...message,
            content: accumulatedContent
          }));
        });
      };
  
      while (true) {
        if (abortControllerRef.current?.signal.aborted) {
          reader.cancel();
          cancelPendingAssistantFlush();
          console.log('用户中断了流式请求');
          return;
        }
  
        const { done, value } = await reader.read();
        if (done) break;
  
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
  
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);
  
              switch (parsed.type) {
                case 'chunk':
                  if (shouldOpenReportPreview && targetFileInfo) {
                    setReportProgressState((prev) => (
                      prev.fileId === targetFileInfo.id && prev.status === 'active' && prev.progress < 80
                        ? {
                            ...prev,
                            visible: true,
                            stageId: 'generating_report',
                            label: '正在生成分析报告',
                            description: '报告内容会持续更新',
                            progress: 80,
                          }
                        : prev
                    ));
                  }
                  accumulatedContent += parsed.content;
                  flushAssistantMessage();
                  break;

                case 'stage':
                  if (targetFileInfo && parsed.content && typeof parsed.content === 'object') {
                    setReportProgressState(createReportProgressState({
                      visible: true,
                      fileId: targetFileInfo.id,
                      stageId: String(parsed.content.id || ''),
                      label: String(parsed.content.label || ''),
                      description: String(parsed.content.description || ''),
                      progress: Number(parsed.content.progress || 0),
                      status: String(parsed.content.status || 'active') as ReportProgressStatus,
                    }));
                  }
                  break;
  
                case 'modifications':
                  console.log('收到修改方案:', parsed.content);
                  // 只有在有文件时才处理修改
                  if (targetFileInfo) {
                    let realModifications: Modification[] = Array.isArray(parsed.content)
                      ? parsed.content as Modification[]
                      : [];
                    if (realModifications.length === 1 && realModifications[0].modifications) {
                      realModifications = realModifications[0].modifications as Modification[];
                    }
                    realModifications = realModifications.map((mod: Modification) => {
                      if (mod.changes && typeof mod.changes === 'object') {
                        mod = { ...mod, ...mod.changes };
                      }
                      if (mod.format_changes && typeof mod.format_changes === 'object') {
                        mod = { ...mod, ...mod.format_changes };
                      }
                      if (mod.properties && typeof mod.properties === 'object') {
                        mod = { ...mod, ...mod.properties };
                      }
                      if (mod.paragraphIndex !== undefined && mod.paragraph_index === undefined) {
                        mod.paragraph_index = mod.paragraphIndex;
                      }
                      return mod;
                    });
                    receivedModifications = {
                      success: true,
                      instruction,
                      ai_explanation: accumulatedContent,
                      modifications: realModifications,
                      file_info: {
                        name: targetFileInfo.name,
                        type: targetFileInfo.type,
                        size: targetFileInfo.size
                      }
                    };
                  }
                  break;
  
                case 'preview':
                  // 修改流程改为直接返回聊天结果，不再自动弹出预览
                  break;
  
                case 'error':
                  console.error('流式错误:', parsed.content);
                  if (shouldOpenReportPreview && targetFileInfo) {
                    setReportProgressState(createReportProgressState({
                      visible: true,
                      fileId: targetFileInfo.id,
                      stageId: 'failed',
                      label: '分析失败',
                      description: '请稍后重试，或缩小分析范围',
                      progress: 100,
                      status: 'failed',
                    }));
                  }
                  throw new Error(parsed.content);

                case 'end':
                  if (shouldOpenReportPreview && targetFileInfo) {
                    setReportProgressState((prev) => (
                      prev.fileId === targetFileInfo.id && prev.status === 'active'
                        ? {
                            ...prev,
                            visible: true,
                            stageId: 'completed',
                            label: '分析已完成',
                            description: '报告已生成完成，可继续阅读、编辑或下载',
                            progress: 100,
                            status: 'completed',
                          }
                        : prev
                    ));
                  }
                  break;
  
                default:
                  console.warn('未知消息类型:', parsed.type);
              }
            } catch (e) {
              console.error('解析流数据失败:', e, line);
            }
          }
        }
      }
  
      flushAssistantMessage(true);
  
      // 只有在有文件且有修改方案时才应用修改
      if (receivedModifications && targetFileInfo) {
        await applyModificationsToFile(receivedModifications, targetFileInfo);
      }
  
      // 更新文件状态为已完成（仅当有文件时）
      setFiles(prev => {
        const newFiles = { ...prev };
        for (const fileId of effectiveRequestFileIds) {
          if (newFiles[fileId]) {
            newFiles[fileId].status = 'completed';
            newFiles[fileId].progress = 100;
          }
        }
        return newFiles;
      });
      shouldRememberRequestedComposerBatch = requestedComposerFileIds.length > 0;
  
    } catch (error) {
      cancelPendingAssistantFlush();
      if (error instanceof Error && error.name === 'AbortError') {
        if (targetFileInfo && shouldOpenReportPreview) {
          setReportProgressState(createReportProgressState({
            visible: true,
            fileId: targetFileInfo.id,
            stageId: 'failed',
            label: '已停止生成',
            description: '你已手动停止本次分析',
            progress: 100,
            status: 'failed',
          }));
        }
        setMessages(prev => [
          ...prev,
          {
            id: Date.now().toString(),
            type: 'assistant',
            content: '⏹️ 已停止生成',
            timestamp: new Date()
          }
        ]);
        return;
      }

      console.error('处理请求失败:', error);
      if (targetFileInfo && shouldOpenReportPreview) {
        setReportProgressState(createReportProgressState({
          visible: true,
          fileId: targetFileInfo.id,
          stageId: 'failed',
          label: '分析失败',
          description: '请稍后重试，或缩小分析范围',
          progress: 100,
          status: 'failed',
        }));
      }
      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          type: 'assistant',
          content: `❌ **处理失败**\n\n${error instanceof Error ? error.message : '未知错误'}\n\n请检查网络连接或稍后重试。`,
          timestamp: new Date()
        }
      ]);
  
      // 标记现有文件为错误状态（若有）
      setFiles(prev => {
        const newFiles = { ...prev };
        for (const fileId of effectiveRequestFileIds) {
          if (newFiles[fileId]) {
            newFiles[fileId].status = 'error';
          }
        }
        return newFiles;
      });
    } finally {
      cancelPendingAssistantFlush();
      if (shouldRememberRequestedComposerBatch) {
        setRememberedFileBatchIds(requestedComposerFileIds);
      }
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  }, [inputText, isLoading, files, composerFileIds, rememberedFileBatchIds, messages, selectedFileId, applyModificationsToFile, updateMessageById, isReportIntent, resetPreviewViewport]);

  const handleKeyPress = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  }, [sendMessage]);

  // 预览控制函数
  const handleZoomIn = () => setScale((prev) => Math.min(prev + 0.1, 2.5));
  const handleZoomOut = () => setScale((prev) => Math.max(prev - 0.1, 0.5));
  const handleRotate = () => setRotation((prev) => (prev + 90) % 360);
  const handleResetView = () => {
    setScale(1);
    setRotation(0);
  };

  const switchPreviewPane = useCallback((mode: PreviewPaneMode) => {
    setPreviewPaneMode(mode);
    resetPreviewViewport();
  }, [resetPreviewViewport]);

  const togglePreviewFullscreen = useCallback(async () => {
    if (!previewPanelRef.current) return;

    try {
      if (document.fullscreenElement === previewPanelRef.current) {
        await document.exitFullscreen();
      } else {
        await previewPanelRef.current.requestFullscreen();
      }
    } catch (error) {
      console.error('切换预览全屏失败:', error);
    }
  }, []);

  const closePreviewPanel = useCallback(async () => {
    if (document.fullscreenElement === previewPanelRef.current) {
      await document.exitFullscreen();
    }

    setShowPreviewPanel(false);
  }, []);

  const openPreviewPanel = useCallback(() => {
    setShowPreviewPanel(true);
  }, []);

  // 获取指定文件的最新分析报告内容
  const getAnalysisReportForFile = useCallback((fileId: string, reportMessageId?: string): string | null => {
    const reportMessages = reportMessagesByFileId.get(fileId) ?? [];
    if (reportMessages.length === 0) return null;

    if (reportMessageId) {
      const selectedMessage = reportMessages.find((message) => message.id === reportMessageId);
      if (selectedMessage) return selectedMessage.content ?? null;
    }

    return getActiveReportMessageForFile(fileId)?.content ?? null;
  }, [getActiveReportMessageForFile, reportMessagesByFileId]);

  const hasAnalysisReportForFile = useCallback((fileId: string): boolean => (
    latestReportByFileId.has(fileId)
  ), [latestReportByFileId]);

  const getEditableReportTextForFile = useCallback((fileId: string, reportMessageId?: string): string => {
    const resolvedMessage = reportMessageId
      ? (reportMessagesByFileId.get(fileId) ?? []).find((message) => message.id === reportMessageId) ?? null
      : getActiveReportMessageForFile(fileId);
    if (!resolvedMessage) return '';

    const reportVersionKey = buildReportVersionKey(fileId, resolvedMessage.id);
    const localEditedReport = editableReportByFileId[reportVersionKey];
    const sourceReport = resolvedMessage.content ?? '';
    const normalizedSourceReport = sourceReport
      ? (formatPreparedReportContent(sourceReport).text || sourceReport)
      : '';

    if (typeof localEditedReport === 'string') {
      // Avoid letting an early empty local cache hide a later real report payload.
      if (localEditedReport.trim() || !normalizedSourceReport.trim()) {
        return localEditedReport;
      }
    }

    return normalizedSourceReport;
  }, [editableReportByFileId, getActiveReportMessageForFile, reportMessagesByFileId]);

  const handleSelectFile = useCallback((fileId: string) => {
    setSelectedFileId(fileId);
    setPreviewPaneMode(hasAnalysisReportForFile(fileId) ? 'report' : 'current');
    setPreviewReadingMode('paged');
    resetPreviewViewport();
  }, [hasAnalysisReportForFile, resetPreviewViewport]);

  const selectedFileHasReport = useMemo(
    () => Boolean(selectedFile && hasAnalysisReportForFile(selectedFile.id)),
    [hasAnalysisReportForFile, selectedFile]
  );

  const canComparePreview = useMemo(
    () => Boolean(selectedFile?.sourceFileId && comparisonFile),
    [comparisonFile, selectedFile]
  );

  const effectivePreviewPaneMode = useMemo<PreviewPaneMode>(() => {
    if (previewPaneMode === 'report' && selectedFileHasReport) return 'report';
    if (previewPaneMode === 'compare' && canComparePreview) return 'compare';
    if (previewPaneMode === 'original' && canPreviewOriginal) return 'original';
    return 'current';
  }, [canComparePreview, canPreviewOriginal, previewPaneMode, selectedFileHasReport]);

  const selectedEditableReportText = useMemo(
    () => (
      selectedFile
        ? getEditableReportTextForFile(selectedFile.id, activeReportMessageForSelectedFile?.id)
        : ''
    ),
    [activeReportMessageForSelectedFile?.id, getEditableReportTextForFile, selectedFile]
  );
  const activeReportProgress = useMemo(() => (
    selectedFile && reportProgressState.fileId === selectedFile.id && reportProgressState.visible
      ? reportProgressState
      : null
  ), [reportProgressState, selectedFile]);
  const visibleReportText = useMemo(() => {
    if (
      selectedFile
      && activeReportProgress?.status === 'active'
      && animatedReportFileId === selectedFile.id
    ) {
      return animatedReportText;
    }

    return selectedEditableReportText;
  }, [activeReportProgress?.status, animatedReportFileId, animatedReportText, selectedEditableReportText, selectedFile]);
  const preparedEditableReport = useMemo(
    () => formatPreparedReportContent(visibleReportText),
    [visibleReportText]
  );
  const selectedReportFormatting = useMemo(
    () => (activeReportVersionKey ? reportFormattingByFileId[activeReportVersionKey] ?? {} : {}),
    [activeReportVersionKey, reportFormattingByFileId]
  );
  const canUndoReportEdit = useMemo(
    () => Boolean(activeReportVersionKey && (reportHistoryByFileId[activeReportVersionKey]?.length ?? 0) > 0),
    [activeReportVersionKey, reportHistoryByFileId]
  );
  const currentSelectedReportBlock = useMemo(
    () => (
      reportSelection
        ? preparedEditableReport.blocks.find((block) => block.key === reportSelection.blockKey) ?? null
        : null
    ),
    [preparedEditableReport.blocks, reportSelection]
  );
  const currentSelectionInlineStyle = useMemo(
    () => getInlineStyleForSelection(selectedReportFormatting, reportSelection),
    [reportSelection, selectedReportFormatting]
  );
  const currentSelectionBlockType = useMemo<ReportBlockType>(
    () => selectedReportFormatting[reportSelection?.blockKey ?? '']?.type
      ?? currentSelectedReportBlock?.type
      ?? 'paragraph',
    [currentSelectedReportBlock?.type, reportSelection?.blockKey, selectedReportFormatting]
  );
  const currentSelectionTextAlign = useMemo<ReportTextAlign>(
    () => selectedReportFormatting[reportSelection?.blockKey ?? '']?.align ?? DEFAULT_REPORT_TEXT_ALIGN,
    [reportSelection?.blockKey, selectedReportFormatting]
  );
  const previousReportLengthRef = useRef(0);

  const clearReportEditingState = useCallback((preserveBrowserSelection = false) => {
    setReportSelection(null);
    setReportManualEditOpen(false);
    setReportManualEditValue('');
    if (!preserveBrowserSelection) {
      clearBrowserSelection();
    }
  }, []);

  const pushReportHistorySnapshot = useCallback((fileId: string, text: string, formatting: ReportFormattingState) => {
    setReportHistoryByFileId((prev) => ({
      ...prev,
      [fileId]: [
        ...(prev[fileId] ?? []),
        {
          text,
          formatting: cloneReportFormatting(formatting),
        },
      ].slice(-20),
    }));
  }, []);

  useEffect(() => {
    const syncedReportVersionKeys: string[] = [];

    setEditableReportByFileId((prev) => {
      let changed = false;
      const next = { ...prev };

      reportMessagesByFileId.forEach((reportMessages, fileId) => {
        reportMessages.forEach((message) => {
          const reportVersionKey = buildReportVersionKey(fileId, message.id);
          const normalizedReport = formatPreparedReportContent(message.content || '').text || message.content || '';
          const previousSource = reportSourceByVersionKeyRef.current[reportVersionKey];
          const currentEditable = prev[reportVersionKey];

          reportSourceByVersionKeyRef.current[reportVersionKey] = normalizedReport;

          if (currentEditable === undefined || currentEditable === previousSource) {
            if (currentEditable !== normalizedReport) {
              next[reportVersionKey] = normalizedReport;
              changed = true;
              syncedReportVersionKeys.push(reportVersionKey);
            }
          }
        });
      });

      return changed ? next : prev;
    });

    if (syncedReportVersionKeys.length > 0) {
      setReportFormattingByFileId((prev) => {
        let changed = false;
        const next = { ...prev };

        syncedReportVersionKeys.forEach((reportVersionKey) => {
          if (next[reportVersionKey]) {
            delete next[reportVersionKey];
            changed = true;
          }
        });

        return changed ? next : prev;
      });

      setReportHistoryByFileId((prev) => {
        let changed = false;
        const next = { ...prev };

        syncedReportVersionKeys.forEach((reportVersionKey) => {
          if ((next[reportVersionKey]?.length ?? 0) > 0) {
            next[reportVersionKey] = [];
            changed = true;
          }
        });

        return changed ? next : prev;
      });
    }
  }, [reportMessagesByFileId]);

  useEffect(() => {
    if (!reportToolbarFeedback) return undefined;

    const timeoutId = window.setTimeout(() => {
      setReportToolbarFeedback('');
    }, 1800);

    return () => window.clearTimeout(timeoutId);
  }, [reportToolbarFeedback]);

  useEffect(() => {
    if (effectivePreviewPaneMode !== 'report') {
      previousReportLengthRef.current = 0;
      return;
    }

    const currentLength = selectedEditableReportText.length;
    const previousLength = previousReportLengthRef.current;

    if (
      activeReportProgress?.status === 'active'
      && currentLength > previousLength
      && currentLength > 0
    ) {
      setReportStreamHighlightNonce((prev) => prev + 1);
    }

    previousReportLengthRef.current = currentLength;
  }, [activeReportProgress?.status, effectivePreviewPaneMode, selectedEditableReportText]);

  useEffect(() => {
    if (!selectedFile) {
      setAnimatedReportFileId(null);
      setAnimatedReportText('');
      return;
    }

    if (activeReportProgress?.status !== 'active') {
      setAnimatedReportFileId(selectedFile.id);
      setAnimatedReportText(selectedEditableReportText);
      return;
    }

    if (animatedReportFileId !== selectedFile.id) {
      setAnimatedReportFileId(selectedFile.id);
      setAnimatedReportText('');
      return;
    }

    if (animatedReportText.length > selectedEditableReportText.length) {
      setAnimatedReportText(selectedEditableReportText);
      return;
    }

    if (animatedReportText === selectedEditableReportText) {
      return;
    }

    const remaining = selectedEditableReportText.length - animatedReportText.length;
    const step = remaining > 80 ? 10 : remaining > 30 ? 6 : remaining > 12 ? 3 : 1;
    const timeoutId = window.setTimeout(() => {
      setAnimatedReportText(selectedEditableReportText.slice(0, animatedReportText.length + step));
    }, 18);

    return () => window.clearTimeout(timeoutId);
  }, [
    activeReportProgress?.status,
    animatedReportFileId,
    animatedReportText,
    selectedEditableReportText,
    selectedFile,
  ]);

  const refreshReportSelection = useCallback(() => {
    if (
      effectivePreviewPaneMode !== 'report'
      || !selectedFile
      || !activeReportVersionKey
      || !reportContentRef.current
    ) {
      if (!reportManualEditOpen) {
        setReportSelection(null);
      }
      return;
    }

    const nextSelection = extractReportSelection(reportContentRef.current);
    if (!nextSelection) {
      if (!reportManualEditOpen) {
        setReportSelection(null);
      }
      return;
    }

    setReportSelection({
      ...nextSelection,
      fileId: selectedFile.id,
      reportVersionKey: activeReportVersionKey,
    });

    if (reportManualEditOpen) {
      setReportManualEditValue(nextSelection.selectedText);
    }
  }, [activeReportVersionKey, effectivePreviewPaneMode, reportManualEditOpen, selectedFile]);

  useEffect(() => {
    if (effectivePreviewPaneMode !== 'report') {
      clearReportEditingState();
      return undefined;
    }

    const handleSelectionChange = () => {
      refreshReportSelection();
    };
    const handleScroll = () => {
      refreshReportSelection();
    };
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (!target) return;
      if (reportContentRef.current?.contains(target)) return;
      if (target.closest('[data-report-selection-toolbar]')) return;
      clearReportEditingState();
    };

    document.addEventListener('selectionchange', handleSelectionChange);
    document.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('resize', handleScroll);
    window.addEventListener('scroll', handleScroll, true);
    reportPreviewScrollRef.current?.addEventListener('scroll', handleScroll);

    return () => {
      document.removeEventListener('selectionchange', handleSelectionChange);
      document.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('resize', handleScroll);
      window.removeEventListener('scroll', handleScroll, true);
      reportPreviewScrollRef.current?.removeEventListener('scroll', handleScroll);
    };
  }, [clearReportEditingState, effectivePreviewPaneMode, refreshReportSelection]);

  useEffect(() => {
    clearReportEditingState();
  }, [activeReportVersionKey, clearReportEditingState, selectedFile?.id]);

  const commitReportSelectionEdit = useCallback((replacementText: string, feedback: string): boolean => {
    if (
      !selectedFile
      || !activeReportVersionKey
      || !reportSelection
      || reportSelection.fileId !== selectedFile.id
      || reportSelection.reportVersionKey !== activeReportVersionKey
    ) {
      return false;
    }

    const nextReportText = replaceSelectionInPreparedReport(
      preparedEditableReport,
      reportSelection,
      replacementText,
    );

    if (nextReportText === null) {
      return false;
    }

    if (nextReportText === selectedEditableReportText) {
      setReportToolbarFeedback('未生成可应用结果');
      return true;
    }

    const reportVersionKey = activeReportVersionKey;
    const nextFormatting = adjustReportFormattingAfterTextReplacement(
      reportFormattingByFileId[reportVersionKey] ?? {},
      reportSelection,
      replacementText,
    );

    pushReportHistorySnapshot(reportVersionKey, selectedEditableReportText, reportFormattingByFileId[reportVersionKey] ?? {});
    setEditableReportByFileId((prev) => ({
      ...prev,
      [reportVersionKey]: nextReportText,
    }));
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [reportVersionKey]: nextFormatting,
    }));
    setReportToolbarFeedback(feedback);
    clearReportEditingState();
    return true;
  }, [
    activeReportVersionKey,
    clearReportEditingState,
    preparedEditableReport,
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
    selectedFile,
  ]);

  const handleReportQuickEdit = useCallback(async (action: ReportQuickEditAction) => {
    if (!reportSelection) return;

    setReportBusyAction(action);
    try {
      await waitForNextPaint();
      const nextText = applyReportQuickEdit(action, reportSelection.selectedText);
      if (!nextText.trim()) {
        setReportToolbarFeedback('未生成可应用结果');
        return;
      }

      const applied = commitReportSelectionEdit(nextText, REPORT_ACTION_FEEDBACK[action]);
      if (!applied) {
        setReportToolbarFeedback('本次选区暂时无法编辑，请重新选择更小范围内容');
      }
    } finally {
      setReportBusyAction(null);
    }
  }, [commitReportSelectionEdit, reportSelection]);

  const handleOpenManualReportEdit = useCallback(() => {
    if (!reportSelection) return;
    setReportManualEditOpen(true);
    setReportManualEditValue(reportSelection.selectedText);
  }, [reportSelection]);

  const handleApplyManualReportEdit = useCallback(async () => {
    if (!reportSelection) return;

    setReportManualEditBusy(true);
    try {
      await waitForNextPaint();
      const applied = commitReportSelectionEdit(reportManualEditValue, '已手动修改选中文本');
      if (!applied) {
        setReportToolbarFeedback('本次选区暂时无法编辑，请重新选择更小范围内容');
      }
    } finally {
      setReportManualEditBusy(false);
    }
  }, [commitReportSelectionEdit, reportManualEditValue, reportSelection]);

  const handleUndoReportEdit = useCallback(() => {
    if (!activeReportVersionKey) return;

    const history = reportHistoryByFileId[activeReportVersionKey] ?? [];
    if (!history.length) return;

    const previousSnapshot = history[history.length - 1];
    setEditableReportByFileId((prev) => ({
      ...prev,
      [activeReportVersionKey]: previousSnapshot.text,
    }));
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [activeReportVersionKey]: cloneReportFormatting(previousSnapshot.formatting),
    }));
    setReportHistoryByFileId((prev) => ({
      ...prev,
      [activeReportVersionKey]: history.slice(0, -1),
    }));
    setReportToolbarFeedback('已回退上一步');
    clearReportEditingState();
  }, [activeReportVersionKey, clearReportEditingState, reportHistoryByFileId]);

  const handleApplyReportTextColor = useCallback((value: string | null) => {
    if (!activeReportVersionKey || !reportSelection) return;

    const currentFormatting = reportFormattingByFileId[activeReportVersionKey] ?? {};
    const nextFormatting = applyInlineFormatToSelection(currentFormatting, reportSelection, { color: value });

    if (JSON.stringify(nextFormatting) === JSON.stringify(currentFormatting)) {
      return;
    }

    pushReportHistorySnapshot(activeReportVersionKey, selectedEditableReportText, currentFormatting);
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [activeReportVersionKey]: nextFormatting,
    }));
    setReportToolbarFeedback(value ? '已更新文字颜色' : '已恢复默认文字颜色');
  }, [
    activeReportVersionKey,
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
  ]);

  const handleApplyReportFontSize = useCallback((value: string | null) => {
    if (!activeReportVersionKey || !reportSelection) return;

    const currentFormatting = reportFormattingByFileId[activeReportVersionKey] ?? {};
    const nextFormatting = applyInlineFormatToSelection(currentFormatting, reportSelection, { fontSize: value });

    if (JSON.stringify(nextFormatting) === JSON.stringify(currentFormatting)) {
      return;
    }

    pushReportHistorySnapshot(activeReportVersionKey, selectedEditableReportText, currentFormatting);
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [activeReportVersionKey]: nextFormatting,
    }));
    setReportToolbarFeedback(value ? '已更新字号' : '已恢复默认字号');
  }, [
    activeReportVersionKey,
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
  ]);

  const handleApplyReportBlockType = useCallback((value: ReportBlockType) => {
    if (!activeReportVersionKey || !reportSelection) return;

    const currentFormatting = reportFormattingByFileId[activeReportVersionKey] ?? {};
    const nextFormatting = applyBlockFormatPatch(currentFormatting, reportSelection.blockKey, {
      type: currentSelectedReportBlock?.type === value ? null : value,
    });

    if (JSON.stringify(nextFormatting) === JSON.stringify(currentFormatting)) {
      return;
    }

    pushReportHistorySnapshot(activeReportVersionKey, selectedEditableReportText, currentFormatting);
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [activeReportVersionKey]: nextFormatting,
    }));
    setReportToolbarFeedback('已更新段落级别');
  }, [
    activeReportVersionKey,
    currentSelectedReportBlock?.type,
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
  ]);

  const handleApplyReportTextAlign = useCallback((value: ReportTextAlign) => {
    if (!activeReportVersionKey || !reportSelection) return;

    const currentFormatting = reportFormattingByFileId[activeReportVersionKey] ?? {};
    const nextFormatting = applyBlockFormatPatch(currentFormatting, reportSelection.blockKey, {
      align: value === DEFAULT_REPORT_TEXT_ALIGN ? null : value,
    });

    if (JSON.stringify(nextFormatting) === JSON.stringify(currentFormatting)) {
      return;
    }

    pushReportHistorySnapshot(activeReportVersionKey, selectedEditableReportText, currentFormatting);
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [activeReportVersionKey]: nextFormatting,
    }));
    setReportToolbarFeedback('已更新段落对齐方式');
  }, [
    activeReportVersionKey,
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
  ]);

  const downloadEditedReport = useCallback(async (file: FileInfo) => {
    const reportText = getEditableReportTextForFile(file.id).trim();
    if (!reportText) return;

    setReportDownloadBusy(true);
    try {
      const sourceFile = file.originalFile || file.file;
      const ext = fileExt(file.name);

      if (sourceFile && SAVEABLE_REPORT_EXTENSIONS.has(ext)) {
        const formData = new FormData();
        formData.append('file', sourceFile, sourceFile.name || file.name);
        formData.append('content', reportText);

        const response = await fetch(buildModule1ApiUrl('/save-edited-document'), {
          method: 'POST',
          body: formData,
          credentials: 'include',
        });

        if (response.ok) {
          const outputBlob = await response.blob();
          const outputName = parseContentDispositionFilename(response.headers.get('Content-Disposition'))
            || `edited_${file.name}`;
          downloadBlob(outputBlob, outputName);
          return;
        }
      }

      const baseName = file.name.replace(/\.[^/.]+$/, '') || file.name;
      downloadBlob(
        new Blob([reportText], { type: 'text/plain;charset=utf-8' }),
        `分析提取报告_${baseName}.txt`,
      );
    } catch (error) {
      console.error('下载编辑后报告失败:', error);
      alert('下载编辑后报告失败，请重试');
    } finally {
      setReportDownloadBusy(false);
    }
  }, [getEditableReportTextForFile]);

  const isCompareMode = effectivePreviewPaneMode === 'compare';
  const isPreviewPdf = effectivePreviewPaneMode !== 'report' && previewCategory === 'pdf' && (!isCompareMode || comparisonCategory === 'pdf');
  const isPreviewExcel = effectivePreviewPaneMode !== 'report' && !isCompareMode && previewCategory === 'excel';
  const isPreviewText = effectivePreviewPaneMode !== 'report' && previewCategory === 'text' && (!isCompareMode || comparisonCategory === 'text');
  const isPreviewImage = effectivePreviewPaneMode !== 'report' && previewCategory === 'image' && (!isCompareMode || comparisonCategory === 'image');
  const isDocxPreview = effectivePreviewPaneMode !== 'report' && !isCompareMode && rawPreviewCategory === 'word';
  const isDocxAwaitingFidelity = isDocxPreview
    && !previewedFile?.convertedPdfBlob
    && previewedFile?.conversionStatus === 'converting';
  const isDocxPreviewFailed = isDocxPreview
    && !previewedFile?.convertedPdfBlob
    && previewedFile?.conversionStatus === 'error';
  const usesPagedPdfPreview = isPreviewPdf && isCompareMode;
  const canTransformPreview = effectivePreviewPaneMode !== 'report' && (isPreviewPdf || isPreviewImage || isPreviewText);
  const currentFileButtonLabel = selectedFile?.sourceFileId ? '修改文件' : '当前文件';
  const isPreviewingOriginalFile = Boolean(
    selectedFile?.sourceFileId
    && previewedFile?.id
    && previewedFile.id === selectedFile.sourceFileId
  );
  const maxPdfPage = useMemo(() => {
    if (!isPreviewPdf) return null;

    if (isCompareMode) {
      const counts = [primaryPdfPageCount, comparisonPdfPageCount].filter(
        (count): count is number => typeof count === 'number' && count > 0
      );
      return counts.length ? Math.min(...counts) : null;
    }

    return primaryPdfPageCount;
  }, [comparisonPdfPageCount, isCompareMode, isPreviewPdf, primaryPdfPageCount]);
  const handlePrimaryPdfLoadSuccess = useCallback((pdf: { numPages: number }) => {
    setPrimaryPdfPageCount(prev => (prev === pdf.numPages ? prev : pdf.numPages));
  }, []);
  const handleComparisonPdfLoadSuccess = useCallback((pdf: { numPages: number }) => {
    setComparisonPdfPageCount(prev => (prev === pdf.numPages ? prev : pdf.numPages));
  }, []);

  useEffect(() => {
    setPrimaryPdfPageCount(null);
  }, [effectivePreviewPaneMode, previewPdfSource, previewedFile?.id]);

  useEffect(() => {
    setComparisonPdfPageCount(null);
  }, [comparisonFile?.id, comparisonPdfSource, effectivePreviewPaneMode]);

  useEffect(() => {
    if (!maxPdfPage) return;
    setPdfPage(prev => Math.min(prev, maxPdfPage));
  }, [maxPdfPage]);

  const navigateToPdfPage = useCallback((nextPage: number) => {
    const boundedPage = maxPdfPage
      ? Math.min(Math.max(Math.round(nextPage), 1), maxPdfPage)
      : Math.max(Math.round(nextPage), 1);

    setPdfPage(boundedPage);
    setPdfPageInput(String(boundedPage));

    if (!usesPagedPdfPreview || isCompareMode) {
      setPdfScrollRequest(createPdfScrollRequest(boundedPage));
    }
  }, [isCompareMode, maxPdfPage, usesPagedPdfPreview]);

  const commitPdfPageInput = useCallback(() => {
    const nextPage = Number.parseInt(pdfPageInput, 10);
    if (!Number.isFinite(nextPage)) {
      setPdfPageInput(String(pdfPage));
      return;
    }

    navigateToPdfPage(nextPage);
  }, [navigateToPdfPage, pdfPage, pdfPageInput]);

  useEffect(() => {
    setPdfPageInput(String(pdfPage));
  }, [pdfPage]);

  // 下载文件
  const downloadFile = useCallback((file: FileInfo) => {
    const fileToDownload = file.file || file.originalFile;
    if (!fileToDownload) return;
    
    try {
      const url = URL.createObjectURL(fileToDownload);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (error) {
      console.error('下载文件失败:', error);
      alert('下载文件失败，请重试');
    }
  }, []);

  // 导出结果
  const exportResults = useCallback(() => {
    if (fileList.length === 0) return;

    const exportData = {
      files: fileList.map(f => ({
        name: f.name,
        size: f.size,
        status: f.status,
        result: f.result,
        uploadTime: f.uploadTime
      })),
      messages: messages
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `doc-interaction-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [fileList, messages]);

  const isSuggestionEligibleAssistantMessage = useCallback((message: Message) => (
    message.type === 'assistant'
    && Boolean(message.content.trim())
    && !message.content.startsWith('❌')
    && !message.content.startsWith('⏹️')
  ), []);

  const latestAssistantMessageWithSuggestions = useMemo(
    () => [...messages].reverse().find(isSuggestionEligibleAssistantMessage) ?? null,
    [isSuggestionEligibleAssistantMessage, messages]
  );

  const latestAssistantSuggestionFile = useMemo(() => {
    if (!latestAssistantMessageWithSuggestions) return selectedFile ?? null;

    const relatedFileId = latestAssistantMessageWithSuggestions.fileIds?.find((fileId) => Boolean(files[fileId]));
    return relatedFileId ? files[relatedFileId] : (selectedFile ?? null);
  }, [files, latestAssistantMessageWithSuggestions, selectedFile]);

  const latestUserInstructionForSuggestions = useMemo(() => {
    if (!latestAssistantMessageWithSuggestions) return '';

    const assistantIndex = messages.findIndex((message) => message.id === latestAssistantMessageWithSuggestions.id);
    if (assistantIndex <= 0) return '';

    for (let index = assistantIndex - 1; index >= 0; index -= 1) {
      const candidate = messages[index];
      if (candidate.type === 'user' && candidate.content.trim()) {
        return candidate.content.trim();
      }
    }

    return '';
  }, [latestAssistantMessageWithSuggestions, messages]);

  const buildFollowUpSuggestions = useCallback((message: Message, relatedFile: FileInfo | null, latestUserInstruction: string): PromptSuggestionItem[] => {
    const capabilityFileName = getCapabilityFileName(relatedFile);
    const fileLabel = capabilityFileName ? `《${capabilityFileName}》` : '这份文档';
    const relatedFileExt = getCapabilityFileExt(relatedFile);
    const normalized = `${latestUserInstruction} ${message.content} ${message.displayMode ?? ''}`.toLowerCase();
    const isAnalysisIntent = /分析|总结|摘要|结论|归纳|说明|报告/.test(normalized) || message.displayMode === 'report';
    const isRiskIntent = /风险|合同|合规|条款|争议|违约|责任|义务/.test(normalized);
    const isModificationIntent = /优化|润色|改写|修改|表达|正式|标题|段落|措辞|文风/.test(normalized);
    const isExtractionIntent = /金额|日期|数据|统计|表格|数值|excel|汇总|提取/.test(normalized);

    const analysisSuggestions: PromptSuggestionItem[] = [
      {
        label: '核心总结',
        prompt: `总结${fileLabel}的核心观点和重点结论`,
        icon: Brain
      },
      {
        label: '200字摘要',
        prompt: `把${fileLabel}的分析结果压缩成 200 字摘要`,
        icon: FileText
      },
      {
        label: '结论优先',
        prompt: `只保留最关键的信息，重新输出${fileLabel}的结论版分析`,
        icon: Brain
      },
      {
        label: '表格整理',
        prompt: `把${fileLabel}的分析结果整理成表格，字段包含：事项、发现、说明`,
        icon: Layers
      },
      {
        label: '风险审阅',
        prompt: `检查${fileLabel}里可能存在的风险点、歧义和遗漏项`,
        icon: AlertCircle
      },
      {
        label: '关键信息',
        prompt: `提取${fileLabel}中的关键数据、日期、金额和人物信息`,
        icon: ScanLine
      }
    ];

    const extractionSuggestions: PromptSuggestionItem[] = [
      {
        label: '关键信息',
        prompt: `提取${fileLabel}中的关键数据、日期、金额和人物信息`,
        icon: ScanLine
      },
      {
        label: '单列金额',
        prompt: `把${fileLabel}中的金额和日期单独列成清单`,
        icon: ScanLine
      },
      {
        label: '按字段分组',
        prompt: `把${fileLabel}提取到的信息按日期、金额、人员、机构重新分组输出`,
        icon: Layers
      },
      {
        label: '表格输出',
        prompt: `把${fileLabel}中的关键数据整理成表格格式输出`,
        icon: FileText
      },
      {
        label: '结果核对',
        prompt: `帮我复核${fileLabel}里提取到的关键数据是否完整，有没有明显遗漏`,
        icon: AlertCircle
      },
      {
        label: '摘要版提取',
        prompt: `只保留最重要的信息，输出${fileLabel}的精简提取结果`,
        icon: Brain
      }
    ];

    const modificationSuggestions: PromptSuggestionItem[] = [
      {
        label: '专业润色',
        prompt: `帮我优化${fileLabel}的表达，让措辞更专业、结构更清晰`,
        icon: Sparkles
      },
      {
        label: '更正式',
        prompt: `把${fileLabel}改成更正式、更像公文的表达`,
        icon: FileText
      },
      {
        label: '结构优化',
        prompt: `在保留原意的前提下，优化${fileLabel}的标题、段落层次和整体结构`,
        icon: Layers
      },
      {
        label: '生成修改版',
        prompt: `在保留原有结构的前提下，直接修改${fileLabel}并生成修改版`,
        icon: FileText
      },
      {
        label: '改动清单',
        prompt: `列出针对${fileLabel}建议修改或已修改的关键点，方便我对比查看`,
        icon: Layers
      },
      {
        label: '再精简些',
        prompt: `在不改变原意的前提下，把${fileLabel}再精简 30%`,
        icon: Sparkles
      }
    ];

    const riskSuggestions: PromptSuggestionItem[] = [
      {
        label: '风险审阅',
        prompt: `检查${fileLabel}里可能存在的风险点、歧义和遗漏项`,
        icon: AlertCircle
      },
      {
        label: '高风险条款',
        prompt: `指出${fileLabel}里最容易引发争议的条款，并解释原因`,
        icon: AlertCircle
      },
      {
        label: '风险排序',
        prompt: `把${fileLabel}中的风险点按高、中、低优先级重新排序，并说明依据`,
        icon: Layers
      },
      {
        label: '修改建议',
        prompt: `针对${fileLabel}里识别出的风险点，给出一版更稳妥的修改建议`,
        icon: Sparkles
      },
      {
        label: '遗漏项检查',
        prompt: `继续检查${fileLabel}里可能遗漏的责任、时间节点和约束条件`,
        icon: ScanLine
      },
      {
        label: '结论摘要',
        prompt: `把${fileLabel}的风险分析整理成简明结论`,
        icon: Brain
      }
    ];

    const excelAnalysisSuggestions: PromptSuggestionItem[] = [
      {
        label: '指标总览',
        prompt: `概括${fileLabel}里的核心指标、异常项和关键结论`,
        icon: Brain
      },
      {
        label: '异常数据',
        prompt: `检查${fileLabel}中的异常值、空值、重复项和格式问题`,
        icon: AlertCircle
      },
      {
        label: '汇总统计',
        prompt: `按列统计${fileLabel}中的总数、均值、最大值和最小值`,
        icon: Layers
      },
      {
        label: '趋势变化',
        prompt: `分析${fileLabel}中的趋势变化和波动点`,
        icon: Brain
      },
      {
        label: '关键字段',
        prompt: `提取${fileLabel}中的关键字段、日期、金额和分类信息`,
        icon: ScanLine
      },
      {
        label: '结论表',
        prompt: `把${fileLabel}的分析结果整理成清晰的结论表`,
        icon: FileText
      }
    ];

    const excelExtractionSuggestions: PromptSuggestionItem[] = [
      {
        label: '字段提取',
        prompt: `提取${fileLabel}中的关键字段、日期、金额和分类信息`,
        icon: ScanLine
      },
      {
        label: '金额清单',
        prompt: `把${fileLabel}中的金额列、日期列和对应项目整理成清单`,
        icon: FileText
      },
      {
        label: '按表汇总',
        prompt: `按工作表分别总结${fileLabel}的主要数据和结论`,
        icon: Layers
      },
      {
        label: '异常标注',
        prompt: `标出${fileLabel}中需要重点复核的异常数据或空白单元格`,
        icon: AlertCircle
      },
      {
        label: '分类汇总',
        prompt: `把${fileLabel}按类别、时间或负责人重新汇总输出`,
        icon: Layers
      },
      {
        label: '业务结论',
        prompt: `基于${fileLabel}的数据给我一个简明业务结论`,
        icon: Brain
      }
    ];

    const imageSuggestions: PromptSuggestionItem[] = [
      {
        label: '识别正文',
        prompt: `识别${fileLabel}中的主要文字内容，并按段落整理`,
        icon: ScanLine
      },
      {
        label: '提取表格',
        prompt: `只提取${fileLabel}里识别到的表格或清单内容`,
        icon: Layers
      },
      {
        label: '关键信息',
        prompt: `从${fileLabel}中提取关键日期、金额、编号和名称`,
        icon: FileText
      },
      {
        label: '疑似错误',
        prompt: `标出${fileLabel}里疑似识别错误、模糊或缺失的内容`,
        icon: AlertCircle
      },
      {
        label: '图片摘要',
        prompt: `总结${fileLabel}里的核心内容和重点信息`,
        icon: Brain
      },
      {
        label: '清洗结果',
        prompt: `把${fileLabel}识别结果中的错位、空行和重复内容清理干净`,
        icon: Sparkles
      }
    ];

    const pdfSuggestions: PromptSuggestionItem[] = [
      {
        label: '核心总结',
        prompt: `总结${fileLabel}的核心内容和主要结论`,
        icon: Brain
      },
      {
        label: '关键信息',
        prompt: `提取${fileLabel}中的日期、金额、人物和关键条款`,
        icon: ScanLine
      },
      {
        label: '结构梳理',
        prompt: `按章节整理${fileLabel}的重点内容和对应页次`,
        icon: Layers
      },
      {
        label: '表格整理',
        prompt: `把${fileLabel}中出现的表格或清单内容整理出来`,
        icon: FileText
      },
      {
        label: '风险审阅',
        prompt: `检查${fileLabel}里可能存在的风险点、歧义和遗漏项`,
        icon: AlertCircle
      },
      {
        label: '结论摘要',
        prompt: `把${fileLabel}的分析结果压缩成简明结论`,
        icon: Brain
      }
    ];

    const ocrSuggestions: PromptSuggestionItem[] = [
      {
        label: '正文重排',
        prompt: `把从${fileLabel}识别出的内容按标题、正文、表格重新整理`,
        icon: Layers
      },
      {
        label: '提取表格',
        prompt: `只提取${fileLabel}里识别到的表格或清单内容`,
        icon: ScanLine
      },
      {
        label: '疑似错误',
        prompt: `标出${fileLabel}中疑似识别错误或不确定的文字内容`,
        icon: AlertCircle
      },
      {
        label: 'OCR摘要',
        prompt: `总结从${fileLabel}识别出的核心内容`,
        icon: Brain
      },
      {
        label: '结构清理',
        prompt: `把${fileLabel}识别结果中的重复、空行和错位内容整理干净`,
        icon: Sparkles
      },
      {
        label: '关键信息',
        prompt: `从${fileLabel}识别结果里提取关键日期、金额和名称`,
        icon: FileText
      }
    ];

    const defaultSuggestions: PromptSuggestionItem[] = [
      {
        label: '核心总结',
        prompt: `总结${fileLabel}的核心观点和重点结论`,
        icon: Brain
      },
      {
        label: '关键信息',
        prompt: `提取${fileLabel}中的关键数据、日期、金额和人物信息`,
        icon: ScanLine
      },
      {
        label: '风险审阅',
        prompt: `检查${fileLabel}里可能存在的风险点、歧义和遗漏项`,
        icon: AlertCircle
      },
      {
        label: '专业润色',
        prompt: `帮我优化${fileLabel}的表达，让措辞更专业、结构更清晰`,
        icon: Sparkles
      },
      {
        label: '生成修改版',
        prompt: `在保留原有结构的前提下，直接修改${fileLabel}并生成修改版`,
        icon: FileText
      },
      {
        label: '改动清单',
        prompt: `列出针对${fileLabel}建议修改或已修改的关键点，方便我对比查看`,
        icon: Layers
      }
    ];

    const isImageFile = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(relatedFileExt);
    const isExcelFile = ['xls', 'xlsx'].includes(relatedFileExt);
    const isEditableDocFile = ['doc', 'docx', 'md', 'txt'].includes(relatedFileExt);
    const isPdfFile = relatedFileExt === 'pdf';

    const suggestionPool = isImageFile
      ? [...imageSuggestions, ...ocrSuggestions]
      : isExcelFile
        ? (isAnalysisIntent
          ? [...excelAnalysisSuggestions, ...excelExtractionSuggestions]
          : [...excelExtractionSuggestions, ...excelAnalysisSuggestions])
        : isEditableDocFile
          ? (isRiskIntent
            ? [...riskSuggestions, ...analysisSuggestions, ...modificationSuggestions, ...extractionSuggestions]
            : isModificationIntent
              ? [...modificationSuggestions, ...analysisSuggestions, ...riskSuggestions, ...extractionSuggestions]
              : isExtractionIntent
                ? [...extractionSuggestions, ...analysisSuggestions, ...riskSuggestions, ...modificationSuggestions]
                : [...analysisSuggestions, ...modificationSuggestions, ...riskSuggestions, ...extractionSuggestions])
          : isPdfFile
            ? (isRiskIntent
              ? [...riskSuggestions, ...pdfSuggestions, ...extractionSuggestions]
              : isExtractionIntent
                ? [...pdfSuggestions, ...extractionSuggestions, ...analysisSuggestions]
                : [...pdfSuggestions, ...analysisSuggestions, ...extractionSuggestions])
            : /图片|ocr|识别|扫描/.test(normalized)
              ? [...imageSuggestions, ...ocrSuggestions]
              : isRiskIntent
                ? [...riskSuggestions, ...analysisSuggestions, ...extractionSuggestions]
                : isModificationIntent
                  ? [...modificationSuggestions, ...analysisSuggestions, ...extractionSuggestions]
                  : isExtractionIntent
                    ? [...extractionSuggestions, ...analysisSuggestions, ...riskSuggestions]
                    : [...defaultSuggestions, ...analysisSuggestions, ...extractionSuggestions];

    return suggestionPool.filter((item, index, array) => (
      array.findIndex((candidate) => candidate.prompt === item.prompt) === index
    ));
  }, []);

  const followUpSuggestions = useMemo(
    () => latestAssistantMessageWithSuggestions
      ? buildFollowUpSuggestions(latestAssistantMessageWithSuggestions, latestAssistantSuggestionFile, latestUserInstructionForSuggestions)
      : [],
    [buildFollowUpSuggestions, latestAssistantMessageWithSuggestions, latestAssistantSuggestionFile, latestUserInstructionForSuggestions]
  );

  const visibleFollowUpSuggestions = useMemo(
    () => getCycledItems(followUpSuggestions, followUpSuggestionBatchIndex * 6, 6),
    [followUpSuggestionBatchIndex, followUpSuggestions]
  );

  const hasMultipleFollowUpSuggestionBatches = followUpSuggestions.length > 6;

  useEffect(() => {
    setFollowUpSuggestionBatchIndex(0);
  }, [latestAssistantMessageWithSuggestions?.id, latestAssistantMessageWithSuggestions?.content, latestUserInstructionForSuggestions]);

  const activeConversationTitle = activeConversation?.title ?? '新对话';
  const activeConversationTimestamp = useMemo(
    () => activeConversation ? formatConversationTimestamp(activeConversation.updatedAt) : '刚刚',
    [activeConversation]
  );
  const activeInstructionTargetFile = useMemo(
    () => selectedFile ?? fileList[0] ?? null,
    [fileList, selectedFile]
  );
  const composerPlaceholder = useMemo(() => {
    if (!activeInstructionTargetFile) return '输入你的指令';

    const ext = getCapabilityFileExt(activeInstructionTargetFile);

    if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(ext)) {
      return '例如：识别这张图片中的文字，并提取关键信息';
    }

    if (['xls', 'xlsx'].includes(ext)) {
      return '例如：分析这个表格的关键数据、异常项和趋势';
    }

    if (ext === 'pdf') {
      return '例如：总结这份 PDF 的重点内容，并标出风险点';
    }

    return '例如：总结这份文档、提取重点，或直接生成修改版';
  }, [activeInstructionTargetFile]);

  const cycleFollowUpSuggestions = useCallback(() => {
    setFollowUpSuggestionBatchIndex(prev => prev + 1);
  }, []);

  const shouldCollapseComposer = useMemo(() => (
    messages.length > 0
    && isBrowsingHistory
    && !isComposerHovered
    && !isComposerFocused
    && !inputText.trim()
    && !isDocumentDragOver
    && !isLoading
  ), [inputText, isBrowsingHistory, isComposerFocused, isComposerHovered, isDocumentDragOver, isLoading, messages.length]);
  const isInitialLanding = messages.length === 0 && fileList.length === 0 && !showPreviewPanel;
  const initialLandingPlaceholder = '尽管问，带图也行';

  const expandComposer = useCallback((focusTextarea = false) => {
    setIsComposerHovered(true);

    if (messagesViewportRef.current) {
      shouldAutoScrollRef.current = true;
    }

    if (!focusTextarea || typeof window === 'undefined') return;
    window.setTimeout(() => {
      composerTextareaRef.current?.focus();
    }, 0);
  }, []);

  return (
    <div
      ref={workbenchRootRef}
      className={`relative h-[100dvh] max-h-[100dvh] min-h-0 w-full overflow-hidden [overflow:clip] ${
        isInitialLanding
          ? 'bg-[linear-gradient(136deg,#eef2fa_0%,#f3f6fb_52%,#edf2fa_100%)]'
          : 'bg-[linear-gradient(140deg,#eef2fa_0%,#f2f5fb_34%,#f4f7fc_68%,#edf3fb_100%)]'
      } dark:bg-[linear-gradient(160deg,#020617_0%,#0f172a_35%,#111827_72%,#020617_100%)]`}
    >
      <div
        className={`pointer-events-none absolute inset-0 ${
          isInitialLanding
            ? 'bg-[radial-gradient(150%_96%_at_50%_18%,rgba(255,255,255,0.56),rgba(255,255,255,0)_52%),linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02))]'
            : 'bg-[radial-gradient(circle_at_14%_16%,rgba(214,222,242,0.34),transparent_34%),radial-gradient(circle_at_88%_10%,rgba(225,236,245,0.28),transparent_28%),linear-gradient(180deg,rgba(255,255,255,0.16),rgba(255,255,255,0.02))]'
        } dark:bg-[radial-gradient(circle_at_top_left,_rgba(37,99,235,0.18),_transparent_24%),radial-gradient(circle_at_bottom_right,_rgba(6,182,212,0.12),_transparent_28%)]`}
      />
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className={`absolute left-0 top-0 ${isInitialLanding ? 'h-[560px] w-[560px] -translate-x-[34%] -translate-y-[18%] bg-[rgba(227,237,253,0.72)] blur-[132px]' : 'h-[360px] w-[360px] -translate-x-[34%] -translate-y-[26%] bg-[#dde4f4]/42 blur-3xl'} rounded-full dark:bg-blue-500/10`} />
        <div className={`absolute left-1/2 top-0 ${isInitialLanding ? 'h-[460px] w-[860px] -translate-x-1/2 -translate-y-[26%] bg-white/55 blur-[120px] dark:bg-sky-400/10' : 'hidden'} rounded-full`} />
        <div className={`absolute right-0 top-0 ${isInitialLanding ? 'h-[500px] w-[500px] translate-x-[14%] -translate-y-[16%] bg-[rgba(231,249,254,0.78)] blur-[136px]' : 'h-[300px] w-[300px] translate-x-[12%] -translate-y-[20%] bg-[#e5edf4]/46 blur-3xl'} rounded-full dark:bg-cyan-400/10`} />
        <div className={`${isInitialLanding ? 'absolute bottom-[-150px] left-[12%] h-[340px] w-[460px] bg-[rgba(227,237,253,0.34)] blur-[132px] dark:bg-blue-500/10' : 'hidden'} rounded-full`} />
      </div>
  
      <div className="relative z-10 flex h-full min-h-0 flex-col">
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <aside
            className={`relative min-h-0 shrink-0 overflow-hidden bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,251,255,0.94))] dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.94),rgba(2,6,23,0.92))] transition-all duration-300 ease-out ${
              isConversationSidebarCollapsed ? 'w-0 border-r-0 opacity-0 pointer-events-none' : 'w-[288px] border-r border-[rgba(191,216,255,0.42)] dark:border-slate-800/80 opacity-100'
            }`}
          >
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(96,165,250,0.06),_transparent_34%)]" />
            <div className="relative z-10 flex h-full flex-col">
              <div className="border-b border-[rgba(194,219,255,0.16)] p-3 pt-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1 select-none">
                    <div
                      className="flex items-center gap-1.5 leading-none"
                      aria-label="AI文档处理"
                    >
                      <button
                        type="button"
                        onClick={() => setIsConversationSidebarCollapsed(true)}
                        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] ${LANDING_CORNER_BUTTON_CLASS}`}
                        title="收起历史对话栏"
                        aria-label="收起历史对话栏"
                      >
                        <img
                          src={SIDEBAR_TOGGLE_ICON_SRC}
                          alt=""
                          aria-hidden="true"
                          className="h-4 w-4 rotate-180 object-contain opacity-80 dark:brightness-0 dark:invert"
                        />
                      </button>
                      <button
                        type="button"
                        onClick={createNewConversation}
                        disabled={isLoading}
                        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] disabled:cursor-not-allowed disabled:opacity-40 ${COBALT_GLASS_BUTTON_CLASS}`}
                        title="创建新对话"
                        aria-label="创建新对话"
                      >
                        <Plus size={16} />
                      </button>
                      <span className="truncate bg-[linear-gradient(135deg,#244a80_0%,#2f67c7_52%,#0f8ea8_100%)] bg-clip-text text-[16px] font-bold tracking-wider text-transparent dark:bg-[linear-gradient(135deg,#e2e8f0_0%,#cbd5e1_42%,#7dd3fc_100%)]">
                        分析文档
                      </span>
                      <span className="ml-1 shrink-0 text-[10px] text-slate-400">刚刚</span>
                    </div>
                  </div>
                </div>
              </div>
  
              <div className="flex-1 overflow-y-auto p-3 pt-3">
                <div className="mb-3 flex items-center justify-between px-1">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#6d8094] dark:text-slate-400">历史记录</span>
                  <span className="rounded-full border border-[#d9e7fd] bg-white px-2 py-0.5 text-[10px] font-medium text-[#2d5787] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                    {orderedConversations.length}
                  </span>
                </div>
  
                <div className="space-y-2 [&>*:last-child]:mb-0">
                  {orderedConversations.map((conversation) => {
                    const isActiveConversation = conversation.id === activeConversationId;
                    const conversationFileCount = Object.keys(conversation.files).length;
                    const conversationCommandCount = conversation.messages.filter((message) => message.type === 'user').length;
  
                    return (
                      <div
                        key={conversation.id}
                        className={`group relative w-full overflow-hidden rounded-[22px] border transition-all ${isActiveConversation ? 'border-[#cfe0ff] bg-[#f4f8ff] text-[#153d67] shadow-[0_14px_30px_-24px_rgba(42,100,246,0.16)] dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-slate-100 dark:shadow-[0_16px_34px_-26px_rgba(14,165,233,0.22)]' : 'border-[#edf3fe] bg-white text-[#244669] hover:border-[#d7e5fb] hover:bg-[#fbfdff] dark:border-slate-800/80 dark:bg-slate-900/88 dark:text-slate-200 dark:hover:border-slate-700 dark:hover:bg-slate-900'} ${isLoading ? 'opacity-60' : ''}`}
                        title={isConversationSidebarCollapsed ? conversation.title : undefined}
                      >
                        <button
                          type="button"
                          onClick={() => activateConversation(conversation.id)}
                          disabled={isLoading}
                          className="w-full rounded-[inherit] px-3 py-3.5 pr-12 text-left disabled:cursor-not-allowed"
                        >
                          <div className="flex items-start gap-3">
                            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] ${isActiveConversation ? 'bg-white shadow-sm dark:bg-slate-800' : 'bg-[#f3f8ff] text-[#4a78ad] dark:bg-slate-800 dark:text-slate-300'}`}>
                              <img 
                                src={DialogIllustrationImage} 
                                alt="" 
                                aria-hidden="true"
                                className={`object-contain drop-shadow-sm transition-all ${isActiveConversation ? 'h-6 w-6' : 'h-4 w-4 opacity-60 grayscale-[0.5]'}`} 
                              />
                            </div>
  
                            <div className="min-w-0 flex-1">
                              <div className="flex items-start justify-between gap-2">
                                <span className="truncate pr-2 text-sm font-semibold">{conversation.title}</span>
                                <span className="shrink-0 text-[10px] text-[#70859a] dark:text-slate-400">
                                  {formatConversationTimestamp(conversation.updatedAt)}
                                </span>
                              </div>
                              <p className="mt-1 line-clamp-2 text-xs leading-5 text-[#6c8094] dark:text-slate-400">
                                {getConversationPreviewText(conversation.messages)}
                              </p>
                              <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-[#6f859d] dark:text-slate-400">
                                <span className="rounded-full bg-[#f4f8ff] px-2 py-0.5 dark:bg-slate-800">
                                  {conversationFileCount} 个文件
                                </span>
                                <span className="rounded-full bg-[#f4f8ff] px-2 py-0.5 dark:bg-slate-800">
                                  {conversationCommandCount} 轮提问
                                </span>
                              </div>
                            </div>
                          </div>
                        </button>

                        <button
                          type="button"
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            deleteConversation(conversation.id);
                          }}
                          disabled={isLoading}
                          className={`absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full border transition-all disabled:cursor-not-allowed ${isActiveConversation ? 'border-[#c8dbff] bg-white/92 text-[#5577a2] hover:border-[#b8d0fb] hover:bg-white dark:border-sky-500/25 dark:bg-slate-900/88 dark:text-slate-300 dark:hover:border-sky-500/40 dark:hover:bg-slate-900' : 'border-[#dbe7fb] bg-white/92 text-[#7b8fa7] hover:border-[#c9dbfb] hover:bg-white hover:text-[#5d7695] dark:border-slate-700 dark:bg-slate-900/92 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:bg-slate-900 dark:hover:text-slate-200'} ${isLoading ? 'opacity-50' : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100'} ${isActiveConversation ? 'opacity-100' : ''}`}
                          title="删除对话"
                          aria-label={`删除对话 ${conversation.title}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </aside>
  
          <div
            className={`grid min-h-0 flex-1 overflow-hidden ${showPreviewPanel ? 'grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : 'grid-cols-1'}`}
            style={contentColumnsStyle}
          >
            <div
              className={`relative min-h-0 min-w-0 flex h-full flex-col overflow-hidden transition-all duration-500 ease-out ${
                isInitialLanding
                  ? 'bg-[linear-gradient(180deg,rgba(238,242,252,0.72),rgba(243,246,252,0.4),rgba(241,245,251,0.2))] shadow-none'
                  : 'bg-[linear-gradient(180deg,#ffffff,#fbfdff)] shadow-[0_18px_42px_-34px_rgba(42,100,246,0.12)]'
              } dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.96),rgba(2,6,23,0.94))] dark:shadow-[0_24px_46px_-28px_rgba(2,6,23,0.88)]`}
            >
              <div
                className={`pointer-events-none absolute inset-0 ${
                  isInitialLanding
                    ? 'bg-[radial-gradient(150%_120%_at_50%_10%,rgba(255,255,255,0.34),rgba(255,255,255,0)_48%),radial-gradient(88%_84%_at_80%_18%,rgba(231,249,254,0.18),rgba(231,249,254,0)_58%),linear-gradient(120deg,rgba(227,237,253,0.16),rgba(227,237,253,0)_26%,rgba(227,237,253,0)_74%,rgba(227,237,253,0.1))]'
                    : 'bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.9),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(96,165,250,0.06),_transparent_24%)]'
                } dark:bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.12),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(34,211,238,0.08),_transparent_24%)]`}
              />
  
              <div className="relative z-10 flex min-h-0 flex-1 flex-col">
                {isInitialLanding ? (
                  <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden !rounded-none !border-0 !shadow-none">
                    <div className="absolute left-4 top-4 z-20 flex items-center gap-3 sm:left-5 sm:top-5">
                      {isConversationSidebarCollapsed && (
                        <button
                          type="button"
                          onClick={() => setIsConversationSidebarCollapsed(false)}
                          className={`flex h-[42px] w-[42px] items-center justify-center rounded-[15px] ${LANDING_CORNER_BUTTON_CLASS}`}
                          title="展开历史对话栏"
                          aria-label="展开历史对话栏"
                        >
                          <img
                            src={SIDEBAR_TOGGLE_ICON_SRC}
                            alt=""
                            aria-hidden="true"
                            className="h-[17px] w-[17px] object-contain opacity-80 dark:brightness-0 dark:invert"
                          />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={createNewConversation}
                        disabled={isLoading}
                        className={`flex h-[42px] w-[42px] items-center justify-center rounded-[15px] text-[#3b5dc9] dark:text-sky-200 disabled:cursor-not-allowed disabled:opacity-40 ${LANDING_CORNER_BUTTON_CLASS}`}
                        title="新建对话"
                        aria-label="新建对话"
                      >
                        <Plus size={21} />
                      </button>
                    </div>

                    <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 pb-10 sm:px-8">
                      <div className="w-full max-w-[820px] -mt-16 flex flex-col items-center">
                        <div className="mx-auto flex w-full flex-col items-center text-center">
                          <div className="mb-0 mt-10 flex w-full justify-center">
                            <div className="flex justify-center w-full">
                              <img
                                src={SMART_DOC_WORDMARK_SRC}
                                alt="SmartDocOps"
                                className="w-[470px] max-w-[92vw] select-none object-contain opacity-95 drop-shadow-[0_14px_28px_rgba(92,114,180,0.15)] sm:w-[546px] ml-[80px] translate-y-3"
                              />
                            </div>
                          </div>

                          {/* 插入智能打字机副标题动效 */}
                          <TypewriterSubtitle />

                          <div
                            className={`relative w-full overflow-hidden rounded-[30px] border border-[#d9e4f8] bg-white/78 shadow-[0_0_0_1px_rgba(188,208,246,0.55),0_14px_34px_-30px_rgba(101,132,212,0.3)] backdrop-blur-[18px] dark:border-slate-700/80 dark:bg-slate-900/84 dark:shadow-[0_28px_72px_-40px_rgba(2,6,23,0.9),0_0_0_1px_rgba(30,41,59,0.9)] transition-all duration-300 ${isDocumentDragOver ? 'ring-2 ring-[rgba(143,181,239,0.24)] shadow-[0_0_0_1px_rgba(173,198,244,0.78),0_22px_52px_-34px_rgba(92,124,208,0.34)] dark:ring-sky-500/20 dark:shadow-[0_28px_72px_-36px_rgba(14,165,233,0.22),0_0_0_1px_rgba(56,189,248,0.28)]' : ''}`}
                            onDragEnter={handleDocumentDragEnter}
                            onDragOver={handleDocumentDragOver}
                            onDragLeave={handleDocumentDragLeave}
                            onDrop={handleDocumentDrop}
                          >
                            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.92),_transparent_34%),linear-gradient(180deg,rgba(250,252,255,0.82),rgba(255,255,255,0.16))] dark:bg-[radial-gradient(circle_at_top_left,_rgba(125,211,252,0.14),_transparent_30%),linear-gradient(180deg,rgba(15,23,42,0.46),rgba(2,6,23,0.1))]" />

                            {isDocumentDragOver && (
                              <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center rounded-[30px] border-2 border-dashed border-[rgba(156,192,255,0.42)] bg-[#f7fbff]/95 text-center dark:border-sky-500/30 dark:bg-slate-950/92">
                                <UploadCloud size={28} className="mb-2 text-[#295a9f] dark:text-sky-300" />
                                <p className="text-sm font-medium text-[#1f4672] dark:text-slate-100">松开即可上传到模块一工作台</p>
                              </div>
                            )}

                            <div className="relative z-10 px-5 pb-4 pt-4 sm:px-6 sm:pb-[16px] sm:pt-[16px]">
                              <textarea
                                ref={composerTextareaRef}
                                value={inputText}
                                onChange={(e) => setInputText(e.target.value)}
                                onKeyPress={handleKeyPress}
                                placeholder={initialLandingPlaceholder}
                                className="min-h-[84px] max-h-[144px] w-full resize-none bg-transparent px-1 py-1 text-[15px] leading-6 text-[#516a88] outline-none placeholder:text-[#a4b1c4] dark:text-slate-100 dark:placeholder:text-slate-500 sm:min-h-[90px]"
                                rows={3}
                                disabled={isLoading}
                              />

                              <div className="mt-2 flex items-center justify-between gap-3">
                                <button
                                  type="button"
                                  onClick={triggerFileInput}
                                  className="flex h-10 w-10 items-center justify-center rounded-full border border-[#d6e2f7] bg-white/94 text-[#6480bd] shadow-[0_10px_20px_-18px_rgba(86,104,145,0.4)] transition-all hover:-translate-y-0.5 hover:border-[#c7d7f3] hover:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:shadow-[0_16px_28px_-20px_rgba(2,6,23,0.8)] dark:hover:border-slate-600 dark:hover:bg-slate-800"
                                  title="上传附件"
                                  aria-label="上传附件"
                                >
                                  <Plus size={18} />
                                </button>

                                <div className="flex items-center gap-3">
                                  {isLoading ? (
                                    <button
                                      type="button"
                                      onClick={stopGeneration}
                                      className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-500 text-white shadow-lg shadow-rose-500/25 transition-colors hover:bg-rose-600"
                                      title="停止生成"
                                    >
                                      <X size={16} />
                                    </button>
                                  ) : (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        void sendMessage();
                                      }}
                                      disabled={!inputText.trim()}
                                      className="flex h-10 w-10 items-center justify-center rounded-full bg-[#9fb4f3] text-white shadow-[0_14px_24px_-18px_rgba(103,126,194,0.48)] transition-all hover:-translate-y-0.5 hover:bg-[#91a8ef] dark:bg-[#2a64f6] dark:shadow-[0_18px_30px_-18px_rgba(14,165,233,0.28)] dark:hover:bg-[#1d4ed8] disabled:cursor-not-allowed disabled:opacity-40"
                                      title="发送指令"
                                    >
                                      <Send size={15} />
                                    </button>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>

                          <div className="mt-7 flex w-full max-w-[150px] items-center gap-3 text-[#9babc1] dark:text-slate-500">
                            <span className="h-px flex-1 bg-[linear-gradient(90deg,rgba(187,201,228,0),rgba(187,201,228,0.92))] dark:bg-[linear-gradient(90deg,rgba(71,85,105,0),rgba(71,85,105,0.9))]" />
                            <span className="text-[11px] font-semibold tracking-[0.14em] text-[#9aaac0] dark:text-slate-400">猜你想问</span>
                            <span className="h-px flex-1 bg-[linear-gradient(90deg,rgba(187,201,228,0.92),rgba(187,201,228,0))] dark:bg-[linear-gradient(90deg,rgba(71,85,105,0.9),rgba(71,85,105,0))]" />
                          </div>

                          <div className="mt-5 flex w-full max-w-[772px] flex-nowrap justify-center gap-2 overflow-x-auto pb-1 sm:gap-3">
                            {INITIAL_LANDING_SUGGESTIONS.map((item) => {
                              const Icon = item.icon;

                              return (
                                <button
                                  key={item.label}
                                  type="button"
                                  onClick={() => { void sendMessage(item.prompt); }}
                                  disabled={isLoading}
                                  className={LANDING_SUGGESTION_BUTTON_CLASS}
                                >
                                  <Icon size={14} />
                                  {item.label}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="shrink-0 border-b border-[#e8effb] bg-[linear-gradient(180deg,#ffffff,#f9fbff)] dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(15,23,42,0.88))] px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0 flex items-center gap-2">
                          {isConversationSidebarCollapsed && (
                            <button
                              type="button"
                              onClick={() => setIsConversationSidebarCollapsed(false)}
                              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] ${COBALT_GLASS_BUTTON_CLASS}`}
                              title="展开历史对话栏"
                              aria-label="展开历史对话栏"
                            >
                              <img
                                src={SIDEBAR_TOGGLE_ICON_SRC}
                                alt=""
                                aria-hidden="true"
                                className="h-4 w-4 object-contain brightness-0 invert"
                              />
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={createNewConversation}
                            disabled={isLoading}
                            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] disabled:cursor-not-allowed disabled:opacity-40 ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                            title="新建对话"
                            aria-label="新建对话"
                          >
                            <Plus size={16} />
                          </button>
                          <div className="min-w-0 ml-1">
                            <div className="flex flex-wrap items-center gap-2">
                              {activeConversation && editingConversationId === activeConversation.id ? (
                                <input
                                  autoFocus
                                  value={conversationTitleDraft}
                                  onChange={(event) => setConversationTitleDraft(event.target.value)}
                                  onBlur={() => commitConversationRename(activeConversation.id)}
                                  onKeyDown={(event) => {
                                    if (event.key === 'Enter') {
                                      event.preventDefault();
                                      commitConversationRename(activeConversation.id);
                                    }
                                    if (event.key === 'Escape') {
                                      event.preventDefault();
                                      cancelConversationRename();
                                    }
                                  }}
                                  className="min-w-[160px] max-w-[280px] rounded-[14px] border border-[#d8e5fb] bg-white px-3 py-1.5 text-[16px] font-bold text-[#1f3f5f] outline-none ring-2 ring-[#e8f0ff] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:ring-slate-700"
                                />
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => activeConversation && startConversationRename(activeConversation)}
                                  className="truncate rounded-[12px] px-1 py-0.5 text-left text-[16px] font-bold text-[#233f5b] transition-colors hover:bg-[#f5f9ff] hover:text-[#102f5a] dark:text-slate-100 dark:hover:bg-slate-800 dark:hover:text-sky-200"
                                  title="点击修改对话名称"
                                >
                                  {activeConversationTitle}
                                </button>
                              )}
                              <span className="text-[10px] text-[#7d8e9f] dark:text-slate-400">{activeConversationTimestamp}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex min-h-0 flex-1 flex-col px-4 pb-0 pt-3">
                      <div
                        ref={messagesViewportRef}
                        onScroll={handleMessagesScroll}
                        className="min-h-0 flex-1 overflow-y-auto pr-1 pb-4 scroll-smooth [overscroll-behavior:contain]"
                      >
                        <div className="space-y-5 pt-3">
                          {messages.map((message) => (
                            <div
                              key={message.id}
                              className={`flex ${message.type === 'user' ? 'justify-end pt-1.5' : 'justify-start'} animate-fadeIn`}
                            >
                              {(() => {
                                const isStreamingMessage = streamingAssistantMessageId === message.id;
                                const isReportMessage = message.type === 'assistant' && message.displayMode === 'report' && Boolean(message.fileIds?.length);
                                const reportFiles = (message.fileIds ?? [])
                                  .map((fileId) => files[fileId])
                                  .filter((file): file is FileInfo => Boolean(file));

                                return (
                              <div
                                className={`max-w-[88%] ${
                                  message.type === 'user'
                                    ? 'rounded-[22px] rounded-tr-md border border-[rgba(42,100,246,0.18)] bg-[rgb(42,100,246)] px-5 py-4 text-white shadow-[0_14px_30px_-24px_rgba(42,100,246,0.34)]'
                                    : 'rounded-[24px] rounded-tl-md border border-[#e7effc] bg-white px-5 py-4 text-slate-700 shadow-[0_12px_28px_-24px_rgba(42,100,246,0.12)] dark:border-slate-800/80 dark:bg-slate-900 dark:text-slate-100 dark:shadow-[0_16px_32px_-24px_rgba(2,6,23,0.82)]'
                                }`}
                              >
                                {isReportMessage ? (
                                  <div className="flex flex-col gap-3">
                                    <div className="space-y-2">
                                      {reportFiles.map((file) => {
                                        const reportItemToneClass = isStreamingMessage
                                          ? 'border-[#dbe7fb] bg-[linear-gradient(180deg,#fbfdff,#f6faff)] shadow-[0_14px_28px_-24px_rgba(42,100,246,0.16)] dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(15,23,42,0.6))] dark:shadow-[0_14px_28px_-24px_rgba(2,6,23,0.72)]'
                                          : 'border-[#e4edf9] bg-white/88 shadow-[0_12px_24px_-24px_rgba(42,100,246,0.1)] dark:border-slate-800/80 dark:bg-slate-900/78 dark:shadow-[0_14px_26px_-24px_rgba(2,6,23,0.66)]';
                                        const reportBadgeClass = isStreamingMessage
                                          ? 'border-[#d8e5fd] bg-[#f8fbff] text-[#255cae] dark:border-slate-700 dark:bg-slate-900/92 dark:text-sky-200'
                                          : 'border-[#dfe8f7] bg-white text-[#537292] dark:border-slate-700 dark:bg-slate-900/92 dark:text-slate-300';

                                        return (
                                          <button
                                            key={`${message.id}-${file.id}`}
                                            type="button"
                                            onClick={() => {
                                              handleSelectFile(file.id);
                                              setActiveReportMessageIdByFileId((prev) => ({
                                                ...prev,
                                                [file.id]: message.id,
                                              }));
                                              setPreviewPaneMode('report');
                                              setShowPreviewPanel(true);
                                              resetPreviewViewport();
                                            }}
                                            className={`flex w-full items-center gap-3 rounded-[18px] border px-3 py-3 text-left transition-all hover:-translate-y-0.5 hover:border-[#d4e3fb] hover:bg-[#f9fbff] dark:hover:border-slate-700 dark:hover:bg-slate-900/82 ${reportItemToneClass}`}
                                          >
                                            <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-[16px] border ${isStreamingMessage ? 'border-[#d8e6fd] bg-[#f5f9ff] dark:border-slate-700 dark:bg-slate-900/82' : 'border-[#e4ecf8] bg-[#fbfdff] dark:border-slate-700 dark:bg-slate-900/72'}`}>
                                              <div className="relative">
                                                <FileFormatIcon
                                                  file={file}
                                                  iconClassName="h-10 w-10"
                                                  fallbackSize={22}
                                                  fallbackClassName="text-[#245eb6] dark:text-sky-300"
                                                />
                                                {isStreamingMessage ? (
                                                  <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
                                                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#2a64f6]/35 dark:bg-sky-400/30" />
                                                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#2a64f6] dark:bg-sky-300" />
                                                  </span>
                                                ) : null}
                                              </div>
                                            </div>
                                            <div className="min-w-0 flex-1">
                                              <p className="truncate text-sm font-semibold text-[#234566] dark:text-slate-100">{file.name}</p>
                                              <p className="mt-1 text-[12px] text-[#73879d] dark:text-slate-400">
                                                {isStreamingMessage ? '报告生成中' : '点击查看分析报告'}
                                              </p>
                                            </div>
                                            <span className={`inline-flex h-8 shrink-0 items-center rounded-full border px-2.5 text-[11px] font-medium ${reportBadgeClass}`}>
                                              {isStreamingMessage ? '生成中' : '可查看'}
                                            </span>
                                          </button>
                                        );
                                      })}
                                    </div>
                                  </div>
                                ) : (
                                  <div className="whitespace-pre-wrap text-[15px] leading-7">
                                    {isStreamingMessage && (
                                      <div className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-[#d7e5fd] bg-[#f7faff] px-2.5 py-1 text-[11px] font-medium text-[#245eb6] dark:border-slate-700 dark:bg-slate-800 dark:text-sky-200">
                                        <span className="h-1.5 w-1.5 rounded-full bg-[#2a64f6] animate-pulse" />
                                        正在实时输出
                                      </div>
                                    )}
                                    {message.content.split('【图片描述】').map((part, index) => {
                                      if (index % 2 === 1) {
                                        return (
                                          <div
                                            key={index}
                                            className="mt-3 rounded-2xl border border-[#e1ecff] bg-[#f6faff] p-3 dark:border-slate-800 dark:bg-slate-950/70"
                                          >
                                            <div className="mb-1.5 flex items-center gap-2 text-[#245eb6] dark:text-sky-300">
                                              <Image size={15} />
                                              <span className="text-xs font-semibold tracking-wide">图片分析</span>
                                            </div>
                                            <p className="text-sm leading-6 text-slate-700 dark:text-slate-200">{part}</p>
                                          </div>
                                        );
                                      }

                                      return <span key={index}>{part}</span>;
                                    })}
                                    {isStreamingMessage && (
                                      <span className="ml-1 inline-block h-4 w-2 rounded-sm bg-[#2a64f6] align-[-2px] animate-pulse" />
                                    )}
                                  </div>
                                )}

                                {message.fileIds && message.fileIds.length > 0 && !isReportMessage && (
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {message.fileIds.map((fileId) => {
                                      const file = files[fileId];
                                      return file ? (
                                        <button
                                          key={fileId}
                                          type="button"
                                          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs transition-colors ${
                                            message.type === 'user'
                                              ? 'bg-white/15 text-white hover:bg-white/20'
                                              : 'bg-[#f1f6ff] text-[#35516d] hover:bg-[#e7f0ff] dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700'
                                          }`}
                                          onClick={() => handleSelectFile(fileId)}
                                        >
                                          <FileFormatIcon
                                            file={file}
                                            iconClassName="h-3.5 w-3.5"
                                            fallbackSize={12}
                                          />
                                          {file.name}
                                        </button>
                                      ) : null;
                                    })}
                                  </div>
                                )}

                                {message.type === 'assistant'
                                  && latestAssistantMessageWithSuggestions?.id === message.id
                                  && visibleFollowUpSuggestions.length > 0
                                  && !(isLoading && messages[messages.length - 1]?.id === message.id) && (
                                    <div className="mt-4 rounded-[20px] border border-[#e7effc] bg-[#fbfdff] p-3 shadow-[0_12px_28px_-24px_rgba(42,100,246,0.12)] dark:border-slate-800 dark:bg-slate-950/72 dark:shadow-[0_16px_32px_-24px_rgba(2,6,23,0.84)]">
                                      <div className="mb-2.5 flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[#5d7390] dark:text-slate-400">
                                          <Sparkles size={13} className="text-[#1d4ed8] dark:text-sky-300" />
                                          猜你想问
                                        </div>
                                        {hasMultipleFollowUpSuggestionBatches && (
                                          <button
                                            type="button"
                                            onClick={cycleFollowUpSuggestions}
                                            className="inline-flex items-center gap-1.5 rounded-full border border-[#dbe8fd] bg-white px-2.5 py-1 text-[11px] font-medium text-[#35516d] transition-colors hover:border-[#c8dcff] hover:bg-[#f7faff] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:bg-slate-800"
                                          >
                                            <RotateCw size={12} />
                                            换一批
                                          </button>
                                        )}
                                      </div>
                                      <div className="flex flex-wrap gap-2">
                                        {visibleFollowUpSuggestions.map((item) => {
                                          const Icon = item.icon;

                                          return (
                                            <button
                                              key={`${message.id}-${item.label}`}
                                              type="button"
                                              onClick={() => { void sendMessage(item.prompt); }}
                                              disabled={isLoading}
                                              className="inline-flex items-center gap-1.5 rounded-full border border-[#dbe8fd] bg-white px-3 py-1.5 text-xs font-medium text-[#35516d] transition-all hover:-translate-y-0.5 hover:border-[#c8dcff] hover:bg-[#f7faff] hover:text-[#234a79] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:bg-slate-800 dark:hover:text-sky-200 disabled:cursor-not-allowed disabled:opacity-50"
                                            >
                                              <Icon size={13} />
                                              {item.label}
                                            </button>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  )}
                              </div>
                                );
                              })()}
                            </div>
                          ))}

                          {isLoading && (
                            <div className="flex justify-start animate-fadeIn">
                              <div className="flex items-center gap-3 rounded-[22px] border border-[#e7effc] bg-white px-4 py-3 shadow-[0_12px_28px_-24px_rgba(42,100,246,0.12)] dark:border-slate-800 dark:bg-slate-900 dark:shadow-[0_16px_32px_-24px_rgba(2,6,23,0.82)]">
                                <div className="flex gap-1.5">
                                  <div className="h-2.5 w-2.5 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.3s]" />
                                  <div className="h-2.5 w-2.5 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.15s]" />
                                  <div className="h-2.5 w-2.5 rounded-full bg-blue-500 animate-bounce" />
                                </div>
                                <span className="text-sm text-slate-500 dark:text-slate-300">正在处理文档指令…</span>
                              </div>
                            </div>
                          )}
                        </div>

                        <div ref={messagesEndRef} />
                      </div>
                    </div>

                    <div
                      className={`relative z-10 mx-auto mt-auto mb-2 w-full px-4 shrink-0 bg-transparent pb-[max(env(safe-area-inset-bottom),12px)] transition-[max-width,transform] duration-300 sm:mb-3 sm:px-5 ${shouldCollapseComposer ? 'max-w-[420px] translate-y-4' : 'max-w-[600px] translate-y-0'}`}
                    >
                      <div
                        className={`relative w-full overflow-hidden rounded-[26px] border border-[#c8dafb] bg-white shadow-[0_18px_42px_-32px_rgba(42,100,246,0.16),0_0_0_1px_rgba(214,227,250,0.96)] dark:border-slate-700/80 dark:bg-slate-900/92 dark:shadow-[0_22px_46px_-30px_rgba(2,6,23,0.9),0_0_0_1px_rgba(30,41,59,0.9)] transition-all duration-300 ${shouldCollapseComposer ? 'rounded-[20px] shadow-[0_24px_48px_-34px_rgba(42,100,246,0.22),0_0_0_1px_rgba(198,218,251,0.98)] dark:shadow-[0_28px_52px_-30px_rgba(2,6,23,0.94),0_0_0_1px_rgba(51,65,85,0.9)]' : ''} ${isDocumentDragOver ? 'shadow-[0_20px_42px_-24px_rgba(42,100,246,0.18),0_0_0_1px_rgba(143,181,239,0.9)] ring-2 ring-[rgba(143,181,239,0.28)] dark:ring-sky-500/20 dark:shadow-[0_22px_46px_-26px_rgba(14,165,233,0.22),0_0_0_1px_rgba(56,189,248,0.24)]' : ''}`}
                        onMouseEnter={() => setIsComposerHovered(true)}
                        onMouseLeave={() => setIsComposerHovered(false)}
                        onFocusCapture={() => setIsComposerFocused(true)}
                        onBlurCapture={(event) => {
                          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                            setIsComposerFocused(false);
                          }
                        }}
                        onDragEnter={handleDocumentDragEnter}
                        onDragOver={handleDocumentDragOver}
                        onDragLeave={handleDocumentDragLeave}
                        onDrop={handleDocumentDrop}
                      >
                        <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-[linear-gradient(180deg,rgba(247,250,255,0.78),rgba(255,255,255,0))] dark:bg-[linear-gradient(180deg,rgba(30,41,59,0.42),rgba(15,23,42,0))]" />

                        {isDocumentDragOver && (
                          <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center rounded-[26px] border-2 border-dashed border-[rgba(156,192,255,0.4)] bg-[#f7fbff] text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.92)] dark:border-sky-500/30 dark:bg-slate-950/94 dark:shadow-none">
                            <UploadCloud size={26} className="mb-2 text-[#295a9f] dark:text-sky-300" />
                            <p className="text-sm font-medium text-[#1f4672] dark:text-slate-100">松开即可把文件放进输入区</p>
                          </div>
                        )}

                        {shouldCollapseComposer ? (
                          <button
                            type="button"
                            onClick={() => expandComposer(true)}
                            className="relative z-10 flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition-all hover:bg-[#fbfdff] dark:hover:bg-slate-900/96"
                            aria-label="展开输入区"
                          >
                            <div className="min-w-0">
                              <p className="text-sm font-semibold text-[#24486f] dark:text-slate-100">输入框已收起</p>
                              <p className="mt-0.5 text-xs text-[#7d8fa4] dark:text-slate-400">你在浏览聊天记录，鼠标移到这里会自动展开</p>
                            </div>
                            <div className="inline-flex h-10 items-center rounded-[16px] border border-[#d6e4fb] bg-[#f7faff] px-3 text-xs font-medium text-[#315987] shadow-[inset_0_1px_0_rgba(255,255,255,0.92)] dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:shadow-none">
                              悬浮展开
                            </div>
                          </button>
                        ) : (
                          <div className="relative z-10 px-3 pb-2.5 pt-2 sm:px-3 sm:pb-3 sm:pt-2.5">
                            {composerFiles.length > 0 && (
                              <div className="custom-scrollbar mb-2.5 overflow-x-auto overflow-y-hidden pb-1.5">
                                <div className="flex min-w-max flex-nowrap gap-2.5 pr-1">
                                  {composerFiles.map((file) => (
                                    <div
                                      key={file.id}
                                      className={`flex min-w-[260px] max-w-[260px] shrink-0 items-center gap-2 rounded-[18px] border px-3 py-2 transition-all ${
                                        selectedFileId === file.id
                                          ? 'border-[rgba(42,100,246,0.18)] bg-[#edf4ff] text-[#1f4e92] shadow-[0_10px_24px_-20px_rgba(42,100,246,0.18)] dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100 dark:shadow-[0_14px_28px_-22px_rgba(14,165,233,0.18)]'
                                          : 'border-[#dfeafb] bg-[#fcfdff] text-[#35516d] hover:border-[#cfe0fb] hover:bg-white dark:border-slate-800 dark:bg-slate-950/68 dark:text-slate-200 dark:hover:border-slate-700 dark:hover:bg-slate-900'
                                      }`}
                                    >
                                      <button
                                        type="button"
                                        onClick={() => handleSelectFile(file.id)}
                                        className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                                      >
                                        <div className="min-w-0">
                                          <div className="flex min-w-0 items-center gap-2">
                                            <FileFormatIcon
                                              file={file}
                                              iconClassName="h-7 w-7"
                                              fallbackSize={20}
                                              fallbackClassName={selectedFileId === file.id ? 'text-[#1f4e92] dark:text-sky-200' : 'text-[#365f91] dark:text-slate-300'}
                                            />
                                            <span className="min-w-0 flex-1 truncate text-base font-medium">{file.name}</span>
                                            {file.sourceFileId && (
                                              <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${selectedFileId === file.id ? 'bg-white text-[#1f4e92] dark:bg-slate-900 dark:text-sky-200' : 'bg-[#f5f8fd] text-[#4f6782] dark:bg-slate-800 dark:text-slate-300'}`}>
                                                修改版
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      </button>

                                      <div className="flex shrink-0 items-center gap-1">
                                        <span className="flex items-center">{getStatusIcon(file)}</span>
                                        <button
                                          type="button"
                                          onClick={() => removeComposerFile(file.id)}
                                          className="inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-[#f3f8ff] dark:hover:bg-slate-800"
                                          title={`移出本次发送 ${file.name}`}
                                        >
                                          <X size={12} />
                                        </button>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            <textarea
                              ref={composerTextareaRef}
                              value={inputText}
                              onChange={(e) => setInputText(e.target.value)}
                              onKeyPress={handleKeyPress}
                              placeholder={composerPlaceholder}
                              className={`w-full resize-none bg-transparent px-1.5 py-0.5 text-[15px] leading-6 text-[#35516d] outline-none placeholder:text-[#8fa3bc] dark:text-slate-100 dark:placeholder:text-slate-500 ${composerFiles.length > 0 ? 'min-h-[50px]' : 'min-h-[38px]'} max-h-[160px]`}
                              rows={1}
                              disabled={isLoading}
                            />

                            <div className="mt-2.5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                              <div className="flex flex-wrap items-center gap-2 text-xs text-[#6c829d] dark:text-slate-400">
                                <button
                                  type="button"
                                  onClick={triggerFileInput}
                                  className={`inline-flex items-center gap-2 rounded-[15px] px-3 py-1.5 text-xs font-medium ${COBALT_GLASS_BUTTON_CLASS}`}
                                >
                                  <Paperclip size={15} />
                                  上传附件
                                </button>
                                <div className="mx-1 h-4 w-px bg-[#dce7fa] dark:bg-slate-700/80" />
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (showPreviewPanel) {
                                      void closePreviewPanel();
                                      return;
                                    }
                                    openPreviewPanel();
                                  }}
                                  className={`flex h-8 w-8 items-center justify-center rounded-[12px] transition-all ${showPreviewPanel ? METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS : METALLIC_SECONDARY_BUTTON_CLASS}`}
                                  title={showPreviewPanel ? '收起预览' : '打开预览'}
                                  aria-label={showPreviewPanel ? '收起预览' : '打开预览'}
                                >
                                  <Eye size={14} />
                                </button>
                                <button
                                  type="button"
                                  onClick={exportResults}
                                  disabled={fileList.length === 0}
                                  className={`flex h-8 w-8 items-center justify-center rounded-[12px] transition-all disabled:cursor-not-allowed disabled:opacity-40 ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                                  title="导出当前会话结果"
                                  aria-label="导出当前会话结果"
                                >
                                  <FileUp size={14} />
                                </button>
                              </div>

                              <div className="flex items-center gap-2 self-end">
                                <span className="text-[10px] text-[#8497ad] dark:text-slate-500">回车发送，Shift + 回车换行</span>
                                {isLoading ? (
                                  <button
                                    type="button"
                                    onClick={stopGeneration}
                                    className="flex h-10 w-10 items-center justify-center rounded-[18px] bg-rose-500 text-white shadow-lg shadow-rose-500/25 transition-colors hover:bg-rose-600"
                                    title="停止生成"
                                  >
                                    <X size={15} />
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      void sendMessage();
                                    }}
                                    disabled={!inputText.trim()}
                                    className={`flex h-10 w-10 items-center justify-center rounded-[18px] disabled:cursor-not-allowed disabled:opacity-40 ${COBALT_GLASS_BUTTON_CLASS}`}
                                    title="发送指令"
                                  >
                                    <Send size={15} />
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* 右侧预览区 */}
            {showPreviewPanel && (
              <div
                ref={previewPanelRef}
                className={`relative h-full min-h-0 min-w-0 flex-1 overflow-hidden bg-[linear-gradient(180deg,#ffffff,#fbfdff)] dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,0.94))] animate-slideIn ${
                  isPreviewFullscreen
                    ? 'h-screen w-screen rounded-none border-0'
                    : 'rounded-none border border-[rgba(191,216,255,0.4)] shadow-[0_22px_46px_-30px_rgba(42,100,246,0.16)] dark:border-slate-800/80 dark:shadow-[0_28px_52px_-32px_rgba(2,6,23,0.88)]'
                }`}
              >
                <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(96,165,250,0.05),_transparent_28%)] dark:bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.1),_transparent_24%)]" />

                <div className="relative z-10 flex h-full flex-col">
                  <div className="shrink-0 border-b border-[#e8effb] bg-[linear-gradient(180deg,#ffffff,#f9fbff)] dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(15,23,42,0.88))] px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[10px] font-semibold tracking-[0.22em] text-[#6f859b] dark:text-slate-400">
                          智能预览
                        </p>
                        {selectedFile && (
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            <h2 className="text-lg font-semibold tracking-tight text-[#173750] dark:text-slate-100">
                              {effectivePreviewPaneMode === 'report'
                                ? '分析/提取报告'
                                : effectivePreviewPaneMode === 'compare'
                                  ? '修改前后对比'
                                  : effectivePreviewPaneMode === 'original'
                                    ? '原文件预览'
                                    : selectedFile.sourceFileId
                                      ? '修改后文件预览'
                                      : '文档预览'}
                            </h2>
                            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${METALLIC_PREVIEW_TAG_CLASS}`}>
                              {effectivePreviewPaneMode === 'report' ? selectedFile.name : previewedFile?.name}
                            </span>
                            <span className="text-xs text-[#6e8298] dark:text-slate-400">
                              {formatFileSize((effectivePreviewPaneMode === 'report' ? selectedFile : previewedFile)?.size ?? selectedFile.size)}
                            </span>
                          </div>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => { void closePreviewPanel(); }}
                        className={`shrink-0 rounded-2xl p-2 transition-all ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                        title="关闭预览"
                        aria-label="关闭预览"
                      >
                        <X size={16} />
                      </button>
                    </div>
  
                    <div className="mt-3 space-y-2">
                      {effectivePreviewPaneMode === 'report' && selectedFile && selectedFileReportMessages.length > 1 && (
                        <div className="custom-scrollbar -mx-0.5 overflow-x-auto px-0.5 pb-0.5">
                          <div className="flex min-w-max items-center gap-2">
                            {selectedFileReportMessages.map((reportMessage, index) => {
                              const isActiveReportVersion = activeReportMessageForSelectedFile?.id === reportMessage.id;
                              return (
                                <button
                                  key={reportMessage.id}
                                  type="button"
                                  onClick={() => {
                                    setActiveReportMessageIdByFileId((prev) => ({
                                      ...prev,
                                      [selectedFile.id]: reportMessage.id,
                                    }));
                                    clearReportEditingState();
                                    resetPreviewViewport();
                                  }}
                                  className={`shrink-0 rounded-xl border px-3 py-1.5 text-xs font-medium transition-all ${
                                    isActiveReportVersion
                                      ? 'border-[#c8dcff] bg-[#edf4ff] text-[#1f4e92] shadow-[0_10px_20px_-18px_rgba(42,100,246,0.25)] dark:border-sky-500/30 dark:bg-sky-500/14 dark:text-sky-100'
                                      : 'border-[#e2ebf8] bg-white text-[#5f7897] hover:border-[#d1dff6] hover:bg-[#f8fbff] dark:border-slate-700 dark:bg-slate-900/86 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-900'
                                  }`}
                                  title={`报告 ${index + 1} · ${formatConversationTimestamp(reportMessage.timestamp)}`}
                                >
                                  报告 {index + 1}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      <div className="flex w-full items-center justify-between gap-2 overflow-x-auto custom-scrollbar rounded-[18px] border border-[#e1ebfb] bg-[#f8fbff] p-1.5 shadow-[0_8px_16px_-16px_rgba(42,100,246,0.18)] dark:border-slate-800/80 dark:bg-slate-900/72 dark:shadow-none">
                        <div className="flex min-w-max flex-1 items-center gap-1.5">
                          <div className="flex shrink-0 items-center gap-1">
                            {selectedFile && selectedFileHasReport && (
                              <button
                                type="button"
                                onClick={() => switchPreviewPane('report')}
                                className={`shrink-0 rounded-[12px] px-2.5 py-1 text-[12px] font-medium transition-all ${
                                  effectivePreviewPaneMode === 'report'
                                    ? METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS
                                    : 'text-[#5f7897] hover:bg-[#edf3ff] hover:text-[#234a79] dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                                }`}
                              >
                                报告
                              </button>
                            )}
                            {selectedFile?.sourceFileId && !isPreviewingOriginalFile && (
                              <button
                                type="button"
                                onClick={() => switchPreviewPane('current')}
                                className={`shrink-0 rounded-[12px] px-2.5 py-1 text-[12px] font-medium transition-all ${
                                  effectivePreviewPaneMode === 'current'
                                    ? METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS
                                    : 'text-[#5f7897] hover:bg-[#edf3ff] hover:text-[#234a79] dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                                }`}
                              >
                                {currentFileButtonLabel}
                              </button>
                            )}
                            {selectedFile && canPreviewOriginal && (
                              <button
                                type="button"
                                onClick={() => switchPreviewPane('original')}
                                className={`shrink-0 rounded-[12px] px-2.5 py-1 text-[12px] font-medium transition-all ${
                                  effectivePreviewPaneMode === 'original'
                                    ? METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS
                                    : 'text-[#5f7897] hover:bg-[#edf3ff] hover:text-[#234a79] dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                                }`}
                              >
                                原文件
                              </button>
                            )}
                            {selectedFile && canComparePreview && (
                              <button
                                type="button"
                                onClick={() => switchPreviewPane('compare')}
                                className={`shrink-0 rounded-[12px] px-2.5 py-1 text-[12px] font-medium transition-all ${
                                  effectivePreviewPaneMode === 'compare'
                                    ? METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS
                                    : 'text-[#5f7897] hover:bg-[#edf3ff] hover:text-[#234a79] dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                                }`}
                              >
                                前后对比
                              </button>
                            )}
                          </div>

                          {(selectedFile || canTransformPreview) && (
                            <div className="mx-0.5 h-3.5 w-px shrink-0 bg-[#d6e4fb] dark:bg-slate-700/80" />
                          )}

                          {selectedFile && isPreviewPdf && (
                            <div className="flex shrink-0 items-center gap-1">
                              <button
                                type="button"
                                onClick={() => navigateToPdfPage(pdfPage - 1)}
                                disabled={pdfPage <= 1}
                                className={`shrink-0 rounded-[12px] p-1.5 transition-colors ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                                title="上一页"
                                aria-label="上一页"
                              >
                                <ChevronLeft size={13} />
                              </button>
                              <div className="flex items-center gap-1.5 rounded-[12px] border border-[#deebff] bg-white/88 px-2 py-1 shadow-[0_6px_14px_-16px_rgba(42,100,246,0.18)] dark:border-slate-700 dark:bg-slate-900/88 dark:shadow-none">
                                <span className="text-[11px] font-medium text-[#6c8197] dark:text-slate-400">
                                  第
                                </span>
                                <input
                                  type="number"
                                  min={1}
                                  max={maxPdfPage ?? undefined}
                                  value={pdfPageInput}
                                  onChange={(event) => setPdfPageInput(event.target.value)}
                                  onBlur={commitPdfPageInput}
                                  onKeyDown={(event) => {
                                    if (event.key === 'Enter') {
                                      event.preventDefault();
                                      commitPdfPageInput();
                                    }
                                  }}
                                  className="w-9 rounded-[6px] border border-[#d6e4fb] bg-white px-1 py-0.5 text-center text-[11px] font-semibold text-[#36516f] outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                                />
                                <span className="text-[11px] font-medium text-[#6c8197] dark:text-slate-400">
                                  页{maxPdfPage ? ` / ${maxPdfPage}` : ''}
                                </span>
                              </div>
                              <button
                                type="button"
                                onClick={() => navigateToPdfPage(pdfPage + 1)}
                                disabled={Boolean(maxPdfPage && pdfPage >= maxPdfPage)}
                                className={`shrink-0 rounded-[12px] p-1.5 transition-colors ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                                title="下一页"
                                aria-label="下一页"
                              >
                                <ChevronRight size={13} />
                              </button>
                              <div className="mx-0.5 h-3.5 w-px shrink-0 bg-[#d6e4fb] dark:bg-slate-700/80" />
                            </div>
                          )}

                          <div className="flex shrink-0 items-center gap-1">
                            <button
                              type="button"
                              onClick={handleZoomOut}
                              disabled={!canTransformPreview}
                              className={`shrink-0 rounded-[12px] p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                              title="缩小"
                              aria-label="缩小"
                            >
                              <ZoomOut size={13} />
                            </button>
                            <span className="min-w-[2.5rem] shrink-0 text-center text-[11px] font-semibold text-[#6c8197] dark:text-slate-400">
                              {Math.round(scale * 100)}%
                            </span>
                            <button
                              type="button"
                              onClick={handleZoomIn}
                              disabled={!canTransformPreview}
                              className={`shrink-0 rounded-[12px] p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                              title="放大"
                              aria-label="放大"
                            >
                              <ZoomIn size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={handleRotate}
                              disabled={!canTransformPreview}
                              className={`shrink-0 rounded-[12px] p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                              title="旋转"
                              aria-label="旋转"
                            >
                              <RotateCw size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={handleResetView}
                              disabled={!canTransformPreview && !isPreviewPdf}
                              className={`shrink-0 rounded-[12px] px-2 py-1.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                              title="重置视图"
                            >
                              重置
                            </button>
                          </div>
                        </div>

                        <div className="flex shrink-0 items-center gap-1.5 pl-1">
                          <button
                            type="button"
                            onClick={() => { void togglePreviewFullscreen(); }}
                            className={`shrink-0 rounded-[12px] p-1.5 transition-colors ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                            title={isPreviewFullscreen ? '退出全屏预览' : '全屏预览'}
                            aria-label={isPreviewFullscreen ? '退出全屏预览' : '全屏预览'}
                          >
                            {isPreviewFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                          </button>

                          {!selectedFile ? (
                            <button
                              type="button"
                              onClick={triggerFileInput}
                              className={`inline-flex h-8 items-center gap-1.5 rounded-[12px] px-3 text-[12px] font-medium ${COBALT_GLASS_BUTTON_CLASS}`}
                            >
                              <UploadCloud size={13} />
                              上传
                            </button>
                          ) : effectivePreviewPaneMode === 'report' ? (
                            <button
                              type="button"
                              onClick={() => { void downloadEditedReport(selectedFile); }}
                              disabled={!getEditableReportTextForFile(selectedFile.id)?.trim() || reportDownloadBusy}
                              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] transition-all disabled:cursor-not-allowed disabled:opacity-40 ${METALLIC_PRIMARY_BUTTON_CLASS}`}
                              title={reportDownloadBusy ? '正在导出编辑稿' : '下载报告'}
                              aria-label={reportDownloadBusy ? '正在导出编辑稿' : '下载报告'}
                            >
                              {reportDownloadBusy ? <Loader size={13} className="animate-spin" /> : <Download size={13} />}
                            </button>
                          ) : previewedFile ? (
                            <button
                              type="button"
                              onClick={() => downloadFile(previewedFile)}
                              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] transition-all ${METALLIC_PRIMARY_BUTTON_CLASS}`}
                              title={`下载 ${previewedFile.name}`}
                              aria-label={`下载 ${previewedFile.name}`}
                            >
                              <Download size={13} />
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </div>
  
                  <div className="relative z-10 flex-1 min-h-0 overflow-hidden">
                    {!selectedFile ? (
                      <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-[22px] border border-[#dce9fc] bg-[#f4f8ff] text-[#1d5a93] shadow-[0_12px_24px_-18px_rgba(42,100,246,0.16)] dark:border-slate-700 dark:bg-slate-900 dark:text-sky-300 dark:shadow-[0_16px_28px_-20px_rgba(2,6,23,0.8)]">
                          <UploadCloud size={28} />
                        </div>
                        <h3 className="text-xl font-semibold text-[#173750] dark:text-slate-100">
                          {fileList.length === 0 ? '先上传文档，预览区已经准备好了' : '从左侧队列选择一份文档开始预览'}
                        </h3>
                        <p className="mt-3 max-w-lg text-sm leading-7 text-[#6b8198] dark:text-slate-400">
                          {fileList.length === 0
                            ? '你现在可以先打开预览，再决定上传哪份文件。上传成功后，这里会自动切换到对应文档的可视化预览。'
                            : '当前已有文档进入工作台，只要选中一个焦点文件，就能在这里查看预览、分析报告和修改前后对比。'}
                        </p>
                        <div className="mt-6 flex flex-wrap justify-center gap-2">
                          <button
                            type="button"
                            onClick={triggerFileInput}
                            className={`inline-flex items-center gap-2 rounded-[18px] px-4 py-2.5 text-sm font-medium ${COBALT_GLASS_BUTTON_CLASS}`}
                          >
                            <UploadCloud size={16} />
                            {fileList.length === 0 ? '上传第一份文档' : '继续添加文档'}
                          </button>
                          {fileList.length > 0 && (
                            <button
                              type="button"
                              onClick={() => handleSelectFile(fileList[0].id)}
                              className={`inline-flex items-center gap-2 rounded-[18px] px-4 py-2.5 text-sm font-medium transition-all ${METALLIC_SECONDARY_BUTTON_CLASS}`}
                            >
                              <Layers size={16} />
                              选中第一份文档
                            </button>
                          )}
                        </div>
                      </div>
                    ) : effectivePreviewPaneMode === 'compare' ? (
                      canComparePreview && comparisonFile ? (
                        isPreviewPdf && previewPdfSource && comparisonPdfSource ? (
                          <div className="grid h-full min-h-0 grid-cols-2 gap-4">
                            <div className={`min-h-0 overflow-auto rounded-[26px] p-4 shadow-inner shadow-slate-400/10 dark:border-slate-800/70 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.86),rgba(51,65,85,0.36))] ${METALLIC_PANEL_CLASS}`}>
                              <div className="mb-3 flex items-center justify-between gap-3">
                                <span className={`shrink-0 whitespace-nowrap rounded-[10px] px-2.5 py-1 text-[11px] font-medium ${METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS}`}>修改后</span>
                                <span className="truncate text-right text-[11px] text-[#6c8197] dark:text-slate-400">{selectedFile.name}</span>
                              </div>
                              <PdfScrollPreview
                                key={`${selectedFile.id}-compare-modified-scroll`}
                                fileSource={previewPdfSource}
                                fileName={selectedFile.name}
                                scale={scale}
                                rotation={rotation}
                                maxWidth={600}
                                initialPage={pdfPage}
                                scrollRequest={pdfScrollRequest}
                                onVisiblePageChange={(page) => {
                                  setPdfPage(prev => (prev === page ? prev : page));
                                }}
                                onLoadSuccess={handlePrimaryPdfLoadSuccess}
                              />
                            </div>
                            <div className={`min-h-0 overflow-auto rounded-[26px] p-4 shadow-inner shadow-slate-400/10 dark:border-slate-800/70 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.86),rgba(51,65,85,0.36))] ${METALLIC_PANEL_CLASS}`}>
                              <div className="mb-3 flex items-center justify-between gap-3">
                                <span className={`shrink-0 whitespace-nowrap rounded-[10px] px-2.5 py-1 text-[11px] font-medium ${METALLIC_PREVIEW_TAG_CLASS}`}>原文件</span>
                                <span className="truncate text-right text-[11px] text-[#6c8197] dark:text-slate-400">{comparisonFile.name}</span>
                              </div>
                              <PdfScrollPreview
                                key={`${comparisonFile.id}-compare-original-scroll`}
                                fileSource={comparisonPdfSource}
                                fileName={comparisonFile.name}
                                scale={scale}
                                rotation={rotation}
                                maxWidth={600}
                                initialPage={pdfPage}
                                scrollRequest={pdfScrollRequest}
                                onVisiblePageChange={(page) => {
                                  setPdfPage(prev => (prev === page ? prev : page));
                                }}
                                onLoadSuccess={handleComparisonPdfLoadSuccess}
                              />
                            </div>
                          </div>
                        ) : isPreviewImage && previewUrl && comparisonPreviewUrl ? (
                          <div className="grid h-full grid-cols-2 gap-4">
                            <div className={`flex flex-col rounded-[26px] p-4 shadow-inner shadow-slate-400/10 dark:border-slate-800/70 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.86),rgba(51,65,85,0.36))] ${METALLIC_PANEL_CLASS}`}>
                              <div className="mb-3 flex items-center justify-between gap-3">
                                <span className={`shrink-0 whitespace-nowrap rounded-[10px] px-2.5 py-1 text-[11px] font-medium ${METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS}`}>修改后</span>
                                <span className="truncate text-right text-[11px] text-[#6c8197] dark:text-slate-400">{selectedFile.name}</span>
                              </div>
                              <div className="flex flex-1 items-center justify-center overflow-auto rounded-[22px] bg-[#f8fbff] p-4 dark:bg-slate-950/40">
                                <img
                                  src={previewUrl}
                                  alt={selectedFile.name}
                                  className="max-h-full max-w-full rounded-[24px] border border-white/70 object-contain shadow-[0_25px_70px_-30px_rgba(15,23,42,0.55)] transition-transform duration-300 ease-out dark:border-slate-700/80"
                                  style={{ transform: `scale(${scale}) rotate(${rotation}deg)` }}
                                />
                              </div>
                            </div>
                            <div className={`flex flex-col rounded-[26px] p-4 shadow-inner shadow-slate-400/10 dark:border-slate-800/70 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.86),rgba(51,65,85,0.36))] ${METALLIC_PANEL_CLASS}`}>
                              <div className="mb-3 flex items-center justify-between gap-3">
                                <span className={`shrink-0 whitespace-nowrap rounded-[10px] px-2.5 py-1 text-[11px] font-medium ${METALLIC_PREVIEW_TAG_CLASS}`}>原文件</span>
                                <span className="truncate text-right text-[11px] text-[#6c8197] dark:text-slate-400">{comparisonFile.name}</span>
                              </div>
                              <div className="flex flex-1 items-center justify-center overflow-auto rounded-[22px] bg-[#f8fbff] p-4 dark:bg-slate-950/40">
                                <img
                                  src={comparisonPreviewUrl}
                                  alt={comparisonFile.name}
                                  className="max-h-full max-w-full rounded-[24px] border border-white/70 object-contain shadow-[0_25px_70px_-30px_rgba(15,23,42,0.55)] transition-transform duration-300 ease-out dark:border-slate-700/80"
                                  style={{ transform: `scale(${scale}) rotate(${rotation}deg)` }}
                                />
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center dark:border-slate-700/70 dark:bg-slate-950/35 ${METALLIC_EMPTY_STATE_CLASS}`}>
                            <Diff size={56} className="mb-4 text-[#b2c8dc] dark:text-slate-600" />
                            <h3 className="text-lg font-semibold text-[#274768] dark:text-slate-200">当前格式暂不支持并排对比</h3>
                            <p className="mt-2 max-w-md text-sm leading-6 text-[#6b8198] dark:text-slate-400">
                              已为你提供“修改文件”和“原文件”两个独立预览标签，可切换查看。
                            </p>
                          </div>
                        )
                      ) : (
                        <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center dark:border-slate-700/70 dark:bg-slate-950/35 ${METALLIC_EMPTY_STATE_CLASS}`}>
                          <Diff size={56} className="mb-4 text-[#b2c8dc] dark:text-slate-600" />
                          <h3 className="text-lg font-semibold text-[#274768] dark:text-slate-200">暂无可对比文件</h3>
                          <p className="mt-2 max-w-md text-sm leading-6 text-[#6b8198] dark:text-slate-400">
                            当前选中文件没有可回看的原始版本。先生成修改后的文件，再切到这里查看前后差异。
                          </p>
                        </div>
                      )
                    ) : effectivePreviewPaneMode === 'report' ? (
                      (() => {
                        if (!hasAnalysisReportForFile(selectedFile.id)) {
                          return (
                            <div className={`flex h-full flex-col items-center justify-center rounded-[26px] text-[#6b8198] dark:border-slate-700/70 dark:bg-slate-950/35 dark:text-slate-500 ${METALLIC_EMPTY_STATE_CLASS}`}>
                              <ScanLine size={54} className="mb-4 text-[#9fb8d0] opacity-70" />
                              <p className="text-lg font-medium text-[#274768] dark:text-slate-200">暂无分析或提取报告</p>
                              <p className="mt-2 text-sm dark:text-slate-400">选择文件后发送分析或提取指令，结果会在这里实时输出。</p>
                            </div>
                          );
                        }

                        const reportToneStyles = REPORT_TONE_STYLES[preparedEditableReport.visualTone] ?? REPORT_TONE_STYLES.analysis;
                        const hasPreparedReportText = preparedEditableReport.text.trim().length > 0;
                        const shouldShowReportProgressCard = false;
                        const reportProgressAppearance = activeReportProgress
                          ? (
                            activeReportProgress.status === 'fallback'
                              ? {
                                  wrapper: 'border-[#ecd9ce] bg-[linear-gradient(180deg,#fffbf8,#fff6f1)] text-[#7b442e] dark:border-amber-900/40 dark:bg-[linear-gradient(180deg,rgba(120,53,15,0.16),rgba(67,20,7,0.12))] dark:text-amber-100',
                                  track: 'bg-[#f4e5dc] dark:bg-amber-950/34',
                                  bar: 'linear-gradient(90deg,#d17a4f,#efb08d)',
                                }
                              : activeReportProgress.status === 'failed'
                                ? {
                                    wrapper: 'border-[#ecd8dc] bg-[linear-gradient(180deg,#fffafb,#fff5f6)] text-[#8d3d49] dark:border-rose-900/40 dark:bg-[linear-gradient(180deg,rgba(127,29,29,0.16),rgba(76,5,25,0.12))] dark:text-rose-100',
                                    track: 'bg-[#f4e1e5] dark:bg-rose-950/34',
                                    bar: 'linear-gradient(90deg,#d65a72,#f29ab0)',
                                  }
                                : activeReportProgress.status === 'completed'
                                  ? {
                                      wrapper: 'border-[#d7e8db] bg-[linear-gradient(180deg,#fafdfb,#f3faf5)] text-[#215d3b] dark:border-emerald-900/34 dark:bg-[linear-gradient(180deg,rgba(6,78,59,0.16),rgba(2,44,34,0.12))] dark:text-emerald-100',
                                      track: 'bg-[#dfede2] dark:bg-emerald-950/34',
                                      bar: 'linear-gradient(90deg,#2f8f63,#71d69a)',
                                    }
                                  : {
                                      wrapper: 'border-[#dbe6f8] bg-[linear-gradient(180deg,#fbfdff,#f5f8ff)] text-[#1d4e88] dark:border-sky-900/34 dark:bg-[linear-gradient(180deg,rgba(14,116,144,0.12),rgba(15,23,42,0.16))] dark:text-sky-100',
                                      track: 'bg-[#e6eefc] dark:bg-sky-950/34',
                                      bar: 'linear-gradient(90deg,#2a64f6,#73abff)',
                                    }
                          )
                          : null;

                        return (
                          <div ref={reportPreviewScrollRef} className="h-full overflow-auto px-5 py-4 [overscroll-behavior:contain] sm:px-6">
                            <div className="prose max-w-none dark:prose-invert">
                              {shouldShowReportProgressCard && reportProgressAppearance ? (
                                <div className={`mb-2 rounded-[16px] border px-3.5 py-2.5 ${reportProgressAppearance.wrapper}`}>
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                      <div className="text-[14px] font-semibold leading-5">
                                        {activeReportProgress.label}
                                      </div>
                                      <div className="mt-0.5 text-[12px] leading-5 opacity-75">
                                        {activeReportProgress.description}
                                      </div>
                                    </div>
                                    <div className="shrink-0 pt-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] opacity-55">
                                      {Math.max(0, Math.min(100, Math.round(activeReportProgress.progress)))}%
                                    </div>
                                  </div>
                                  <div className={`mt-2 h-1.5 overflow-hidden rounded-full ${reportProgressAppearance.track}`}>
                                    <div
                                      className="h-full rounded-full transition-[width] duration-500 ease-out"
                                      style={{
                                        width: `${Math.max(6, Math.min(100, activeReportProgress.progress))}%`,
                                        backgroundImage: reportProgressAppearance.bar,
                                      }}
                                    />
                                  </div>
                                </div>
                              ) : null}
                              {hasPreparedReportText ? (
                                <div className="relative mx-auto max-w-[1120px]">
                                  <div
                                    ref={reportContentRef}
                                    className={`rounded-[22px] border bg-[linear-gradient(180deg,#ffffff,#fcfdff)] px-5 py-5 shadow-[0_18px_38px_-32px_rgba(42,100,246,0.14)] dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.82))] dark:shadow-[0_24px_48px_-36px_rgba(2,6,23,0.78)] sm:px-8 sm:py-7 ${METALLIC_PANEL_SOFT_CLASS}`}
                                  >
                                    {preparedEditableReport.blocks.map((block, index) => {
                                    const isStreamingTailBlock = (
                                      activeReportProgress?.status === 'active'
                                      && index === preparedEditableReport.blocks.length - 1
                                    );
                                    const blockFormatting = selectedReportFormatting[block.key];
                                    const effectiveBlockType = blockFormatting?.type ?? block.type;
                                    const effectiveAlign = blockFormatting?.align ?? DEFAULT_REPORT_TEXT_ALIGN;
                                    const textSegments = buildReportTextSegments(block.text, blockFormatting?.inlineFormats);
                                    const renderedText = textSegments.map((segment, segmentIndex) => (
                                      <span
                                        key={`${block.key}-${segmentIndex}`}
                                        style={{
                                          color: segment.color,
                                          fontSize: segment.fontSize,
                                        }}
                                      >
                                        {segment.text}
                                      </span>
                                    ));
                                    if (effectiveBlockType === 'heading1') {
                                      return (
                                        <h4
                                          key={isStreamingTailBlock ? `${block.key}-${reportStreamHighlightNonce}` : block.key}
                                          data-report-block-key={block.key}
                                          data-report-block-type={effectiveBlockType}
                                          className={`${reportToneStyles.heading1} ${isStreamingTailBlock ? 'report-stream-highlight typewriter' : ''}`}
                                          style={{ textAlign: effectiveAlign }}
                                        >
                                          {renderedText}
                                        </h4>
                                      );
                                    }

                                    if (effectiveBlockType === 'heading2') {
                                      return (
                                        <h5
                                          key={isStreamingTailBlock ? `${block.key}-${reportStreamHighlightNonce}` : block.key}
                                          data-report-block-key={block.key}
                                          data-report-block-type={effectiveBlockType}
                                          className={`${reportToneStyles.heading2} ${isStreamingTailBlock ? 'report-stream-highlight typewriter' : ''}`}
                                          style={{ textAlign: effectiveAlign }}
                                        >
                                          {renderedText}
                                        </h5>
                                      );
                                    }

                                    if (effectiveBlockType === 'heading3') {
                                      return (
                                        <div
                                          key={isStreamingTailBlock ? `${block.key}-${reportStreamHighlightNonce}` : block.key}
                                          data-report-block-key={block.key}
                                          data-report-block-type={effectiveBlockType}
                                          className={`${reportToneStyles.heading3} ${isStreamingTailBlock ? 'report-stream-highlight typewriter' : ''}`}
                                          style={{ textAlign: effectiveAlign }}
                                        >
                                          {renderedText}
                                        </div>
                                      );
                                    }

                                    return (
                                      <p
                                        key={isStreamingTailBlock ? `${block.key}-${reportStreamHighlightNonce}` : block.key}
                                        data-report-block-key={block.key}
                                        data-report-block-type={effectiveBlockType}
                                        className={`${reportToneStyles.paragraph} ${isStreamingTailBlock ? 'report-stream-highlight typewriter' : ''}`}
                                        style={{ textAlign: effectiveAlign }}
                                      >
                                        {renderedText}
                                      </p>
                                    );
                                    })}
                                  </div>

                                  {reportSelection?.fileId === selectedFile.id ? (
                                    <ReportSelectionToolbar
                                      anchorRect={reportSelection.rect}
                                      busyAction={reportBusyAction}
                                      canUndo={canUndoReportEdit}
                                      manualEditOpen={reportManualEditOpen}
                                      manualEditValue={reportManualEditValue}
                                      manualEditBusy={reportManualEditBusy}
                                      feedback={reportToolbarFeedback}
                                      currentTextColor={currentSelectionInlineStyle.color ?? null}
                                      currentFontSize={currentSelectionInlineStyle.fontSize ?? null}
                                      currentBlockType={currentSelectionBlockType}
                                      currentTextAlign={currentSelectionTextAlign}
                                      onAction={(action) => { void handleReportQuickEdit(action); }}
                                      onUndo={handleUndoReportEdit}
                                      onOpenManualEdit={handleOpenManualReportEdit}
                                      onManualEditChange={setReportManualEditValue}
                                      onManualEditApply={() => { void handleApplyManualReportEdit(); }}
                                      onManualEditCancel={() => {
                                        setReportManualEditOpen(false);
                                        setReportManualEditValue(reportSelection.selectedText);
                                      }}
                                      onTextColorChange={handleApplyReportTextColor}
                                      onFontSizeChange={handleApplyReportFontSize}
                                      onBlockTypeChange={handleApplyReportBlockType}
                                      onTextAlignChange={handleApplyReportTextAlign}
                                    />
                                  ) : null}
                                </div>
                              ) : (
                                activeReportProgress?.status === 'failed' ? (
                                  <div className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-sm text-[#8d3d49] dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-100 ${METALLIC_PANEL_SOFT_CLASS}`}>
                                    <AlertCircle size={16} />
                                    <span>本次分析暂未生成报告，请稍后重试或缩小分析范围。</span>
                                  </div>
                                ) : activeReportProgress?.status === 'fallback' ? (
                                  <div className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-sm text-[#7b442e] dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-100 ${METALLIC_PANEL_SOFT_CLASS}`}>
                                    <CheckCircle size={16} />
                                    <span>已返回本地整理摘要，你可以先查看结果，稍后再重试 AI 分析。</span>
                                  </div>
                                ) : activeReportProgress?.status === 'completed' ? (
                                  <div className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-sm text-[#215d3b] dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-100 ${METALLIC_PANEL_SOFT_CLASS}`}>
                                    <AlertCircle size={16} />
                                    <span>分析已完成，但本次报告内容为空。请重试一次，或缩小分析范围。</span>
                                  </div>
                                ) : null
                              )}
                            </div>
                          </div>
                        );
                      })()
                    ) : previewedFile?.status === 'processing' ? (
                      <div className={`flex h-full flex-col items-center justify-center rounded-[26px] text-[#6b8198] dark:border-slate-700/70 dark:bg-slate-950/35 dark:text-slate-300 ${METALLIC_EMPTY_STATE_CLASS}`}>
                        <Loader size={42} className="mb-4 animate-spin text-[#6a89a8] dark:text-slate-400" />
                        <p className="text-lg font-medium text-[#274768] dark:text-slate-100">正在准备预览</p>
                        <p className="mt-2 text-sm text-[#7f95aa] dark:text-slate-500">
                          文档处理中，请稍候…
                        </p>
                      </div>
                    ) : isDocxAwaitingFidelity ? (
                      <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-[22px] border border-[#dce9fc] bg-[#f4f8ff] text-[#1d5a93] shadow-[0_12px_24px_-18px_rgba(42,100,246,0.16)] dark:border-slate-700 dark:bg-slate-900 dark:text-sky-300 dark:shadow-[0_16px_28px_-20px_rgba(2,6,23,0.8)]">
                          <Loader size={28} className="animate-spin" />
                        </div>
                        <h3 className="text-xl font-semibold text-[#173750] dark:text-slate-100">
                          正在将 Word 转为 PDF 预览
                        </h3>
                        <p className="mt-3 max-w-lg text-sm leading-7 text-[#6b8198] dark:text-slate-400">
                          转换完成后会直接按 PDF 方式预览，并支持正常翻页浏览。
                        </p>
                      </div>
                    ) : isDocxPreviewFailed ? (
                      <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-[22px] border border-amber-200 bg-amber-50 text-amber-600 shadow-[0_12px_24px_-18px_rgba(217,119,6,0.18)] dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300 dark:shadow-[0_16px_28px_-20px_rgba(2,6,23,0.8)]">
                          <AlertCircle size={28} />
                        </div>
                        <h3 className="text-xl font-semibold text-[#173750] dark:text-slate-100">
                          Word 转 PDF 失败
                        </h3>
                        <p className="mt-3 max-w-lg text-sm leading-7 text-[#6b8198] dark:text-slate-400">
                          {previewedFile?.error || WORD_PREVIEW_FALLBACK_MESSAGE}
                        </p>
                        {previewedFile && (
                          <button
                            type="button"
                            onClick={() => downloadFile(previewedFile)}
                            className={`mt-6 inline-flex items-center gap-2 rounded-[18px] px-4 py-2.5 text-sm font-medium ${COBALT_GLASS_BUTTON_CLASS}`}
                          >
                            <Download size={16} />
                            下载原文件
                          </button>
                        )}
                      </div>
                    ) : isPreviewPdf && previewPdfSource ? (
                      <div className="flex h-full min-h-0 flex-col px-4 py-4 sm:px-5 sm:py-5">
                        {usesPagedPdfPreview ? (
                          <PdfPagedPreview
                            fileSource={previewPdfSource}
                            fileName={previewedFileName}
                            pageNumber={pdfPage}
                            scale={scale}
                            rotation={rotation}
                            maxWidth={isPreviewFullscreen ? 1440 : 1040}
                            onLoadSuccess={handlePrimaryPdfLoadSuccess}
                          />
                        ) : (
                          <PdfScrollPreview
                            key={`${previewedFile?.id ?? 'preview'}-scroll`}
                            fileSource={previewPdfSource}
                            fileName={previewedFileName}
                            scale={scale}
                            rotation={rotation}
                            maxWidth={isPreviewFullscreen ? 1440 : 1040}
                            initialPage={pdfPage}
                            scrollRequest={pdfScrollRequest}
                            onVisiblePageChange={(page) => {
                              setPdfPage(prev => (prev === page ? prev : page));
                            }}
                            onLoadSuccess={handlePrimaryPdfLoadSuccess}
                          />
                        )}
                      </div>
                    ) : isPreviewImage && previewUrl ? (
                      <div className="flex h-full items-center justify-center overflow-auto px-6 py-6">
                        <img
                          src={previewUrl}
                          alt={previewedFileName}
                          className="max-h-full max-w-full rounded-[28px] border border-white/70 object-contain shadow-[0_25px_70px_-30px_rgba(15,23,42,0.55)] transition-transform duration-300 ease-out dark:border-slate-700/80"
                          style={{ transform: `scale(${scale}) rotate(${rotation}deg)` }}
                        />
                      </div>
                    ) : isPreviewText ? (
                      <div className="h-full overflow-auto px-6 py-5">
                        <div
                          className={`mx-auto max-w-4xl rounded-[24px] px-6 py-5 shadow-[0_20px_60px_-35px_rgba(15,23,42,0.4)] transition-transform duration-300 ease-out dark:border-slate-700/70 dark:bg-slate-900 ${METALLIC_PANEL_SOFT_CLASS}`}
                          style={{ transform: `scale(${scale}) rotate(${rotation}deg)`, transformOrigin: 'top center' }}
                        >
                          <pre className="whitespace-pre-wrap break-words text-sm leading-7 text-[#284665] dark:text-slate-200">
                            {previewText || '文本预览加载中...'}
                          </pre>
                        </div>
                      </div>
                    ) : isPreviewExcel && previewedFile ? (
                      <div className="h-full px-4 py-4 sm:px-5 sm:py-5">
                        <ExcelPreview file={previewedFile} />
                      </div>
                    ) : (
                      <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center dark:border-slate-700/70 dark:bg-slate-950/35 ${METALLIC_EMPTY_STATE_CLASS}`}>
                        <img src={CustomDocIconImage} alt="Document" className="mb-4 h-14 w-14 object-contain opacity-50 drop-shadow-sm" />
                        <h3 className="text-lg font-semibold text-[#274768] dark:text-slate-200">当前格式暂不支持浏览器内预览</h3>
                        <p className="mt-2 max-w-md text-sm leading-6 text-[#6b8198] dark:text-slate-400">
                          {previewedFile?.name || '该文件'} 已成功生成，但浏览器无法直接渲染这种格式。你仍然可以切换回原文件查看，或下载文件后在本地打开。
                        </p>
                        {previewedFile && (
                          <button
                            type="button"
                            onClick={() => downloadFile(previewedFile)}
                            className={`mt-6 flex h-11 w-11 items-center justify-center rounded-2xl transition-all hover:-translate-y-0.5 hover:shadow-xl ${METALLIC_PRIMARY_BUTTON_CLASS}`}
                            title={`下载 ${previewedFile.name}`}
                            aria-label={`下载 ${previewedFile.name}`}
                          >
                            <Download size={16} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
  
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        accept=".pdf,.doc,.docx,.txt,.xlsx,.md,.jpg,.jpeg,.png,.gif,.bmp,.webp"
        multiple
        className="hidden"
      />
  
    </div>
  );
}
