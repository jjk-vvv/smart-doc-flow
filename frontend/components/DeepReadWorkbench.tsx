import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  Braces,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  PlayCircle,
  ScanLine,
  Trash2,
  UploadCloud,
  File,
  Settings,
  ChevronRight,
  Layers,
  Cpu,
  Zap,
  ZoomIn,
  ZoomOut,
  RotateCw,
  Maximize,
  X,
  Search,
  Plus
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import {
  readExtractionDocuments,
  writeExtractionDocuments,
  type ExtractionDocument,
  type ExtractionEntity,
} from '../lib/extractionStore';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type DocumentResult = ExtractionDocument;

type ExtractResponse = {
  documents: DocumentResult[];
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

const DEFAULT_SCHEMA = {
  fields: {
    contract_amount: 'number',
    start_date: 'string',
    end_date: 'string',
    tax_rate: 'number',
    region: 'string',
  },
  dependencies: {
    tax_rate: ['region'],
  },
};

const ALLOWED_EXTENSIONS = new Set(['pdf', 'docx', 'xlsx', 'txt', 'md']);

const isAllowedFile = (file: File) => {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  return ALLOWED_EXTENSIONS.has(ext);
};

const fileExt = (name: string) => name.split('.').pop()?.toLowerCase() ?? '';

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

export const DeepReadWorkbench: React.FC<{ isSidebarCollapsed?: boolean }> = ({ isSidebarCollapsed = false }) => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [schemaText, setSchemaText] = useState<string>(JSON.stringify(DEFAULT_SCHEMA, null, 2));
  const [documents, setDocuments] = useState<DocumentResult[]>([]);
  const [activeDocIndex, setActiveDocIndex] = useState(0);
  const [activeFieldKey, setActiveFieldKey] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [infoMessage, setInfoMessage] = useState('每批最多上传 5 个文件。');
  const [showSchema, setShowSchema] = useState(false); // UI Toggle
  
  // Viewport Controls
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeDoc = documents[activeDocIndex] ?? null;
  const activeSourceFile = useMemo(() => {
    if (!activeDoc || selectedFiles.length === 0) return null;

    const exact = selectedFiles.find((file) => file.name === activeDoc.file_name);
    if (exact) return exact;

    const targetName = activeDoc.file_name.toLowerCase();
    const insensitive = selectedFiles.find((file) => file.name.toLowerCase() === targetName);
    if (insensitive) return insensitive;

    const byIndex = selectedFiles[activeDocIndex] ?? null;
    if (byIndex && fileExt(byIndex.name) === fileExt(activeDoc.file_name)) return byIndex;

    return byIndex;
  }, [activeDoc, activeDocIndex, selectedFiles]);
  const activeExt = activeDoc ? fileExt(activeDoc.file_name) : '';
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string>('');
  const [pdfPage, setPdfPage] = useState(1);

  useEffect(() => {
    const cached = readExtractionDocuments();
    if (cached.length === 0) return;
    setDocuments(cached);
    setInfoMessage(`Loaded ${cached.length} cached extraction result(s).`);
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
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(activeSourceFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [activeSourceFile]);

  useEffect(() => {
    let cancelled = false;
    if (!activeSourceFile || !['txt', 'md'].includes(activeExt)) {
      setPreviewText('');
      return () => {
        cancelled = true;
      };
    }
    activeSourceFile.text().then((text) => {
      if (cancelled) return;
      const maxChars = 12000;
      setPreviewText(text.length > maxChars ? `${text.slice(0, maxChars)}\n\n... [truncated]` : text);
    });
    return () => {
      cancelled = true;
    };
  }, [activeSourceFile, activeExt]);

  const fieldItems = useMemo<FieldItem[]>(() => {
    if (!activeDoc) return [];

    const entries = Object.entries(activeDoc.result) as Array<[string, ExtractionEntity]>;
    return entries.map(([fieldName, entity]) => ({
      bbox: Array.isArray(entity.bbox) ? entity.bbox : [],
      key: fieldName,
      label: toFieldLabel(fieldName),
      valueText: entity.value == null ? 'null' : String(entity.value),
      confidence: entity.confidence ?? 0,
      refId: entity.source_ref_id,
      pageNumber: toPageNumber(Array.isArray(entity.bbox) ? entity.bbox : []),
    }));
  }, [activeDoc]);

  const inferredPdfPageCount = useMemo(() => {
    if (activeExt !== 'pdf') return 1;
    const maxByRefs = fieldItems.reduce((maxPage, item) => {
      if (item.pageNumber == null) return maxPage;
      return Math.max(maxPage, item.pageNumber);
    }, 1);
    return Math.max(1, maxByRefs);
  }, [activeExt, fieldItems]);

  const currentPdfPage = Math.min(Math.max(pdfPage, 1), inferredPdfPageCount);

  useEffect(() => {
    if (activeExt !== 'pdf') return;
    if (pdfPage !== currentPdfPage) {
      setPdfPage(currentPdfPage);
    }
  }, [activeExt, currentPdfPage, pdfPage]);

  const overlayItems = useMemo(() => {
    if (activeExt !== 'pdf') {
      return fieldItems.filter((item) => item.bbox.length === 5);
    }
    return fieldItems.filter((item) => item.bbox.length === 5 && item.pageNumber === currentPdfPage);
  }, [activeExt, currentPdfPage, fieldItems]);

  const avgConfidence = useMemo(() => {
    if (fieldItems.length === 0) return 0;
    const total = fieldItems.reduce((acc, item) => acc + item.confidence, 0);
    return Math.round((total / fieldItems.length) * 100);
  }, [fieldItems]);

  const onSelectFiles = (event: React.ChangeEvent<HTMLInputElement>) => {
    const incomingRaw = Array.from(event.target.files ?? []);
    const incoming = incomingRaw.filter(isAllowedFile);
    const rejectedCount = incomingRaw.length - incoming.length;
    if (incoming.length === 0) {
      if (rejectedCount > 0) {
        setInfoMessage('未添加任何文件，仅支持 PDF/DOCX/XLSX/TXT/MD。');
      }
      return;
    }

    const byIdentity = new Map<string, File>();
    [...selectedFiles, ...incoming].forEach((file) => {
      const key = `${file.name}:${file.size}:${file.lastModified}`;
      byIdentity.set(key, file);
    });

    const merged = Array.from(byIdentity.values());
    const limited = merged.slice(0, 5);

    setSelectedFiles(limited);
    if (merged.length > 5) {
      setInfoMessage('批处理上限为 5 个文件，超出部分已忽略。');
    } else if (rejectedCount > 0) {
      setInfoMessage(`已忽略 ${rejectedCount} 个不支持的文件，仅支持 PDF/DOCX/XLSX/TXT/MD。`);
    } else {
      setInfoMessage(`已选择 ${limited.length} 个文件，可开始抽取。`);
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const clearAllFiles = () => {
    setSelectedFiles([]);
    setDocuments([]);
    setActiveDocIndex(0);
    setActiveFieldKey(null);
    setPdfPage(1);
    setErrorMessage('');
    setInfoMessage('文件队列已清空。');
    setScale(1);
    setRotation(0);
  };

  const runExtraction = async () => {
    if (selectedFiles.length === 0) {
      setErrorMessage('请至少上传一个文件。');
      return;
    }

    let schemaObj: unknown;
    try {
      schemaObj = JSON.parse(schemaText);
    } catch (error) {
      setErrorMessage(error instanceof Error ? `规则模板 JSON 格式错误：${error.message}` : '规则模板 JSON 格式错误。');
      return;
    }

    setErrorMessage('');
    setActiveFieldKey(null);
    setIsProcessing(true);
    setInfoMessage(`正在执行 ${selectedFiles.length} 个文件的抽取...`);

    try {
      const formData = new FormData();
      selectedFiles.forEach((file) => formData.append('files', file));
      formData.append('schema', JSON.stringify(schemaObj));

      const response = await fetch('/extract/batch', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || '抽取请求失败');
      }

      const payload = (await response.json()) as ExtractResponse;
      if (!payload.documents || payload.documents.length === 0) {
        throw new Error('后端未返回抽取结果');
      }

      setDocuments(payload.documents);
      writeExtractionDocuments(payload.documents);
      setActiveDocIndex(0);
      setPdfPage(1);

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
        const sourceText = sourceSet.size > 0 ? Array.from(sourceSet).slice(0, 3).join(', ') : 'n/a';
        const figureSourceText = figureSourceSet.size > 0 ? Array.from(figureSourceSet).slice(0, 3).join(', ') : 'n/a';
        setInfoMessage(
          `已完成 ${payload.documents.length} 份文档抽取，缓存命中 ${cacheHits} 份，识别表格 ${totalTables} 张（来源: ${sourceText}），识别图像 ${totalFigures} 张（来源: ${figureSourceText}）。`
        );
      }
    } catch (error) {
      console.error(error);
      setErrorMessage(error instanceof Error ? error.message : '抽取失败');
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
    anchor.download = `module2-extraction-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
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

  return (
    <div className="relative h-[calc(100vh-2rem)] flex gap-4 overflow-hidden p-2 text-foreground isolate">
      {/* Background Ambience - Enhances Glassmorphism */}
      <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] bg-blue-100/40 dark:bg-primary/10 rounded-full blur-[120px] pointer-events-none -z-10 animate-[pulse_8s_infinite]" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] bg-indigo-100/40 dark:bg-blue-600/10 rounded-full blur-[100px] pointer-events-none -z-10 animate-[pulse_10s_infinite_reverse]" />

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.xlsx,.txt,.md"
        multiple
        className="hidden"
        onChange={onSelectFiles}
      />

      {/* LEFT SIDEBAR: Controls & Inputs */}
      <div className="w-[340px] flex flex-col gap-4 min-w-[300px] shrink-0">
        {/* Brand Header */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 relative overflow-hidden group shadow-sm border border-slate-100 dark:border-slate-800">
            <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity duration-500">
                <ScanLine size={80} className="text-primary rotate-12" />
            </div>
            <div className="relative z-10">
                <div className="flex items-center gap-3 mb-3">
                    <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400">
                        <FileText size={22} strokeWidth={2.5} />
                    </div>
                    <h2 className="text-xl font-bold font-['Microsoft_YaHei'] tracking-tight text-slate-800 dark:text-slate-100">
                        智能文档解析
                    </h2>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed font-medium font-['Microsoft_YaHei']">
                    基于 Gemini 多模态大模型的文档结构化抽取引擎。支持 PDF/DOCX/XLSX/TXT/MD 批量处理与字段级溯源。
                </p>
            </div>
        </div>

        {/* Action Panel */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl flex-1 flex flex-col overflow-hidden border border-slate-100 dark:border-slate-800 shadow-sm">
            <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <h3 className="text-sm font-bold font-['Microsoft_YaHei'] flex items-center gap-2 text-slate-700 dark:text-slate-200">
                    <Layers size={16} className="text-blue-500" />
                    任务队列
                </h3>
                <span className={cn(
                    "text-[10px] px-2.5 py-1 rounded-full font-bold transition-colors",
                    selectedFiles.length > 0 ? "bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400" : "bg-slate-100 dark:bg-slate-800 text-slate-400"
                )}>
                    {selectedFiles.length}/5
                </span>
            </div>
            
            <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-3">
                {selectedFiles.length === 0 ? (
                    <div 
                        onClick={() => fileInputRef.current?.click()}
                        className="h-full min-h-[160px] border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-2xl flex flex-col items-center justify-center text-slate-400 hover:border-blue-400 hover:bg-blue-50/50 dark:hover:bg-blue-900/10 transition-all cursor-pointer group p-6 text-center"
                    >
                        <div className="w-16 h-16 rounded-full bg-slate-50 dark:bg-slate-800 flex items-center justify-center mb-4 group-hover:scale-110 group-hover:bg-blue-100 dark:group-hover:bg-blue-900/30 group-hover:text-blue-600 transition-all duration-300">
                            <UploadCloud size={32} />
                        </div>
                        <p className="text-sm font-bold font-['Microsoft_YaHei'] text-slate-600 dark:text-slate-300 group-hover:text-blue-600 transition-colors">点击上传文档</p>
                        <p className="text-[10px] opacity-60 mt-2 font-['Microsoft_YaHei']">支持 PDF, DOCX, XLSX, TXT, MD</p>
                        <p className="text-[10px] opacity-40 mt-1 font-['Microsoft_YaHei']">每次最多上传 5 个文件</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        <button 
                            onClick={() => fileInputRef.current?.click()}
                            className="w-full border border-dashed border-slate-200 dark:border-slate-700 rounded-xl p-3 flex items-center justify-center gap-2 text-xs font-bold text-slate-500 hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50/50 transition-all group"
                        >
                            <div className="p-1 rounded bg-slate-100 dark:bg-slate-800 group-hover:bg-white transition-colors">
                                <UploadCloud size={14} /> 
                            </div>
                            添加更多文件
                        </button>
                        {selectedFiles.map((file, index) => (
                            <div key={`${file.name}:${index}`} className="flex items-center justify-between p-3 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50 group hover:border-blue-200 hover:bg-white dark:hover:bg-slate-800 hover:shadow-sm transition-all">
                                <div className="flex items-center gap-3 overflow-hidden">
                                    <div className="w-10 h-10 rounded-lg bg-white dark:bg-slate-900 flex items-center justify-center text-slate-400 group-hover:text-blue-500 transition-colors shadow-sm">
                                        <File size={18} />
                                    </div>
                                    <div className="flex flex-col min-w-0">
                                        <span className="text-xs font-bold truncate text-slate-700 dark:text-slate-200">{file.name}</span>
                                        <span className="text-[10px] text-slate-400 font-mono">{(file.size / 1024).toFixed(1)} KB</span>
                                    </div>
                                </div>
                                <button onClick={() => removeFile(index)} className="opacity-0 group-hover:opacity-100 p-2 hover:bg-red-50 hover:text-red-500 rounded-lg transition-all">
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="p-5 border-t border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 space-y-4">
                 <div className="flex gap-3">
                    <button 
                        onClick={() => setShowSchema(!showSchema)}
                        className={cn(
                            "flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-xs font-bold border transition-all",
                            showSchema 
                            ? "bg-blue-50 border-blue-200 text-blue-600 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-400" 
                            : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                        )}
                    >
                        <Settings size={14} />
                        {showSchema ? '隐藏规则' : '配置规则'}
                    </button>
                    {selectedFiles.length > 0 && (
                        <button 
                            onClick={clearAllFiles}
                            className="px-4 py-3 rounded-xl text-xs font-bold border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-red-600 hover:bg-red-50 hover:border-red-200 transition-all"
                        >
                            清空
                        </button>
                    )}
                 </div>
                 
                 <button
                    onClick={runExtraction}
                    disabled={isProcessing || selectedFiles.length === 0}
                    className={cn(
                        'w-full flex items-center justify-center gap-2 rounded-xl py-4 text-sm font-bold shadow-lg transition-all active:scale-[0.98] relative overflow-hidden',
                        isProcessing || selectedFiles.length === 0
                        ? 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-600 cursor-not-allowed shadow-none'
                        : 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-blue-500/25 hover:shadow-blue-500/40 hover:brightness-110'
                    )}
                >
                    {isProcessing && (
                         <div className="absolute inset-0 bg-white/20 animate-[shimmer_2s_infinite] skew-x-12 -translate-x-full" />
                    )}
                    {isProcessing ? <Loader2 size={18} className="animate-spin" /> : <PlayCircle size={18} />}
                    {isProcessing ? '正在智能抽取...' : '开始抽取'}
                </button>
            </div>
        </div>
      </div>

      {/* CENTER: Workbench Area */}
      <div className="flex-1 flex flex-col gap-4 min-w-0 relative">
        {/* Schema Editor Overlay */}
        {showSchema && (
            <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[90%] max-w-2xl z-50 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl shadow-2xl rounded-2xl animate-in slide-in-from-top-4 fade-in duration-200 flex flex-col max-h-[500px] border border-slate-200 dark:border-slate-700 overflow-hidden ring-1 ring-slate-900/5">
                    <div className="p-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/50">
                    <h3 className="text-xs font-bold font-['Microsoft_YaHei'] flex items-center gap-2 text-slate-700 dark:text-slate-200">
                        <Braces size={14} className="text-blue-500" /> JSON 提取规则配置
                    </h3>
                    <div className="flex gap-2">
                            <button onClick={() => setSchemaText(JSON.stringify(DEFAULT_SCHEMA, null, 2))} className="text-[10px] text-blue-500 hover:underline px-2 font-medium">恢复默认</button>
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

            {/* Floating Toolbar */}
            <div className="absolute top-6 left-1/2 -translate-x-1/2 z-40 h-12 pl-4 pr-2 rounded-2xl bg-white dark:bg-slate-900 shadow-[0_8px_30px_rgb(0,0,0,0.12)] border border-slate-200 dark:border-slate-700 flex items-center gap-2 transition-all select-none max-w-[98%]">
                <div className="flex items-center gap-1 overflow-hidden pl-0 min-w-0 flex-1">
                     {activeDoc ? (
                        <>
                            <div className="flex flex-col min-w-0 max-w-[180px]">
                                <span className="text-sm font-bold font-['Microsoft_YaHei'] truncate text-slate-900 dark:text-slate-100">{activeDoc.file_name}</span>
                                <span className="text-[10px] font-bold font-['Microsoft_YaHei'] text-slate-500 flex items-center gap-1.5">
                                    <span className={cn("w-2 h-2 rounded-full shrink-0", activeDoc.cached ? "bg-emerald-500" : "bg-amber-500")} />
                                    <span className="truncate">{activeDoc.cached ? "已缓存" : "实时预览"}</span>
                                </span>
                            </div>
                        </>
                     ) : (
                         <div className="flex items-center gap-1 text-slate-900 dark:text-slate-100 pl-0 pr-1">
                           <Maximize size={16} strokeWidth={2.5} className="shrink-0" />
                           <span className="text-sm font-bold font-['Microsoft_YaHei'] whitespace-nowrap">
                               {isSidebarCollapsed ? "预览视窗" : "预览"}
                           </span>
                        </div>
                     )}
                </div>

                <div className="h-5 w-px bg-slate-200 dark:bg-slate-700 shrink-0" />

                <div className="flex items-center gap-1 shrink-0">
                    <button onClick={handleZoomOut} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl text-slate-700 hover:text-blue-700 transition-all active:scale-95 shrink-0"><ZoomOut size={16} strokeWidth={2}/></button>
                    <span className="text-xs font-bold font-mono w-10 text-center text-slate-900 dark:text-slate-100 shrink-0">{Math.round(scale * 100)}%</span>
                    <button onClick={handleZoomIn} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl text-slate-700 hover:text-blue-700 transition-all active:scale-95 shrink-0"><ZoomIn size={16} strokeWidth={2}/></button>
                    <button onClick={handleRotate} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl text-slate-700 hover:text-blue-700 transition-all ml-0.5 active:scale-95 shrink-0"><RotateCw size={16} strokeWidth={2}/></button>
                    <button onClick={handleResetView} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl text-slate-700 hover:text-blue-700 transition-all active:scale-95 shrink-0" title="重置视图"><Maximize size={16} strokeWidth={2}/></button>
                </div>

                <div className="h-5 w-px bg-slate-200 dark:bg-slate-700 shrink-0" />

                {activeExt === 'pdf' && (
                    <>
                        <div className="flex items-center gap-1 shrink-0">
                            <button
                                onClick={handlePrevPdfPage}
                                disabled={currentPdfPage <= 1}
                                className={cn(
                                    "p-2 rounded-xl transition-all active:scale-95 shrink-0",
                                    currentPdfPage > 1
                                        ? "text-slate-700 hover:text-blue-700 hover:bg-slate-100 dark:hover:bg-slate-800"
                                        : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                )}
                                title="Previous page"
                            >
                                <ChevronRight size={16} className="rotate-180" />
                            </button>
                            <span className="text-xs font-bold font-mono min-w-[64px] text-center text-slate-900 dark:text-slate-100 shrink-0">
                                P{currentPdfPage}/{inferredPdfPageCount}
                            </span>
                            <button
                                onClick={handleNextPdfPage}
                                disabled={currentPdfPage >= inferredPdfPageCount}
                                className={cn(
                                    "p-2 rounded-xl transition-all active:scale-95 shrink-0",
                                    currentPdfPage < inferredPdfPageCount
                                        ? "text-slate-700 hover:text-blue-700 hover:bg-slate-100 dark:hover:bg-slate-800"
                                        : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                )}
                                title="Next page"
                            >
                                <ChevronRight size={16} />
                            </button>
                        </div>
                        <div className="h-5 w-px bg-slate-200 dark:bg-slate-700 shrink-0" />
                    </>
                )}

                <button
                    onClick={exportResults}
                    disabled={documents.length === 0}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold font-['Microsoft_YaHei'] transition-all shadow-sm active:scale-95 shrink-0 whitespace-nowrap",
                        documents.length > 0
                        ? "bg-blue-600 text-white hover:bg-blue-700 hover:shadow-blue-500/25"
                        : "opacity-100 bg-slate-100 dark:bg-slate-800 text-slate-500 cursor-not-allowed"
                    )}
                >
                    <Download size={14} strokeWidth={2.5} />
                    <span>导出</span>
                </button>
            </div>

            <div className="flex-1 overflow-auto flex items-center justify-center p-8 custom-scrollbar relative z-10">
                 {!activeDoc ? (
                   <div className="flex flex-col items-center justify-center h-full select-none pointer-events-none perspective-1000">
                       {/* Ethereal Floating Stack */}
                       <div className="relative w-40 h-48 mb-12 transform-style-3d group">
                           {/* Animated Background Glow */}
                           <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-blue-100/50 dark:bg-blue-500/10 rounded-full blur-[80px] animate-pulse-slow" />
                           
                           {/* Card 3 (Bottom) */}
                           <div className="absolute inset-0 bg-slate-50 dark:bg-slate-800/80 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-lg transform translate-z-[-20px] scale-90 translate-y-4 rotate-[-6deg] opacity-60 transition-transform duration-700 group-hover:rotate-[-12deg] group-hover:translate-y-6" />
                           
                           {/* Card 2 (Middle) */}
                           <div className="absolute inset-0 bg-white dark:bg-slate-900/90 rounded-2xl border border-slate-200 dark:border-slate-700/80 shadow-xl backdrop-blur-sm transform translate-z-[-10px] scale-95 translate-y-2 rotate-[-3deg] opacity-80 transition-transform duration-700 group-hover:rotate-[-6deg] group-hover:translate-y-3" />
                           
                           {/* Card 1 (Top - Main) */}
                           <div className="absolute inset-0 bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-2xl flex flex-col items-center justify-center overflow-hidden transition-transform duration-700 group-hover:-translate-y-2 group-hover:rotate-2">
                               {/* Scanning Line Effect */}
                               <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-blue-500/50 to-transparent blur-[2px] animate-scan-slow opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                               
                               {/* Abstract Content Skeleton */}
                               <div className="w-24 space-y-3 opacity-20 dark:opacity-10">
                                   <div className="h-2 w-12 bg-slate-400 rounded-full" />
                                   <div className="h-1.5 w-full bg-slate-400 rounded-full" />
                                   <div className="h-1.5 w-5/6 bg-slate-400 rounded-full" />
                                   <div className="h-1.5 w-4/6 bg-slate-400 rounded-full" />
                                   <div className="h-24 w-full bg-slate-100 dark:bg-slate-800 rounded-lg mt-4 border border-slate-200 dark:border-slate-700" />
                               </div>

                               {/* Floating Plus Icon */}
                               <div className="absolute inset-0 flex items-center justify-center pt-16">
                                   <div className="w-14 h-14 rounded-2xl bg-white dark:bg-slate-800 shadow-xl shadow-blue-500/10 border border-slate-100 dark:border-slate-700 flex items-center justify-center text-blue-500 transform transition-transform duration-500 group-hover:scale-110 group-hover:rotate-90 relative overflow-hidden">
                                       <div className="absolute inset-0 bg-blue-50/50 dark:bg-blue-900/20 opacity-0 group-hover:opacity-100 transition-opacity" />
                                       <Plus size={28} strokeWidth={2.5} className="relative z-10" />
                                   </div>
                               </div>
                           </div>
                       </div>

                       {/* Text Content */}
                       <div className="text-center space-y-4 relative z-10">
                           <h3 className="text-xl font-bold font-['Microsoft_YaHei'] tracking-tight text-slate-700 dark:text-slate-200">
                               智能文档解析
                           </h3>
                           <div className="flex items-center justify-center gap-3">
                               <div className="h-px w-8 bg-gradient-to-r from-transparent to-slate-200 dark:to-slate-700" />
                               <p className="text-xs text-slate-400 font-medium font-['Microsoft_YaHei']">
                                   请选择或上传文档以开始深度结构化解析
                               </p>
                               <div className="h-px w-8 bg-gradient-to-l from-transparent to-slate-200 dark:to-slate-700" />
                           </div>
                       </div>
                   </div>
                ) : (
                   <div 
                       className="relative shadow-2xl dark:shadow-black/50 transition-all duration-300 ease-out origin-center will-change-transform"
                       style={{ 
                           transform: `scale(${scale}) rotate(${rotation}deg)`,
                           transition: isProcessing ? 'none' : 'transform 0.3s ease-out'
                       }}
                   >
                        <div className="w-[595px] h-[842px] relative bg-white dark:bg-[#1a1b26] ring-1 ring-slate-200/50 dark:ring-white/10 shadow-2xl overflow-hidden">
                            {activeExt === 'pdf' && previewUrl ? (
                              <iframe
                                title={`preview-${activeDoc.file_name}`}
                                src={`${previewUrl}#page=${currentPdfPage}&toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
                                className="absolute inset-0 w-full h-full border-0 pointer-events-none"
                              />
                            ) : ['txt', 'md'].includes(activeExt) ? (
                              <div className="absolute inset-0 p-6 overflow-auto bg-slate-50/70 dark:bg-slate-900/60">
                                <pre className="text-[10px] leading-5 whitespace-pre-wrap break-words font-mono text-slate-700 dark:text-slate-200">
                                  {previewText || '文本预览加载中...'}
                                </pre>
                              </div>
                            ) : (
                              <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8 bg-slate-50/70 dark:bg-slate-900/50">
                                <div className="w-14 h-14 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center mb-4 text-slate-500">
                                  <FileText size={26} />
                                </div>
                                <h4 className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-2">{activeDoc.file_name}</h4>
                                <p className="text-[11px] text-slate-500 dark:text-slate-400 max-w-[320px] leading-relaxed">
                                  {activeSourceFile
                                    ? '当前格式暂不支持浏览器内预览（DOCX/XLSX），已保留抽取定位层与字段明细。'
                                    : '未找到本地原始文件（可能为缓存结果），仅展示字段定位层与抽取结果。'}
                                </p>
                              </div>
                            )}

                            <div className="absolute inset-0 flex items-center justify-center opacity-[0.04] pointer-events-none">
                                <span className="text-6xl font-bold uppercase tracking-widest text-slate-900 dark:text-slate-100 rotate-45 select-none">{activeDoc.file_name}</span>
                            </div>

                            {/* Bounding Boxes */}
                            {overlayItems.map((item) => {
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
                                            {item.pageNumber ? ` (P${item.pageNumber})` : ''}
                                          </div>
                                          <div className="text-slate-300 text-[9px]">{Math.floor(item.confidence * 100)}% Confidence</div>
                                          <div className="absolute bottom-[-4px] left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-900 rotate-45"></div>
                                      </div>
                                  </div>
                                );
                              })}
                         </div>
                    </div>
                 )}
            </div>
            
            {/* Context Bar */}
            <div className="h-9 border-t border-border/50 bg-white/60 dark:bg-slate-900/60 backdrop-blur-md flex items-center justify-between px-4 text-[10px] text-muted-foreground z-20">
                <div className="flex items-center gap-4">
                     <span>{infoMessage}</span>
                </div>
                {activeDoc && (
                    <div className="font-mono opacity-50">
                        REF: {activeDoc.file_hash.substring(0, 8)}...
                    </div>
                )}
            </div>
        </div>
      </div>

      {/* RIGHT SIDEBAR: Results & Stats */}
      <div className="w-[320px] flex flex-col gap-4 min-w-[300px] shrink-0">
         {/* KPI Cards */}
         <div className="grid grid-cols-2 gap-3">
             <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 flex flex-col justify-between h-24 relative overflow-hidden group hover:shadow-md transition-all">
                <div className="absolute -right-3 -bottom-3 opacity-[0.03] group-hover:opacity-[0.08] transition-opacity rotate-12 text-blue-600">
                    <FileText size={80} />
                </div>
                <div className="flex items-center gap-2 mb-1">
                    <div className="p-1.5 rounded-lg bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400">
                        <Layers size={14} />
                    </div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">处理文档</span>
                </div>
                <div className="flex items-baseline gap-1 mt-1">
                    <span className="text-3xl font-bold text-slate-800 dark:text-slate-100 tracking-tight">{documents.length}</span>
                    <span className="text-xs text-slate-400 font-medium">份</span>
                </div>
                <div className="h-1 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden mt-1">
                     <div className="h-full bg-blue-500 transition-all duration-1000 ease-out" style={{ width: documents.length > 0 ? '100%' : '0%' }}></div>
                </div>
             </div>
             <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 flex flex-col justify-between h-24 relative overflow-hidden group hover:shadow-md transition-all">
                <div className="absolute -right-3 -bottom-3 opacity-[0.03] group-hover:opacity-[0.08] transition-opacity rotate-12 text-emerald-600">
                    <CheckCircle2 size={80} />
                </div>
                <div className="flex items-center gap-2 mb-1">
                    <div className={cn("p-1.5 rounded-lg", avgConfidence > 80 ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400" : "bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400")}>
                        <Zap size={14} />
                    </div>
                    <span className="text-[10px] font-bold font-['Microsoft_YaHei'] uppercase tracking-wider text-slate-500">平均置信度</span>
                </div>
                <div className="flex items-baseline gap-1 mt-1">
                    <span className={cn("text-3xl font-bold tracking-tight transition-colors", avgConfidence > 80 ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400")}>
                        {avgConfidence}
                    </span>
                    <span className="text-xs text-slate-400 font-medium">%</span>
                </div>
                <div className="h-1 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden mt-1">
                     <div className={cn("h-full transition-all duration-1000 ease-out", avgConfidence > 80 ? "bg-emerald-500" : "bg-amber-500")} style={{ width: `${avgConfidence}%` }}></div>
                </div>
             </div>
         </div>

         {/* Document Switcher (if multiple) */}
         {documents.length > 1 && (
             <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-2 max-h-32 overflow-y-auto custom-scrollbar space-y-1 shadow-sm">
                 {documents.map((doc, idx) => (
                     <button
                        key={idx}
                        onClick={() => { setActiveDocIndex(idx); setActiveFieldKey(null); }}
                        className={cn(
                            "w-full text-left px-3 py-2.5 rounded-xl text-xs flex items-center justify-between transition-all border",
                            activeDocIndex === idx 
                            ? "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 font-bold border-blue-100 dark:border-blue-800" 
                            : "bg-transparent border-transparent hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                        )}
                     >
                        <span className="truncate max-w-[180px]">{doc.file_name}</span>
                        <div className="flex items-center gap-2">
                             {doc.errors.length > 0 && <AlertCircle size={12} className="text-red-500" />}
                             <span className="text-[10px] opacity-50 font-mono">#{idx + 1}</span>
                        </div>
                     </button>
                 ))}
             </div>
         )}

         {/* Fields List */}
         <div className="flex-1 flex flex-col overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm">
            <div className="p-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50 flex items-center justify-between">
                 <h3 className="text-sm font-bold flex items-center gap-2 text-slate-800 dark:text-slate-200">
                    <ScanLine size={16} className="text-blue-500" />
                    抽取结果
                 </h3>
                 {fieldItems.length > 0 && (
                     <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-400 font-medium">共 {fieldItems.length} 个字段</span>
                     </div>
                 )}
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-3 bg-slate-50/30 dark:bg-slate-900/30">
                 {/* Error Banner */}
                 {errorMessage && (
                    <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 text-red-600 dark:text-red-400 text-xs font-bold flex gap-2 items-start animate-in slide-in-from-top-2">
                        <AlertCircle size={14} className="shrink-0 mt-0.5" />
                        <span className="leading-relaxed">{errorMessage}</span>
                    </div>
                 )}

                 {!activeDoc && !errorMessage && (
                     <div className="h-full flex flex-col items-center justify-center text-slate-300 dark:text-slate-700 gap-4">
                         <div className="p-4 rounded-full bg-slate-50 dark:bg-slate-800 mb-2">
                            <Search size={32} strokeWidth={1.5} />
                         </div>
                         <div className="text-center space-y-1">
                             <p className="text-xs font-bold text-slate-500 dark:text-slate-400">暂无数据</p>
                             <p className="text-[10px] text-slate-400 dark:text-slate-600">请先在左侧开始抽取任务</p>
                         </div>
                     </div>
                 )}

                 {activeDoc && activeDoc.errors.length > 0 && (
                    <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800 text-amber-600 dark:text-amber-400 text-xs space-y-1">
                        {activeDoc.errors.map((e, i) => (
                            <div key={i} className="flex gap-2">
                                <AlertCircle size={12} className="mt-0.5 shrink-0" />
                                <span>{e}</span>
                            </div>
                        ))}
                    </div>
                 )}

                 {fieldItems.map((item) => (
                    <div
                        key={item.key}
                        onClick={() => {
                          setActiveFieldKey(item.key);
                          if (activeExt === 'pdf' && item.pageNumber) {
                            setPdfPage(item.pageNumber);
                          }
                        }}
                        onMouseEnter={() => setActiveFieldKey(item.key)}
                        onMouseLeave={() => setActiveFieldKey(null)}
                        className={cn(
                            "group rounded-xl border p-3 transition-all duration-200 cursor-pointer relative overflow-hidden",
                            activeFieldKey === item.key
                            ? "border-blue-500 shadow-md scale-[1.02] bg-white dark:bg-slate-900 ring-1 ring-blue-500 z-10"
                            : "border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-blue-200 hover:shadow-sm"
                        )}
                    >
                        {activeFieldKey === item.key && (
                            <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500 animate-in fade-in"></div>
                        )}
                        
                        <div className="flex justify-between items-start mb-1.5">
                            <span className={cn(
                                "text-[10px] font-bold font-['Microsoft_YaHei'] uppercase tracking-wider transition-colors",
                                activeFieldKey === item.key ? "text-blue-600 dark:text-blue-400" : "text-slate-500 dark:text-slate-400"
                            )}>
                                {item.label}
                            </span>
                            <div className="flex items-center gap-1.5">
                                {activeExt === 'pdf' && item.pageNumber && (
                                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-300">
                                    P{item.pageNumber}
                                  </span>
                                )}
                                <span className={cn(
                                    "text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-full border",
                                    item.confidence > 0.8 
                                    ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-800" 
                                    : "bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400 border-amber-100 dark:border-amber-800"
                                )}>
                                    {Math.floor(item.confidence * 100)}%
                                </span>
                            </div>
                        </div>
                        
                        <div className="text-sm font-medium text-slate-800 dark:text-slate-200 break-all leading-snug font-mono">
                            {item.valueText}
                        </div>
                        
                        {/* Interactive Confidence Bar */}
                        <div className="mt-2.5 h-1 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                            <div 
                                className={cn("h-full rounded-full transition-all duration-500", item.confidence > 0.8 ? "bg-emerald-500" : "bg-amber-500")}
                                style={{ width: `${item.confidence * 100}%` }}
                            ></div>
                        </div>
                    </div>
                 ))}
            </div>
         </div>
      </div>
    </div>
  );
};
