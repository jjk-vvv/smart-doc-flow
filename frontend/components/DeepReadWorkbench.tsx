import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  Braces,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  PlayCircle,
  ScanLine,
  Trash2,
  UploadCloud,
  File,
  Settings,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCw,
  Maximize,
  X,
  Search,
  Plus,
  LocateFixed,
  Bot,
  Sparkles,
  Send,
  HelpCircle
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import {
  readExtractionDocuments,
  writeExtractionDocuments,
  type ExtractionDocument,
  type ExtractionEntity,
  type TraceHit,
} from '../lib/extractionStore';
import { LuckysheetPreview } from './LuckysheetPreview';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type DocumentResult = ExtractionDocument;

type ExtractResponse = {
  documents: DocumentResult[];
};

type SummarizeResponse = {
  summary: string;
};

type TraceLocateResponse = {
  hit_count: number;
  truncated: boolean;
  hits: TraceHit[];
};

type AssistantQueryResponse = {
  ok: boolean;
  answer: string;
  summary_used: string;
  matched_fields: Array<{
    field_name: string;
    label: string;
    value: unknown;
    confidence: number;
    source_ref_id?: string | null;
    page?: number | null;
    bbox?: number[];
  }>;
  matched_trace_hits: TraceHit[];
  persisted: boolean;
  persisted_rows: number;
  warnings: string[];
};

type FieldItem = {
  key: string;
  label: string;
  valueText: string;
  confidence: number;
  refId?: string | null;
  bbox: number[];
  pageNumber: number | null;
};

type AssistantDialogMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

const DEFAULT_SCHEMA = {
  auto_infer: true,
  prefer_llm: true,
  max_auto_fields: 12,
};

type OfficePreviewState = {
  status: 'idle' | 'queued' | 'running' | 'completed' | 'failed';
  jobId?: string;
  pdfUrl?: string;
  error?: string;
};

const ALLOWED_EXTENSIONS = new Set(['pdf', 'doc', 'docx', 'xlsx', 'txt', 'md', 'png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff']);
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff']);

const isAllowedFile = (file: File) => {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  return ALLOWED_EXTENSIONS.has(ext);
};

const fileExt = (name: string) => name.split('.').pop()?.toLowerCase() ?? '';
const fileIdentityKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;

const toPageNumber = (bbox: number[]) => {
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
  // Heuristic normalization for different coordinate systems
  const maxVal = Math.max(x + w, y + h);

  if (maxVal <= 1.5) {
    // Normalized 0-1 coordinates
    return {
      x: x * 100,
      y: y * 100,
      w: w * 100,
      h: h * 100,
    };
  }

  if (maxVal <= 100) {
    // Already percent?
    return { x, y, w, h };
  }

  // A4 standard points (approx)
  return {
    x: (x / 595) * 100,
    y: (y / 842) * 100,
    w: (w / 595) * 100,
    h: (h / 842) * 100,
  };
};

const hasMeaningfulBox = (bbox: number[]) => {
  if (!Array.isArray(bbox) || bbox.length !== 5) return false;
  const [, x, y, w, h] = bbox.map((n) => Number(n));
  if (![x, y, w, h].every((n) => Number.isFinite(n))) return false;
  if (w <= 0 || h <= 0) return false;
  // Avoid fake full-page placeholders: [1, 0, 0, 1, 1]
  if (x <= 0.0001 && y <= 0.0001 && w >= 0.995 && h >= 0.995) return false;
  return true;
};

const toFieldLabel = (name: string) =>
  (
    {
      contract_amount: '合同金额',
      start_date: '开始日期',
      end_date: '结束日期',
      tax_rate: '税率',
      region: '地区',
      invoice_number: '发票号码',
      invoice_date: '开票日期',
      buyer_name: '购买方名称',
      seller_name: '销售方名称',
      total_amount: '合计金额',
    } as Record<string, string>
  )[name] ?? name;

const toTraceHits = (doc: DocumentResult | null, fieldKey?: string | null): TraceHit[] => {
  if (!doc || !Array.isArray(doc.trace_hits)) return [];
  const key = (fieldKey || '').trim().toLowerCase();
  const out = doc.trace_hits.filter((hit) => {
    if (!hit || typeof hit !== 'object') return false;
    const objectType = String(hit.object_type || '');
    if (!objectType) return false;
    if (!key) return true;
    const objectId = String(hit.object_id || '').toLowerCase();
    const snippet = String(hit.snippet || '').toLowerCase();
    return objectId === key || snippet.includes(`${key}:`);
  });
  return out.sort((a, b) => Number(b.confidence || 0) - Number(a.confidence || 0));
};

const toTraceHitKey = (hit: TraceHit, idx: number) =>
  `${String(hit.object_type || 'trace')}:${String(hit.object_id || '')}:${String(hit.ref_id || '')}:${idx}`;

const toTracePage = (hit: TraceHit): number => {
  const pageRaw = Number(hit.page || 0);
  if (Number.isFinite(pageRaw) && pageRaw > 0) return Math.round(pageRaw);
  const bbox = Array.isArray(hit.bbox) ? hit.bbox : [];
  if (bbox.length === 5) {
    const p = Number(bbox[0] || 0);
    if (Number.isFinite(p) && p > 0) return Math.round(p);
  }
  const locator = (hit.locator ?? {}) as Record<string, unknown>;
  const locatorPage = Number(locator.page ?? 0);
  return Number.isFinite(locatorPage) && locatorPage > 0 ? Math.round(locatorPage) : 0;
};

const resolveArtifactUrl = (hit: TraceHit): string => {
  const direct = String(hit.artifact_url || '').trim();
  if (direct) return direct;
  const pathRaw = String(hit.artifact_path || '').trim();
  if (!pathRaw) return '';
  const normalized = pathRaw.replace(/\\/g, '/');
  const encoded = normalized
    .split('/')
    .filter(Boolean)
    .map((seg) => encodeURIComponent(seg))
    .join('/');
  return encoded ? `/extract/artifact/${encoded}` : '';
};

export const DeepReadWorkbench: React.FC<{ isSidebarCollapsed?: boolean }> = ({ isSidebarCollapsed = false }) => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [schemaText, setSchemaText] = useState<string>(JSON.stringify(DEFAULT_SCHEMA, null, 2));
  const [documents, setDocuments] = useState<DocumentResult[]>([]);
  const [activeDocIndex, setActiveDocIndex] = useState(0);
  const [activeFieldKey, setActiveFieldKey] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [infoMessage, setInfoMessage] = useState("每批最多上传 5 个文件。");
  const [activeSummaryText, setActiveSummaryText] = useState('');
  const [activeSummaryLoading, setActiveSummaryLoading] = useState(false);
  const [summaryDocName, setSummaryDocName] = useState('');
  const [traceHits, setTraceHits] = useState<TraceHit[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState('');
  const [assistantStatus, setAssistantStatus] = useState<'idle' | 'confirmed' | 'rolled_back'>('idle');
  const [assistantMessage, setAssistantMessage] = useState("等待生成可执行建议。");
  const [assistantInput, setAssistantInput] = useState('');
  const [assistantQueryLoading, setAssistantQueryLoading] = useState(false);
  const [assistantAnswer, setAssistantAnswer] = useState('');
  const [assistantWarnings, setAssistantWarnings] = useState<string[]>([]);
  const [assistantDialog, setAssistantDialog] = useState<AssistantDialogMessage[]>([]);
  const [showAssistantHelp, setShowAssistantHelp] = useState(false);
  const [showSchema, setShowSchema] = useState(false); // UI Toggle
  
  // Viewport Controls
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [activeTraceKey, setActiveTraceKey] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textPreviewRef = useRef<HTMLDivElement>(null);
  const assistantDialogRef = useRef<HTMLDivElement>(null);
  const summaryRequestSeqRef = useRef(0);
  const traceRequestSeqRef = useRef(0);

  const activeDoc = documents[activeDocIndex] ?? null;
  const activeSourceFile = useMemo(() => {
    // Priority 1: Match activeDoc if it exists
    if (activeDoc && selectedFiles.length > 0) {
      const exact = selectedFiles.find((file) => file.name === activeDoc.file_name);
      if (exact) return exact;

      const targetName = activeDoc.file_name.toLowerCase();
      const insensitive = selectedFiles.find((file) => file.name.toLowerCase() === targetName);
      if (insensitive) return insensitive;

      const byIndex = selectedFiles[activeDocIndex] ?? null;
      if (byIndex && fileExt(byIndex.name) === fileExt(activeDoc.file_name)) return byIndex;

      return byIndex;
    }

    // Priority 2: Fallback to selectedFiles based on index (Pre-extraction preview)
    if (!activeDoc && selectedFiles.length > 0) {
      return selectedFiles[activeDocIndex] ?? selectedFiles[0];
    }

    return null;
  }, [activeDoc, activeDocIndex, selectedFiles]);
  const activeExt = activeSourceFile ? fileExt(activeSourceFile.name) : (activeDoc ? fileExt(activeDoc.file_name) : '');
  const activeDisplayName = activeDoc?.file_name || activeSourceFile?.name || '当前文档';
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string>('');
  const [officePreviewMap, setOfficePreviewMap] = useState<Record<string, OfficePreviewState>>({});
  const [pdfPage, setPdfPage] = useState(1);
  const assistantActionable = useMemo(
    () => Boolean(activeDoc && (((activeDoc.errors?.length ?? 0) > 0) || ((activeDoc.soft_warnings?.length ?? 0) > 0))),
    [activeDoc]
  );
  const showLeftPanel = selectedFiles.length > 0 || documents.length > 0;
  const activeOfficePreview = useMemo(() => {
    if (!activeSourceFile) return null;
    return officePreviewMap[fileIdentityKey(activeSourceFile)] || null;
  }, [activeSourceFile, officePreviewMap]);
  const activeDocPreviewPdfUrl = useMemo(() => {
    const val = String(activeDoc?.diagnostics?.office_pdf_preview_url || '').trim();
    return val || '';
  }, [activeDoc?.diagnostics]);
  const activeConvertedPdfUrl = useMemo(() => {
    const fromUpload = String(activeOfficePreview?.pdfUrl || '').trim();
    if (fromUpload) return fromUpload;
    return activeDocPreviewPdfUrl;
  }, [activeOfficePreview?.pdfUrl, activeDocPreviewPdfUrl]);
  const activeRenderExt = useMemo(() => {
    if ((activeExt === 'doc' || activeExt === 'docx') && activeConvertedPdfUrl) return 'pdf';
    return activeExt;
  }, [activeExt, activeConvertedPdfUrl]);

  useEffect(() => {
    const cached = readExtractionDocuments();
    if (cached.length === 0) return;
    setDocuments(cached);
    setInfoMessage(`已加载 ${cached.length} 条本地缓存抽取结果。`);
  }, []);

  useEffect(() => {
    if (documents.length === 0) {
      setActiveDocIndex(0);
      return;
    }
    if (activeDocIndex > documents.length - 1) {
      setActiveDocIndex(documents.length - 1);
    }
  }, [activeDocIndex, documents]);

  useEffect(() => {
    setPdfPage(1);
  }, [activeDoc?.file_hash]);

  useEffect(() => {
    if (!activeSourceFile) {
      if (activeConvertedPdfUrl && (activeExt === 'doc' || activeExt === 'docx')) {
        setPreviewUrl(activeConvertedPdfUrl);
      } else {
        setPreviewUrl(null);
      }
      return;
    }
    if ((activeExt === 'doc' || activeExt === 'docx') && activeConvertedPdfUrl) {
      setPreviewUrl(activeConvertedPdfUrl);
      return;
    }
    const url = URL.createObjectURL(activeSourceFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [activeSourceFile, activeExt, activeConvertedPdfUrl]);

  useEffect(() => {
    let cancelled = false;
    if (!activeSourceFile) {
      setPreviewText('');
      return () => {
        cancelled = true;
      };
    }

    if (['txt', 'md'].includes(activeExt)) {
      activeSourceFile.text().then((text) => {
        if (cancelled) return;
        const maxChars = 12000;
        setPreviewText(text.length > maxChars ? `${text.slice(0, maxChars)}\n\n...【内容已截断】` : text);
      });
      return () => {
        cancelled = true;
      };
    }

    setPreviewText('');
    return () => {
      cancelled = true;
    };
  }, [activeSourceFile, activeExt]);

  const activeTraceHit = useMemo(() => {
    if (!activeTraceKey) return null;
    const idx = traceHits.findIndex((hit, i) => toTraceHitKey(hit, i) === activeTraceKey);
    if (idx < 0) return null;
    return traceHits[idx];
  }, [activeTraceKey, traceHits]);

  const previewHighlight = useMemo(() => {
    if (!['txt', 'md'].includes(activeExt)) return null;
    const sourceText = previewText || '';
    if (!sourceText) return null;
    const rawSnippet = String(activeTraceHit?.snippet || '').split('|')[0].trim();
    const fieldEntity = activeDoc && activeFieldKey ? activeDoc.result?.[activeFieldKey] : null;
    const fieldFallback = fieldEntity?.value == null ? '' : String(fieldEntity.value);
    let keyword = rawSnippet || fieldFallback;
    keyword = keyword.replace(/^[^:：]{1,30}[:：]\s*/, '').trim();
    if (keyword.length < 2) return null;
    if (keyword.length > 64) keyword = keyword.slice(0, 64);

    const lowerText = sourceText.toLowerCase();
    const lowerKeyword = keyword.toLowerCase();
    const start = lowerText.indexOf(lowerKeyword);
    if (start < 0) return null;
    return {
      before: sourceText.slice(0, start),
      hit: sourceText.slice(start, start + keyword.length),
      after: sourceText.slice(start + keyword.length),
    };
  }, [activeExt, previewText, activeTraceHit, activeFieldKey, activeDoc]);

  const xlsxLocatorHint = useMemo(() => {
    if (activeRenderExt !== 'xlsx') return null;
    const locator = (activeTraceHit?.locator ?? {}) as Record<string, unknown>;
    return {
      sheet_index: Number(locator.sheet_index || 0),
      row_index: Number(locator.row_index || 0),
      col_index: Number(locator.col_index || 0),
      sheet_name: String(locator.sheet_name || ''),
    };
  }, [activeRenderExt, activeTraceHit]);

  useEffect(() => {
    if (!previewHighlight || !textPreviewRef.current) return;
    const mark = textPreviewRef.current.querySelector('mark[data-preview-highlight="true"]');
    if (!mark) return;
    mark.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [previewHighlight]);

  useEffect(() => {
    const panel = assistantDialogRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [assistantDialog, assistantQueryLoading]);

  const requestSummary = async (doc: DocumentResult) => {
    if (!doc) return;
    const seq = ++summaryRequestSeqRef.current;
    setSummaryDocName(doc.file_name);
    setActiveSummaryLoading(true);
    try {
      const response = await fetch('/extract/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_name: doc.file_name,
          result: doc.result,
          diagnostics: doc.diagnostics ?? {},
          errors: doc.errors ?? [],
          soft_warnings: doc.soft_warnings ?? [],
          max_chars: 520,
        }),
      });
      if (!response.ok) {
        throw new Error('摘要生成失败');
      }
      const payload = (await response.json()) as SummarizeResponse;
      if (seq !== summaryRequestSeqRef.current) return;
      setActiveSummaryText((payload.summary || "").trim() || "暂无摘要。");
    } catch (error) {
      if (seq !== summaryRequestSeqRef.current) return;
      const fallback = (doc.errors?.[0] ?? '').trim();
      setActiveSummaryText(fallback || "暂时无法生成摘要，请稍后重试。");
    } finally {
      if (seq === summaryRequestSeqRef.current) {
        setActiveSummaryLoading(false);
      }
    }
  };

  const requestTraceHits = async (doc: DocumentResult, fieldKey?: string | null) => {
    if (!doc) return;
    const seq = ++traceRequestSeqRef.current;
    setTraceLoading(true);
    setTraceError('');
    try {
      const response = await fetch('/extract/trace/locate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document: doc,
          field_name: fieldKey || undefined,
          top_k: 40,
        }),
      });
      if (!response.ok) {
        throw new Error('溯源定位失败');
      }
      const payload = (await response.json()) as TraceLocateResponse;
      if (seq !== traceRequestSeqRef.current) return;
      const hits = Array.isArray(payload.hits) ? payload.hits : [];
      setTraceHits(hits.length > 0 ? hits : toTraceHits(doc, fieldKey));
    } catch (error) {
      if (seq !== traceRequestSeqRef.current) return;
      setTraceHits(toTraceHits(doc, fieldKey));
      setTraceError(error instanceof Error ? error.message : '溯源定位失败');
    } finally {
      if (seq === traceRequestSeqRef.current) {
        setTraceLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!activeDoc) {
      setSummaryDocName('');
      setActiveSummaryText('');
      setActiveSummaryLoading(false);
      return;
    }
    void requestSummary(activeDoc);
  }, [activeDoc?.file_hash]);

  useEffect(() => {
    if (!activeDoc) {
      setTraceHits([]);
      setTraceError('');
      setTraceLoading(false);
      setActiveTraceKey('');
      return;
    }
    if (Array.isArray(activeDoc.trace_hits) && activeDoc.trace_hits.length > 0) {
      setTraceHits(toTraceHits(activeDoc, activeFieldKey));
      setTraceError('');
      setTraceLoading(false);
      return;
    }
    void requestTraceHits(activeDoc, activeFieldKey);
  }, [activeDoc?.file_hash, activeFieldKey]);

  useEffect(() => {
    if (!activeDoc) {
      setAssistantStatus('idle');
      setAssistantMessage("等待生成可执行建议。");
      return;
    }
    if (assistantActionable) {
      setAssistantStatus('idle');
      setAssistantMessage("检测到异常或软告警，请确认是否接受当前结果，或执行回滚后重试。");
    } else {
      setAssistantStatus('idle');
      setAssistantMessage("当前批次无需执行变更，结果可直接使用。");
    }
  }, [activeDoc?.file_hash, assistantActionable]);

  useEffect(() => {
    setAssistantInput('');
    setAssistantAnswer('');
    setAssistantWarnings([]);
    setAssistantDialog([]);
    setAssistantQueryLoading(false);
    setOfficePreviewMap({});
    setActiveTraceKey('');
  }, [activeDoc?.file_hash]);

  const fieldItems = useMemo<FieldItem[]>(() => {
    if (!activeDoc) return [];

    const entries = Object.entries(activeDoc.result) as Array<[string, ExtractionEntity]>;
    const meaningful = entries.filter(([, entity]) => {
      if (!entity) return false;
      const value = entity.value;
      if (value == null) return false;
      const text = String(value).trim();
      if (!text || text.toLowerCase() === 'null') return false;
      const conf = Number(entity.confidence ?? 0);
      return Number.isFinite(conf) && conf >= 0.2;
    });

    return meaningful.map(([fieldName, entity]) => ({
      bbox: Array.isArray(entity.bbox) ? entity.bbox : [],
      key: fieldName,
      label: toFieldLabel(fieldName),
      valueText: String(entity.value),
      confidence: entity.confidence ?? 0,
      refId: entity.source_ref_id,
      pageNumber: toPageNumber(Array.isArray(entity.bbox) ? entity.bbox : []),
    }));
  }, [activeDoc]);

  const inferredPdfPageCount = useMemo(() => {
    if (activeRenderExt !== 'pdf') return 1;
    const maxByRefs = fieldItems.reduce((maxPage, item) => {
      if (item.pageNumber == null) return maxPage;
      return Math.max(maxPage, item.pageNumber);
    }, 1);
    const maxByTrace = traceHits.reduce((maxPage, hit) => {
      const page = Number(hit.page || 0);
      if (!Number.isFinite(page) || page < 1) return maxPage;
      return Math.max(maxPage, Math.round(page));
    }, 1);
    return Math.max(1, maxByRefs, maxByTrace);
  }, [activeRenderExt, fieldItems, traceHits]);

  const currentPdfPage = Math.min(Math.max(pdfPage, 1), inferredPdfPageCount);

  useEffect(() => {
    if (activeRenderExt !== 'pdf') return;
    if (pdfPage !== currentPdfPage) {
      setPdfPage(currentPdfPage);
    }
  }, [activeRenderExt, currentPdfPage, pdfPage]);

  const overlayItems = useMemo(() => {
    const drawable = activeRenderExt === 'pdf' || IMAGE_EXTENSIONS.has(activeRenderExt);
    if (!drawable) return [];
    if (activeRenderExt !== 'pdf') {
      return fieldItems.filter((item) => hasMeaningfulBox(item.bbox));
    }
    return fieldItems.filter(
      (item) => hasMeaningfulBox(item.bbox) && item.pageNumber === currentPdfPage
    );
  }, [activeRenderExt, currentPdfPage, fieldItems]);

  const overlayTraceItems = useMemo(() => {
    const drawable = activeRenderExt === 'pdf' || IMAGE_EXTENSIONS.has(activeRenderExt);
    if (!drawable) return [];
    const filtered = traceHits.filter((hit) => {
      const bbox = Array.isArray(hit.bbox) ? hit.bbox : [];
      if (!hasMeaningfulBox(bbox)) return false;
      if (String(hit.object_type || '').toLowerCase() === 'field') return false;
      if (activeRenderExt !== 'pdf') return true;
      const page = Number(hit.page || bbox[0] || 0);
      return Number.isFinite(page) && Math.round(page) === currentPdfPage;
    });
    return filtered.slice(0, 24);
  }, [traceHits, activeRenderExt, currentPdfPage]);

  const avgConfidence = useMemo(() => {
    if (fieldItems.length === 0) return 0;
    const total = fieldItems.reduce((acc, item) => acc + item.confidence, 0);
    return Math.round((total / fieldItems.length) * 100);
  }, [fieldItems]);

  const traceTypeStats = useMemo(() => {
    const stats = {
      field: 0,
      table: 0,
      figure: 0,
      other: 0,
    };

    traceHits.forEach((hit) => {
      const typ = String(hit.object_type || '').toLowerCase();
      if (typ === 'field') {
        stats.field += 1;
      } else if (typ === 'table') {
        stats.table += 1;
      } else if (typ === 'figure') {
        stats.figure += 1;
      } else {
        stats.other += 1;
      }
    });

    return stats;
  }, [traceHits]);

  const traceGroups = useMemo(() => {
    const grouped = {
      field: [] as Array<{ hit: TraceHit; idx: number }>,
      table: [] as Array<{ hit: TraceHit; idx: number }>,
      figure: [] as Array<{ hit: TraceHit; idx: number }>,
      other: [] as Array<{ hit: TraceHit; idx: number }>,
    };
    traceHits.forEach((hit, idx) => {
      const typ = String(hit.object_type || "").toLowerCase();
      if (typ === "field") {
        grouped.field.push({ hit, idx });
      } else if (typ === "table") {
        grouped.table.push({ hit, idx });
      } else if (typ === "figure") {
        grouped.figure.push({ hit, idx });
      } else {
        grouped.other.push({ hit, idx });
      }
    });
    return [
      { key: "field", label: "字段", items: grouped.field },
      { key: "table", label: "表格", items: grouped.table },
      { key: "figure", label: "图表", items: grouped.figure },
      { key: "other", label: "其他", items: grouped.other },
    ].filter((group) => group.items.length > 0);
  }, [traceHits]);

  const tableCount = useMemo(() => {
    const raw = Number(activeDoc?.diagnostics?.table_count ?? 0);
    return Number.isFinite(raw) && raw > 0 ? Math.round(raw) : 0;
  }, [activeDoc?.diagnostics?.table_count]);

  const figureCount = useMemo(() => {
    const raw = Number(activeDoc?.diagnostics?.figure_count ?? 0);
    return Number.isFinite(raw) && raw > 0 ? Math.round(raw) : 0;
  }, [activeDoc?.diagnostics?.figure_count]);

  const pollOfficePreview = async (file: File, key: string, jobId: string) => {
    const maxPoll = 80;
    for (let i = 0; i < maxPoll; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      const response = await fetch(`/extract/preview/office/status/${encodeURIComponent(jobId)}`);
      if (!response.ok) continue;
      const payload = await response.json();
      const status = String(payload.status || '').toLowerCase();
      if (status === 'completed') {
        const pdfUrl = String(payload.artifact_url || '').trim();
        setOfficePreviewMap((prev) => ({
          ...prev,
          [key]: {
            status: 'completed',
            jobId,
            pdfUrl,
          },
        }));
        if (activeSourceFile && fileIdentityKey(activeSourceFile) === key && pdfUrl) {
          setPreviewUrl(pdfUrl);
        }
        return;
      }
      if (status === 'failed') {
        setOfficePreviewMap((prev) => ({
          ...prev,
          [key]: {
            status: 'failed',
            jobId,
            error: String(payload.error || 'DOC/DOCX 预览转换失败'),
          },
        }));
        return;
      }
      setOfficePreviewMap((prev) => ({
        ...prev,
        [key]: {
          ...(prev[key] || { status: 'queued' as const }),
          status: status === 'running' ? 'running' : 'queued',
          jobId,
        },
      }));
    }
    setOfficePreviewMap((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] || { status: 'queued' as const }),
        status: 'failed',
        jobId,
        error: 'DOC/DOCX 预览转换超时',
      },
    }));
  };

  const ensureOfficePreview = async (file: File) => {
    const ext = fileExt(file.name);
    if (ext !== 'doc' && ext !== 'docx') return;
    const key = fileIdentityKey(file);
    const current = officePreviewMap[key];
    if (current && (current.status === 'running' || current.status === 'queued' || current.status === 'completed')) {
      return;
    }
    setOfficePreviewMap((prev) => ({
      ...prev,
      [key]: { status: 'queued' },
    }));
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch('/extract/preview/office/start', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || 'DOC/DOCX 预览转换失败');
      }
      const payload = await response.json();
      const status = String(payload.status || '').toLowerCase();
      const jobId = String(payload.job_id || '').trim();
      const pdfUrl = String(payload.artifact_url || '').trim();
      if (status === 'completed' && pdfUrl) {
        setOfficePreviewMap((prev) => ({
          ...prev,
          [key]: {
            status: 'completed',
            jobId,
            pdfUrl,
          },
        }));
        return;
      }
      if (!jobId) {
        throw new Error('DOC/DOCX 预览任务创建失败');
      }
      setOfficePreviewMap((prev) => ({
        ...prev,
        [key]: {
          status: status === 'running' ? 'running' : 'queued',
          jobId,
        },
      }));
      void pollOfficePreview(file, key, jobId);
    } catch (error) {
      setOfficePreviewMap((prev) => ({
        ...prev,
        [key]: {
          status: 'failed',
          error: error instanceof Error ? error.message : 'DOC/DOCX 预览转换失败',
        },
      }));
    }
  };

  const mergeSelectedFiles = (incomingRaw: File[]) => {
    const incoming = incomingRaw.filter(isAllowedFile);
    const rejectedCount = incomingRaw.length - incoming.length;
    if (incoming.length === 0) {
      if (rejectedCount > 0) {
        setInfoMessage("未添加任何文件，仅支持常见文档与图片格式。");
      }
      return;
    }

    const byIdentity = new Map<string, File>();
    [...selectedFiles, ...incoming].forEach((file) => {
      byIdentity.set(fileIdentityKey(file), file);
    });
    const merged = Array.from(byIdentity.values());
    const limited = merged.slice(0, 5);
    setSelectedFiles(limited);
    if (merged.length > 5) {
      setInfoMessage("批处理上限为 5 个文件，超出部分已忽略。");
    } else if (rejectedCount > 0) {
      setInfoMessage(`已忽略 ${rejectedCount} 个不支持的文件，仅支持常见文档与图片格式。`);
    } else {
      setInfoMessage(`已选择 ${limited.length} 个文件，可开始抽取。`);
    }
    incoming.forEach((file) => {
      void ensureOfficePreview(file);
    });
  };

  const onSelectFiles = (event: React.ChangeEvent<HTMLInputElement>) => {
    const incomingRaw = Array.from(event.target.files ?? []) as File[];
    mergeSelectedFiles(incomingRaw);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => {
      const removed = prev[index];
      if (removed) {
        const key = fileIdentityKey(removed);
        setOfficePreviewMap((map) => {
          if (!(key in map)) return map;
          const copied = { ...map };
          delete copied[key];
          return copied;
        });
      }
      return prev.filter((_, i) => i !== index);
    });
  };

  const clearAllFiles = () => {
    setSelectedFiles([]);
    setDocuments([]);
    setActiveDocIndex(0);
    setActiveFieldKey(null);
    setPdfPage(1);
    setErrorMessage('');
    setInfoMessage("文件队列已清空。");
    setScale(1);
    setRotation(0);
    summaryRequestSeqRef.current += 1;
    traceRequestSeqRef.current += 1;
    setSummaryDocName('');
    setActiveSummaryText('');
    setActiveSummaryLoading(false);
    setTraceHits([]);
    setTraceError('');
    setTraceLoading(false);
    setActiveTraceKey('');
    setAssistantStatus('idle');
    setAssistantMessage("等待生成可执行建议。");
    setAssistantInput('');
    setAssistantAnswer('');
    setAssistantWarnings([]);
    setAssistantQueryLoading(false);
    
    // Clear local storage cache
    writeExtractionDocuments([]);
  };

  const runExtraction = async () => {
    if (selectedFiles.length === 0) {
      setErrorMessage("请至少上传一个文件。");
      return;
    }

    let schemaObj: unknown;
    try {
      schemaObj = JSON.parse(schemaText);
    } catch (error) {
      setErrorMessage(error instanceof Error ? `规则模板格式错误：${error.message}` : "规则模板格式错误。");
      return;
    }

    setErrorMessage('');
    setActiveFieldKey(null);
    setIsProcessing(true);
    setInfoMessage(`正在执行 ${selectedFiles.length} 个文件的抽取...`);
    setActiveSummaryLoading(true);
    setActiveSummaryText('已收到抽取任务，正在生成智能摘要...');
    setSummaryDocName(selectedFiles.length === 1 ? selectedFiles[0].name : '当前批次');
    setAssistantMessage("任务已提交，解析与摘要正在同步执行。");
    setAssistantAnswer('');
    setAssistantWarnings([]);
    traceRequestSeqRef.current += 1;
    setTraceHits([]);
    setTraceError('');
    setTraceLoading(false);
    setActiveTraceKey('');

    try {
      const requestBatchWithRetry = async (attempts: number) => {
        let lastError: unknown = null;
        for (let i = 1; i <= attempts; i += 1) {
          const formData = new FormData();
          selectedFiles.forEach((file) => formData.append('files', file));
          formData.append('schema', JSON.stringify(schemaObj));
          try {
            return await fetch('/extract/batch', {
              method: 'POST',
              body: formData,
            });
          } catch (error) {
            lastError = error;
            if (i < attempts) {
              setInfoMessage(`网络抖动，正在重试抽取请求（${i}/${attempts - 1}）...`);
              await new Promise((resolve) => setTimeout(resolve, 600 * i));
              continue;
            }
          }
        }
        throw lastError instanceof Error ? lastError : new Error('抽取请求失败');
      };

      const response = await requestBatchWithRetry(2);

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || '抽取请求失败');
      }

      const payload = (await response.json()) as ExtractResponse;
      if (!payload.documents || payload.documents.length === 0) {
        throw new Error("后端未返回抽取结果");
      }

      setDocuments(payload.documents);
      writeExtractionDocuments(payload.documents);
      setActiveDocIndex(0);
      setPdfPage(1);
      if (payload.documents.length > 0) {
        void requestSummary(payload.documents[0]);
      }

      const firstErrorDoc = payload.documents.find((doc) => doc.errors && doc.errors.length > 0);
      if (firstErrorDoc) {
        setErrorMessage(firstErrorDoc.errors.join(' | '));
      } else {
        const cacheHits = payload.documents.filter((doc) => doc.cached).length;
        const totalTables = payload.documents.reduce((acc, doc) => {
          const raw = doc.diagnostics?.table_count;
          const val = typeof raw === 'number' ? raw : Number(raw ?? 0);
          return acc + (Number.isFinite(val) ? val : 0);
        }, 0);
        const totalFigures = payload.documents.reduce((acc, doc) => {
          const raw = doc.diagnostics?.figure_count;
          const val = typeof raw === 'number' ? raw : Number(raw ?? 0);
          return acc + (Number.isFinite(val) ? val : 0);
        }, 0);
        const sourceSet = new Set<string>();
        const figureSourceSet = new Set<string>();
        payload.documents.forEach((doc) => {
          const srcRaw = doc.diagnostics?.table_sources;
          if (!srcRaw || typeof srcRaw !== 'object') return;
          Object.keys(srcRaw as Record<string, unknown>).forEach((key) => sourceSet.add(key));
          const figRaw = doc.diagnostics?.figure_sources;
          if (figRaw && typeof figRaw === 'object') {
            Object.keys(figRaw as Record<string, unknown>).forEach((key) => figureSourceSet.add(key));
          }
        });
        const sourceText = sourceSet.size > 0 ? Array.from(sourceSet).slice(0, 3).join(', ') : '未知';
        const figureSourceText = figureSourceSet.size > 0 ? Array.from(figureSourceSet).slice(0, 3).join(', ') : '未知';
        const softWarningCount = payload.documents.reduce((acc, doc) => acc + (doc.soft_warnings?.length ?? 0), 0);
        const autoSchemaDocs = payload.documents.reduce((acc, doc) => {
          const mode = String(doc.diagnostics?.schema_mode || '');
          return acc + (mode === 'auto' ? 1 : 0);
        }, 0);
        setInfoMessage(
          `已完成 ${payload.documents.length} 份文档抽取，缓存命中 ${cacheHits} 份，智能字段识别 ${autoSchemaDocs} 份，识别表格 ${totalTables} 张（来源: ${sourceText}），识别图像 ${totalFigures} 张（来源: ${figureSourceText}），软告警 ${softWarningCount} 条。`
        );
      }
    } catch (error) {
      console.error(error);
      setErrorMessage(error instanceof Error ? error.message : '抽取失败');
      setActiveSummaryLoading(false);
      setActiveSummaryText("抽取失败，无法生成摘要。");
    } finally {
      setIsProcessing(false);
    }
  };

  const exportResults = () => {
    if (documents.length === 0) return;

    const blob = new Blob([JSON.stringify({ documents }, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `模块二抽取结果_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleZoomIn = () => setScale((prev) => Math.min(prev + 0.1, 2.5));
  const handleZoomOut = () => setScale((prev) => Math.max(prev - 0.1, 0.5));
  const handleRotate = () => setRotation((prev) => (prev + 90) % 360);
  const handlePrevPdfPage = () => {
    setPdfPage((prev) => Math.max(1, prev - 1));
    setActiveFieldKey(null);
  };
  const handleNextPdfPage = () => {
    setPdfPage((prev) => Math.min(inferredPdfPageCount, prev + 1));
    setActiveFieldKey(null);
  };
  const handleResetView = () => {
    setScale(1);
    setRotation(0);
  };

  const writeClipboard = async (text: string, successHint: string) => {
    const payload = String(text || '').trim();
    if (!payload) return;
    try {
      await navigator.clipboard.writeText(payload);
      setInfoMessage(successHint);
      return;
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = payload;
      textarea.setAttribute('readonly', 'true');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setInfoMessage(successHint);
    }
  };

  const tablePreviewToTsv = (headers: string[], rows: string[][]) => {
    const lines: string[] = [];
    if (headers.length > 0) {
      lines.push(headers.join('\t'));
    }
    rows.forEach((row) => lines.push(row.join('\t')));
    return lines.join('\n');
  };

  const handleAssistantConfirm = () => {
    if (!assistantActionable) {
      setAssistantStatus('confirmed');
      setAssistantMessage("已确认：当前无需执行操作。");
      return;
    }
    setAssistantStatus('confirmed');
    setAssistantMessage("已确认保留当前抽取结果。");
  };
  const handleAssistantRollback = () => {
    if (!assistantActionable) {
      setAssistantStatus('rolled_back');
      setAssistantMessage("回滚请求已忽略：当前无可回滚项。");
      return;
    }
    setAssistantStatus('rolled_back');
    setActiveFieldKey(null);
    setTraceHits(toTraceHits(activeDoc, null));
    setAssistantMessage("已执行回滚：定位高亮已重置，你可以重新选择字段或重新抽取。");
  };

  const runAssistantInstruction = async () => {
    const instruction = assistantInput.trim();
    if (!activeDoc) {
      setAssistantWarnings(["当前没有可用文档，请先完成抽取。"]);
      return;
    }
    if (!instruction) {
      setAssistantWarnings(["请输入具体提取需求后再发送。"]);
      return;
    }

    const persistRequested = /(入库|落库|保存|存储|写入数据库|写库)/.test(instruction);
    const userDialogMsg: AssistantDialogMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: 'user',
      content: instruction,
    };
    setAssistantDialog((prev) => [...prev, userDialogMsg]);
    setAssistantQueryLoading(true);
    setAssistantWarnings([]);
    try {
      const response = await fetch('/extract/assistant/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document: activeDoc,
          summary: activeSummaryText,
          user_instruction: instruction,
          persist: persistRequested,
          top_k: 16,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || '助手处理失败');
      }

      const payload = (await response.json()) as AssistantQueryResponse;
      const nextAnswer = (payload.answer || "").trim() || "助手已完成处理。";
      setAssistantAnswer(nextAnswer);
      setAssistantMessage(nextAnswer);
      setAssistantWarnings(Array.isArray(payload.warnings) ? payload.warnings : []);
      setAssistantDialog((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'assistant',
          content: nextAnswer,
        },
      ]);
      if (Array.isArray(payload.matched_trace_hits) && payload.matched_trace_hits.length > 0) {
        setTraceHits(payload.matched_trace_hits);
      }
      if (Array.isArray(payload.matched_fields) && payload.matched_fields.length > 0) {
        const firstField = String(payload.matched_fields[0].field_name || '').trim();
        if (firstField) {
          setActiveFieldKey(firstField);
        }
        const firstPage = Number(payload.matched_fields[0].page || 0);
        if (activeRenderExt === 'pdf' && Number.isFinite(firstPage) && firstPage > 0) {
          setPdfPage(Math.round(firstPage));
        }
      }
      if (payload.persisted) {
        setInfoMessage(`助手已完成数据库写入，共 ${payload.persisted_rows} 条记录。`);
      }
      setAssistantInput('');
    } catch (error) {
      const message = error instanceof Error ? error.message : '助手处理失败';
      setAssistantWarnings([message]);
      const failedAnswer = "助手处理失败，请检查指令后重试。";
      setAssistantAnswer(failedAnswer);
      setAssistantDialog((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'assistant',
          content: failedAnswer,
        },
      ]);
    } finally {
      setAssistantQueryLoading(false);
    }
  };

  const workbenchGridClass = showLeftPanel
    ? "grid flex-1 min-h-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(240px,24vw)_minmax(0,1fr)] 2xl:grid-cols-[minmax(240px,18vw)_minmax(560px,1fr)_minmax(320px,22vw)]"
    : "grid flex-1 min-h-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(320px,28vw)] 2xl:grid-cols-[minmax(560px,1fr)_minmax(340px,24vw)]";
  const rightPanelClass = showLeftPanel
    ? "flex h-full w-full min-w-0 shrink-0 flex-col gap-3 xl:col-span-2 2xl:col-span-1"
    : "flex h-full w-full min-w-0 shrink-0 flex-col gap-3";
  const showTraceOverlay = false;

  return (
    <div className="relative h-[calc(100vh-2rem)] overflow-hidden p-2 text-foreground flex flex-col">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.doc,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg,.bmp,.webp,.tif,.tiff"
        multiple
        className="hidden"
        data-testid="module2-file-input"
        onChange={onSelectFiles}
      />

      <div className={workbenchGridClass}>
        {/* 左侧：上传与任务助手 */}
        {showLeftPanel && <div data-testid="module2-left-panel" className="flex h-full min-h-0 flex-col gap-3">
          <div className="flex h-auto min-h-[240px] flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm backdrop-blur dark:border-slate-700 dark:bg-slate-900/85 animate-in slide-in-from-left-4 fade-in duration-500 xl:min-h-[280px] xl:max-h-[46vh]">
              <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
                <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-100">
                  <UploadCloud size={15} className="text-blue-600 dark:text-blue-400" />
                  文件上传
                </h3>
                {selectedFiles.length > 0 && (
                  <span data-testid="module2-file-count" className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                    {selectedFiles.length}/5
                  </span>
                )}
              </div>

              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 custom-scrollbar">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  data-testid="module2-add-files"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-xs font-bold text-slate-700 shadow-sm transition-all hover:bg-slate-50 hover:text-blue-600 hover:shadow-md dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                >
                  <span className="flex items-center justify-center gap-2">
                    <UploadCloud size={14} />
                    {selectedFiles.length > 0 ? '添加更多文件' : '添加文件'}
                  </span>
                </button>

                {selectedFiles.length === 0 && (
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 px-3 py-5 text-center text-[11px] text-slate-500 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-400">
                    尚未选择文件，支持 PDF、Word、Excel、文本与图片格式。
                  </div>
                )}

                {selectedFiles.map((file, index) => (
                    <div
                      key={`${file.name}:${index}`}
                      className="group flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2.5 transition-colors hover:border-blue-200 dark:border-slate-700 dark:bg-slate-800/60 dark:hover:border-blue-700"
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <div className="rounded-lg bg-slate-100 p-2 text-slate-500 dark:bg-slate-700 dark:text-slate-300">
                          <File size={14} />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-xs font-bold text-slate-700 dark:text-slate-100">{file.name}</p>
                          <p className="text-[10px] text-slate-500 dark:text-slate-400">{(file.size / 1024).toFixed(1)} KB</p>
                        </div>
                      </div>
                      <button
                        onClick={() => removeFile(index)}
                        className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))
                }
              </div>

              <div className="space-y-3 border-t border-slate-200 p-4 dark:border-slate-700">
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowSchema(!showSchema)}
                    className={cn(
                      'flex-1 rounded-xl border px-3 py-2.5 text-xs font-bold transition-all shadow-sm',
                      showSchema
                        ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-200'
                        : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50 hover:border-slate-400 hover:text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700'
                    )}
                  >
                    <span className="inline-flex items-center justify-center gap-1.5">
                      <Settings size={14} />
                      {showSchema ? '隐藏规则' : '配置规则'}
                    </span>
                  </button>
                  <button
                    onClick={clearAllFiles}
                    disabled={selectedFiles.length === 0 && documents.length === 0}
                    data-testid="module2-clear-files"
                    className="rounded-xl border border-transparent bg-transparent px-4 py-2.5 text-xs font-bold text-slate-600 transition-colors hover:bg-red-50 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-400 dark:hover:bg-red-900/20"
                  >
                    清空
                  </button>
                </div>
                <div className="relative group/extract-btn">
                  <button
                    onClick={runExtraction}
                    disabled={isProcessing || selectedFiles.length === 0}
                    data-testid="module2-start-extract"
                    className={cn(
                      'w-full rounded-xl py-3 text-sm font-bold text-white transition-all duration-300',
                      isProcessing || selectedFiles.length === 0
                        ? 'cursor-not-allowed bg-slate-100 text-slate-400 border border-slate-200 dark:bg-slate-800 dark:text-slate-600 dark:border-slate-700'
                        : 'bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-500/30 hover:shadow-blue-500/40 hover:-translate-y-0.5 active:translate-y-0'
                    )}
                  >
                    <span className="inline-flex items-center gap-2">
                      {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <PlayCircle size={16} strokeWidth={2.5} />}
                      {isProcessing ? "正在抽取..." : "开始提取"}
                    </span>
                  </button>
                  {/* Tooltip for disabled state */}
                  {selectedFiles.length === 0 && !isProcessing && (
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 bg-slate-800 text-white text-[10px] rounded-lg shadow-xl opacity-0 group-hover/extract-btn:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
                      请先上传文件
                      <div className="absolute top-full left-1/2 -translate-x-1/2 border-[4px] border-transparent border-t-slate-800"></div>
                    </div>
                  )}
                </div>
              </div>
            </div>

          <div className="flex-1 flex flex-col min-h-0 rounded-2xl border border-slate-200/80 bg-white/90 p-3 shadow-sm backdrop-blur dark:border-slate-700 dark:bg-slate-900/85 transition-all duration-300">
            <div className="mb-2 flex items-center justify-between shrink-0">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                 <Bot size={16} className="text-blue-500" />
                 信息提取任务助手
              </h3>
              <button
                onClick={() => setShowAssistantHelp(true)}
                className="flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[10px] font-bold text-blue-600 transition-colors hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300 dark:hover:bg-blue-900/40"
              >
                <HelpCircle size={12} />
                助手功能说明
              </button>
            </div>
            
            {documents.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 p-4 text-center text-slate-400 select-none">
                    {isProcessing || selectedFiles.length > 0 ? (
                      <div className="w-full rounded-xl border border-slate-100 bg-white/60 p-3 text-left dark:border-slate-700 dark:bg-slate-900/30">
                        <div className="mb-1 flex items-center gap-1.5 opacity-70 text-blue-600 dark:text-blue-400">
                          <Sparkles size={12} />
                          <span className="text-[10px] font-bold">AI智能总结</span>
                        </div>
                        <p data-testid="module2-summary-text" className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-400 whitespace-pre-wrap break-words">
                          {activeSummaryLoading ? "正在生成文档摘要..." : (activeSummaryText || "已接收任务，等待抽取结果。")}
                        </p>
                        <p className="mt-2 text-[10px] text-slate-400 dark:text-slate-500">
                          抽取完成后可在下方对话框继续发送定向提取指令。
                        </p>
                      </div>
                    ) : (
                      <>
                        <Bot size={48} strokeWidth={1} className="mb-3 opacity-20" />
                        <p className="text-xs">请先上传并处理文档</p>
                      </>
                    )}
                </div>
            ) : (
                <>
                <div className="flex-1 flex flex-col min-h-0 gap-3 overflow-hidden">
                    <div className="shrink-0 rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-xs leading-relaxed text-slate-600 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-200 relative">
                    <div className="absolute top-3 left-0 w-1 h-4 bg-blue-400 rounded-r-full"></div>
                    {assistantMessage}
                    </div>
                    
                    <div className="flex-1 overflow-y-auto custom-scrollbar rounded-xl border border-slate-100 bg-white/40 p-2.5 dark:border-slate-800 dark:bg-slate-900/30 flex flex-col gap-2">
                    <div className="shrink-0">
                        <div className="flex items-center gap-1.5 mb-1 opacity-70 text-blue-600 dark:text-blue-400">
                            <Sparkles size={12} />
                            <span className="text-[10px] font-bold">AI智能总结</span>
                        </div>
                        <p data-testid="module2-summary-text" className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-400 whitespace-pre-wrap break-words">
                            {activeSummaryLoading ? "正在生成文档摘要..." : (activeSummaryText || "暂无摘要。")}
                        </p>
                    </div>

                    <div className="shrink-0 space-y-1">
                        <div
                          ref={assistantDialogRef}
                          data-testid="module2-assistant-dialog"
                          className="max-h-48 space-y-2 overflow-y-auto rounded-xl border border-slate-100 bg-white/70 p-2 dark:border-slate-700 dark:bg-slate-900/40"
                        >
                          {assistantDialog.length === 0 ? (
                            <p className="text-[10px] text-slate-400 dark:text-slate-500">
                              等待指令，发送需求后这里会显示完整对话。
                            </p>
                          ) : (
                            assistantDialog.slice(-16).map((msg) => (
                              <div
                                key={msg.id}
                                className={cn(
                                  "rounded-lg px-2 py-1.5 text-[10px] leading-relaxed break-words",
                                  msg.role === 'assistant'
                                    ? "border border-blue-100 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300"
                                    : "border border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                                )}
                              >
                                <p className="mb-0.5 opacity-70">{msg.role === 'assistant' ? '助手' : '用户'}</p>
                                <p>{msg.content}</p>
                              </div>
                            ))
                          )}
                          {assistantQueryLoading && (
                            <div className="inline-flex items-center gap-1 rounded-lg border border-blue-100 bg-blue-50 px-2 py-1 text-[10px] text-blue-600 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
                              <Loader2 size={10} className="animate-spin" />
                              助手处理中...
                            </div>
                          )}
                        </div>
                        <div className="relative">
                        <textarea
                            data-testid="module2-assistant-input"
                            value={assistantInput}
                            onChange={(e) => setAssistantInput(e.target.value)}
                            onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                if (!assistantQueryLoading) {
                                void runAssistantInstruction();
                                }
                            }
                            }}
                            placeholder="例如：提取合同金额和税率并入库"
                            className="w-full min-h-[72px] resize-none rounded-xl border border-slate-200 bg-white/90 px-3 py-2 pr-10 text-xs text-slate-700 outline-none transition-colors focus:border-blue-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                        />
                        <button
                            type="button"
                            data-testid="module2-assistant-send"
                            onClick={() => void runAssistantInstruction()}
                            disabled={assistantQueryLoading || !activeDoc}
                            className={cn(
                            'absolute bottom-2 right-2 rounded-lg p-1.5 transition-colors',
                            assistantQueryLoading || !activeDoc
                                ? 'cursor-not-allowed bg-slate-200 text-slate-400 dark:bg-slate-800 dark:text-slate-600'
                                : 'bg-blue-600 text-white hover:bg-blue-700'
                            )}
                        >
                            {assistantQueryLoading ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                        </button>
                        </div>

                        {assistantWarnings.length > 0 && (
                        <div className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-[10px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                            {assistantWarnings.join("；")}
                        </div>
                        )}

                        {assistantAnswer && (
                        <div
                            data-testid="module2-assistant-answer"
                            className="rounded-lg border border-blue-200 bg-blue-50 px-2 py-1.5 text-[10px] leading-relaxed text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300"
                        >
                            {assistantAnswer}
                        </div>
                        )}
                    </div>
                    </div>
                </div>

                <div className="flex gap-2 shrink-0 mt-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                <button
                    onClick={handleAssistantConfirm}
                    className={cn(
                    'flex-1 rounded-lg border py-2 text-xs font-bold transition-colors',
                    assistantStatus === 'confirmed'
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200'
                        : 'border-slate-200 bg-white text-slate-600 hover:border-emerald-300 hover:text-emerald-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200'
                    )}
                >
                    确认结果
                </button>
                <button
                    onClick={handleAssistantRollback}
                    className={cn(
                    'flex-1 rounded-lg border py-2 text-xs font-bold transition-colors',
                    assistantStatus === 'rolled_back'
                        ? 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200'
                        : 'border-slate-200 bg-white text-slate-600 hover:border-amber-300 hover:text-amber-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200'
                    )}
                >
                    回滚定位
                </button>
                </div>
                </>
            )}
          </div>
        </div>}

      {/* CENTER: Workbench Area */}
      <div className="relative flex h-full min-h-0 flex-col gap-4">
        {/* Schema Editor Overlay */}
        {showSchema && (
            <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[90%] max-w-2xl z-50 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl shadow-2xl rounded-2xl animate-in slide-in-from-top-4 fade-in duration-200 flex flex-col max-h-[500px] border border-slate-200 dark:border-slate-700 overflow-hidden ring-1 ring-slate-900/5">
                    <div className="p-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/50">
                    <h3 className="text-xs font-bold font-['Microsoft_YaHei'] flex items-center gap-2 text-slate-700 dark:text-slate-200">
                        <Braces size={14} className="text-blue-500" /> 规则模板配置
                    </h3>
                    <div className="flex gap-2">
                            <button onClick={() => setSchemaText(JSON.stringify(DEFAULT_SCHEMA, null, 2))} className="text-[10px] text-blue-500 hover:underline px-2 font-medium">恢复智能规则</button>
                            <button onClick={() => setShowSchema(false)} className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors text-slate-500"><X size={14}/></button>
                    </div>
                    </div>
                    <textarea
                    value={schemaText}
                    onChange={(e) => setSchemaText(e.target.value)}
                    className="flex-1 w-full bg-transparent p-4 font-mono text-xs outline-none resize-none text-slate-700 dark:text-slate-300 placeholder:text-slate-400"
                    spellCheck={false}
                />
            </div>
        )}

        {/* Main Canvas with Floating Toolbar */}
        <div className="flex-1 relative overflow-hidden flex flex-col bg-slate-50/50 dark:bg-slate-950/50 rounded-2xl border border-slate-200/60 dark:border-slate-800 group isolate">
            {/* Dot Grid Background */}
            <div className="absolute inset-0 opacity-[0.4] dark:opacity-[0.1] pointer-events-none -z-10" 
                 style={{ backgroundImage: 'radial-gradient(circle, #cbd5e1 1.5px, transparent 1.5px)', backgroundSize: '24px 24px' }}>
            </div>

            {/* Fixed Header Toolbar */}
            <div className="relative z-20 flex w-full shrink-0 items-center gap-2 border-b border-slate-200 bg-white/80 px-4 py-2 backdrop-blur-sm dark:border-slate-800 dark:bg-slate-900/80">
                <div className="flex flex-1 items-center gap-1 overflow-hidden min-w-0">
                     {activeDoc || activeSourceFile ? (
                        <>
                            <div className="flex flex-col min-w-0 max-w-[200px] sm:max-w-[300px]">
                                <span className="text-sm font-bold font-['Microsoft_YaHei'] truncate text-slate-900 dark:text-slate-100">{activeDoc?.file_name ?? activeSourceFile?.name}</span>
                                <span className="text-[10px] font-bold font-['Microsoft_YaHei'] text-slate-500 flex items-center gap-1.5">
                                    {activeDoc ? (
                                        <>
                                            <span className={cn("w-2 h-2 rounded-full shrink-0", activeDoc.cached ? "bg-emerald-500" : "bg-amber-500")} />
                                            <span className="truncate">{activeDoc.cached ? "已缓存" : "实时预览"}</span>
                                        </>
                                    ) : (
                                        <>
                                            <span className="w-2 h-2 rounded-full shrink-0 bg-blue-500" />
                                            <span className="truncate">待提取</span>
                                        </>
                                    )}
                                </span>
                            </div>
                        </>
                     ) : (
                         <div className="flex items-center gap-2 text-slate-900 dark:text-slate-100">
                           <Maximize size={18} strokeWidth={2.5} className="shrink-0 text-blue-600 dark:text-blue-400" />
                           <span className="text-sm font-bold font-['Microsoft_YaHei'] whitespace-nowrap">
                               {isSidebarCollapsed ? "预览视窗" : "文档预览"}
                           </span>
                        </div>
                     )}
                </div>

                <div className="h-5 w-px bg-slate-200 dark:bg-slate-700 shrink-0 mx-2" />

                <div className="flex items-center gap-1 shrink-0">
                    <button onClick={handleZoomOut} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-700 hover:text-blue-600 transition-colors active:scale-95 shrink-0" title="缩小"><ZoomOut size={16} strokeWidth={2}/></button>
                    <span className="text-xs font-bold font-mono w-10 text-center text-slate-900 dark:text-slate-100 shrink-0">{Math.round(scale * 100)}%</span>
                    <button onClick={handleZoomIn} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-700 hover:text-blue-600 transition-colors active:scale-95 shrink-0" title="放大"><ZoomIn size={16} strokeWidth={2}/></button>
                    <button onClick={handleRotate} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-700 hover:text-blue-600 transition-colors ml-0.5 active:scale-95 shrink-0" title="旋转"><RotateCw size={16} strokeWidth={2}/></button>
                    <button onClick={handleResetView} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-700 hover:text-blue-600 transition-colors active:scale-95 shrink-0" title="重置视图"><Maximize size={16} strokeWidth={2}/></button>
                </div>

                {activeRenderExt === 'pdf' && (
                    <>
                        <div className="h-5 w-px bg-slate-200 dark:bg-slate-700 shrink-0 mx-2" />
                        <div className="flex items-center gap-1 shrink-0">
                            <button
                                onClick={handlePrevPdfPage}
                                disabled={currentPdfPage <= 1}
                                className={cn(
                                    "p-1.5 rounded-lg transition-colors active:scale-95 shrink-0",
                                    currentPdfPage > 1
                                        ? "text-slate-700 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-slate-800"
                                        : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                )}
                                title="上一页"
                            >
                                <ChevronRight size={16} className="rotate-180" />
                            </button>
                            <span className="text-xs font-bold font-mono min-w-[60px] text-center text-slate-900 dark:text-slate-100 shrink-0">
                                {`${currentPdfPage} / ${inferredPdfPageCount}`}
                            </span>
                            <button
                                onClick={handleNextPdfPage}
                                disabled={currentPdfPage >= inferredPdfPageCount}
                                className={cn(
                                    "p-1.5 rounded-lg transition-colors active:scale-95 shrink-0",
                                    currentPdfPage < inferredPdfPageCount
                                        ? "text-slate-700 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-slate-800"
                                        : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                )}
                                title="下一页"
                            >
                                <ChevronRight size={16} />
                            </button>
                        </div>
                    </>
                )}

                <div className="h-5 w-px bg-slate-200 dark:bg-slate-700 shrink-0 mx-2" />

                <div className="flex items-center gap-2 shrink-0">
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-slate-700 hover:bg-slate-100 hover:text-blue-600 transition-colors dark:text-slate-300 dark:hover:bg-slate-800"
                        title="添加更多文件"
                    >
                        <Plus size={16} strokeWidth={2.5} />
                        <span className="hidden sm:inline">添加</span>
                    </button>

                    {!activeDoc && selectedFiles.length > 0 ? (
                        <button
                            onClick={runExtraction}
                            disabled={isProcessing}
                            className={cn(
                                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold font-['Microsoft_YaHei'] transition-all shadow-sm active:scale-95 shrink-0 whitespace-nowrap",
                                isProcessing
                                ? "bg-slate-100 text-slate-400 cursor-not-allowed dark:bg-slate-800 dark:text-slate-600"
                                : "bg-blue-600 text-white hover:bg-blue-700 hover:shadow-blue-500/25"
                            )}
                        >
                            {isProcessing ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} strokeWidth={2.5} />}
                            <span>开始提取</span>
                        </button>
                    ) : (
                        <button
                            onClick={exportResults}
                            disabled={documents.length === 0}
                            className={cn(
                                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold font-['Microsoft_YaHei'] transition-all shadow-sm active:scale-95 shrink-0 whitespace-nowrap",
                                documents.length > 0
                                ? "bg-slate-100 text-slate-700 hover:bg-slate-200 hover:text-blue-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                                : "opacity-50 bg-slate-50 text-slate-400 cursor-not-allowed dark:bg-slate-900 dark:text-slate-600"
                            )}
                        >
                            <Download size={14} strokeWidth={2.5} />
                            <span>导出结果</span>
                        </button>
                    )}
                </div>
            </div>

            <div className="relative z-10 flex flex-1 items-center justify-center overflow-auto p-3 sm:p-6 custom-scrollbar">
                 {!activeSourceFile ? (
                    <div
                     data-testid="module2-center-uploader"
                     onClick={() => fileInputRef.current?.click()}
                     onDragOver={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const dropped = Array.from(e.dataTransfer?.files ?? []) as File[];
                      mergeSelectedFiles(dropped);
                    }}
                    className="group relative flex flex-col items-center justify-center h-full w-full select-none cursor-pointer overflow-hidden rounded-3xl border-2 border-dashed border-slate-300 bg-slate-50/50 transition-all duration-500 hover:border-blue-400 hover:bg-blue-50/50 hover:shadow-lg hover:shadow-blue-500/5 dark:border-slate-700 dark:bg-slate-900/30 dark:hover:border-blue-500/50 dark:hover:bg-blue-900/10"
                  >
                     {/* Creative Background Elements */}
                     <div className="absolute inset-0 opacity-0 transition-opacity duration-700 group-hover:opacity-100 pointer-events-none">
                        <div className="absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 animate-pulse rounded-full bg-blue-100/30 blur-[100px] dark:bg-[#7E92B5]/10" />
                     </div>
 
                     {/* Main 3D Container */}
                     <div className="relative z-10 mb-8 h-32 w-32 perspective-[1000px] pointer-events-none">
                        {/* Floating Card System */}
                        <div className="relative h-full w-full transition-transform duration-500 group-hover:scale-110">
                            
                            {/* Bottom Card - Data Layer */}
                            <div className="absolute inset-0 rounded-2xl border border-slate-200 bg-white/80 shadow-sm transition-all duration-500 ease-out group-hover:-translate-y-4 group-hover:-translate-x-6 group-hover:-rotate-12 dark:border-slate-700 dark:bg-slate-800/80 flex flex-col p-3 gap-2 opacity-60">
                                <div className="h-1.5 w-2/3 rounded-full bg-slate-200 dark:bg-slate-600"/>
                                <div className="h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-600"/>
                                <div className="h-1.5 w-4/5 rounded-full bg-slate-200 dark:bg-slate-600"/>
                            </div>
 
                            {/* Middle Card - Structure Layer */}
                            <div className="absolute inset-0 rounded-2xl border border-slate-200 bg-white/90 shadow-md transition-all duration-500 ease-out group-hover:-translate-y-8 group-hover:translate-x-6 group-hover:rotate-12 dark:border-slate-700 dark:bg-slate-800/90 flex items-center justify-center opacity-80">
                                <div className="h-12 w-16 rounded border border-dashed border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/50 flex items-center justify-center">
                                    <ScanLine size={16} className="text-slate-400 dark:text-slate-500" />
                                </div>
                            </div>
 
                            {/* Top Card - Action Layer */}
                            <div className="absolute inset-0 flex items-center justify-center rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 shadow-xl transition-all duration-500 cubic-bezier(0.34, 1.56, 0.64, 1) group-hover:-translate-y-12 group-hover:scale-110 group-hover:shadow-blue-200/50 dark:border-slate-600 dark:from-slate-800 dark:to-slate-900 z-20">
                                <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm border border-slate-100 text-blue-400 transition-all duration-500 group-hover:bg-blue-500 group-hover:text-white group-hover:border-blue-500 group-hover:rotate-0 dark:bg-slate-800 dark:border-slate-700 dark:text-[#8DA3C1]">
                                    <UploadCloud size={28} className="transition-all duration-500 group-hover:scale-110" />
                                    {/* Ripple Effect Ring */}
                                    <div className="absolute inset-0 rounded-2xl border-2 border-blue-200 opacity-0 transition-all duration-700 group-hover:animate-ping group-hover:opacity-100"/>
                                </div>
                            </div>
 
                            {/* Shadow Base */}
                            <div className="absolute -bottom-6 left-1/2 h-4 w-24 -translate-x-1/2 rounded-[100%] bg-slate-400/20 blur-xl transition-all duration-500 group-hover:w-32 group-hover:bg-blue-200/40 dark:bg-black/40 scale-x-150" />
                        </div>
                     </div>
                     
                     {/* Text Content */}
                    <div className="relative z-10 text-center transition-transform duration-500 group-hover:translate-y-2">
                       <h3 className="mb-2 text-lg font-bold text-slate-900 transition-colors group-hover:text-blue-700 dark:text-slate-100 dark:group-hover:text-[#8DA3C1]">
                           点击或拖拽上传文档
                       </h3>
                       <p className="text-xs text-slate-600 transition-colors group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-300 mb-3 font-medium">
                           支持 PDF, Word, Excel, 图片等多种格式
                       </p>
                       <span className="inline-flex items-center gap-1.5 rounded-full bg-white border border-slate-200 px-3 py-1 text-[10px] font-bold text-slate-600 transition-all duration-300 group-hover:bg-blue-50 group-hover:text-blue-600 group-hover:border-blue-200 group-hover:shadow-sm dark:bg-slate-800 dark:text-slate-400 dark:group-hover:bg-[#1E293B]/50 dark:group-hover:text-[#8DA3C1]">
                           <Sparkles size={10} />
                           智能深度解析 & 溯源定位
                       </span>
                    </div>
                   </div>
                ) : (
                   <div 
                        className="relative w-full max-w-[860px] origin-center shadow-2xl transition-all duration-300 ease-out will-change-transform dark:shadow-black/50"
                        style={{ 
                            transform: `scale(${scale}) rotate(${rotation}deg)`,
                            transition: isProcessing ? 'none' : 'transform 0.3s ease-out'
                        }}
                    >
                         <div className="relative aspect-[595/842] w-full overflow-hidden bg-white ring-1 ring-slate-200/50 shadow-2xl dark:bg-[#1a1b26] dark:ring-white/10">
                            {activeRenderExt === 'pdf' && previewUrl ? (
                              <iframe
                                title={`preview-${activeDisplayName}`}
                                src={`${previewUrl}#page=${currentPdfPage}&toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
                                className="absolute inset-0 w-full h-full border-0 pointer-events-none"
                              />
                            ) : (activeExt === 'doc' || activeExt === 'docx') ? (
                              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-50/70 p-6 text-center dark:bg-slate-900/60">
                                <div className="rounded-xl border border-slate-200 bg-white/90 px-4 py-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                                  {activeOfficePreview?.status === 'failed'
                                    ? (activeOfficePreview.error || 'Word 预览转换失败，请先执行抽取或重新上传。')
                                    : (activeOfficePreview?.status === 'completed'
                                      ? 'Word 已转换完成，正在加载 PDF 预览...'
                                      : '后端正在将 Word 异步转换为 PDF 预览，请稍候...')}
                                </div>
                                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                  支持 .doc/.docx，转换完成后自动切换为 PDF 预览。
                                </p>
                              </div>
                            ) : IMAGE_EXTENSIONS.has(activeExt) && previewUrl ? (
                              <div className="absolute inset-0 flex items-center justify-center bg-slate-50/70 dark:bg-slate-900/60 p-6">
                                <img
                                  src={previewUrl}
                                  alt={activeDisplayName}
                                  className="max-h-full max-w-full object-contain rounded-md shadow-sm"
                                />
                              </div>
                            ) : activeRenderExt === 'xlsx' ? (
                              <div className="absolute inset-0 overflow-hidden bg-slate-50/70 p-1 dark:bg-slate-900/60 sm:p-2">
                                <LuckysheetPreview
                                  file={activeSourceFile}
                                  locator={xlsxLocatorHint}
                                  className="rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
                                />
                              </div>
                            ) : ['txt', 'md'].includes(activeRenderExt) ? (
                              <div ref={textPreviewRef} className="absolute inset-0 p-6 overflow-auto bg-slate-50/70 dark:bg-slate-900/60">
                                <pre className="text-[10px] leading-5 whitespace-pre-wrap break-words font-mono text-slate-700 dark:text-slate-200">
                                  {previewHighlight ? (
                                    <>
                                      {previewHighlight.before}
                                      <mark data-preview-highlight="true" className="rounded bg-amber-200/80 px-0.5 text-slate-900 dark:bg-amber-400/40 dark:text-slate-100">
                                        {previewHighlight.hit}
                                      </mark>
                                      {previewHighlight.after}
                                    </>
                                  ) : (
                                    previewText || '文本预览加载中...'
                                  )}
                                </pre>
                              </div>
                            ) : (
                              <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8 bg-slate-50/70 dark:bg-slate-900/50">
                                <div className="w-14 h-14 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center mb-4 text-slate-500">
                                  <FileText size={26} />
                                </div>
                                <h4 className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-2">{activeDisplayName}</h4>
                                <p className="text-[11px] text-slate-500 dark:text-slate-400 max-w-[320px] leading-relaxed">
                                  {activeSourceFile
                                    ? "当前格式暂不支持浏览器内预览，已保留抽取定位层与字段明细。"
                                    : "未找到本地原始文件（可能为缓存结果），仅展示字段定位层与抽取结果。"}
                                </p>
                              </div>
                            )}



                            {/* Bounding Boxes (hidden by default for cleaner trace view) */}
                              {showTraceOverlay && overlayItems.map((item) => {
                               const box = toPercentBox(item.bbox);
                               const isActive = activeFieldKey === item.key;
                               return (
                                 <div
                                   key={item.key}
                                   style={{
                                     left: `${box.x}%`,
                                     top: `${box.y}%`,
                                     width: `${box.w}%`,
                                     height: `${box.h}%`,
                                   }}
                                   onMouseEnter={() => setActiveFieldKey(item.key)}
                                   onMouseLeave={() => setActiveFieldKey(null)}
                                   className={cn(
                                     'absolute border-2 rounded-[2px] cursor-pointer transition-all duration-200 z-10',
                                     isActive
                                       ? 'border-blue-500 bg-blue-500/20 shadow-[0_0_20px_rgba(59,130,246,0.5)] z-30 scale-[1.05]'
                                       : 'border-blue-400/30 bg-blue-400/5 hover:border-blue-500/80 hover:bg-blue-500/10'
                                   )}
                                 >
                                     {/* Floating Label on Hover */}
                                     <div className={cn(
                                         "absolute -top-10 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] px-2.5 py-1.5 rounded-md shadow-xl whitespace-nowrap pointer-events-none transition-all transform",
                                         isActive ? "opacity-100 translate-y-0 scale-100" : "opacity-0 translate-y-2 scale-95"
                                      )}>
                                          <div className="font-bold">
                                            {item.label}
                                            {item.pageNumber ? `（第${item.pageNumber}页）` : ''}
                                          </div>
                                          <div className="text-slate-500 dark:text-slate-400 text-[9px] font-medium">{Math.floor(item.confidence * 100)}% 置信度</div>
                                          <div className="absolute bottom-[-4px] left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-900 rotate-45"></div>
                                      </div>
                                  </div>
                                );
                              })}

                              {showTraceOverlay && overlayTraceItems.map((hit, idx) => {
                                const rawBox = Array.isArray(hit.bbox) ? hit.bbox : [];
                                const box = toPercentBox(rawBox);
                                const typ = String(hit.object_type || 'trace').toLowerCase();
                                const label = typ === 'table' ? '表格溯源' : typ === 'figure' ? '图表溯源' : '溯源';
                                const traceKey = toTraceHitKey(hit, idx);
                                const isTraceActive = traceKey === activeTraceKey;
                                return (
                                  <div
                                    key={`trace-${traceKey}`}
                                    style={{
                                      left: `${box.x}%`,
                                      top: `${box.y}%`,
                                      width: `${box.w}%`,
                                      height: `${box.h}%`,
                                    }}
                                    className={cn(
                                      'absolute border border-dashed rounded-sm z-[9] pointer-events-none transition-all',
                                      typ === 'figure' ? 'border-amber-500/80 bg-amber-400/10' : 'border-emerald-500/80 bg-emerald-400/10',
                                      isTraceActive && 'ring-2 ring-blue-500/70 border-blue-500 bg-blue-500/10'
                                    )}
                                  >
                                    <div className="absolute -top-5 left-0 px-1.5 py-0.5 rounded bg-slate-900/90 text-white text-[9px] whitespace-nowrap">
                                      {label}
                                    </div>
                                  </div>
                                );
                              })}
                         </div>
                    </div>
                 )}
            </div>
            
            {/* Context Bar */}
            <div className="z-20 flex h-9 items-center justify-between border-t border-border/50 bg-white/60 px-3 text-[10px] text-muted-foreground backdrop-blur-md sm:px-4 dark:bg-slate-900/60">
                <div className="flex min-w-0 items-center gap-2 sm:gap-4">
                     <span data-testid="module2-info-message" className="truncate">{infoMessage}</span>
                     <span className="opacity-70" data-testid="module2-trace-status">
                       {traceLoading ? "溯源定位中..." : `溯源命中 ${traceHits.length} 条`}
                     </span>
                </div>
                {activeDoc && (
                    <div className="hidden font-mono opacity-50 sm:block">
                        引用编号: {activeDoc.file_hash.substring(0, 8)}...
                    </div>
                )}
            </div>
        </div>
      </div>

      {/* 右侧：文档与抽取结果 */}
      <div className={rightPanelClass}>
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900/85">
          <div className="mb-2 flex items-center justify-between px-1">
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">文档列表</h3>
            <span className="text-[10px] text-slate-500 dark:text-slate-400">{documents.length > 0 ? `${documents.length} 份` : ''}</span>
          </div>
          {documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center text-slate-600 select-none dark:text-slate-400">
              <div className="mb-3 rounded-2xl bg-slate-50 p-4 shadow-sm border border-slate-100 dark:bg-slate-800/50 dark:border-slate-700">
                 <FileText size={24} strokeWidth={1.5} className="text-slate-500 dark:text-slate-400" />
              </div>
              <p className="text-xs font-bold text-slate-900 dark:text-slate-100 mb-1">暂无已解析文档</p>
              <p className="text-[10px] font-medium text-slate-600 max-w-[200px] leading-relaxed dark:text-slate-400">
                请在左侧上传文档并点击提取，结果将展示在这里
              </p>
            </div>
          ) : (
            <div className="max-h-40 space-y-1 overflow-y-auto custom-scrollbar">
              {documents.map((doc, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setActiveDocIndex(idx);
                    setActiveFieldKey(null);
                  }}
                  className={cn(
                    "w-full rounded-xl border px-3 py-2 text-left text-xs transition-colors",
                    activeDocIndex === idx
                      ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-200"
                      : "border-transparent text-slate-600 hover:border-slate-200 hover:bg-slate-50 dark:text-slate-300 dark:hover:border-slate-700 dark:hover:bg-slate-800"
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-semibold">{doc.file_name}</span>
                    <span className="text-[10px] opacity-60">#{idx + 1}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-1 text-[10px] opacity-80">
                    {doc.errors.length > 0 ? <AlertCircle size={11} className="text-red-500" /> : <CheckCircle2 size={11} className="text-emerald-500" />}
                    {doc.errors.length > 0 ? `异常 ${doc.errors.length} 条` : "状态正常"}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex-1 min-h-0 flex flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm dark:border-slate-700 dark:bg-slate-900/85">
          <div className="border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
            <div className="flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-100">
                <ScanLine size={16} className="text-blue-500" />
                抽取结果
              </h3>
              <span className="text-[10px] text-slate-500 dark:text-slate-400">{fieldItems.length > 0 ? `${fieldItems.length} 个字段` : ''}</span>
            </div>
            {fieldItems.length > 0 && (
              <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
                <span className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  平均置信度 {avgConfidence}%
                </span>
                <span className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  表格 {tableCount} / 图表 {figureCount}
                </span>
              </div>
            )}
          </div>

          <div className="border-b border-slate-200 bg-slate-50/40 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800/30">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-700 dark:text-slate-200">
                <LocateFixed size={14} className={cn("text-slate-400", traceHits.length > 0 && "text-blue-500")} />
                溯源定位
              </div>
              <span className="text-[10px] text-slate-500 dark:text-slate-400">
                {traceLoading ? "定位中..." : `${traceHits.length} 条命中`}
              </span>
            </div>

            {(traceTypeStats.field > 0 || traceTypeStats.table > 0 || traceTypeStats.figure > 0 || traceTypeStats.other > 0) && (
              <div className="mb-2 flex flex-wrap gap-1 text-[10px]">
                {traceTypeStats.field > 0 && <span className="rounded-md bg-blue-50 px-2 py-1 text-blue-600 dark:bg-blue-900/20 dark:text-blue-300">字段 {traceTypeStats.field}</span>}
                {traceTypeStats.table > 0 && <span className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-300">表格 {traceTypeStats.table}</span>}
                {traceTypeStats.figure > 0 && <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-600 dark:bg-amber-900/20 dark:text-amber-300">图表 {traceTypeStats.figure}</span>}
                {traceTypeStats.other > 0 && <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-600 dark:bg-slate-700 dark:text-slate-300">其他 {traceTypeStats.other}</span>}
              </div>
            )}

            {traceError && (
              <p className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
                {traceError}
              </p>
            )}

            {traceHits.length > 0 ? (
              <div className="max-h-[46vh] space-y-1 overflow-y-auto custom-scrollbar pr-1">
                {traceGroups.map((group) => (
                  <div key={`trace-group-${group.key}`} className="space-y-1.5">
                    <div className="rounded-md bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      {group.label} · {group.items.length}
                    </div>
                    <div className="space-y-1">
                {group.items.map(({ hit, idx }) => {
                  const objectType = String(hit.object_type || "field").toLowerCase();
                  const objectLabel =
                    objectType === "field" ? "字段" : objectType === "table" ? "表格" : objectType === "figure" ? "图表" : "其他";
                  const objectId = String(hit.object_id || "");
                  const page = toTracePage(hit);
                  const snippet = String(hit.snippet || "");
                  const traceKey = toTraceHitKey(hit, idx);
                  const isActiveTrace = activeTraceKey === traceKey;
                  const artifactUrl = resolveArtifactUrl(hit);
                  const locator = (hit.locator ?? {}) as Record<string, unknown>;
                  const tablePreview = (locator.table_preview ?? {}) as Record<string, unknown>;
                  const tableHeaders = Array.isArray(tablePreview.headers)
                    ? tablePreview.headers.map((x) => String(x ?? ''))
                    : [];
                  const tableRows = Array.isArray(tablePreview.rows)
                    ? tablePreview.rows.map((row) =>
                        Array.isArray(row) ? row.map((cell) => String(cell ?? '')) : []
                      )
                    : [];
                  const figureKeyPoints = Array.isArray(locator.key_points)
                    ? locator.key_points.map((x) => String(x ?? '')).filter(Boolean).slice(0, 3)
                    : [];
                  const figureModesRaw = Array.isArray(locator.content_modes)
                    ? locator.content_modes.map((x) => String(x ?? '').trim().toLowerCase()).filter(Boolean)
                    : [];
                  const figureModes = figureModesRaw.slice(0, 4);
                  const modeLabelMap: Record<string, string> = {
                    dataframe: '数据表',
                    topology: '拓扑',
                    text: '文本',
                    visual: '视觉',
                  };
                  const figureDataframe = (locator.dataframe ?? {}) as Record<string, unknown>;
                  const figureDfHeaders = Array.isArray(figureDataframe.headers)
                    ? figureDataframe.headers.map((x) => String(x ?? '')).filter(Boolean).slice(0, 8)
                    : [];
                  const figureDfRows = Array.isArray(figureDataframe.rows)
                    ? figureDataframe.rows
                        .map((row) => (Array.isArray(row) ? row.map((cell) => String(cell ?? '')) : []))
                        .filter((row) => row.length > 0)
                        .slice(0, 3)
                    : [];
                  const figureTopology = (locator.topology ?? {}) as Record<string, unknown>;
                  const figureTopologyNodes = Array.isArray(figureTopology.nodes) ? figureTopology.nodes.length : 0;
                  const figureTopologyEdges = Array.isArray(figureTopology.edges) ? figureTopology.edges.length : 0;
                  const figureTextBlocks = Array.isArray(locator.text_blocks)
                    ? locator.text_blocks.map((x) => String(x ?? '').trim()).filter(Boolean).slice(0, 3)
                    : [];
                  const locatorHints: string[] = [];
                  const sheetName = String(locator.sheet_name || '').trim();
                  if (sheetName) locatorHints.push(`工作表：${sheetName}`);
                  const tableRow = Number(locator.row_index || 0);
                  if (Number.isFinite(tableRow) && tableRow > 0) locatorHints.push(`行：${Math.round(tableRow)}`);
                  const tableCol = Number(locator.col_index || 0);
                  if (Number.isFinite(tableCol) && tableCol > 0) locatorHints.push(`列：${Math.round(tableCol)}`);
                  const paragraphIndex = Number(locator.paragraph_index || 0);
                  if (Number.isFinite(paragraphIndex) && paragraphIndex > 0) locatorHints.push(`段落：${Math.round(paragraphIndex)}`);
                  const chunkIndex = Number(locator.chunk_index || 0);
                  if (Number.isFinite(chunkIndex) && chunkIndex > 0) locatorHints.push(`片段：${Math.round(chunkIndex)}`);
                  const lineStart = Number(locator.line_start || 0);
                  const lineEnd = Number(locator.line_end || 0);
                  if (Number.isFinite(lineStart) && lineStart > 0) {
                    const rangeText = Number.isFinite(lineEnd) && lineEnd >= lineStart
                      ? `${Math.round(lineStart)}-${Math.round(lineEnd)}`
                      : `${Math.round(lineStart)}`;
                    locatorHints.push(`行号：${rangeText}`);
                  }
                  const locatorSummary = locatorHints.join(' · ');
                  return (
                    <div
                      key={`trace-list-${traceKey}`}
                      onClick={() => {
                        setActiveTraceKey(traceKey);
                        if (objectType === "field" && objectId) {
                          setActiveFieldKey(objectId);
                        }
                        if (activeRenderExt === "pdf" && Number.isFinite(page) && page > 0) {
                          setPdfPage(Math.round(page));
                        }
                      }}
                      onKeyDown={(e) => {
                        if (e.key !== 'Enter' && e.key !== ' ') return;
                        e.preventDefault();
                        setActiveTraceKey(traceKey);
                        if (objectType === "field" && objectId) {
                          setActiveFieldKey(objectId);
                        }
                        if (activeRenderExt === "pdf" && Number.isFinite(page) && page > 0) {
                          setPdfPage(Math.round(page));
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      className={cn(
                        "w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-left transition-colors hover:border-blue-300 hover:bg-blue-50/40 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-blue-700 dark:hover:bg-slate-800",
                        isActiveTrace && "border-blue-400 bg-blue-50/60 ring-1 ring-blue-400 dark:border-blue-700 dark:bg-blue-900/20"
                      )}
                    >
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="text-[10px] font-bold text-slate-500 dark:text-slate-300">{objectLabel}</span>
                        <div className="flex items-center gap-1">
                          {activeRenderExt === 'pdf' && page > 0 && <span className="text-[10px] text-slate-400">{`第${Math.round(page)}页`}</span>}
                          <span className="text-[10px] text-slate-400">{Math.round((Number(hit.confidence || 0) || 0) * 100)}%</span>
                        </div>
                      </div>
                      <p className="line-clamp-2 text-[11px] leading-relaxed text-slate-700 dark:text-slate-200">
                        {snippet || objectId || "溯源片段"}
                      </p>
                      {locatorSummary && (
                        <p className="mt-1 text-[10px] text-slate-500 dark:text-slate-400">
                          {locatorSummary}
                        </p>
                      )}

                      {objectType === 'figure' && figureModes.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {figureModes.map((mode) => (
                            <span
                              key={`${traceKey}-mode-${mode}`}
                              className="rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700 dark:bg-amber-900/20 dark:text-amber-300"
                            >
                              {modeLabelMap[mode] || mode}
                            </span>
                          ))}
                        </div>
                      )}

                      {artifactUrl && (
                        <div className="mt-2 overflow-hidden rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
                          <a href={artifactUrl} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                            <img
                              src={artifactUrl}
                              alt={`${objectLabel}-preview-${idx + 1}`}
                              className="h-40 w-full object-contain bg-white p-1 dark:bg-slate-900 sm:h-56"
                              loading="lazy"
                            />
                          </a>
                        </div>
                      )}

                      {objectType === 'table' && tableRows.length > 0 && (
                        <div className="mt-2 overflow-x-auto rounded-md border border-slate-200 dark:border-slate-700">
                          <table className="min-w-full text-[11px] text-slate-700 dark:text-slate-200">
                            <thead className="bg-slate-100 dark:bg-slate-800">
                              <tr>
                                {(tableHeaders.length > 0 ? tableHeaders : tableRows[0]).map((header, hIdx) => (
                                  <th key={`tbl-h-${idx}-${hIdx}`} className="border-b border-r border-slate-200 px-1.5 py-1 text-left font-bold dark:border-slate-700">
                                    {header || `列${hIdx + 1}`}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {tableRows.slice(0, 3).map((row, rIdx) => (
                                <tr key={`tbl-r-${idx}-${rIdx}`} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800/50">
                                  {(tableHeaders.length > 0 ? tableHeaders : row).map((_, cIdx) => (
                                    <td key={`tbl-c-${idx}-${rIdx}-${cIdx}`} className="max-w-[180px] border-b border-r border-slate-100 px-1.5 py-1 align-top break-words dark:border-slate-800">
                                      {String(row[cIdx] ?? "").trim() || "—"}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {objectType === 'figure' && figureKeyPoints.length > 0 && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {figureKeyPoints.join("；")}
                        </div>
                      )}

                      {objectType === 'figure' && figureDfRows.length > 0 && (
                        <div className="mt-2 overflow-x-auto rounded-md border border-slate-200 dark:border-slate-700">
                          <table className="min-w-full text-[10px] text-slate-700 dark:text-slate-200">
                            <thead className="bg-slate-100 dark:bg-slate-800">
                              <tr>
                                {(figureDfHeaders.length > 0 ? figureDfHeaders : figureDfRows[0]).map((header, hIdx) => (
                                  <th key={`fig-df-h-${idx}-${hIdx}`} className="border-b border-r border-slate-200 px-1.5 py-1 text-left font-bold dark:border-slate-700">
                                    {header || `列${hIdx + 1}`}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {figureDfRows.map((row, rIdx) => (
                                <tr key={`fig-df-r-${idx}-${rIdx}`} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800/50">
                                  {(figureDfHeaders.length > 0 ? figureDfHeaders : row).map((_, cIdx) => (
                                    <td key={`fig-df-c-${idx}-${rIdx}-${cIdx}`} className="max-w-[160px] border-b border-r border-slate-100 px-1.5 py-1 align-top break-words dark:border-slate-800">
                                      {String(row[cIdx] ?? "").trim() || "—"}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {objectType === 'figure' && (figureTopologyNodes > 0 || figureTopologyEdges > 0) && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {`拓扑节点 ${figureTopologyNodes} · 拓扑连边 ${figureTopologyEdges}`}
                        </div>
                      )}

                      {objectType === 'figure' && figureTextBlocks.length > 0 && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {figureTextBlocks.join("；")}
                        </div>
                      )}

                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            void writeClipboard(snippet || objectId || "", "已复制溯源片段。");
                          }}
                          className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[10px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
                        >
                          <Copy size={11} />
                          复制片段
                        </button>
                        {objectType === 'table' && tableRows.length > 0 && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              void writeClipboard(
                                tablePreviewToTsv(
                                  tableHeaders.length > 0 ? tableHeaders : tableRows[0],
                                  tableRows
                                ),
                                "已复制表格内容（TSV）。"
                              );
                            }}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[10px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
                          >
                            <Copy size={11} />
                            复制表格
                          </button>
                        )}
                        {artifactUrl && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              void writeClipboard(artifactUrl, "已复制截图链接");
                            }}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[10px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
                          >
                            <Copy size={11} />
                            {"复制链接"}
                          </button>
                        )}
                        {artifactUrl && (
                          <a
                            href={artifactUrl}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[10px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
                          >
                            <ExternalLink size={11} />
                            查看截图
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-slate-400 dark:text-slate-500">暂无相关溯源信息</p>
            )}
          </div>

          <div className="flex-1 min-h-0 space-y-2 overflow-y-auto custom-scrollbar bg-slate-50/30 p-3 dark:bg-slate-900/30">
            {errorMessage && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-600 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                <div className="flex items-start gap-2">
                  <AlertCircle size={14} className="mt-0.5 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              </div>
            )}

            {!activeDoc && !errorMessage && (
              <div className="flex h-full flex-col items-center justify-center text-center select-none">
                <ScanLine size={32} strokeWidth={1} className="mb-2 opacity-20 text-slate-400 dark:text-slate-500" />
                <p className="text-xs text-slate-400 dark:text-slate-500">暂无抽取结果</p>
              </div>
            )}

            {activeDoc && activeDoc.errors.length > 0 && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                {activeDoc.errors.map((e, i) => (
                  <div key={i} className="flex gap-2">
                    <AlertCircle size={12} className="mt-0.5 shrink-0" />
                    <span>{e}</span>
                  </div>
                ))}
              </div>
            )}

            {activeDoc && (activeDoc.soft_warnings?.length ?? 0) > 0 && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-xs text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
                {(activeDoc.soft_warnings ?? []).slice(0, 4).map((warn, i) => (
                  <div key={i} className="flex gap-2">
                    <AlertCircle size={12} className="mt-0.5 shrink-0" />
                    <span>{warn}</span>
                  </div>
                ))}
              </div>
            )}

            {fieldItems.map((item) => (
              <div
                key={item.key}
                onClick={() => {
                  setActiveFieldKey(item.key);
                  const hitIndex = traceHits.findIndex(
                    (hit) =>
                      String(hit.object_type || '').toLowerCase() === 'field' &&
                      String(hit.object_id || '').toLowerCase() === item.key.toLowerCase()
                  );
                  if (hitIndex >= 0) {
                    const hit = traceHits[hitIndex];
                    setActiveTraceKey(toTraceHitKey(hit, hitIndex));
                  }
                  if (activeRenderExt === "pdf" && item.pageNumber) {
                    setPdfPage(item.pageNumber);
                  }
                }}
                onMouseEnter={() => setActiveFieldKey(item.key)}
                onMouseLeave={() => setActiveFieldKey(null)}
                className={cn(
                  "cursor-pointer rounded-xl border p-2.5 transition-all duration-200",
                  activeFieldKey === item.key
                    ? "border-blue-500 bg-white shadow-sm ring-1 ring-blue-500 dark:bg-slate-900"
                    : "border-slate-200 bg-white hover:border-blue-300 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-blue-700"
                )}
              >
                <div className="mb-1 flex items-start justify-between gap-2">
                  <span className={cn("text-[10px] font-bold tracking-wide", activeFieldKey === item.key ? "text-blue-600 dark:text-blue-300" : "text-slate-500 dark:text-slate-400")}>
                    {item.label}
                  </span>
                  <div className="flex items-center gap-1.5">
                    {activeRenderExt === "pdf" && item.pageNumber && <span className="text-[10px] text-slate-400">{`第${item.pageNumber}页`}</span>}
                    <span
                      className={cn(
                        "rounded-full border px-1.5 py-0.5 text-[9px] font-bold",
                        item.confidence > 0.8
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300"
                          : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300"
                      )}
                    >
                      {Math.floor(item.confidence * 100)}%
                    </span>
                  </div>
                </div>

                <div className="break-all font-mono text-sm leading-snug text-slate-800 dark:text-slate-200">{item.valueText}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
      {showAssistantHelp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in zoom-in-95 duration-200">
          <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
            <div className="flex items-center justify-between border-b border-slate-100 p-4 dark:border-slate-800">
              <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                <Bot className="text-blue-500" size={20} />
                信息提取助手功能说明
              </h3>
              <button 
                onClick={() => setShowAssistantHelp(false)}
                className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300 transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              <div className="flex gap-3">
                <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 font-bold">1</div>
                <div>
                  <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">智能解析与提取</h4>
                  <p>上传文档后，助手会自动分析文档结构，您可以直接查看右侧提取结果，或在下方对话框输入指令（如“提取发票金额”）进行定向提取。</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400 font-bold">2</div>
                <div>
                  <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">多模态溯源定位</h4>
                  <p>点击提取结果中的字段，系统会自动定位到文档原文位置。支持文字、表格、印章及图片的精准溯源。</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400 font-bold">3</div>
                <div>
                  <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">交互式结果修正</h4>
                  <p>如果对结果不满意，可直接告诉助手“金额不对，应该是xxx”，助手会根据反馈进行修正并重新定位。</p>
                </div>
              </div>
            </div>
            <div className="bg-slate-50 p-4 text-center dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-800">
              <button 
                onClick={() => setShowAssistantHelp(false)}
                className="px-6 py-2 rounded-xl bg-blue-600 text-white font-bold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-500/20 text-sm"
              >
                开始使用
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
