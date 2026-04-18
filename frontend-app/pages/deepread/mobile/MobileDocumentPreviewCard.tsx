import React, { useEffect, useMemo, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileImage,
  FileSpreadsheet,
  FileText,
  Loader2,
  MonitorPlay,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import { LuckysheetPreview } from '../../../components/LuckysheetPreview';
import { PdfJsViewer, type PdfViewMode } from '../../../components/PdfJsViewer';
import { cn } from '../../../lib/utils';
import { parseErrorMessage } from '../../../shared/api/client';
import {
  resolveExtractArtifactUrlFromTraceHit,
  toAbsoluteExtractUrl,
} from '../../../shared/api/extraction';
import type { ExtractionDocument } from '../../../shared/state/extractionDocuments';
import {
  readWorkbenchSession,
  subscribeWorkbenchSessionUpdates,
  type WorkbenchSessionSnapshot,
} from '../../../shared/state/workbenchSession';
import {
  formatPreviewMetric,
  getFileExtension,
  pickOfficePreviewByFileName,
  pickPersistedWorkbenchFile,
  pickPersistedWorkbenchFileFromDiagnostics,
  pickPersistedWorkbenchFileFromExtractionJob,
  restoreWorkbenchFile,
  toRecord,
} from './documentPreviewRuntime';

type MobileDocumentPreviewCardProps = {
  activeDoc: ExtractionDocument | null;
  preferredBase: string;
  activeSourceFile?: File | null;
};

type PreviewKind = 'pdf' | 'text' | 'spreadsheet' | 'image' | 'unsupported';

const TEXT_EXTENSIONS = new Set(['txt', 'md', 'csv']);
const SPREADSHEET_EXTENSIONS = new Set(['xls', 'xlsx']);
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff']);

const resolvePdfPreviewUrl = (
  document: ExtractionDocument | null,
  preferredBase: string,
  session: WorkbenchSessionSnapshot | null,
): string => {
  const fileName = String(document?.file_name || '').trim();
  const bySession = fileName
    ? pickOfficePreviewByFileName(session?.officePreviewMap || {}, fileName)
    : null;
  const diagnostics = toRecord(document?.diagnostics);
  const byFileResolved = resolveExtractArtifactUrlFromTraceHit(
    {
      artifact_by_file_url: String(
        diagnostics.office_pdf_preview_by_file_url
        || diagnostics.pdf_preview_by_file_url
        || '',
      ).trim(),
      artifact_file_id: String(
        diagnostics.office_pdf_preview_file_id
        || diagnostics.pdf_preview_file_id
        || '',
      ).trim(),
    },
    preferredBase,
  );
  if (byFileResolved) return byFileResolved;

  const direct = String(
    bySession?.pdfUrl
    || diagnostics.office_pdf_preview_url
    || diagnostics.pdf_preview_url
    || '',
  ).trim();
  return direct ? toAbsoluteExtractUrl(direct, preferredBase) : '';
};

const resolveMarkdownArtifactUrl = (
  document: ExtractionDocument | null,
  preferredBase: string,
): string => {
  const diagnostics = toRecord(document?.diagnostics);
  const byFileResolved = resolveExtractArtifactUrlFromTraceHit(
    {
      artifact_by_file_url: String(
        diagnostics.assistant1_source_markdown_artifact_by_file_url
        || diagnostics.markdown_artifact_by_file_url
        || '',
      ).trim(),
      artifact_file_id: String(
        diagnostics.assistant1_source_markdown_artifact_file_id
        || diagnostics.markdown_artifact_file_id
        || '',
      ).trim(),
    },
    preferredBase,
  );
  if (byFileResolved) return byFileResolved;

  const direct = String(
    diagnostics.assistant1_source_markdown_artifact_url
    || diagnostics.markdown_artifact_url
    || '',
  ).trim();
  return direct ? toAbsoluteExtractUrl(direct, preferredBase) : '';
};

const resolveImageArtifactUrl = (
  document: ExtractionDocument | null,
  preferredBase: string,
): string => {
  const diagnostics = toRecord(document?.diagnostics);
  const byFileResolved = resolveExtractArtifactUrlFromTraceHit(
    {
      artifact_by_file_url: String(
        diagnostics.image_preview_by_file_url
        || diagnostics.preview_by_file_url
        || diagnostics.source_artifact_by_file_url
        || diagnostics.artifact_by_file_url
        || '',
      ).trim(),
      artifact_file_id: String(
        diagnostics.image_preview_file_id
        || diagnostics.preview_file_id
        || diagnostics.source_artifact_file_id
        || diagnostics.artifact_file_id
        || '',
      ).trim(),
    },
    preferredBase,
  );
  if (byFileResolved) return byFileResolved;

  const directCandidates = [
    diagnostics.image_preview_url,
    diagnostics.preview_url,
    diagnostics.source_artifact_url,
    diagnostics.artifact_url,
  ];
  for (const candidate of directCandidates) {
    const raw = String(candidate || '').trim();
    if (raw) return toAbsoluteExtractUrl(raw, preferredBase);
  }
  return '';
};

const createPdfScrollRequest = (page: number) => ({
  page,
  nonce: Date.now() + Math.round(Math.random() * 1000),
});

export const MobileDocumentPreviewCard: React.FC<MobileDocumentPreviewCardProps> = ({
  activeDoc,
  preferredBase,
  activeSourceFile = null,
}) => {
  const [workbenchSession, setWorkbenchSession] = useState<WorkbenchSessionSnapshot | null>(() =>
    readWorkbenchSession(),
  );
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [textPreview, setTextPreview] = useState('');
  const [textLoading, setTextLoading] = useState(false);
  const [textError, setTextError] = useState('');
  const [sourceBlobUrl, setSourceBlobUrl] = useState('');
  const [scale, setScale] = useState(1);
  const [pdfViewMode, setPdfViewMode] = useState<PdfViewMode>('fit-width');
  const [pdfPageCount, setPdfPageCount] = useState(1);
  const [pdfVisiblePage, setPdfVisiblePage] = useState(1);
  const [pdfScrollRequest, setPdfScrollRequest] = useState<{ page: number; nonce: number } | null>(
    null,
  );

  useEffect(() => {
    const sync = () => setWorkbenchSession(readWorkbenchSession());
    sync();
    return subscribeWorkbenchSessionUpdates(sync);
  }, []);

  const matchedSessionFile = useMemo(
    () => pickPersistedWorkbenchFile(workbenchSession, activeDoc?.file_name || ''),
    [activeDoc?.file_name, workbenchSession],
  );
  const extractionJobFile = useMemo(
    () => pickPersistedWorkbenchFileFromExtractionJob(
      workbenchSession,
      activeDoc?.file_name || '',
      String(activeDoc?.file_hash || '').trim(),
    ),
    [activeDoc?.file_hash, activeDoc?.file_name, workbenchSession],
  );
  const diagnosticsFile = useMemo(
    () => pickPersistedWorkbenchFileFromDiagnostics(
      toRecord(activeDoc?.diagnostics),
      activeDoc?.file_name || '',
      String(activeDoc?.file_hash || '').trim(),
    ),
    [activeDoc?.diagnostics, activeDoc?.file_hash, activeDoc?.file_name],
  );
  const restoreCandidateFile = matchedSessionFile || extractionJobFile || diagnosticsFile;

  useEffect(() => {
    let cancelled = false;
    if (activeSourceFile) {
      setSourceFile(activeSourceFile);
      setSourceLoading(false);
      setSourceError('');
      return () => {
        cancelled = true;
      };
    }

    if (!restoreCandidateFile) {
      setSourceFile(null);
      setSourceLoading(false);
      setSourceError('');
      return () => {
        cancelled = true;
      };
    }

    const run = async () => {
      setSourceLoading(true);
      setSourceError('');
      try {
        const restored = await restoreWorkbenchFile(restoreCandidateFile, preferredBase);
        if (cancelled) return;
        setSourceFile(restored);
      } catch (error) {
        if (cancelled) return;
        setSourceFile(null);
        setSourceError(error instanceof Error ? error.message : '源文件恢复失败');
      } finally {
        if (!cancelled) setSourceLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [
    activeSourceFile,
    preferredBase,
    restoreCandidateFile?.artifactByFileUrl,
    restoreCandidateFile?.artifactFileId,
    restoreCandidateFile?.artifactPath,
    restoreCandidateFile?.artifactUrl,
    restoreCandidateFile?.key,
    restoreCandidateFile?.lastModified,
    restoreCandidateFile?.name,
  ]);

  useEffect(() => {
    if (!sourceFile) {
      setSourceBlobUrl('');
      return () => undefined;
    }
    const url = URL.createObjectURL(sourceFile);
    setSourceBlobUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [sourceFile]);

  const fileExtension = useMemo(
    () => getFileExtension(sourceFile?.name || activeDoc?.file_name || ''),
    [activeDoc?.file_name, sourceFile?.name],
  );
  const isOfficeDocument = fileExtension === 'doc' || fileExtension === 'docx';
  const isPdfDocument = fileExtension === 'pdf';

  const previewKind = useMemo<PreviewKind>(() => {
    if (!activeDoc) return 'unsupported';
    if (isPdfDocument || isOfficeDocument) return 'pdf';
    if (SPREADSHEET_EXTENSIONS.has(fileExtension)) return 'spreadsheet';
    if (TEXT_EXTENSIONS.has(fileExtension)) return 'text';
    if (IMAGE_EXTENSIONS.has(fileExtension)) return 'image';
    return 'unsupported';
  }, [activeDoc, fileExtension, isOfficeDocument, isPdfDocument]);

  const pdfPreviewUrl = useMemo(
    () => resolvePdfPreviewUrl(activeDoc, preferredBase, workbenchSession),
    [activeDoc, preferredBase, workbenchSession],
  );
  const markdownArtifactUrl = useMemo(
    () => resolveMarkdownArtifactUrl(activeDoc, preferredBase),
    [activeDoc, preferredBase],
  );
  const imageArtifactUrl = useMemo(
    () => resolveImageArtifactUrl(activeDoc, preferredBase),
    [activeDoc, preferredBase],
  );

  const pdfRenderUrl = useMemo(() => {
    if (previewKind !== 'pdf') return '';
    if (isOfficeDocument) return pdfPreviewUrl;
    if (isPdfDocument && sourceBlobUrl) return sourceBlobUrl;
    return pdfPreviewUrl || sourceBlobUrl;
  }, [isOfficeDocument, isPdfDocument, pdfPreviewUrl, previewKind, sourceBlobUrl]);

  const imageRenderUrl = useMemo(() => {
    if (previewKind !== 'image') return '';
    return sourceBlobUrl || imageArtifactUrl;
  }, [imageArtifactUrl, previewKind, sourceBlobUrl]);

  const openExternalUrl = useMemo(() => {
    if (previewKind === 'pdf') return pdfRenderUrl;
    if (previewKind === 'image') return imageRenderUrl;
    if (previewKind === 'text') return markdownArtifactUrl || sourceBlobUrl;
    return '';
  }, [imageRenderUrl, markdownArtifactUrl, pdfRenderUrl, previewKind, sourceBlobUrl]);

  const workbookMetrics = useMemo(() => {
    if (previewKind !== 'spreadsheet') return [];
    const diagnostics = toRecord(activeDoc?.diagnostics);
    return [
      { label: '工作表', value: formatPreviewMetric(diagnostics.xlsx_source_sheet_count) },
      { label: '总行数', value: formatPreviewMetric(diagnostics.xlsx_source_total_rows) },
      { label: '总列数', value: formatPreviewMetric(diagnostics.xlsx_source_total_cols) },
      { label: '非空单元格', value: formatPreviewMetric(diagnostics.xlsx_source_total_nonempty_cells) },
    ];
  }, [activeDoc?.diagnostics, previewKind]);

  useEffect(() => {
    let cancelled = false;
    if (previewKind !== 'text') {
      setTextPreview('');
      setTextLoading(false);
      setTextError('');
      return () => {
        cancelled = true;
      };
    }

    const run = async () => {
      setTextLoading(true);
      setTextError('');
      try {
        let rawText = '';
        if (sourceFile && TEXT_EXTENSIONS.has(fileExtension)) {
          rawText = await sourceFile.text();
        } else if (markdownArtifactUrl) {
          const response = await fetch(markdownArtifactUrl, {
            credentials: 'include',
            cache: 'no-store',
          });
          if (!response.ok) {
            throw new Error(await parseErrorMessage(response));
          }
          rawText = await response.text();
        }
        if (cancelled) return;
        const normalized = rawText.trim();
        const maxChars = 18000;
        setTextPreview(
          normalized.length > maxChars
            ? `${normalized.slice(0, maxChars)}\n\n...[内容已截断]`
            : normalized,
        );
      } catch (error) {
        if (cancelled) return;
        setTextError(error instanceof Error ? error.message : '文本预览加载失败');
      } finally {
        if (!cancelled) setTextLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [fileExtension, markdownArtifactUrl, previewKind, sourceFile]);

  const previewIdentity = useMemo(
    () =>
      [
        activeDoc?.file_hash || '',
        sourceFile?.name || '',
        sourceBlobUrl,
        pdfRenderUrl,
        previewKind,
      ].join('|'),
    [activeDoc?.file_hash, pdfRenderUrl, previewKind, sourceBlobUrl, sourceFile?.name],
  );

  useEffect(() => {
    setScale(1);
    setPdfViewMode('fit-width');
    setPdfPageCount(1);
    setPdfVisiblePage(1);
    setPdfScrollRequest(createPdfScrollRequest(1));
  }, [previewIdentity]);

  const currentPdfPage = Math.min(Math.max(pdfVisiblePage, 1), Math.max(pdfPageCount, 1));

  const jumpToPdfPage = (page: number) => {
    const safePage = Math.min(Math.max(1, Math.round(page)), Math.max(pdfPageCount, 1));
    setPdfVisiblePage(safePage);
    setPdfScrollRequest(createPdfScrollRequest(safePage));
  };

  const previewCanvasTitle = useMemo(() => {
    if (previewKind === 'pdf') return isOfficeDocument ? 'PDF 预览画布' : 'PDF 原文件画布';
    if (previewKind === 'text') return '文本画布';
    if (previewKind === 'spreadsheet') return '表格画布';
    if (previewKind === 'image') return '图片画布';
    return '预览画布';
  }, [isOfficeDocument, previewKind]);

  const previewStatusLabel = useMemo(() => {
    if (sourceLoading) return '正在恢复当前文件的源文件与预览资源…';
    if (sourceError) return sourceError;
    if (isOfficeDocument && pdfPreviewUrl) return '当前展示解析阶段生成的 PDF 预览产物';
    if (isOfficeDocument && sourceFile) return '已恢复 Office 源文件，正在等待生成可渲染的 PDF 预览';
    if (isOfficeDocument) return '当前 Office 文件的 PDF 预览产物尚未就绪';
    if (isPdfDocument && sourceFile) return '当前直接渲染上传或恢复的 PDF 源文件';
    if (previewKind === 'text' && markdownArtifactUrl) return '当前展示解析阶段生成的 Markdown 文本产物';
    if (previewKind === 'text' && sourceFile) return '当前直接渲染上传或恢复的文本源文件';
    if (previewKind === 'image' && imageArtifactUrl) return '当前展示解析阶段生成的图片产物';
    if (previewKind === 'image' && sourceFile) return '当前直接渲染上传或恢复的图片源文件';
    if (previewKind === 'spreadsheet' && sourceFile) return '当前直接渲染上传或恢复的表格源文件';
    if (sourceFile) return '当前直接渲染上传或恢复的源文件';
    return '当前还没有可直接渲染的预览资源，系统会自动回退到可用产物';
  }, [
    imageArtifactUrl,
    isOfficeDocument,
    isPdfDocument,
    markdownArtifactUrl,
    pdfPreviewUrl,
    previewKind,
    sourceError,
    sourceFile,
    sourceLoading,
  ]);

  const fallbackTitle = useMemo(() => {
    if (previewKind === 'unsupported') return '当前文件暂不支持直接预览';
    if (isOfficeDocument) return '当前 Office 预览尚未就绪';
    if (previewKind === 'spreadsheet') return '当前还未恢复到完整表格画布';
    return '当前预览产物尚未就绪';
  }, [isOfficeDocument, previewKind]);

  const fallbackDescription = useMemo(() => {
    if (sourceError) return sourceError;
    if (isOfficeDocument) {
      return sourceFile
        ? '已恢复上传的 Office 源文件，但手机端画布只能渲染解析阶段生成的 PDF 预览。请先开始解析，完成后再回到这里查看。'
        : '当前还没有找到 Office 文件对应的 PDF 预览产物。解析完成后，这里会自动切换到可渲染的 PDF 画布。';
    }
    if (previewKind === 'spreadsheet') {
      return '当前还没有恢复到可直接渲染的表格源文件。源文件可用后，这里会直接展示完整工作表。';
    }
    return '当前还没有可直接渲染的预览资源。系统会优先使用源文件，其次回退到解析阶段生成的可用产物。';
  }, [isOfficeDocument, previewKind, sourceError, sourceFile]);

  if (!activeDoc) {
    return (
      <section className="mb-6">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-[17px] font-bold text-slate-800 dark:text-slate-100">文件预览</h3>
        </div>
        <div className="rounded-[26px] bg-white px-5 py-10 text-center shadow-[0_8px_32px_rgba(0,0,0,0.03)] dark:bg-slate-800/60 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
            <MonitorPlay size={22} />
          </div>
          <p className="text-[15px] font-semibold text-slate-700 dark:text-slate-200">请先选择一份已解析文档。</p>
          <p className="mt-1 text-[13px] leading-6 text-slate-400 dark:text-slate-500">
            这里会直接承接当前文档的移动端预览，不再依赖旧的大预览面板。
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="flex flex-1 flex-col">
      {/* 隐藏冗余的“文件预览”大标题和文件名，因为最外层的 Modal Header 已经展示过了 */}
      <div className="flex flex-1 flex-col overflow-hidden rounded-[24px] bg-white shadow-[0_8px_24px_rgba(15,23,42,0.04)] ring-1 ring-slate-200/50 dark:bg-slate-800/60 dark:ring-slate-700/60 dark:shadow-none">
        <div className="border-b border-slate-100/80 px-3 py-2.5 dark:border-slate-700/60">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-semibold text-slate-800 dark:text-slate-100">{activeDoc?.file_name || previewCanvasTitle}</p>
              </div>

              {previewKind === 'pdf' && pdfRenderUrl && (
                <div className="flex shrink-0 items-center gap-2">
                  <div className="flex items-center gap-0.5 rounded-full bg-slate-100/80 px-1.5 py-1 dark:bg-slate-900/60">
                    <button
                      type="button"
                      onClick={() => jumpToPdfPage(currentPdfPage - 1)}
                      disabled={currentPdfPage <= 1}
                      className="inline-flex h-6 w-6 items-center justify-center rounded-full text-slate-500 transition enabled:hover:bg-white enabled:hover:text-slate-900 disabled:cursor-not-allowed disabled:text-slate-300 dark:text-slate-400 dark:enabled:hover:bg-white/10 dark:enabled:hover:text-white dark:disabled:text-slate-600"
                      title="上一页"
                    >
                      <ChevronLeft size={13} />
                    </button>
                    <span className="min-w-[36px] text-center text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                      {`${currentPdfPage} / ${Math.max(pdfPageCount, 1)}`}
                    </span>
                    <button
                      type="button"
                      onClick={() => jumpToPdfPage(currentPdfPage + 1)}
                      disabled={currentPdfPage >= Math.max(pdfPageCount, 1)}
                      className="inline-flex h-6 w-6 items-center justify-center rounded-full text-slate-500 transition enabled:hover:bg-white enabled:hover:text-slate-900 disabled:cursor-not-allowed disabled:text-slate-300 dark:text-slate-400 dark:enabled:hover:bg-white/10 dark:enabled:hover:text-white dark:disabled:text-slate-600"
                      title="下一页"
                    >
                      <ChevronRight size={13} />
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setPdfViewMode((prev) =>
                        prev === 'fit-width' ? 'fit-page' : prev === 'fit-page' ? 'actual' : 'fit-width',
                      );
                      setScale(1);
                    }}
                    className="rounded-full bg-slate-100/80 px-2.5 py-1 text-[11px] font-semibold text-slate-600 transition hover:bg-slate-200 hover:text-slate-900 dark:bg-slate-900/60 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
                  >
                    {pdfViewMode === 'fit-width'
                      ? '适宽'
                      : pdfViewMode === 'fit-page'
                        ? '整页'
                        : '原始'}
                  </button>
                </div>
              )}
            </div>

            {previewKind === 'spreadsheet' && workbookMetrics.length > 0 && (
              <div className="grid grid-cols-2 gap-2 mt-1">
                {workbookMetrics.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-[12px] bg-slate-50/90 px-2.5 py-2 ring-1 ring-slate-100 dark:bg-slate-900/55 dark:ring-slate-700/60"
                  >
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">{item.label}</p>
                    <p className="mt-0.5 text-[14px] font-semibold text-slate-800 dark:text-slate-100">{item.value}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="relative flex flex-1 min-h-[460px] overflow-hidden bg-[#F5F9FA] dark:bg-slate-900/50">
          {/* 全息光斑背景装饰 */}
          <div className="pointer-events-none absolute -left-12 top-1/4 h-[200px] w-[200px] rounded-full bg-cyan-400/20 blur-[60px] dark:bg-cyan-500/15" />
          <div className="pointer-events-none absolute -right-12 bottom-1/4 h-[200px] w-[200px] rounded-full bg-blue-400/20 blur-[60px] dark:bg-blue-500/15" />

          {(sourceLoading || (previewKind === 'text' && textLoading)) && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/55 backdrop-blur-sm dark:bg-slate-950/55">
              <div className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-[13px] text-slate-700 shadow-lg dark:bg-slate-800 dark:text-slate-200">
                <Loader2 size={15} className="animate-spin" />
                {sourceLoading ? '正在恢复源文件预览…' : '正在加载文本预览…'}
              </div>
            </div>
          )}

          {previewKind === 'pdf' && pdfRenderUrl ? (
            <PdfJsViewer
              key={`${previewIdentity}:${pdfRenderUrl}`}
              src={pdfRenderUrl}
              scale={scale}
              rotation={0}
              viewMode={pdfViewMode}
              scrollRequest={pdfScrollRequest}
              onPageCount={setPdfPageCount}
              onVisiblePageChange={setPdfVisiblePage}
            />
          ) : previewKind === 'spreadsheet' && sourceFile ? (
            <div className="absolute inset-0 min-h-0 overflow-hidden">
              <LuckysheetPreview
                file={sourceFile}
                className="h-full min-h-0 rounded-none border-0 bg-white dark:bg-slate-950"
              />
            </div>
          ) : previewKind === 'text' ? (
            <div className="absolute inset-0 overflow-auto px-2 py-3 sm:px-3">
              <div className="min-h-full rounded-[24px] border border-sky-100/90 bg-white/96 px-4 py-4 shadow-[0_20px_48px_rgba(148,163,184,0.14)] ring-1 ring-white/70 dark:border-sky-100/75 dark:bg-white/95 dark:ring-white/80">
                {textError ? (
                  <p className="rounded-[16px] bg-rose-50 px-4 py-3 text-[13px] leading-6 text-rose-600">
                    {textError}
                  </p>
                ) : (
                  <pre className="whitespace-pre-wrap break-words font-sans text-[14px] font-medium leading-[1.92] tracking-[0.01em] text-slate-800 sm:text-[15px]">
                    {textPreview || '当前暂未读取到文本内容。'}
                  </pre>
                )}
              </div>
            </div>
          ) : previewKind === 'image' && imageRenderUrl ? (
            <div className="absolute inset-0 flex items-center justify-center p-4">
              <img
                src={imageRenderUrl}
                alt={activeDoc.file_name}
                className="max-h-full max-w-full rounded-[18px] border border-white/70 object-contain shadow-[0_18px_46px_rgba(15,23,42,0.18)] dark:border-white/10"
              />
            </div>
          ) : previewKind === 'spreadsheet' ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center p-6">
              <div className="flex w-full max-w-[280px] flex-col items-center justify-center rounded-[24px] bg-white p-8 text-center shadow-[0_8px_30px_rgba(15,23,42,0.04)] ring-1 ring-slate-100 dark:bg-slate-800/80 dark:shadow-[0_8px_30px_rgba(0,0,0,0.1)] dark:ring-white/[0.05]">
                <div className="mb-5 flex h-[60px] w-[60px] items-center justify-center rounded-[18px] bg-[#E8F8F5] text-emerald-500 shadow-[0_8px_24px_rgba(16,185,129,0.15)] ring-1 ring-white/50 dark:bg-emerald-500/20 dark:text-emerald-300 dark:shadow-[0_8px_24px_rgba(16,185,129,0.08)] dark:ring-white/10">
                  <FileSpreadsheet size={28} strokeWidth={1.5} />
                </div>
                <p className="text-[16px] font-bold tracking-tight text-slate-800 dark:text-slate-100">当前还未恢复到完整表格画布</p>
                <p className="mt-2.5 text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
                  当前还没有恢复到可直接渲染的表格源文件。源文件可用后，这里会直接展示完整工作表。
                </p>
              </div>
            </div>
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center p-6">
              <div className="flex w-full max-w-[280px] flex-col items-center justify-center rounded-[24px] bg-white p-8 text-center shadow-[0_8px_30px_rgba(15,23,42,0.04)] ring-1 ring-slate-100 dark:bg-slate-800/80 dark:shadow-[0_8px_30px_rgba(0,0,0,0.1)] dark:ring-white/[0.05]">
                <div
                  className={cn(
                    'mb-5 flex h-[60px] w-[60px] items-center justify-center rounded-[18px] shadow-[0_8px_24px_rgba(14,165,233,0.15)] ring-1 ring-white/50 dark:shadow-[0_8px_24px_rgba(14,165,233,0.08)] dark:ring-white/10',
                    previewKind === 'image'
                      ? 'bg-amber-50 text-amber-500 dark:bg-amber-500/20 dark:text-amber-300 shadow-[0_8px_24px_rgba(245,158,11,0.15)]'
                      : previewKind === 'unsupported'
                        ? 'bg-slate-50 text-slate-500 dark:bg-slate-700 dark:text-slate-400 shadow-[0_8px_24px_rgba(100,116,139,0.15)]'
                        : 'bg-[#EAF5FD] text-sky-500 dark:bg-sky-500/20 dark:text-sky-300',
                  )}
                >
                  {previewKind === 'image' ? <FileImage size={28} strokeWidth={1.5} /> : <FileText size={28} strokeWidth={1.5} />}
                </div>
                <p className="text-[16px] font-bold tracking-tight text-slate-800 dark:text-slate-100">
                  {fallbackTitle}
                </p>
                <p className="mt-2.5 text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
                  {fallbackDescription}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
