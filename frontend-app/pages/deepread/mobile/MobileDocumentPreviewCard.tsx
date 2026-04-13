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
  const direct = String(
    diagnostics.assistant1_source_markdown_artifact_url
    || diagnostics.markdown_artifact_url
    || '',
  ).trim();
  if (direct) return toAbsoluteExtractUrl(direct, preferredBase);

  const artifactPath = String(
    diagnostics.assistant1_source_markdown_artifact_path
    || diagnostics.markdown_artifact_path
    || '',
  ).trim();
  if (!artifactPath) return '';

  return resolveExtractArtifactUrlFromTraceHit(
    { artifact_path: artifactPath },
    preferredBase,
  );
};

const resolveImageArtifactUrl = (
  document: ExtractionDocument | null,
  preferredBase: string,
): string => {
  const diagnostics = toRecord(document?.diagnostics);
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

  const pathCandidates = [
    diagnostics.source_artifact_path,
    diagnostics.artifact_path,
  ];
  for (const candidate of pathCandidates) {
    const raw = String(candidate || '').trim();
    if (!raw) continue;
    const resolved = resolveExtractArtifactUrlFromTraceHit(
      { artifact_path: raw },
      preferredBase,
    );
    if (resolved) return resolved;
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

    if (!matchedSessionFile) {
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
        const restored = await restoreWorkbenchFile(matchedSessionFile, preferredBase);
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
    matchedSessionFile?.artifactPath,
    matchedSessionFile?.artifactUrl,
    matchedSessionFile?.key,
    matchedSessionFile?.lastModified,
    matchedSessionFile?.name,
    preferredBase,
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

  const previewKind = useMemo<PreviewKind>(() => {
    if (!activeDoc) return 'unsupported';
    if (fileExtension === 'pdf' || fileExtension === 'doc' || fileExtension === 'docx') return 'pdf';
    if (SPREADSHEET_EXTENSIONS.has(fileExtension)) return 'spreadsheet';
    if (TEXT_EXTENSIONS.has(fileExtension)) return 'text';
    if (IMAGE_EXTENSIONS.has(fileExtension)) return 'image';
    return 'unsupported';
  }, [activeDoc, fileExtension]);

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
    if ((fileExtension === 'doc' || fileExtension === 'docx') && pdfPreviewUrl) return pdfPreviewUrl;
    if (fileExtension === 'pdf' && sourceBlobUrl) return sourceBlobUrl;
    return pdfPreviewUrl || sourceBlobUrl;
  }, [fileExtension, pdfPreviewUrl, previewKind, sourceBlobUrl]);

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

  const previewStatusLabel = useMemo(() => {
    if (sourceLoading) return '正在恢复当前文件的源文件画布…';
    if (sourceFile) return '当前直接渲染上传源文件画布';
    if (previewKind === 'pdf' && pdfPreviewUrl) return '当前渲染解析阶段生成的 PDF 预览产物';
    if (previewKind === 'text' && markdownArtifactUrl) return '当前渲染解析阶段生成的 Markdown 文本产物';
    if (previewKind === 'image' && imageArtifactUrl) return '当前渲染解析阶段生成的图片产物';
    if (sourceError) return sourceError;
    return '当前暂未恢复到可直接渲染的源文件，已自动使用可用产物兜底';
  }, [imageArtifactUrl, markdownArtifactUrl, pdfPreviewUrl, previewKind, sourceError, sourceFile, sourceLoading]);

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
          <p className="text-[15px] font-semibold text-slate-700 dark:text-slate-200">请先选择一份已解析文档</p>
          <p className="mt-1 text-[13px] leading-6 text-slate-400 dark:text-slate-500">
            后续这个区域会直接承接文件画布，不再依赖旧工作区的大预览面板。
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="mb-6">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[17px] font-bold text-slate-800 dark:text-slate-100">文件预览</h3>
          <p className="mt-1 truncate text-[12px] text-slate-500 dark:text-slate-400">
            {activeDoc.file_name}
          </p>
        </div>
        {openExternalUrl && (
          <a
            href={openExternalUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-white text-slate-600 shadow-sm ring-1 ring-slate-200/70 transition hover:text-slate-900 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700/70 dark:hover:text-white"
            title="在新窗口打开当前预览"
            aria-label="在新窗口打开当前预览"
          >
            <ExternalLink size={16} />
          </a>
        )}
      </div>

      <div className="overflow-hidden rounded-[28px] bg-white shadow-[0_10px_36px_rgba(15,23,42,0.06)] ring-1 ring-slate-200/60 dark:bg-slate-800/60 dark:ring-slate-700/60 dark:shadow-[0_10px_36px_rgba(0,0,0,0.22)]">
        <div className="border-b border-slate-100/80 px-4 py-3.5 dark:border-slate-700/60">
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[14px] font-semibold text-slate-800 dark:text-slate-100">
                  {previewKind === 'pdf'
                    ? '原文件画布'
                    : previewKind === 'text'
                      ? '文本画布'
                      : previewKind === 'spreadsheet'
                        ? '表格画布'
                        : previewKind === 'image'
                          ? '图片画布'
                          : '预览画布'}
                </p>
                <p className="mt-1 text-[12px] leading-5 text-slate-500 dark:text-slate-400">
                  {previewStatusLabel}
                </p>
              </div>

              {previewKind === 'pdf' && pdfRenderUrl && (
                <div className="flex shrink-0 items-center gap-1 rounded-full bg-slate-100/80 px-2 py-1 dark:bg-slate-900/60">
                  <button
                    type="button"
                    onClick={() => setScale((prev) => Math.max(prev - 0.1, 0.6))}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-600 transition hover:bg-white hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white"
                    title="缩小"
                  >
                    <ZoomOut size={15} />
                  </button>
                  <span className="w-10 text-center text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                    {`${Math.round(scale * 100)}%`}
                  </span>
                  <button
                    type="button"
                    onClick={() => setScale((prev) => Math.min(prev + 0.1, 2.4))}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-600 transition hover:bg-white hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white"
                    title="放大"
                  >
                    <ZoomIn size={15} />
                  </button>
                </div>
              )}
            </div>

            {previewKind === 'spreadsheet' && workbookMetrics.length > 0 && (
              <div className="grid grid-cols-2 gap-2">
                {workbookMetrics.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-[16px] bg-slate-50/90 px-3 py-2.5 ring-1 ring-slate-100 dark:bg-slate-900/55 dark:ring-slate-700/60"
                  >
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">{item.label}</p>
                    <p className="mt-1 text-[16px] font-semibold text-slate-800 dark:text-slate-100">{item.value}</p>
                  </div>
                ))}
              </div>
            )}

            {previewKind === 'pdf' && pdfRenderUrl && (
              <div className="flex items-center justify-between gap-3 rounded-[16px] bg-slate-50/90 px-3 py-2 ring-1 ring-slate-100 dark:bg-slate-900/55 dark:ring-slate-700/60">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => jumpToPdfPage(currentPdfPage - 1)}
                    disabled={currentPdfPage <= 1}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-600 transition enabled:hover:bg-white enabled:hover:text-slate-900 disabled:cursor-not-allowed disabled:text-slate-300 dark:text-slate-300 dark:enabled:hover:bg-white/10 dark:enabled:hover:text-white dark:disabled:text-slate-600"
                    title="上一页"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <span className="min-w-[62px] text-center text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                    {`${currentPdfPage} / ${Math.max(pdfPageCount, 1)}`}
                  </span>
                  <button
                    type="button"
                    onClick={() => jumpToPdfPage(currentPdfPage + 1)}
                    disabled={currentPdfPage >= Math.max(pdfPageCount, 1)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-600 transition enabled:hover:bg-white enabled:hover:text-slate-900 disabled:cursor-not-allowed disabled:text-slate-300 dark:text-slate-300 dark:enabled:hover:bg-white/10 dark:enabled:hover:text-white dark:disabled:text-slate-600"
                    title="下一页"
                  >
                    <ChevronRight size={16} />
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
                  className="rounded-full bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 shadow-sm transition hover:text-slate-900 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 dark:hover:text-white"
                >
                  {pdfViewMode === 'fit-width'
                    ? '铺满宽度'
                    : pdfViewMode === 'fit-page'
                      ? '整页适配'
                      : '原始尺寸'}
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="relative h-[68vh] min-h-[420px] overflow-hidden bg-[linear-gradient(180deg,rgba(247,250,255,0.96),rgba(235,243,255,0.9))] dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.96),rgba(2,6,23,0.94))]">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle,_rgba(96,165,250,0.22)_1px,_transparent_1px)] bg-[length:24px_24px] opacity-60 dark:opacity-20" />

          {(sourceLoading || (previewKind === 'text' && textLoading)) && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/55 backdrop-blur-sm dark:bg-slate-950/55">
              <div className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-[13px] text-slate-700 shadow-lg dark:bg-slate-800 dark:text-slate-200">
                <Loader2 size={15} className="animate-spin" />
                {sourceLoading ? '正在恢复源文件画布…' : '正在加载文本预览…'}
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
            <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300">
                <FileSpreadsheet size={28} />
              </div>
              <p className="text-[15px] font-semibold text-slate-800 dark:text-slate-100">当前还未恢复到完整表格画布</p>
              <p className="mt-2 max-w-[22rem] text-[13px] leading-6 text-slate-500 dark:text-slate-400">
                已经将表格预览主入口上浮到这里；一旦当前会话中的源文件可用，这里会直接渲染完整工作表，而不是再跳去旧工作区。
              </p>
            </div>
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
              <div
                className={cn(
                  'mb-4 flex h-16 w-16 items-center justify-center rounded-full',
                  previewKind === 'image'
                    ? 'bg-amber-50 text-amber-500 dark:bg-amber-500/10 dark:text-amber-300'
                    : previewKind === 'unsupported'
                      ? 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                      : 'bg-sky-50 text-sky-500 dark:bg-sky-500/10 dark:text-sky-300',
                )}
              >
                {previewKind === 'image' ? <FileImage size={28} /> : <FileText size={28} />}
              </div>
              <p className="text-[15px] font-semibold text-slate-800 dark:text-slate-100">
                {previewKind === 'unsupported' ? '当前文件暂不支持直接预览' : '当前预览产物还未就绪'}
              </p>
              <p className="mt-2 max-w-[22rem] text-[13px] leading-6 text-slate-500 dark:text-slate-400">
                {sourceError
                  ? sourceError
                  : '这个区域现在就是手机端文件画布主入口。后续文件预览会优先在这里完成，而不是回到旧的大预览面板。'}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
