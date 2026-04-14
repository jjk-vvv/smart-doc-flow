﻿import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ChevronDown,
  CheckCircle2,
  Clock3,
  Download,
  Eye,
  FolderOpen,
  HelpCircle,
  Loader2,
  PanelLeft,
  Play,
  RefreshCw,
  Trash2,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import {
  cancelModule3Run,
  createModule3Run,
  fetchModule3DocumentPreviewText,
  fetchModule3RunStatus,
  module3RunDownloadUrl,
  normalizeModule3Status,
  uploadModule3Docset,
  uploadModule3Template,
  type Module3RunStatusResponse,
  type Module3TaskStatus,
} from "../../lib/module3Api";
import {
  readFusionGridState,
  writeFusionGridState,
  type FusionDocumentType,
  type FusionGridDocsetRecord,
  type FusionGridState,
  type FusionGridTaskRecord,
  type FusionGridTemplateRecord,
} from "../../lib/fusionGridStore";
import { Module3ExcelPreview } from "./Module3ExcelPreview";
import { Module3WordPreview } from "./Module3WordPreview";
import excelIconUrl from "../../assets/xlsx.png";
import mdIconUrl from "../../assets/md.png";
import txtIconUrl from "../../assets/txt.png";
import wordIconUrl from "../../assets/WORD.png";

type PreviewDocument = {
  id: string;
  name: string;
  fileId: string | null;
  type: FusionDocumentType;
  runId?: string;
};

type FloatingRunNotice = {
  taskId: string;
  taskName: string;
  phase: "running" | "done";
};

const cn = (...values: Array<string | false | null | undefined>) =>
  values.filter(Boolean).join(" ");

const nowText = () =>
  new Date().toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

const formatBytes = (bytes: number) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return "未知大小";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** index;
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
};

const getDocumentType = (filename: string): FusionDocumentType => {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "xlsx") return "xlsx";
  if (ext === "docx") return "docx";
  if (ext === "txt") return "txt";
  if (ext === "md") return "md";
  return "other";
};

const basename = (value?: string | null) => {
  if (!value) return "";
  const name = value.split(/[\\/]/).pop() ?? value;
  return name.replace(/^tpl_[a-z0-9]+__/, "");
};

const getTaskOutputName = (task: {
  outputName?: string | null;
  templateName: string;
}) => {
  const outputName = String(task.outputName || "").trim();
  if (outputName) return outputName;
  return basename(task.templateName);
};

const canPreviewByRunType = (type: FusionDocumentType): boolean =>
  type === "docx" || type === "xlsx";

const fileIconAsset = (type: FusionDocumentType) => {
  if (type === "docx") {
    return { src: wordIconUrl, alt: "Word" } as const;
  }
  if (type === "xlsx") {
    return { src: excelIconUrl, alt: "Excel" } as const;
  }
  if (type === "md") {
    return { src: mdIconUrl, alt: "Markdown" } as const;
  }
  return { src: txtIconUrl, alt: "Text" } as const;
};

const FileTypeIcon = ({
  type,
  className,
}: {
  type: FusionDocumentType;
  className?: string;
}) => {
  const icon = fileIconAsset(type);
  return (
    <img
      src={icon.src}
      alt={icon.alt}
      className={cn("h-6 w-6 shrink-0 object-contain", className)}
    />
  );
};

const taskMeta = (status: Module3TaskStatus) => {
  switch (status) {
    case "done":
      return [
        "已完成",
        "bg-emerald-100 text-emerald-700",
        <CheckCircle2 size={14} key="i" />,
      ] as const;
    case "running":
      return [
        "执行中",
        "bg-blue-100 text-blue-700",
        <Loader2 size={14} className="animate-spin" key="i" />,
      ] as const;
    case "cancelled":
      return [
        "已取消",
        "bg-amber-100 text-amber-700",
        <XCircle size={14} key="i" />,
      ] as const;
    case "failed":
      return [
        "失败",
        "bg-red-100 text-red-700",
        <XCircle size={14} key="i" />,
      ] as const;
    default:
      return [
        "等待中",
        "bg-slate-100 text-slate-700",
        <Clock3 size={14} key="i" />,
      ] as const;
  }
};

const updateTask = (
  task: FusionGridTaskRecord,
  status: Module3RunStatusResponse,
): FusionGridTaskRecord => ({
  ...task,
  status: normalizeModule3Status(status.status, status.error),
  fillRate: Math.max(
    0,
    Math.min(
      100,
      Math.round(
        (status.fill_rate <= 1 ? status.fill_rate * 100 : status.fill_rate) ||
          0,
      ),
    ),
  ),
  filled: Number.isFinite(status.filled) ? status.filled : task.filled,
  total: Number.isFinite(status.total) ? status.total : task.total,
  outputFileId: status.output_file_id ?? task.outputFileId ?? null,
  outputName: status.output_name ?? task.outputName ?? null,
  error: status.error ?? null,
});

const PlainPreview = ({
  title,
  content,
}: {
  title: string;
  content: string;
}) => (
  <div className="flex min-h-[320px] flex-col">
    <div className="border-b border-slate-200 bg-white px-4 py-3 text-xs text-slate-500">
      {title}
    </div>
    <pre className="min-h-[320px] overflow-auto whitespace-pre-wrap break-words px-4 py-4 text-[13px] leading-6 text-slate-700">
      {content || "（文件内容为空或无法预览）"}
    </pre>
  </div>
);

const BottomSheet = ({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) => (
  <div className="fixed inset-0 z-[55] flex items-end bg-black/40 p-3 sm:items-center sm:justify-center">
    <div className="flex max-h-[min(84vh,760px)] w-full max-w-md flex-col overflow-hidden rounded-t-[32px] sm:rounded-[32px] bg-white shadow-2xl dark:bg-[#1A1D24]">
      <div className="flex items-start justify-between gap-3 px-6 pb-4 pt-6 relative">
        <div className="absolute top-2 left-1/2 -translate-x-1/2 w-10 h-1.5 rounded-full bg-slate-200 sm:hidden dark:bg-white/10" />
        <div className="min-w-0">
          <h3 className="mt-2 text-[20px] font-bold text-slate-900 dark:text-slate-100">{title}</h3>
          {subtitle ? (
            <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="mt-1 rounded-full bg-slate-100 p-2 text-slate-500 active:scale-95 transition-transform dark:bg-white/5 dark:text-slate-400"
          aria-label={`关闭${title}`}
          title={`关闭${title}`}
        >
          <X size={18} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 pb-6 pt-2">{children}</div>
    </div>
  </div>
);

export const FusionGrid: React.FC = () => {
  const [gridState, setGridState] = useState<FusionGridState>(() =>
    readFusionGridState(),
  );
  const [previewDocument, setPreviewDocument] =
    useState<PreviewDocument | null>(null);
  const [previewContent, setPreviewContent] = useState("");
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [infoMessage, setInfoMessage] = useState(
    "按模板、文档、要求、任务、结果的顺序完成填充。",
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [isUploadingTemplate, setIsUploadingTemplate] = useState(false);
  const [isUploadingDocset, setIsUploadingDocset] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isTemplatePanelOpen, setIsTemplatePanelOpen] = useState(false);
  const [isDocsetPanelOpen, setIsDocsetPanelOpen] = useState(false);
  const [isCurrentDocsetOpen, setIsCurrentDocsetOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSidebarFullWidth, setIsSidebarFullWidth] = useState(false);
  const [isTaskPanelOpen, setIsTaskPanelOpen] = useState(false);
  const [floatingRunNotice, setFloatingRunNotice] =
    useState<FloatingRunNotice | null>(null);
  const [collapsedRunningNoticeTaskId, setCollapsedRunningNoticeTaskId] =
    useState<string | null>(null);
  const [isFloatingRunNoticeVisible, setIsFloatingRunNoticeVisible] =
    useState(false);
  const [cancellingTaskIds, setCancellingTaskIds] = useState<string[]>([]);
  const templateInputRef = useRef<HTMLInputElement>(null);
  const docsetInputRef = useRef<HTMLInputElement>(null);

  const templates = gridState.templates;
  const docsets = gridState.docsets;
  const tasks = gridState.tasks;
  const selectedTemplate = useMemo(
    () =>
      templates.find((item) => item.id === gridState.selectedTemplateId) ??
      null,
    [templates, gridState.selectedTemplateId],
  );
  const selectedDocset = useMemo(
    () =>
      docsets.find((item) => item.id === gridState.selectedDocsetId) ?? null,
    [docsets, gridState.selectedDocsetId],
  );
  const selectedTask = useMemo(
    () => tasks.find((item) => item.id === gridState.selectedTaskId) ?? null,
    [tasks, gridState.selectedTaskId],
  );
  const latestTemplate = templates[0] ?? null;
  const latestTask = tasks[0] ?? null;

  const latestOutput =
    latestTask?.status === "done"
      ? (() => {
          const outputName = getTaskOutputName(latestTask);
          const outputType = getDocumentType(outputName);
          if (!latestTask.outputFileId && !canPreviewByRunType(outputType)) {
            return null;
          }
          return {
            id: latestTask.id,
            name: outputName,
            fileId: latestTask.outputFileId ?? null,
            type: outputType,
            runId: latestTask.id,
          };
        })()
      : null;

  const selectedOutput =
    selectedTask?.status === "done"
      ? (() => {
          const outputName = getTaskOutputName(selectedTask);
          const outputType = getDocumentType(outputName);
          if (!selectedTask.outputFileId && !canPreviewByRunType(outputType)) {
            return null;
          }
          return {
            id: selectedTask.id,
            name: outputName,
            fileId: selectedTask.outputFileId ?? null,
            type: outputType,
            runId: selectedTask.id,
          };
        })()
      : null;

  useEffect(() => {
    writeFusionGridState(gridState);
  }, [gridState]);

  useEffect(() => {
    setGridState((current) => ({
      ...current,
      selectedTemplateId: current.templates.some(
        (item) => item.id === current.selectedTemplateId,
      )
        ? current.selectedTemplateId
        : (current.templates[0]?.id ?? null),
      selectedDocsetId: current.docsets.some(
        (item) => item.id === current.selectedDocsetId,
      )
        ? current.selectedDocsetId
        : (current.docsets[0]?.id ?? null),
      selectedTaskId: current.tasks.some(
        (item) => item.id === current.selectedTaskId,
      )
        ? current.selectedTaskId
        : (current.tasks[0]?.id ?? null),
    }));
  }, [templates, docsets, tasks]);

  useEffect(() => {
    if (!floatingRunNotice) return;
    const task = tasks.find((item) => item.id === floatingRunNotice.taskId);
    if (!task) return;
    if (floatingRunNotice.phase === "running" && task.status === "done") {
      setFloatingRunNotice({
        taskId: task.id,
        taskName: getTaskOutputName(task),
        phase: "done",
      });
      setCollapsedRunningNoticeTaskId(null);
      return;
    }
    if (
      floatingRunNotice.phase === "running" &&
      (task.status === "failed" || task.status === "cancelled")
    ) {
      setFloatingRunNotice(null);
    }
  }, [floatingRunNotice, tasks]);

  useEffect(() => {
    if (!collapsedRunningNoticeTaskId) return;
    const task = tasks.find((item) => item.id === collapsedRunningNoticeTaskId);
    if (!task) {
      setCollapsedRunningNoticeTaskId(null);
      return;
    }
    if (task.status === "done") {
      setFloatingRunNotice({
        taskId: task.id,
        taskName: getTaskOutputName(task),
        phase: "done",
      });
      setCollapsedRunningNoticeTaskId(null);
      return;
    }
    if (task.status === "failed" || task.status === "cancelled") {
      setCollapsedRunningNoticeTaskId(null);
    }
  }, [collapsedRunningNoticeTaskId, tasks]);

  useEffect(() => {
    if (!floatingRunNotice) {
      setIsFloatingRunNoticeVisible(false);
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      setIsFloatingRunNoticeVisible(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [floatingRunNotice?.taskId]);

  const dismissFloatingRunNotice = () => {
    setIsFloatingRunNoticeVisible(false);
    window.setTimeout(() => {
      setFloatingRunNotice(null);
    }, 240);
  };

  useEffect(() => {
    if (floatingRunNotice?.phase !== "done") return;
    const timer = window.setTimeout(() => {
      dismissFloatingRunNotice();
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [floatingRunNotice]);

  useEffect(() => {
    const ids = tasks
      .filter((item) => item.status === "running")
      .map((item) => item.id);
    if (ids.length === 0) return;
    const timer = window.setInterval(() => {
      ids.forEach((id) => {
        fetchModule3RunStatus(id)
          .then((status) => {
            setGridState((current) => ({
              ...current,
              tasks: current.tasks.map((item) =>
                item.id === id ? updateTask(item, status) : item,
              ),
            }));
          })
          .catch(() => undefined);
      });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [tasks]);

  useEffect(() => {
    if (!selectedDocset) setIsCurrentDocsetOpen(false);
  }, [selectedDocset]);

  useEffect(() => {
    if (
      !previewDocument &&
      !isSidebarOpen &&
      !isHelpOpen &&
      !isTemplatePanelOpen &&
      !isDocsetPanelOpen &&
      !isCurrentDocsetOpen
    ) {
      return;
    }
    const { style: bodyStyle } = document.body;
    const { style: htmlStyle } = document.documentElement;
    const previousBodyOverflow = bodyStyle.overflow;
    const previousBodyPosition = bodyStyle.position;
    const previousBodyTop = bodyStyle.top;
    const previousBodyWidth = bodyStyle.width;
    const previousBodyLeft = bodyStyle.left;
    const previousBodyRight = bodyStyle.right;
    const previousHtmlOverflow = htmlStyle.overflow;
    const previousHtmlOverscrollBehavior = htmlStyle.overscrollBehavior;
    const scrollY = window.scrollY;
    bodyStyle.overflow = "hidden";
    bodyStyle.position = "fixed";
    bodyStyle.top = `-${scrollY}px`;
    bodyStyle.left = "0";
    bodyStyle.right = "0";
    bodyStyle.width = "100%";
    htmlStyle.overflow = "hidden";
    htmlStyle.overscrollBehavior = "none";
    return () => {
      bodyStyle.overflow = previousBodyOverflow;
      bodyStyle.position = previousBodyPosition;
      bodyStyle.top = previousBodyTop;
      bodyStyle.width = previousBodyWidth;
      bodyStyle.left = previousBodyLeft;
      bodyStyle.right = previousBodyRight;
      htmlStyle.overflow = previousHtmlOverflow;
      htmlStyle.overscrollBehavior = previousHtmlOverscrollBehavior;
      window.scrollTo(0, scrollY);
    };
  }, [
    isCurrentDocsetOpen,
    isDocsetPanelOpen,
    isHelpOpen,
    isSidebarOpen,
    isTemplatePanelOpen,
    previewDocument,
  ]);

  const loadPreview = async (document: PreviewDocument) => {
    const fallback = `文件名: ${document.name}\nfile_id: ${document.fileId ?? "unknown"}`;
    if (document.type === "docx" || document.type === "xlsx") {
      setPreviewContent(fallback);
      return;
    }
    if (!document.fileId) {
      setPreviewContent(fallback);
      return;
    }
    try {
      const text = await fetchModule3DocumentPreviewText(document.fileId);
      setPreviewContent(text || fallback);
    } catch {
      setPreviewContent(fallback);
    }
  };

  const openPreview = async (document: PreviewDocument) => {
    if (previewDocument?.id === document.id) {
      setPreviewDocument(null);
      setPreviewContent("");
      return;
    }
    setPreviewDocument(document);
    setPreviewContent("");
    setIsPreviewLoading(true);
    await loadPreview(document);
    setIsPreviewLoading(false);
  };

  const removeTemplate = (id: string) =>
    setGridState((current) => ({
      ...current,
      templates: current.templates.filter((item) => item.id !== id),
      selectedTemplateId:
        current.selectedTemplateId === id ? null : current.selectedTemplateId,
    }));

  const removeDocset = (id: string) =>
    setGridState((current) => ({
      ...current,
      docsets: current.docsets.filter((item) => item.id !== id),
      selectedDocsetId:
        current.selectedDocsetId === id ? null : current.selectedDocsetId,
    }));

  const removeTask = (id: string) =>
    setGridState((current) => ({
      ...current,
      tasks: current.tasks.filter((item) => item.id !== id),
      selectedTaskId:
        current.selectedTaskId === id ? null : current.selectedTaskId,
    }));

  const handleTemplateUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setErrorMessage("");
    setInfoMessage("正在上传模板并解析字段。");
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
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "模板上传失败");
    } finally {
      setIsUploadingTemplate(false);
    }
  };

  const handleDocsetUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const files = event.target.files ? Array.from(event.target.files) : [];
    event.target.value = "";
    if (files.length === 0) return;
    setErrorMessage("");
    setInfoMessage(`正在上传 ${files.length} 个文档。`);
    setIsUploadingDocset(true);
    try {
      const response = await uploadModule3Docset(files);
      const sizeMap = new Map(
        files.map((file) => [file.name, formatBytes(file.size)] as const),
      );
      const record: FusionGridDocsetRecord = {
        id: response.doc_set_id,
        count: response.count,
        uploadTime: nowText(),
        files: response.files.map((file) => ({
          filename: file.filename,
          fileId: file.file_id ?? null,
          size: sizeMap.get(file.filename) ?? "未知大小",
          type: getDocumentType(file.filename),
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
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "文档上传失败");
    } finally {
      setIsUploadingDocset(false);
    }
  };

  const handleStartRun = async () => {
    if (!selectedTemplate) return setErrorMessage("请先上传并选择模板。");
    if (!selectedDocset) return setErrorMessage("请先上传并选择文档集。");
    setErrorMessage("");
    setInfoMessage("正在创建填充任务。");
    setIsRunning(true);
    try {
      const run = await createModule3Run({
        template_id: selectedTemplate.id,
        doc_set_id: selectedDocset.id,
        prompt: gridState.draftRequirements.trim() || undefined,
      });
      let status: Module3RunStatusResponse | null = null;
      try {
        status = await fetchModule3RunStatus(run.run_id);
      } catch {}
      const nextTask: FusionGridTaskRecord = {
        id: run.run_id,
        createdAt: nowText(),
        status: normalizeModule3Status(
          status?.status ?? run.status,
          status?.error,
        ),
        fillRate: Math.max(
          0,
          Math.min(
            100,
            Math.round(
              (status?.fill_rate ?? 0) <= 1
                ? (status?.fill_rate ?? 0) * 100
                : (status?.fill_rate ?? 0),
            ),
          ),
        ),
        filled: status?.filled ?? 0,
        total: status?.total ?? selectedDocset.count,
        templateId: selectedTemplate.id,
        templateName: selectedTemplate.name,
        docsetId: selectedDocset.id,
        docsetLabel: `${selectedDocset.count} 个文件`,
        outputFileId: status?.output_file_id ?? null,
        outputName: status?.output_name ?? null,
        error: status?.error ?? null,
      };
      setGridState((current) => ({
        ...current,
        tasks: [
          nextTask,
          ...current.tasks.filter((item) => item.id !== nextTask.id),
        ],
        selectedTaskId: nextTask.id,
      }));
      setFloatingRunNotice({
        taskId: nextTask.id,
        taskName: getTaskOutputName(nextTask),
        phase: nextTask.status === "done" ? "done" : "running",
      });
      setCollapsedRunningNoticeTaskId(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "任务创建失败");
    } finally {
      setIsRunning(false);
    }
  };

  const handleRefreshAll = async () => {
    if (tasks.length === 0) return;
    setIsRefreshing(true);
    try {
      const refreshed = await Promise.all(
        tasks.map(async (task) => ({
          taskId: task.id,
          status: await fetchModule3RunStatus(task.id),
        })),
      );
      const map = new Map(refreshed.map((item) => [item.taskId, item.status]));
      setGridState((current) => ({
        ...current,
        tasks: current.tasks.map((task) =>
          map.get(task.id) ? updateTask(task, map.get(task.id)!) : task,
        ),
      }));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "刷新失败");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleCancelTask = async (taskId: string) => {
    setCancellingTaskIds((current) =>
      current.includes(taskId) ? current : [...current, taskId],
    );
    setGridState((current) => ({
      ...current,
      tasks: current.tasks.map((task) =>
        task.id === taskId
          ? {
              ...task,
              status: "cancelled",
              error: "正在取消任务...",
            }
          : task,
      ),
    }));
    try {
      await cancelModule3Run(taskId);
    } catch (error) {
      setGridState((current) => ({
        ...current,
        tasks: current.tasks.map((task) =>
          task.id === taskId
            ? {
                ...task,
                status: "running",
                error: null,
              }
            : task,
        ),
      }));
      setErrorMessage(error instanceof Error ? error.message : "取消失败");
    } finally {
      setCancellingTaskIds((current) => current.filter((id) => id !== taskId));
    }
  };

  const stats = {
    total: tasks.length,
    done: tasks.filter((item) => item.status === "done").length,
    failed: tasks.filter((item) => item.status === "failed").length,
  };

  return (
    <div className="min-h-screen overflow-x-hidden bg-[#EAF7F8] pb-[env(safe-area-inset-bottom)] dark:bg-[#0B1120]">
      <input
        ref={templateInputRef}
        type="file"
        accept=".xlsx,.docx"
        className="hidden"
        onChange={handleTemplateUpload}
        aria-label="上传模板文件"
        title="上传模板文件"
      />
      <input
        ref={docsetInputRef}
        type="file"
        multiple
        accept=".xlsx,.docx,.txt,.md"
        className="hidden"
        onChange={handleDocsetUpload}
        aria-label="上传文档集文件"
        title="上传文档集文件"
      />

      {floatingRunNotice ? (
        <div className="pointer-events-none fixed inset-x-0 top-4 z-[65] flex justify-center px-4">
          <div
            className={cn(
              "pointer-events-auto origin-top flex w-full max-w-[420px] items-center justify-between gap-3 rounded-full border bg-white/95 px-4 py-3 shadow-lg backdrop-blur transition-[opacity,transform] duration-300 ease-out",
              isFloatingRunNoticeVisible
                ? "scale-100 opacity-100"
                : "scale-x-95 scale-y-75 opacity-0",
              floatingRunNotice.phase === "done"
                ? "border-emerald-200 shadow-emerald-100"
                : "border-sky-200 shadow-sky-100",
            )}
          >
            <div className="min-w-0">
              <p
                className={cn(
                  "flex items-center gap-2 text-sm font-semibold",
                  floatingRunNotice.phase === "done"
                    ? "text-emerald-700"
                    : "text-sky-700",
                )}
              >
                {floatingRunNotice.phase === "done" ? (
                  <CheckCircle2 size={16} />
                ) : (
                  <Loader2 size={16} className="animate-spin" />
                )}
                {floatingRunNotice.phase === "done" ? "填充完成" : "正在填充"}
              </p>
              <p className="truncate text-xs pl-6 text-slate-500">
                {floatingRunNotice.phase === "done"
                  ? "请点击左侧栏查看任务详情"
                  : floatingRunNotice.taskName}
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                if (floatingRunNotice.phase === "running") {
                  setCollapsedRunningNoticeTaskId(floatingRunNotice.taskId);
                  dismissFloatingRunNotice();
                  return;
                }
                dismissFloatingRunNotice();
                setIsSidebarOpen(false);
                setIsSidebarFullWidth(false);
              }}
              className={cn(
                "inline-flex h-10 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-medium",
                floatingRunNotice.phase === "done"
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-sky-100 text-sky-700",
              )}
            >
              <ArrowUp size={16} />
              收起
            </button>
          </div>
        </div>
      ) : null}

      {isHelpOpen ? (
        <BottomSheet
          title="模块三使用说明"
          onClose={() => setIsHelpOpen(false)}
        >
          <div className="space-y-3 text-sm leading-6 text-slate-600">
            <p>1. 先上传模板，再上传文档集。</p>
            <p>2. 用户要求里写筛选、格式和保留规则。</p>
            <p>3. 在任务区刷新、取消、预览和下载结果。</p>
            <p>4. DOCX 与 XLSX 结果会进入全屏结构化预览。</p>
          </div>
        </BottomSheet>
      ) : null}

      {isTemplatePanelOpen ? (
        <BottomSheet
          title="模板管理"
          subtitle="上传、切换和查看当前模板字段。"
          onClose={() => setIsTemplatePanelOpen(false)}
        >
          <button
            type="button"
            onClick={() => templateInputRef.current?.click()}
            className="flex w-full flex-col items-center justify-center rounded-[24px] border-2 border-dashed border-slate-300 px-4 py-5 text-center"
          >
            {isUploadingTemplate ? (
              <Loader2 size={24} className="animate-spin text-slate-400" />
            ) : (
              <UploadCloud size={24} className="text-slate-400" />
            )}
            <span className="mt-3 text-sm font-semibold text-slate-800">
              {isUploadingTemplate ? "模板上传中..." : "上传模板"}
            </span>
          </button>
          {templates.length > 1 ? (
            <select
              value={gridState.selectedTemplateId ?? latestTemplate?.id ?? ""}
              onChange={(event) =>
                setGridState((current) => ({
                  ...current,
                  selectedTemplateId: event.target.value || null,
                }))
              }
              className="mt-4 h-11 w-full rounded-2xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none"
              aria-label="选择模板"
              title="选择模板"
            >
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          ) : null}
          <div className="mt-4 space-y-2">
            {selectedTemplate ? (
              <div className="rounded-[22px] border border-sky-300 bg-sky-50 px-3 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      {selectedTemplate.name}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {selectedTemplate.size} · {selectedTemplate.fields.length}{" "}
                      个字段
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeTemplate(selectedTemplate.id)}
                    className="rounded-full p-2 text-slate-400"
                    aria-label="删除当前模板"
                    title="删除当前模板"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ) : (
              <div className="rounded-[24px] border-2 border-dashed border-slate-200 bg-white/40 px-4 py-6 text-center text-[14px] font-medium text-slate-400 dark:border-white/10 dark:bg-white/5">
                暂无模板
              </div>
            )}
          </div>
        </BottomSheet>
      ) : null}

      {isDocsetPanelOpen ? (
        <BottomSheet
          title="文档集管理"
          subtitle="上传文档、切换文档集并查看当前文件清单。"
          onClose={() => setIsDocsetPanelOpen(false)}
        >
          <button
            type="button"
            onClick={() => docsetInputRef.current?.click()}
            className="flex w-full flex-col items-center justify-center rounded-[24px] border-2 border-dashed border-slate-300 px-4 py-5 text-center"
          >
            {isUploadingDocset ? (
              <Loader2 size={24} className="animate-spin text-slate-400" />
            ) : (
              <FolderOpen size={24} className="text-slate-400" />
            )}
            <span className="mt-3 text-sm font-semibold text-slate-800">
              {isUploadingDocset ? "文档上传中..." : "上传文档集"}
            </span>
          </button>
          {docsets.length > 1 ? (
            <select
              value={gridState.selectedDocsetId ?? ""}
              onChange={(event) =>
                setGridState((current) => ({
                  ...current,
                  selectedDocsetId: event.target.value || null,
                }))
              }
              className="mt-4 h-11 w-full rounded-2xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none"
              aria-label="选择文档集"
              title="选择文档集"
            >
              {docsets.map((docset, index) => (
                <option key={docset.id} value={docset.id}>
                  文档集 {docsets.length - index} · {docset.count} 个文件
                </option>
              ))}
            </select>
          ) : null}
          <div className="mt-4 space-y-2">
            {selectedDocset ? (
              selectedDocset.files.map((file) => (
                <div
                  key={`${selectedDocset.id}:${file.fileId || file.filename}`}
                  className="flex items-center gap-3 rounded-[20px] border border-slate-200 bg-slate-50 px-3 py-3"
                >
                  <FileTypeIcon type={file.type} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-900">
                      {file.filename}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">{file.size}</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[24px] border-2 border-dashed border-slate-200 bg-white/40 px-4 py-6 text-center text-[14px] font-medium text-slate-400 dark:border-white/10 dark:bg-white/5">
                暂无文档集
              </div>
            )}
          </div>
        </BottomSheet>
      ) : null}

      {isCurrentDocsetOpen && selectedDocset ? (
        <BottomSheet
          title="当前文档集"
          subtitle={`${selectedDocset.count} 个文件 · ${selectedDocset.uploadTime}`}
          onClose={() => setIsCurrentDocsetOpen(false)}
        >
          <div className="space-y-2">
            {selectedDocset.files.map((file) => (
              <div
                key={`${selectedDocset.id}:${file.fileId || file.filename}`}
                className="flex items-center gap-3 rounded-[20px] border border-slate-200 bg-slate-50 px-3 py-3"
              >
                <FileTypeIcon type={file.type} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900">
                    {file.filename}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">{file.size}</p>
                </div>
              </div>
            ))}
          </div>
        </BottomSheet>
      ) : null}

      {previewDocument ? (
        <div className="fixed inset-0 z-[70] flex flex-col bg-[#f6f9fc]">
          <div className="sticky top-0 z-10 border-b border-slate-200 bg-white/96 px-4 pb-4 pt-[max(14px,env(safe-area-inset-top))] backdrop-blur">
            <div className="flex items-center justify-between gap-3 pt-2">
              <button
                type="button"
                onClick={() => setPreviewDocument(null)}
                className="inline-flex h-11 min-w-[78px] items-center justify-center gap-2 rounded-2xl px-3 text-sm font-medium text-slate-700"
              >
                <ArrowLeft size={16} />
                返回
              </button>
              <div className="min-w-0 flex-1 text-center">
                <p className="truncate text-lg font-semibold text-slate-900">
                  {previewDocument.name}
                </p>
              </div>
              <div className="h-11 min-w-[78px] shrink-0" aria-hidden="true" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto pb-[max(12px,env(safe-area-inset-bottom))]">
            <div className="h-full overflow-hidden bg-neutral-50">
              {isPreviewLoading ? (
                <div className="flex min-h-[calc(100vh-120px)] items-center justify-center px-6">
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 size={20} className="animate-spin" />
                    <span>正在加载预览...</span>
                  </div>
                </div>
              ) : previewDocument.type === "docx" ? (
                <Module3WordPreview
                  document={{
                    id: previewDocument.runId ?? previewDocument.id,
                    name: previewDocument.name,
                  }}
                  fallbackContent={
                    previewContent ||
                    `文件名: ${previewDocument.name}\nfile_id: ${previewDocument.fileId ?? "unknown"}`
                  }
                />
              ) : previewDocument.type === "xlsx" && previewDocument.runId ? (
                <Module3ExcelPreview
                  document={{
                    id: previewDocument.runId,
                    name: previewDocument.name,
                  }}
                  fallbackContent={
                    previewContent ||
                    `文件名: ${previewDocument.name}\nfile_id: ${previewDocument.fileId ?? "unknown"}`
                  }
                />
              ) : (
                <PlainPreview
                  title={previewDocument.name}
                  content={previewContent}
                />
              )}
            </div>
          </div>
        </div>
      ) : null}

      <div
        className={cn(
          "fixed inset-0 z-30 bg-slate-950/35 transition-opacity duration-300",
          isSidebarOpen
            ? "pointer-events-auto opacity-100"
            : "pointer-events-none opacity-0",
        )}
        onClick={() => {
          setIsSidebarOpen(false);
          setIsSidebarFullWidth(false);
        }}
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex flex-col overflow-visible border-none bg-[#F8FAFC]/95 shadow-2xl shadow-slate-900/10 px-4 pb-[max(20px,env(safe-area-inset-bottom))] pt-4 backdrop-blur-xl transition-transform duration-300 dark:bg-[#0B1120]/95 dark:shadow-none",
          isSidebarFullWidth ? "w-full max-w-none" : "w-[82vw] max-w-[320px]",
          isSidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {isSidebarOpen ? (
          <button
            type="button"
            onClick={() => setIsSidebarFullWidth((current) => !current)}
            className="absolute -right-5 top-1/2 z-20 inline-flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-white shadow-md text-slate-500 transition-transform active:scale-95 dark:bg-[#1A1D24] dark:text-slate-300"
            aria-label={isSidebarFullWidth ? "收缩任务中心" : "展开任务中心"}
            title={isSidebarFullWidth ? "收缩任务中心" : "展开任务中心"}
          >
            {isSidebarFullWidth ? (
              <ArrowLeft size={18} />
            ) : (
              <ArrowRight size={18} />
            )}
          </button>
        ) : null}
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="mt-1 text-2xl font-bold text-slate-950">任务中心</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              在这里查看和打开任务结果。
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setIsSidebarOpen(false);
              setIsSidebarFullWidth(false);
            }}
            className="rounded-full p-2 text-slate-400"
            aria-label="关闭任务中心"
            title="关闭任务中心"
          >
            <X size={18} />
          </button>
        </div>
        <div
          className="mt-5 min-h-0 flex-1 overflow-y-auto overscroll-y-contain pb-4 pr-1 touch-pan-y [-webkit-overflow-scrolling:touch]"
        >
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "总任务", value: stats.total, tone: "bg-slate-100" },
                { label: "已完成", value: stats.done, tone: "bg-emerald-50" },
                { label: "失败", value: stats.failed, tone: "bg-red-50" },
              ].map((item) => (
                <div
                  key={item.label}
                  className={cn("rounded-2xl px-3 py-3 text-center", item.tone)}
                >
                  <div className="text-lg font-bold text-slate-900">
                    {item.value}
                  </div>
                  <div className="text-[11px] text-slate-500">{item.label}</div>
                </div>
              ))}
            </div>
            {tasks.map((task) => {
              const isCancelling = cancellingTaskIds.includes(task.id);
              const [label, badge, icon] = isCancelling
                ? ([
                    "取消中",
                    "bg-amber-100 text-amber-700",
                    <Loader2 size={14} className="animate-spin" key="i" />,
                  ] as const)
                : taskMeta(task.status);
              const previewName = getTaskOutputName(task);
              const previewType = getDocumentType(previewName);
              const previewTarget =
                task.status === "done" &&
                (Boolean(task.outputFileId) || canPreviewByRunType(previewType))
                  ? {
                      id: task.id,
                      name: previewName,
                      fileId: task.outputFileId ?? null,
                      type: previewType,
                      runId: task.id,
                    }
                  : null;
              return (
                <div
                  key={task.id}
                  onClick={() =>
                    setGridState((current) => ({
                      ...current,
                      selectedTaskId: task.id,
                    }))
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setGridState((current) => ({
                        ...current,
                        selectedTaskId: task.id,
                      }));
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  className={cn(
                    "w-full rounded-[28px] p-5 text-left transition-all active:scale-[0.98] border-none",
                    gridState.selectedTaskId === task.id
                      ? "bg-white shadow-md ring-2 ring-cyan-500/20 dark:bg-white/10 dark:ring-cyan-400/30"
                      : "bg-white/60 shadow-sm dark:bg-white/5",
                  )}
                  aria-label={`任务 ${getTaskOutputName(task)}，状态 ${label}`}
                >
                  <div className="flex items-start gap-3">
                    <FileTypeIcon
                      type={getDocumentType(getTaskOutputName(task))}
                      className="mt-0.5"
                    />
                    <div
                      className={cn(
                        "min-w-0 flex-1",
                        isSidebarFullWidth && "flex items-start gap-4",
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-slate-900">
                              {getTaskOutputName(task)}
                            </p>
                            <div
                              className={cn(
                                "mt-1 text-[11px] text-slate-500",
                                isSidebarFullWidth
                                  ? "flex flex-col items-start gap-1"
                                  : "flex flex-wrap items-center gap-2",
                              )}
                            >
                              <span
                                className={cn(
                                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
                                  badge,
                                )}
                              >
                                {icon}
                                {label}
                              </span>
                              <span>{task.fillRate}%</span>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              removeTask(task.id);
                            }}
                            className="rounded-full p-2 text-slate-400"
                            aria-label="删除任务"
                            title="删除任务"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        {!isSidebarFullWidth ? (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {task.status === "running" ? (
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleCancelTask(task.id);
                                }}
                                disabled={cancellingTaskIds.includes(task.id)}
                                className="inline-flex min-h-[40px] items-center gap-2 rounded-2xl bg-amber-100 px-3 text-xs font-medium text-amber-700 disabled:opacity-50"
                                aria-label="取消任务"
                                title="取消任务"
                              >
                                {cancellingTaskIds.includes(task.id) ? (
                                  <Loader2 size={14} className="animate-spin" />
                                ) : (
                                  <X size={14} />
                                )}
                                取消
                              </button>
                            ) : null}
                            {previewTarget ? (
                              <>
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    setIsSidebarOpen(false);
                                    void openPreview(previewTarget);
                                  }}
                                  className="inline-flex min-h-[40px] items-center gap-2 rounded-2xl bg-slate-100 px-3 text-xs font-medium text-slate-700"
                                  aria-label="预览结果"
                                  title="预览结果"
                                >
                                  <Eye size={14} />
                                  预览
                                </button>
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    window.location.assign(
                                      module3RunDownloadUrl(task.id),
                                    );
                                  }}
                                  className="inline-flex min-h-[40px] items-center gap-2 rounded-2xl bg-emerald-100 px-3 text-xs font-medium text-emerald-700"
                                  aria-label="下载结果"
                                  title="下载结果"
                                >
                                  <Download size={14} />
                                  下载
                                </button>
                              </>
                            ) : null}
                          </div>
                        ) : null}
                        <p className="mt-3 text-[11px] text-slate-400">
                          {task.createdAt}
                        </p>
                      </div>
                        {isSidebarFullWidth ? (
                          <div className="flex shrink-0 flex-wrap items-center gap-2 self-center">
                            {task.status === "running" ? (
                              <button
                                type="button"
                                onClick={(event) => {
                                event.stopPropagation();
                                void handleCancelTask(task.id);
                              }}
                              disabled={cancellingTaskIds.includes(task.id)}
                              className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-2xl bg-amber-100 px-3 text-xs font-medium text-amber-700 disabled:opacity-50"
                              aria-label="取消任务"
                              title="取消任务"
                            >
                              {cancellingTaskIds.includes(task.id) ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : (
                                <X size={14} />
                              )}
                              取消
                            </button>
                          ) : null}
                          {previewTarget ? (
                            <>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setIsSidebarOpen(false);
                                  void openPreview(previewTarget);
                                }}
                                className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-2xl bg-slate-100 px-3 text-xs font-medium text-slate-700"
                                aria-label="预览结果"
                                title="预览结果"
                              >
                                <Eye size={14} />
                                预览
                              </button>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  window.location.assign(
                                    module3RunDownloadUrl(task.id),
                                  );
                                }}
                                className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-2xl bg-emerald-100 px-3 text-xs font-medium text-emerald-700"
                                aria-label="下载结果"
                                title="下载结果"
                              >
                                <Download size={14} />
                                下载
                              </button>
                            </>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </aside>

      <div className="mx-auto flex w-full max-w-[460px] flex-col px-4 pb-8 pt-[max(16px,env(safe-area-inset-top))]">
        <header className="sticky top-0 z-20 -mx-4 px-4 pb-4 backdrop-blur-md bg-[#EAF7F8]/80 dark:bg-[#0B1120]/80">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="mt-3 text-[30px] font-black tracking-tight text-slate-950 dark:text-slate-100">
                多源数据融合
              </h1>
            </div>
            <div className="mt-3 flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => setIsHelpOpen(true)}
                className="flex h-11 w-11 items-center justify-center rounded-[20px] bg-white text-slate-500 shadow-sm dark:bg-white/5 dark:text-slate-300"
                aria-label="打开使用说明"
                title="打开使用说明"
              >
                <HelpCircle size={18} />
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsSidebarFullWidth(false);
                  setIsSidebarOpen(true);
                }}
                className="flex h-11 w-11 items-center justify-center rounded-[20px] bg-white text-slate-500 shadow-sm dark:bg-white/5 dark:text-slate-300"
                aria-label="打开任务中心"
                title="打开任务中心"
              >
                <PanelLeft size={18} />
              </button>
            </div>
          </div>
        </header>

        <div className="space-y-4 pt-4">
          <section className="mb-10">
            <div className="mb-4">
              <h2 className="mt-1 text-[22px] font-bold text-slate-950 dark:text-slate-100">
                资源准备
              </h2>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setIsTemplatePanelOpen(true)}
                className="group relative flex min-h-[100px] flex-col items-start justify-between overflow-hidden rounded-[28px] bg-white p-5 text-left shadow-sm active:scale-[0.98] transition-transform dark:bg-white/5"       
              >
                <div className="absolute -right-4 -top-4 h-24 w-24 rounded-full bg-sky-50/50 blur-2xl dark:bg-sky-900/20" />
                <div className="flex w-full items-center justify-between gap-3 relative z-10">
                  <div className="flex h-10 w-10 items-center justify-center rounded-[16px] bg-sky-50 text-sky-600 dark:bg-sky-500/20 dark:text-sky-300">
                    {isUploadingTemplate ? (
                      <Loader2 size={20} className="animate-spin" />
                    ) : (
                      <UploadCloud size={20} />
                    )}
                  </div>
                </div>
                <div className="mt-3 relative z-10">
                  <p className="text-[15px] font-bold text-slate-900 dark:text-slate-100">        
                    模板管理
                  </p>
                </div>
              </button>
              <button
                type="button"
                onClick={() => setIsDocsetPanelOpen(true)}
                className="group relative flex min-h-[100px] flex-col items-start justify-between overflow-hidden rounded-[28px] bg-white p-5 text-left shadow-sm active:scale-[0.98] transition-transform dark:bg-white/5"       
              >
                <div className="absolute -right-4 -top-4 h-24 w-24 rounded-full bg-indigo-50/50 blur-2xl dark:bg-indigo-900/20" />
                <div className="flex w-full items-center justify-between gap-3 relative z-10">
                  <div className="flex h-10 w-10 items-center justify-center rounded-[16px] bg-indigo-50 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                    {isUploadingDocset ? (
                      <Loader2 size={20} className="animate-spin" />
                    ) : (
                      <FolderOpen size={20} />
                    )}
                  </div>
                </div>
                <div className="mt-3 relative z-10">
                  <p className="text-[15px] font-bold text-slate-900 dark:text-slate-100">        
                    文档集管理
                  </p>
                </div>
              </button>
            </div>
            <div className="mt-4 grid gap-3">
              {selectedTemplate ? (
                <div
                  onClick={() => setIsTemplatePanelOpen(true)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setIsTemplatePanelOpen(true);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  className="flex w-full items-center justify-between gap-3 overflow-hidden rounded-[24px] bg-white shadow-sm px-4 py-3.5 text-left dark:bg-white/5"
                  aria-label={`查看模板 ${selectedTemplate.name}`}
                >
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <div className="flex min-w-0 items-center gap-2">
                      <p className="min-w-0 truncate text-sm font-semibold text-slate-900">
                        {selectedTemplate.name}
                      </p>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {selectedTemplate.size} · {selectedTemplate.fields.length}{" "}
                      个字段
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      removeTemplate(selectedTemplate.id);
                    }}
                    className="shrink-0 rounded-full p-2 text-slate-400"
                    aria-label="删除已选模板"
                    title="删除已选模板"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ) : (
                <div className="rounded-[24px] border-2 border-dashed border-slate-200 bg-white/40 px-4 py-6 text-center text-[14px] font-medium text-slate-400 dark:border-white/10 dark:bg-white/5">
                  暂无模板
                </div>
              )}
              {selectedDocset ? (
                <div className="overflow-hidden rounded-[24px] bg-white shadow-sm dark:bg-white/5">
                  <div className="flex items-center justify-between gap-3 px-3 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-900">
                        当前文档集
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {selectedDocset.count} 个文件 ·{" "}
                        {selectedDocset.uploadTime}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setIsCurrentDocsetOpen((current) => !current)
                      }
                      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-slate-400"
                      aria-label={isCurrentDocsetOpen ? "收起文档集" : "展开文档集"}
                      title={isCurrentDocsetOpen ? "收起文档集" : "展开文档集"}
                      aria-expanded={isCurrentDocsetOpen}
                    >
                      <ChevronDown size={16} />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="rounded-[24px] border-2 border-dashed border-slate-200 bg-white/40 px-4 py-6 text-center text-[14px] font-medium text-slate-400 dark:border-white/10 dark:bg-white/5">
                  暂无文档集
                </div>
              )}
            </div>
          </section>

          <section className="mt-12">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-[22px] font-bold text-slate-950 dark:text-slate-100">用户要求</h2>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                {gridState.draftRequirements.length}/600
              </span>
            </div>
            <textarea
              value={gridState.draftRequirements}
              onChange={(event) =>
                setGridState((current) => ({
                  ...current,
                  draftRequirements: event.target.value,
                }))
              }
              maxLength={600}
              rows={4}
              placeholder="例如：只保留 2025 年山东相关数据，金额统一保留两位小数。"
              className="min-h-[100px] w-full resize-none rounded-[24px] border-none bg-white shadow-sm px-5 py-4 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:ring-4 focus:ring-cyan-500/10 dark:bg-white/5 dark:text-slate-200 dark:focus:ring-cyan-400/20"
              aria-label="用户要求"
              title="用户要求"
            />
            <button
              type="button"
              onClick={handleStartRun}
              disabled={isRunning || !selectedTemplate || !selectedDocset}
              className="mt-6 flex h-[56px] w-full items-center justify-center gap-2 rounded-full bg-slate-900 text-[16px] font-bold text-white shadow-lg shadow-slate-900/20 active:scale-[0.98] transition-transform disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:shadow-none"
            >
              {isRunning ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Play size={16} />
              )}
              {isRunning ? "创建中..." : "开始填充"}
            </button>
            {errorMessage ? (
              <p className="mt-2 rounded-2xl bg-red-50 px-3 py-2 text-xs text-red-600">
                {errorMessage}
              </p>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  );
};
