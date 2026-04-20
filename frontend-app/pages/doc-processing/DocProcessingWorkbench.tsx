import React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { 
  FileText, X, CheckCircle, Plus, Palette, Loader,
  Brain, Download, Eye,
  ChevronLeft, ChevronRight, Diff,
  Clock, AlertCircle,
  ZoomIn, ZoomOut, RotateCw, Layers, ScanLine,
  UploadCloud, Sparkles, ArrowRight
} from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { Image } from 'lucide-react';
import { LuckysheetPreview } from './LuckysheetPreview';
import { MobileCurrentFileCard } from './mobile/MobileCurrentFileCard';
import { MobileComposer } from './mobile/MobileComposer';
import { MobileMessageList } from './mobile/MobileMessageList';
import { MobilePreviewPage } from './mobile/MobilePreviewPage';
import { MobileReportPage } from './mobile/MobileReportPage';
import { MobileUtilityDrawer } from './mobile/MobileUtilityDrawer';
import { prepareReportContent } from './lib/reportFormatting.js';
import { applyReportQuickEdit, type ReportQuickEditAction } from './lib/reportQuickEdit';
import {
  adjustReportFormattingAfterTextReplacement,
  applyBlockFormatPatch,
  applyInlineFormatToSelection,
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
import {
  writeModule1RecentActivities,
  type Module1RecentActivityRecord,
  type Module1RecentActivityStatus,
} from '../../shared/state/module1RecentActivities';

import PdfIconImage from '../../assets/pdf.png';
import DialogIllustrationImage from '../../assets/对话框插图.png';
import WordIconImage from '../../assets/WORD.png';
import TxtIconImage from '../../assets/txt.png';
import ExcelIconImage from '../../assets/xlsx.png';
import MdIconImage from '../../assets/md.png';
import CustomDocIconImage from '../../assets/文档.png';
import AppLogoImage from '../../assets/app-logo.png';

const pdfWorkerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();
pdfjs.GlobalWorkerOptions.workerSrc = `${pdfWorkerSrc}?v=${pdfjs.version}`;
const ALLOWED_UPLOAD_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt', '.xlsx', '.md', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'];
const MAX_UPLOAD_FILE_SIZE = 20 * 1024 * 1024;
const WORD_PREVIEW_FALLBACK_MESSAGE = '当前环境暂时无法把 Word 转成 PDF 预览，你仍然可以继续处理并下载原文件。';
const SAVEABLE_REPORT_EXTENSIONS = new Set(['doc', 'docx', 'txt', 'md', 'csv']);
const FILE_TYPE_ICON_MAP: Record<string, string> = {
  pdf: PdfIconImage,
  doc: WordIconImage,
  docx: WordIconImage,
  txt: TxtIconImage,
  md: MdIconImage,
  xls: ExcelIconImage,
  xlsx: ExcelIconImage,
};
const METALLIC_PRIMARY_BUTTON_CLASS = `
  relative
  border-0
  bg-[#14b8a6]
  text-white shadow-[0_8px_20px_rgba(20,184,166,0.25)]
  hover:-translate-y-0.5 hover:bg-[#0d9488]
  hover:shadow-[0_12px_24px_rgba(20,184,166,0.35)]
  active:translate-y-0 active:scale-[0.98]
  transition-all duration-200
`.replace(/\s+/g, ' ').trim();

const METALLIC_SECONDARY_BUTTON_CLASS = `
  relative
  border border-slate-200/60
  bg-white
  text-slate-600 shadow-[0_2px_8px_rgba(0,0,0,0.04)]
  hover:-translate-y-0.5 hover:bg-slate-50
  hover:shadow-[0_4px_12px_rgba(0,0,0,0.06)]
  dark:border-white/[0.05]
  dark:bg-slate-800/80
  dark:text-slate-200
  dark:shadow-[0_4px_12px_rgba(0,0,0,0.2)]
  dark:hover:bg-slate-700/80
  transition-all duration-200
`.replace(/\s+/g, ' ').trim();
const METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS = `
  relative
  border-0
  bg-cyan-50
  text-cyan-700 shadow-[0_4px_12px_rgba(6,182,212,0.15)]
  dark:bg-cyan-900/40
  dark:text-cyan-300
`.replace(/\s+/g, ' ').trim();
const COBALT_GLASS_BUTTON_CLASS = `
  relative
  border-0
  bg-[#06b6d4]
  text-white shadow-[0_8px_24px_rgba(6,182,212,0.25)]
  transition-all duration-200
  hover:-translate-y-0.5 hover:bg-[#0891b2]
  hover:shadow-[0_12px_28px_rgba(6,182,212,0.35)]
  active:translate-y-0 active:scale-[0.98]
`.replace(/\s+/g, ' ').trim();
const METALLIC_PANEL_CLASS = 'border-0 bg-white shadow-[0_8px_32px_rgba(15,23,42,0.04)] ring-1 ring-slate-100 dark:bg-slate-800/60 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)] dark:ring-white/[0.05]';
const METALLIC_PANEL_SOFT_CLASS = 'border-0 bg-[#f8fafc] shadow-sm dark:bg-slate-900/50';
const METALLIC_EMPTY_STATE_CLASS = 'border-0 rounded-[24px] bg-white shadow-[0_8px_32px_rgba(15,23,42,0.04)] ring-1 ring-slate-100 dark:bg-slate-800/60 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)] dark:ring-white/[0.05]';
const METALLIC_PREVIEW_TAG_CLASS = 'border-0 bg-[#e0f2fe] text-[#0369a1] dark:bg-sky-500/20 dark:text-sky-300';

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

type PreviewPaneMode = 'report' | 'current' | 'original' | 'compare';
type PdfReadingMode = 'scroll' | 'paged';
type PreviewCategory = 'pdf' | 'excel' | 'text' | 'image' | 'word' | 'other';
type MobileWorkbenchView = 'home' | 'preview' | 'report';

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

const toRecentActivitySummary = (value: unknown, fallback: string): string => {
  const normalized = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (!normalized) return fallback;
  return normalized.length > 52 ? `${normalized.slice(0, 52)}...` : normalized;
};

const getLatestConversationMessageForFile = (
  messages: Message[],
  fileId: string,
  matcher?: (message: Message) => boolean,
): Message | null => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message.fileIds?.includes(fileId)) continue;
    if (matcher && !matcher(message)) continue;
    if (!message.content.trim()) continue;
    return message;
  }
  return null;
};

const getModule1RecentActivityStatus = (
  file: FileInfo,
  hasReport: boolean,
): Module1RecentActivityStatus => {
  if (file.status === 'error') return 'failed';
  if (file.status === 'processing' || file.status === 'uploading' || file.status === 'converting') {
    return 'running';
  }
  if (file.status === 'completed' || hasReport || Boolean(file.sourceFileId)) {
    return 'completed';
  }
  if (file.status === 'ready') return 'ready';
  return 'review';
};

const getModule1RecentActivitySummary = (
  file: FileInfo,
  latestMessage: Message | null,
  latestReportMessage: Message | null,
  conversationPreview: string,
): string => {
  if (file.status === 'error') {
    return toRecentActivitySummary(file.error || file.result, '处理失败，请重新上传');
  }
  if (file.status === 'uploading') return '文件上传中';
  if (file.status === 'converting') return '预览转换中';
  if (file.status === 'processing') return '文档处理中';
  if (latestReportMessage) return '分析报告已生成';
  if (file.sourceFileId) {
    return toRecentActivitySummary(file.result, '已生成修改稿');
  }
  if (file.status === 'completed') {
    return toRecentActivitySummary(file.result, '文档处理已完成');
  }
  if (file.result) {
    return toRecentActivitySummary(file.result, '文件已就绪，可继续提问');
  }
  if (latestMessage) {
    return toRecentActivitySummary(latestMessage.content, conversationPreview);
  }
  return conversationPreview || '文件已就绪，可继续提问';
};

const buildModule1RecentActivityRecords = (
  conversations: ConversationRecord[],
): Module1RecentActivityRecord[] => {
  const records = conversations.flatMap((conversation) => {
    const conversationPreview = getConversationPreviewText(conversation.messages);
    return Object.values(conversation.files).map((file) => {
      const latestReportMessage = getLatestConversationMessageForFile(
        conversation.messages,
        file.id,
        (message) => message.type === 'assistant' && message.displayMode === 'report',
      );
      const latestMessage = getLatestConversationMessageForFile(
        conversation.messages,
        file.id,
      );
      const updatedAt = Math.max(
        file.uploadTime.getTime(),
        latestMessage?.timestamp.getTime() ?? 0,
        latestReportMessage?.timestamp.getTime() ?? 0,
      );
      return {
        id: `${conversation.id}:${file.id}`,
        conversationId: conversation.id,
        fileId: file.id,
        fileName: file.name,
        updatedAt: new Date(updatedAt).toISOString(),
        status: getModule1RecentActivityStatus(file, Boolean(latestReportMessage)),
        summary: getModule1RecentActivitySummary(
          file,
          latestMessage,
          latestReportMessage,
          conversationPreview,
        ),
        progressPercent: typeof file.progress === 'number'
          ? Math.max(0, Math.min(100, Math.round(file.progress)))
          : null,
      };
    });
  });

  return records
    .sort((left, right) => (
      new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime()
    ))
    .slice(0, 20);
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
  <div className="relative overflow-hidden rounded-[24px] border border-[#d9e7fd] bg-[linear-gradient(180deg,#ffffff,#f8fbff)] shadow-[0_24px_54px_-34px_rgba(15,23,42,0.3)] dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(30,41,59,0.88))] dark:shadow-[0_28px_54px_-34px_rgba(2,6,23,0.82)]">
    <span className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-[linear-gradient(180deg,rgba(255,255,255,0.4),rgba(255,255,255,0))] dark:bg-[linear-gradient(180deg,rgba(148,163,184,0.08),rgba(148,163,184,0))]" />
    {pageLabel && (
      <div className="absolute right-2.5 top-2.5 z-10 rounded-full border border-[#dbe7fb] bg-white/92 px-2.5 py-1 text-[10px] font-medium tracking-[0.08em] text-[#5e7896] shadow-[0_10px_18px_-16px_rgba(42,100,246,0.28)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/92 dark:text-slate-300 dark:shadow-none">
        {pageLabel}
      </div>
    )}
    <div className="relative z-10 flex items-start justify-center p-1.5 sm:p-2.5">
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
          <div className="flex min-h-[320px] items-center justify-center text-sm text-[#6a86a3]">
            <Loader size={18} className="mr-2 animate-spin text-[#6a86a3]" />
            正在加载 PDF 预览…
          </div>
        }
        error={
          <div className="flex min-h-[320px] items-center justify-center text-sm text-rose-500">
            PDF 预览加载失败，请尝试下载后查看。
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
              <div className="flex min-h-[320px] items-center justify-center text-sm text-[#6a86a3]">
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
          <div className="flex min-h-[320px] items-center justify-center text-sm text-[#6a86a3]">
            <Loader size={18} className="mr-2 animate-spin text-[#6a86a3]" />
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
          className="flex h-full min-h-0 w-full min-w-0 flex-1 overflow-auto rounded-[28px] border border-[#dde8fc] bg-[linear-gradient(180deg,#f4f8ff,#edf3ff)] p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] [overscroll-behavior:contain] [-webkit-overflow-scrolling:touch] touch-pan-y dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.94),rgba(30,41,59,0.86))] sm:p-3"
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
                      <div className="flex min-h-[320px] items-center justify-center text-sm text-[#6a86a3]">
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

// ---------- 主组件 ----------
export const DocProcessingWorkbench: React.FC<{ onBack?: () => void }> = ({ onBack }) => {
  const initialConversation = useMemo(() => createConversationRecord(1), []);
  const hydratingConversationRef = useRef(false);
  const activeConversationIdRef = useRef(initialConversation.id);

  const [conversations, setConversations] = useState<ConversationRecord[]>(() => [initialConversation]);
  const [activeConversationId, setActiveConversationId] = useState(initialConversation.id);

  // 文档存储
  const [files, setFiles] = useState<Record<string, FileInfo>>(initialConversation.files);
  const [composerFileIds, setComposerFileIds] = useState<string[]>(initialConversation.composerFileIds);
  const [rememberedFileBatchIds, setRememberedFileBatchIds] = useState<string[]>(initialConversation.rememberedFileBatchIds);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(initialConversation.selectedFileId);
  
  // 聊天状态
  const [messages, setMessages] = useState<Message[]>(initialConversation.messages);
  const [inputText, setInputText] = useState(initialConversation.inputText);
  const [isLoading, setIsLoading] = useState(false);
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
  const reportPreviewScrollRef = useRef<HTMLDivElement>(null);
  const reportContentRef = useRef<HTMLDivElement>(null);
  const reportSourceByFileIdRef = useRef<Record<string, string>>({});
  const documentDragDepthRef = useRef(0);
  const [showPreviewPanel, setShowPreviewPanel] = useState(initialConversation.showPreviewPanel);
  const [isDocumentDragOver, setIsDocumentDragOver] = useState(false);
  const [primaryPdfPageCount, setPrimaryPdfPageCount] = useState<number | null>(null);
  const [comparisonPdfPageCount, setComparisonPdfPageCount] = useState<number | null>(null);
  const [pdfScrollRequest, setPdfScrollRequest] = useState<PdfScrollRequest | null>(null);
  const [isBrowsingHistory, setIsBrowsingHistory] = useState(false);
  const [isComposerHovered, setIsComposerHovered] = useState(false);
  const [isComposerFocused, setIsComposerFocused] = useState(false);
  const [editableReportByFileId, setEditableReportByFileId] = useState<Record<string, string>>({});
  const [reportFormattingByFileId, setReportFormattingByFileId] = useState<Record<string, ReportFormattingState>>({});
  const [reportHistoryByFileId, setReportHistoryByFileId] = useState<Record<string, ReportHistorySnapshot[]>>({});
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

  const [mobileView, setMobileView] = useState<MobileWorkbenchView>('home');
  const [showUtilityDrawer, setShowUtilityDrawer] = useState(false);

  // 计算属性
  const fileList = useMemo(() => Object.values(files), [files]);
  const composerFiles = useMemo(() => getFilesByIds(files, composerFileIds), [composerFileIds, files]);
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
  const recentActivityConversations = useMemo(
    () => conversations.map((conversation) => (
      conversation.id === activeConversationId
        ? {
            ...conversation,
            updatedAt: getConversationUpdatedAt(messages, files, conversation.updatedAt),
            messages,
            files,
          }
        : conversation
    )),
    [activeConversationId, conversations, files, messages],
  );
  const selectedFile = useMemo(
    () => selectedFileId ? files[selectedFileId] : null,
    [files, selectedFileId]
  );
  const latestReportByFileId = useMemo(() => {
    const reportMap = new Map<string, Message>();

    messages.forEach((message) => {
      if (message.type !== 'assistant' || message.displayMode !== 'report' || !message.fileIds?.length) {
        return;
      }

      message.fileIds.forEach((fileId) => {
        const existing = reportMap.get(fileId);
        if (!existing || existing.timestamp.getTime() <= message.timestamp.getTime()) {
          reportMap.set(fileId, message);
        }
      });
    });

    return reportMap;
  }, [messages]);
  
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
    writeModule1RecentActivities(
      buildModule1RecentActivityRecords(recentActivityConversations),
    );
  }, [recentActivityConversations]);

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
      return;
    }

    const nextConversation = createConversationRecord(conversations.length + 1);
    setConversations((prev) => [nextConversation, ...commitCurrentConversation(prev)]);
    setActiveConversationId(nextConversation.id);
    loadConversation(nextConversation);
  }, [activeConversationId, commitCurrentConversation, conversations, files, inputText, isLoading, loadConversation, messages]);

  const activateConversation = useCallback((conversationId: string) => {
    if (conversationId === activeConversationId || isLoading) return;

    const nextConversation = conversations.find((conversation) => conversation.id === conversationId);
    if (!nextConversation) return;

    setConversations((prev) => commitCurrentConversation(prev));
    setActiveConversationId(conversationId);
    loadConversation(nextConversation);
  }, [activeConversationId, commitCurrentConversation, conversations, isLoading, loadConversation]);

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
    setConversations(nextConversations);

    if (conversationId !== activeConversationId) {
      return;
    }

    if (!nextActiveConversation) {
      return;
    }

    setActiveConversationId(nextActiveConversation.id);
    loadConversation(nextActiveConversation);
  }, [activeConversationId, commitCurrentConversation, conversations, isLoading, loadConversation]);

  // ---------- Word转PDF转换函数 ----------
  const convertWordToPdf = async (file: File): Promise<{ pdfBlob: Blob; pdfFile: File } | null> => {
    const formData = new FormData();
    formData.append('file', file, file.name || 'document.docx');
    
    try {
      console.log(`开始转换Word文件: ${file.name}`);
      const response = await fetch(buildModule1ApiUrl('/convert/docx-to-pdf'), {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });
      
      // 先检查响应状态
      if (!response.ok) {
        const errorText = await response.text();
        console.error('服务器返回错误:', response.status, errorText);
        throw new Error(`转换失败: ${response.status} - ${errorText}`);
      }
      
      // 检查响应内容类型
      const contentType = response.headers.get('content-type');
      console.log('响应内容类型:', contentType);
      
      // 如果不是PDF，可能返回了错误信息
      if (!contentType?.includes('application/pdf')) {
        const errorText = await response.text();
        console.error('返回的不是PDF文件:', errorText);
        throw new Error(`服务器返回了错误: ${errorText}`);
      }
      
      const pdfBlob = await response.blob();
      
      // 检查blob是否有效
      if (pdfBlob.size === 0) {
        throw new Error('转换后的PDF文件为空');
      }
      
      console.log('PDF Blob大小:', pdfBlob.size, 'bytes');
      
      const pdfFileName = file.name.replace(/\.[^/.]+$/, '') + '.pdf';
      
      // 修复：使用Blob和File的兼容方式创建File对象
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
      return { pdfBlob, pdfFile };
    } catch (error) {
      console.error('Word转PDF失败:', error);
      return null;
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

      if (conversionResult) {
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
                error: WORD_PREVIEW_FALLBACK_MESSAGE,
                result: WORD_PREVIEW_FALLBACK_MESSAGE
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
                error: WORD_PREVIEW_FALLBACK_MESSAGE,
                result: WORD_PREVIEW_FALLBACK_MESSAGE
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
      let previewFallbackNote = '';

      if (modifiedExt === '.doc' || modifiedExt === '.docx') {
        const conversionResult = await convertWordToPdf(modifiedFile as File);
        if (conversionResult) {
          URL.revokeObjectURL(modifiedPreviewUrl);
          modifiedPreviewUrl = URL.createObjectURL(conversionResult.pdfBlob);
          modifiedPreviewType = 'application/pdf';
          modifiedPreviewBlob = conversionResult.pdfBlob;
        } else {
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
          originalFile: modifiedFile,
          sourceFileId: targetFile.id,
          result: `已应用 ${modificationCount} 项修改${previewFallbackNote ? '，并保留原文件下载' : ''}`
        };
        
        return newFiles;
      });
      
      // 自动选中新文件
      setSelectedFileId(newFileId);
      setPreviewPaneMode('current');
      setShowPreviewPanel(true);
      setMobileView('preview');
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
  }, []);

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
        return <Loader size={14} className="text-[#6a86a3] animate-spin" />;
      case 'completed':
        return <CheckCircle size={15} className="text-emerald-500" />;
      case 'error':
        return <AlertCircle size={14} className="text-red-500" />;
      case 'uploading':
      default:
        return <Clock size={14} className="text-[#8daad0]" />;
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
  
      // 报告结果仍按报告语义处理，但移动端不再自动切到报告页。
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
                            description: '报告内容会在聊天区持续更新',
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

  // 获取指定文件的最新分析报告内容
  const getAnalysisReportForFile = useCallback((fileId: string): string | null => {
    return latestReportByFileId.get(fileId)?.content ?? null;
  }, [latestReportByFileId]);

  const hasAnalysisReportForFile = useCallback((fileId: string): boolean => (
    latestReportByFileId.has(fileId)
  ), [latestReportByFileId]);

  const getEditableReportTextForFile = useCallback((fileId: string): string => {
    const localEditedReport = editableReportByFileId[fileId];
    const sourceReport = getAnalysisReportForFile(fileId);
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
  }, [editableReportByFileId, getAnalysisReportForFile]);

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
    () => (selectedFile ? getEditableReportTextForFile(selectedFile.id) : ''),
    [getEditableReportTextForFile, selectedFile]
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
    () => (selectedFile ? reportFormattingByFileId[selectedFile.id] ?? {} : {}),
    [reportFormattingByFileId, selectedFile]
  );
  const canUndoReportEdit = useMemo(
    () => Boolean(selectedFile && (reportHistoryByFileId[selectedFile.id]?.length ?? 0) > 0),
    [reportHistoryByFileId, selectedFile]
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
    const syncedFileIds: string[] = [];

    setEditableReportByFileId((prev) => {
      let changed = false;
      const next = { ...prev };

      latestReportByFileId.forEach((message, fileId) => {
        const normalizedReport = formatPreparedReportContent(message.content || '').text || message.content || '';
        const previousSource = reportSourceByFileIdRef.current[fileId];
        const currentEditable = prev[fileId];

        reportSourceByFileIdRef.current[fileId] = normalizedReport;

        if (currentEditable === undefined || currentEditable === previousSource) {
          if (currentEditable !== normalizedReport) {
            next[fileId] = normalizedReport;
            changed = true;
            syncedFileIds.push(fileId);
          }
        }
      });

      return changed ? next : prev;
    });

    if (syncedFileIds.length > 0) {
      setReportFormattingByFileId((prev) => {
        let changed = false;
        const next = { ...prev };

        syncedFileIds.forEach((fileId) => {
          if (next[fileId]) {
            delete next[fileId];
            changed = true;
          }
        });

        return changed ? next : prev;
      });

      setReportHistoryByFileId((prev) => {
        let changed = false;
        const next = { ...prev };

        syncedFileIds.forEach((fileId) => {
          if ((next[fileId]?.length ?? 0) > 0) {
            next[fileId] = [];
            changed = true;
          }
        });

        return changed ? next : prev;
      });
    }
  }, [latestReportByFileId]);

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
    if (effectivePreviewPaneMode !== 'report' || !selectedFile || !reportContentRef.current) {
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
    });

    if (reportManualEditOpen) {
      setReportManualEditValue(nextSelection.selectedText);
    }
  }, [effectivePreviewPaneMode, reportManualEditOpen, selectedFile]);

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
  }, [clearReportEditingState, selectedFile?.id]);

  const commitReportSelectionEdit = useCallback((replacementText: string, feedback: string): boolean => {
    if (!selectedFile || !reportSelection || reportSelection.fileId !== selectedFile.id) {
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

    const fileId = selectedFile.id;
    const nextFormatting = adjustReportFormattingAfterTextReplacement(
      reportFormattingByFileId[fileId] ?? {},
      reportSelection,
      replacementText,
    );

    pushReportHistorySnapshot(fileId, selectedEditableReportText, reportFormattingByFileId[fileId] ?? {});
    setEditableReportByFileId((prev) => ({
      ...prev,
      [fileId]: nextReportText,
    }));
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [fileId]: nextFormatting,
    }));
    setReportToolbarFeedback(feedback);
    clearReportEditingState();
    return true;
  }, [
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
    if (!selectedFile) return;

    const fileId = selectedFile.id;
    const history = reportHistoryByFileId[fileId] ?? [];
    if (!history.length) return;

    const previousSnapshot = history[history.length - 1];
    setEditableReportByFileId((prev) => ({
      ...prev,
      [fileId]: previousSnapshot.text,
    }));
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [fileId]: cloneReportFormatting(previousSnapshot.formatting),
    }));
    setReportHistoryByFileId((prev) => ({
      ...prev,
      [fileId]: history.slice(0, -1),
    }));
    setReportToolbarFeedback('已回退上一步');
    clearReportEditingState();
  }, [clearReportEditingState, reportHistoryByFileId, selectedFile]);

  const handleApplyReportTextColor = useCallback((value: string | null) => {
    if (!selectedFile || !reportSelection) return;

    const fileId = selectedFile.id;
    const currentFormatting = reportFormattingByFileId[fileId] ?? {};
    const nextFormatting = applyInlineFormatToSelection(currentFormatting, reportSelection, { color: value });

    if (JSON.stringify(nextFormatting) === JSON.stringify(currentFormatting)) {
      return;
    }

    pushReportHistorySnapshot(fileId, selectedEditableReportText, currentFormatting);
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [fileId]: nextFormatting,
    }));
    setReportToolbarFeedback(value ? '已更新文字颜色' : '已恢复默认文字颜色');
  }, [
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
    selectedFile,
  ]);

  const handleApplyReportFontSize = useCallback((value: string | null) => {
    if (!selectedFile || !reportSelection) return;

    const fileId = selectedFile.id;
    const currentFormatting = reportFormattingByFileId[fileId] ?? {};
    const nextFormatting = applyInlineFormatToSelection(currentFormatting, reportSelection, { fontSize: value });

    if (JSON.stringify(nextFormatting) === JSON.stringify(currentFormatting)) {
      return;
    }

    pushReportHistorySnapshot(fileId, selectedEditableReportText, currentFormatting);
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [fileId]: nextFormatting,
    }));
    setReportToolbarFeedback(value ? '已更新字号' : '已恢复默认字号');
  }, [
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
    selectedFile,
  ]);

  const handleApplyReportBlockType = useCallback((value: ReportBlockType) => {
    if (!selectedFile || !reportSelection) return;

    const fileId = selectedFile.id;
    const currentFormatting = reportFormattingByFileId[fileId] ?? {};
    const nextFormatting = applyBlockFormatPatch(currentFormatting, reportSelection.blockKey, {
      type: currentSelectedReportBlock?.type === value ? null : value,
    });

    if (JSON.stringify(nextFormatting) === JSON.stringify(currentFormatting)) {
      return;
    }

    pushReportHistorySnapshot(fileId, selectedEditableReportText, currentFormatting);
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [fileId]: nextFormatting,
    }));
    setReportToolbarFeedback('已更新段落级别');
  }, [
    currentSelectedReportBlock?.type,
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
    selectedFile,
  ]);

  const handleApplyReportTextAlign = useCallback((value: ReportTextAlign) => {
    if (!selectedFile || !reportSelection) return;

    const fileId = selectedFile.id;
    const currentFormatting = reportFormattingByFileId[fileId] ?? {};
    const nextFormatting = applyBlockFormatPatch(currentFormatting, reportSelection.blockKey, {
      align: value === DEFAULT_REPORT_TEXT_ALIGN ? null : value,
    });

    if (JSON.stringify(nextFormatting) === JSON.stringify(currentFormatting)) {
      return;
    }

    pushReportHistorySnapshot(fileId, selectedEditableReportText, currentFormatting);
    setReportFormattingByFileId((prev) => ({
      ...prev,
      [fileId]: nextFormatting,
    }));
    setReportToolbarFeedback('已更新段落对齐方式');
  }, [
    pushReportHistorySnapshot,
    reportFormattingByFileId,
    reportSelection,
    selectedEditableReportText,
    selectedFile,
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
  const initialLandingPlaceholder = '尽管问，带图也行';

  const mobileCurrentFile = useMemo(
    () => selectedFile ?? fileList[0] ?? null,
    [fileList, selectedFile]
  );
  const renderMobileFileIcon = useCallback((file: { id: string; name: string; size: number; status: string }) => (
    <FileFormatIcon
      file={files[file.id]}
      iconClassName="h-8 w-8"
      fallbackSize={20}
    />
  ), [files]);
  const renderMobileComposerFileIcon = useCallback((file: { id: string; name: string; selected: boolean }) => (
    <FileFormatIcon
      file={files[file.id]}
      iconClassName="h-4 w-4"
      fallbackSize={14}
    />
  ), [files]);
  const mobileCurrentFileHasReport = useMemo(
    () => Boolean(mobileCurrentFile && hasAnalysisReportForFile(mobileCurrentFile.id)),
    [hasAnalysisReportForFile, mobileCurrentFile]
  );
  const isMobileHomeLanding = mobileView === 'home' && messages.length === 0 && fileList.length === 0;

  const openMobileWorkbenchView = useCallback((nextView: MobileWorkbenchView, mode?: PreviewPaneMode) => {
    const nextFile = selectedFile ?? fileList[0] ?? null;
    if (!nextFile) {
      setShowUtilityDrawer(true);
      return;
    }

    if (selectedFile?.id !== nextFile.id) {
      setSelectedFileId(nextFile.id);
    }

    if (mode) {
      setPreviewPaneMode(mode);
    }
    setShowPreviewPanel(true);
    resetPreviewViewport();
    setShowUtilityDrawer(false);
    setMobileView(nextView);
  }, [fileList, resetPreviewViewport, selectedFile]);

  const closeMobileWorkbenchView = useCallback(() => {
    setMobileView('home');
    setShowPreviewPanel(false);
    clearReportEditingState();
  }, [clearReportEditingState]);

  useEffect(() => {
    if (mobileView === 'home') return;
    if (!mobileCurrentFile) {
      setMobileView('home');
      setShowPreviewPanel(false);
      return;
    }
    if (mobileView === 'report' && !hasAnalysisReportForFile(mobileCurrentFile.id)) {
      setMobileView('home');
      setShowPreviewPanel(false);
    }
  }, [hasAnalysisReportForFile, mobileCurrentFile, mobileView]);

  if (mobileView !== 'home') {
    const mobileTaskTitle = mobileView === 'report' ? '分析/提取报告' : '文档预览';

    return (
      <div
        ref={workbenchRootRef}
        className="fixed inset-0 z-[100] flex flex-col overflow-hidden bg-[linear-gradient(180deg,#eef3fb_0%,#f6f9fe_56%,#edf3fb_100%)] dark:bg-[linear-gradient(180deg,#020617_0%,#0f172a_44%,#020617_100%)]"
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(96,165,250,0.14),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(34,211,238,0.08),_transparent_24%)]" />

        <div className="relative z-20 shrink-0 border-b border-slate-200/60 bg-white/95 px-4 py-3 backdrop-blur-xl dark:border-slate-800/80 dark:bg-slate-950/95 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                onClick={closeMobileWorkbenchView}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-50 text-slate-600 transition-colors hover:bg-slate-100 active:bg-slate-200 dark:bg-slate-900/60 dark:text-slate-300 dark:hover:bg-slate-800"
                title="返回对话工作台"
                aria-label="返回对话工作台"
              >
                <ChevronLeft size={22} strokeWidth={2.5} className="-ml-0.5" />
              </button>
              <div className="min-w-0">
                <p className="text-[12px] font-bold tracking-wider text-slate-500 dark:text-slate-400">{mobileTaskTitle}</p>
                <h2 className="truncate text-[17px] font-black tracking-tight text-slate-800 dark:text-slate-100">{mobileCurrentFile?.name || '未知文件'}</h2>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {mobileView === 'preview' && mobileCurrentFile ? (
                <button
                  type="button"
                  onClick={() => downloadFile(previewedFile ?? mobileCurrentFile)}
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-cyan-50 text-cyan-600 transition-colors hover:bg-cyan-100 active:bg-cyan-200 dark:bg-cyan-900/30 dark:text-cyan-400 dark:hover:bg-cyan-900/50"
                  title="下载当前文件"
                  aria-label="下载当前文件"
                >
                  <Download size={18} strokeWidth={2.5} />
                </button>
              ) : null}
              {mobileView === 'report' && mobileCurrentFile ? (
                <button
                  type="button"
                  onClick={() => { void downloadEditedReport(mobileCurrentFile); }}
                  disabled={!getEditableReportTextForFile(mobileCurrentFile.id)?.trim() || reportDownloadBusy}
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-cyan-50 text-cyan-600 transition-colors hover:bg-cyan-100 active:bg-cyan-200 disabled:opacity-50 disabled:cursor-not-allowed dark:bg-cyan-900/30 dark:text-cyan-400 dark:hover:bg-cyan-900/50"
                  title="下载报告"
                  aria-label="下载报告"
                >
                  {reportDownloadBusy ? <Loader size={18} strokeWidth={2.5} className="animate-spin" /> : <Download size={18} strokeWidth={2.5} />}
                </button>
              ) : null}
            </div>
          </div>
        </div>

        <div className="relative z-10 min-h-0 flex-1 overflow-hidden bg-white dark:bg-slate-950">
            {mobileView === 'preview' ? (
              <MobilePreviewPage
                currentFile={previewedFile}
                mode={effectivePreviewPaneMode === 'report' ? 'current' : effectivePreviewPaneMode}
                canPreviewOriginal={canPreviewOriginal}
                canComparePreview={canComparePreview}
                isPreviewPdf={isPreviewPdf}
                canTransformPreview={canTransformPreview}
                pdfPage={pdfPage}
                maxPdfPage={maxPdfPage}
                pdfPageInput={pdfPageInput}
                scale={scale}
                secondaryButtonClassName={METALLIC_SECONDARY_BUTTON_CLASS}
                secondaryActiveButtonClassName={METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS}
                onSwitchMode={(mode) => setPreviewPaneMode(mode)}
                onPdfPageInputChange={setPdfPageInput}
                onPdfPageInputCommit={commitPdfPageInput}
                onNavigatePdfPage={navigateToPdfPage}
                onZoomOut={handleZoomOut}
                onZoomIn={handleZoomIn}
                onRotate={handleRotate}
                onResetView={handleResetView}
                body={
                  !mobileCurrentFile ? (
                    <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                      <img src={CustomDocIconImage} alt="Document" className="mb-4 h-14 w-14 object-contain opacity-50 drop-shadow-sm" />
                      <h3 className="text-lg font-semibold text-[#274768] dark:text-slate-200">当前没有可预览文件</h3>
                      <p className="mt-2 max-w-md text-sm leading-6 text-[#6b8198] dark:text-slate-400">
                        先上传文件，或者从工具抽屉里切换到一份已有文件。
                      </p>
                    </div>
                  ) : effectivePreviewPaneMode === 'compare' && canComparePreview && comparisonFile ? (
                    <div className="grid h-full min-h-0 grid-cols-1 gap-2 overflow-auto sm:grid-cols-2">
                      <div className={`min-h-[280px] overflow-auto rounded-[24px] p-2 ${METALLIC_PANEL_CLASS}`}>
                        <div className="mb-3 flex items-center justify-between">
                          <span className={`rounded-full px-3 py-1 text-xs font-medium ${METALLIC_SECONDARY_ACTIVE_BUTTON_CLASS}`}>修改后</span>
                          <span className="text-xs text-[#6c8197] dark:text-slate-400">{mobileCurrentFile.name}</span>
                        </div>
                        {isPreviewPdf && previewPdfSource ? (
                          <PdfScrollPreview
                            key={`${mobileCurrentFile.id}-compare-modified-scroll`}
                            fileSource={previewPdfSource}
                            fileName={mobileCurrentFile.name}
                            scale={scale}
                            rotation={rotation}
                            maxWidth={580}
                            initialPage={pdfPage}
                            scrollRequest={pdfScrollRequest}
                            onVisiblePageChange={(page) => {
                              setPdfPage((prev) => (prev === page ? prev : page));
                            }}
                            onLoadSuccess={handlePrimaryPdfLoadSuccess}
                          />
                        ) : isPreviewImage && previewUrl ? (
                          <div className="flex min-h-[320px] items-center justify-center overflow-auto rounded-[22px] bg-[#f8fbff] p-2 dark:bg-slate-950/40">
                            <img
                              src={previewUrl}
                              alt={mobileCurrentFile.name}
                              className="max-h-full max-w-full rounded-[24px] object-contain shadow-[0_25px_70px_-30px_rgba(15,23,42,0.55)]"
                              style={{ transform: `scale(${scale}) rotate(${rotation}deg)` }}
                            />
                          </div>
                        ) : (
                          <div className={`flex min-h-[320px] items-center justify-center rounded-[22px] px-6 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                            <span className="text-sm text-[#6b8198] dark:text-slate-400">当前格式暂不支持移动端并排对比。</span>
                          </div>
                        )}
                      </div>
                      <div className={`min-h-[280px] overflow-auto rounded-[24px] p-2 ${METALLIC_PANEL_CLASS}`}>
                        <div className="mb-3 flex items-center justify-between">
                          <span className={`rounded-full px-3 py-1 text-xs font-medium ${METALLIC_PREVIEW_TAG_CLASS}`}>原文件</span>
                          <span className="text-xs text-[#6c8197] dark:text-slate-400">{comparisonFile.name}</span>
                        </div>
                        {isPreviewPdf && comparisonPdfSource ? (
                          <PdfScrollPreview
                            key={`${comparisonFile.id}-compare-original-scroll`}
                            fileSource={comparisonPdfSource}
                            fileName={comparisonFile.name}
                            scale={scale}
                            rotation={rotation}
                            maxWidth={580}
                            initialPage={pdfPage}
                            scrollRequest={pdfScrollRequest}
                            onVisiblePageChange={(page) => {
                              setPdfPage((prev) => (prev === page ? prev : page));
                            }}
                            onLoadSuccess={handleComparisonPdfLoadSuccess}
                          />
                        ) : comparisonPreviewUrl ? (
                          <div className="flex min-h-[320px] items-center justify-center overflow-auto rounded-[22px] bg-[#f8fbff] p-2 dark:bg-slate-950/40">
                            <img
                              src={comparisonPreviewUrl}
                              alt={comparisonFile.name}
                              className="max-h-full max-w-full rounded-[24px] object-contain shadow-[0_25px_70px_-30px_rgba(15,23,42,0.55)]"
                              style={{ transform: `scale(${scale}) rotate(${rotation}deg)` }}
                            />
                          </div>
                        ) : (
                          <div className={`flex min-h-[320px] items-center justify-center rounded-[22px] px-6 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                            <span className="text-sm text-[#6b8198] dark:text-slate-400">当前格式暂不支持移动端并排对比。</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : previewedFile?.status === 'processing' ? (
                    <div className={`flex h-full flex-col items-center justify-center rounded-[26px] ${METALLIC_EMPTY_STATE_CLASS}`}>
                      <Loader size={42} className="mb-4 animate-spin text-[#6a89a8]" />
                      <p className="text-lg font-medium text-[#274768] dark:text-slate-100">正在准备预览</p>
                    </div>
                  ) : isDocxAwaitingFidelity ? (
                    <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                      <Loader size={30} className="mb-4 animate-spin text-[#6a89a8]" />
                      <p className="text-lg font-medium text-[#274768] dark:text-slate-100">正在将 Word 转为 PDF 预览</p>
                    </div>
                  ) : isDocxPreviewFailed ? (
                    <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                      <AlertCircle size={30} className="mb-4 text-amber-500" />
                      <p className="text-lg font-medium text-[#274768] dark:text-slate-100">Word 转 PDF 失败</p>
                      <p className="mt-2 text-sm text-[#6b8198] dark:text-slate-400">{previewedFile?.error || WORD_PREVIEW_FALLBACK_MESSAGE}</p>
                    </div>
                  ) : isPreviewPdf && previewPdfSource ? (
                    <div className="relative flex h-full min-h-0 w-full overflow-hidden bg-white dark:bg-slate-950">
                      {usesPagedPdfPreview ? (
                        <PdfPagedPreview
                          fileSource={previewPdfSource}
                          fileName={previewedFileName}
                          pageNumber={pdfPage}
                          scale={scale}
                          rotation={rotation}
                          maxWidth={900}
                          onLoadSuccess={handlePrimaryPdfLoadSuccess}
                        />
                      ) : (
                        <PdfScrollPreview
                          key={`${previewedFile?.id ?? 'preview'}-mobile-scroll`}
                          fileSource={previewPdfSource}
                          fileName={previewedFileName}
                          scale={scale}
                          rotation={rotation}
                          maxWidth={820}
                          initialPage={pdfPage}
                          scrollRequest={pdfScrollRequest}
                          onVisiblePageChange={(page) => {
                            setPdfPage((prev) => (prev === page ? prev : page));
                          }}
                          onLoadSuccess={handlePrimaryPdfLoadSuccess}
                        />
                      )}
                    </div>
                  ) : isPreviewImage && previewUrl ? (
                    <div className="flex h-full items-center justify-center overflow-auto rounded-[24px] bg-white/70 p-2 dark:bg-slate-950/50">
                      <img
                        src={previewUrl}
                        alt={previewedFileName}
                        className="max-h-full max-w-full rounded-[24px] border border-white/70 object-contain shadow-[0_25px_70px_-30px_rgba(15,23,42,0.55)]"
                        style={{ transform: `scale(${scale}) rotate(${rotation}deg)` }}
                      />
                    </div>
                  ) : isPreviewText ? (
                    <div className="h-full overflow-auto rounded-[24px] p-2">
                      <div
                        className={`mx-auto max-w-none rounded-[24px] px-4 py-4 ${METALLIC_PANEL_SOFT_CLASS}`}
                        style={{ transform: `scale(${scale}) rotate(${rotation}deg)`, transformOrigin: 'top center' }}
                      >
                        <pre className="whitespace-pre-wrap break-words text-sm leading-7 text-[#284665] dark:text-slate-200">
                          {previewText || '文本预览加载中...'}
                        </pre>
                      </div>
                    </div>
                  ) : isPreviewExcel && previewedFile ? (
                    <div className="h-full">
                      <ExcelPreview file={previewedFile} />
                    </div>
                  ) : (
                    <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${METALLIC_EMPTY_STATE_CLASS}`}>
                      <img src={CustomDocIconImage} alt="Document" className="mb-4 h-14 w-14 object-contain opacity-50 drop-shadow-sm" />
                      <h3 className="text-lg font-semibold text-[#274768] dark:text-slate-200">当前格式暂不支持浏览器内预览</h3>
                      <p className="mt-2 max-w-md text-sm leading-6 text-[#6b8198] dark:text-slate-400">
                        {previewedFile?.name || '该文件'} 可以下载后在本地继续查看。
                      </p>
                    </div>
                  )
                }
              />
            ) : (
              <MobileReportPage
                currentFileId={mobileCurrentFile?.id ?? null}
                currentFileName={mobileCurrentFile?.name ?? null}
                hasReport={Boolean(mobileCurrentFile && hasAnalysisReportForFile(mobileCurrentFile.id))}
                emptyStateClassName={METALLIC_EMPTY_STATE_CLASS}
                panelSoftClassName={METALLIC_PANEL_SOFT_CLASS}
                activeStatus={activeReportProgress?.status}
                blocks={preparedEditableReport.blocks}
                formatting={selectedReportFormatting}
                toneStyles={REPORT_TONE_STYLES[preparedEditableReport.visualTone] ?? REPORT_TONE_STYLES.analysis}
                streamHighlightNonce={reportStreamHighlightNonce}
                reportContentRef={reportContentRef}
                reportPreviewScrollRef={reportPreviewScrollRef}
                selection={reportSelection}
                busyAction={reportBusyAction}
                canUndo={canUndoReportEdit}
                manualEditOpen={reportManualEditOpen}
                manualEditValue={reportManualEditValue}
                manualEditBusy={reportManualEditBusy}
                toolbarFeedback={reportToolbarFeedback}
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
                  setReportManualEditValue(reportSelection?.selectedText ?? '');
                }}
                onTextColorChange={handleApplyReportTextColor}
                onFontSizeChange={handleApplyReportFontSize}
                onBlockTypeChange={handleApplyReportBlockType}
                onTextAlignChange={handleApplyReportTextAlign}
              />
            )}
          </div>
        </div>
    );
  }

  return (
    <div
      ref={workbenchRootRef}
      className="relative h-[100dvh] w-full overflow-hidden bg-[#F4FBFB] pb-[env(safe-area-inset-bottom)] dark:bg-slate-950"
      onDragEnter={handleDocumentDragEnter}
      onDragOver={handleDocumentDragOver}
      onDragLeave={handleDocumentDragLeave}
      onDrop={handleDocumentDrop}
    >
      <div className="relative z-10 flex h-full flex-col">
        <div className="shrink-0 px-4 py-3 pb-2 pt-[max(12px,env(safe-area-inset-top))] transition-all duration-300 bg-transparent">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              {onBack && (
                <button
                  type="button"
                  onClick={onBack}
                  className="flex h-8 w-8 -ml-2 items-center justify-center rounded-full text-slate-700 transition-all active:scale-95 dark:text-slate-300"
                >
                  <ChevronLeft size={24} strokeWidth={2.5} />
                </button>
              )}
              <h2 className="truncate text-[22px] font-black tracking-tight text-slate-800 dark:text-slate-100">AI文档处理</h2>
            </div>
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => setShowUtilityDrawer(true)}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-50 text-slate-500 transition-all hover:bg-slate-100 active:scale-95 dark:bg-slate-800/80 dark:text-slate-400 dark:hover:bg-slate-700/80"
                title="打开工具抽屉"
                aria-label="打开工具抽屉"
              >
                <Layers size={18} strokeWidth={2.5} />
              </button>
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
          {isMobileHomeLanding ? (
            <div className="flex min-h-[60vh] w-full flex-col items-center justify-center px-4 pt-12 pb-8">
              {/* Logo / Ring */}
              <div className="mb-6 flex items-center justify-center relative animate-fade-in-up" style={{ animationDuration: '0.8s', animationFillMode: 'both' }}>
                <div className="absolute h-[90px] w-[90px] rounded-full bg-white blur-lg dark:bg-white/30 animate-pulse-slow"></div>
                <div className="relative z-10 flex h-[72px] w-[72px] items-center justify-center">
                  <img src={AppLogoImage} alt="App Logo" className="h-[64px] w-[64px] object-contain" />
                </div>
              </div>

              {/* Title */}
              <div className="mb-4 flex flex-col items-center">
                <h3 className="text-[22px] font-bold tracking-tight text-slate-800 dark:text-slate-100 overflow-hidden whitespace-nowrap border-r-[3px] border-slate-800/40 dark:border-slate-100/40 animate-typing-text pr-1" style={{ animationDuration: '1.2s', animationDelay: '0.2s', animationFillMode: 'both', width: 'max-content' }}>
                  今天想处理什么文档？
                </h3>
                <p className="mt-2 text-[14px] text-slate-500 dark:text-slate-400 animate-fade-in-up" style={{ animationDuration: '0.8s', animationDelay: '1.4s', animationFillMode: 'both' }}>
                  点击问问看
                </p>
              </div>

              {/* Shortcuts */}
              <div className="w-full max-w-[340px] flex flex-col items-center space-y-3.5 animate-fade-in-up" style={{ animationDuration: '0.8s', animationDelay: '0.6s', animationFillMode: 'both' }}>
                <button
                  type="button"
                  onClick={() => setInputText('总结该文档重点')}
                  className="group relative flex w-fit items-center justify-center gap-2.5 rounded-full bg-white px-5 py-3 shadow-[0_2px_8px_rgba(0,0,0,0.04)] ring-1 ring-slate-100 transition-all active:scale-[0.98] active:bg-slate-50 dark:bg-slate-800 dark:ring-white/10 dark:active:bg-slate-700"
                >
                  <div className="absolute inset-0 rounded-full opacity-0 transition-opacity group-active:opacity-100 bg-gradient-to-r from-violet-500/5 to-fuchsia-500/5 dark:from-violet-400/10 dark:to-fuchsia-400/10" />
                  <span className="relative z-10 text-[18px] opacity-90">💡</span>
                  <span className="relative z-10 text-[15px] font-normal text-[#1f2329] dark:text-slate-200">总结该文档重点</span>
                  <ArrowRight size={16} className="relative z-10 ml-0.5 text-[#8f959e] transition-transform group-active:translate-x-1 dark:text-slate-500" strokeWidth={1.5} />
                </button>
                <button
                  type="button"
                  onClick={() => setInputText('提取文件关键信息')}
                  className="group relative flex w-fit items-center justify-center gap-2.5 rounded-full bg-white px-5 py-3 shadow-[0_2px_8px_rgba(0,0,0,0.04)] ring-1 ring-slate-100 transition-all active:scale-[0.98] active:bg-slate-50 dark:bg-slate-800 dark:ring-white/10 dark:active:bg-slate-700"
                >
                  <div className="absolute inset-0 rounded-full opacity-0 transition-opacity group-active:opacity-100 bg-gradient-to-r from-blue-500/5 to-cyan-500/5 dark:from-blue-400/10 dark:to-cyan-400/10" />
                  <span className="relative z-10 text-[18px] opacity-90">📄</span>
                  <span className="relative z-10 text-[15px] font-normal text-[#1f2329] dark:text-slate-200">提取文件关键信息</span>
                  <ArrowRight size={16} className="relative z-10 ml-0.5 text-[#8f959e] transition-transform group-active:translate-x-1 dark:text-slate-500" strokeWidth={1.5} />
                </button>
                <button
                  type="button"
                  onClick={() => setInputText('检查文件里面体现了什么风险')}
                  className="group relative flex w-fit items-center justify-center gap-2.5 rounded-full bg-white px-5 py-3 shadow-[0_2px_8px_rgba(0,0,0,0.04)] ring-1 ring-slate-100 transition-all active:scale-[0.98] active:bg-slate-50 dark:bg-slate-800 dark:ring-white/10 dark:active:bg-slate-700"
                >
                  <div className="absolute inset-0 rounded-full opacity-0 transition-opacity group-active:opacity-100 bg-gradient-to-r from-emerald-500/5 to-teal-500/5 dark:from-emerald-400/10 dark:to-teal-400/10" />
                  <span className="relative z-10 text-[18px] opacity-90">🛡️</span>
                  <span className="relative z-10 text-[15px] font-normal text-[#1f2329] dark:text-slate-200">检查文件里面体现了什么风险</span>
                  <ArrowRight size={16} className="relative z-10 ml-0.5 text-[#8f959e] transition-transform group-active:translate-x-1 dark:text-slate-500" strokeWidth={1.5} />
                </button>
              </div>
            </div>
          ) : null}

          {!isMobileHomeLanding && mobileCurrentFile ? (
            <MobileCurrentFileCard
              currentFile={mobileCurrentFile}
              hasReport={mobileCurrentFileHasReport}
              formatFileSize={formatFileSize}
              renderFileIcon={renderMobileFileIcon}
              onOpenPreview={() => openMobileWorkbenchView('preview', 'current')}
              onOpenReport={() => openMobileWorkbenchView('report', 'report')}
              primaryButtonClassName={COBALT_GLASS_BUTTON_CLASS}
              secondaryButtonClassName={METALLIC_SECONDARY_BUTTON_CLASS}
              softPanelClassName={METALLIC_PANEL_SOFT_CLASS}
            />
          ) : null}

          <MobileMessageList
            messages={messages}
            filesById={files}
            streamingAssistantMessageId={streamingAssistantMessageId}
            messagesViewportRef={messagesViewportRef}
            messagesEndRef={messagesEndRef}
            onScroll={handleMessagesScroll}
            onOpenReportFile={(fileId) => {
              handleSelectFile(fileId);
              setPreviewPaneMode('report');
              setShowPreviewPanel(true);
              setMobileView('report');
              resetPreviewViewport();
            }}
            renderFileIcon={renderMobileFileIcon}
            followUpItems={visibleFollowUpSuggestions}
            showFollowUpSuggestions={Boolean(latestAssistantMessageWithSuggestions) && streamingAssistantMessageId === null}
            showBatchSwitcher={hasMultipleFollowUpSuggestionBatches}
            onRotateSuggestions={cycleFollowUpSuggestions}
            onPickSuggestion={(prompt) => { void sendMessage(prompt); }}
            disabled={isLoading}
          />
          
          {/* 为悬浮输入框留出安全的底部滚动空间 */}
          <div className="h-[120px] shrink-0 pointer-events-none" />
        </div>

        <MobileComposer
          files={composerFiles.map((file) => ({
            id: file.id,
            name: file.name,
            selected: selectedFileId === file.id,
          }))}
          inputText={inputText}
          placeholder={mobileCurrentFile ? composerPlaceholder : initialLandingPlaceholder}
          disabled={isLoading}
          textareaRef={composerTextareaRef}
          secondaryButtonClassName={METALLIC_SECONDARY_BUTTON_CLASS}
          primaryButtonClassName={COBALT_GLASS_BUTTON_CLASS}
          renderFileIcon={renderMobileComposerFileIcon}
          onSelectFile={handleSelectFile}
          onRemoveFile={removeComposerFile}
          onInputChange={setInputText}
          onKeyPress={handleKeyPress}
          onUpload={triggerFileInput}
          onOpenUtilityDrawer={() => setShowUtilityDrawer(true)}
          onStop={stopGeneration}
          onSend={() => {
            void sendMessage();
          }}
        />

        <MobileUtilityDrawer
          visible={showUtilityDrawer}
          fileCount={fileList.length}
          conversationCount={orderedConversations.length}
          files={fileList}
          conversations={orderedConversations.map((conversation) => ({
            id: conversation.id,
            title: conversation.title,
            preview: getConversationPreviewText(conversation.messages),
            active: conversation.id === activeConversationId,
          }))}
          selectedFileId={selectedFileId}
          emptyStateClassName={METALLIC_EMPTY_STATE_CLASS}
          primaryButtonClassName={COBALT_GLASS_BUTTON_CLASS}
          secondaryButtonClassName={METALLIC_SECONDARY_BUTTON_CLASS}
          renderFileIcon={renderMobileFileIcon}
          formatFileSize={formatFileSize}
          onClose={() => setShowUtilityDrawer(false)}
          onSelectFile={(fileId) => {
            handleSelectFile(fileId);
            setShowUtilityDrawer(false);
          }}
          onSelectConversation={(conversationId) => {
            activateConversation(conversationId);
            setShowUtilityDrawer(false);
          }}
        />
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
