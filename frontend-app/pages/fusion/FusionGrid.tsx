﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿import React, { useEffect, useMemo, useRef, useState } from "react";
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
  parseModule3MissingResource,
  uploadModule3Docset,
  uploadModule3Template,
  type Module3RunStatusResponse,
  type Module3TaskStatus,
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
import { useMobileOverlayRegistration } from "../../shared/hooks/useMobileOverlayPresence";
import {
  describeMobileDownloadResult,
  downloadUrlToMobileDevice,
} from "../../shared/mobileDownload";
import { MobilePageShell } from "../../components/mobile/MobilePageShell";
import { Module3ExcelPreview } from "./Module3ExcelPreview";
import { Module3WordPreview } from "./Module3WordPreview";
import excelIconUrl from "../../assets/xlsx.png";
import mdIconUrl from "../../assets/md.png";
import txtIconUrl from "../../assets/txt.png";
import wordIconUrl from "../../assets/WORD.png";
import colorCursorUrl from "../../assets/彩色光标.png";

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
  <div className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center bg-black/32 sm:p-4" data-mobile-overlay="true">
    <div className="flex max-h-[var(--mobile-sheet-max-height)] w-full max-w-md flex-col overflow-hidden rounded-t-[32px] sm:rounded-[32px] bg-white shadow-2xl dark:bg-[#1A1D24] pb-[var(--mobile-safe-bottom)]">
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
  const requirementsTextareaRef = useRef<HTMLTextAreaElement>(null);

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
  const missingStartRequirements = useMemo(() => {
    const missing: string[] = [];
    if (!selectedTemplate) missing.push("模板文件");
    if (!selectedDocset) missing.push("文档集");
    return missing;
  }, [selectedDocset, selectedTemplate]);
  const canStartRun = !isRunning && missingStartRequirements.length === 0;

  useMobileOverlayRegistration(
    Boolean(
      previewDocument ||
        isSidebarOpen ||
        isHelpOpen ||
        isTemplatePanelOpen ||
        isDocsetPanelOpen ||
        isCurrentDocsetOpen ||
        isTaskPanelOpen,
    ),
  );

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

  const dropMissingRunDependency = (
    kind: "template" | "docset",
    missingId: string,
  ) => {
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
  };

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
        setErrorMessage(error instanceof Error ? error.message : "任务创建失败");
      }
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

  const handleDownloadTask = async (task: FusionGridTaskRecord) => {
    try {
      setErrorMessage("");
      const suggestedName = getTaskOutputName(task) || `run_${task.id}.bin`;
      const result = await downloadUrlToMobileDevice({
        url: module3RunDownloadUrl(task.id),
        fileName: suggestedName,
        moduleName: "module3",
      });
      setInfoMessage(describeMobileDownloadResult(result));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "下载失败");
    }
  };

  const stats = {
    total: tasks.length,
    done: tasks.filter((item) => item.status === "done").length,
    failed: tasks.filter((item) => item.status === "failed").length,
  };

  return (
    <MobilePageShell
      withBottomNav={false}
      constrain="none"
      className="overflow-x-hidden bg-gradient-to-b from-[#C5F1F3] via-[#E6F7F9] to-[#F2F5F8] dark:from-slate-900 dark:via-slate-900 dark:to-slate-950"
    >
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
          title="自定义智能填表使用说明"
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
            className="group flex w-full items-center gap-3 rounded-[24px] bg-slate-50/80 px-5 py-4 text-left transition-colors active:bg-slate-100 dark:bg-white/5 dark:active:bg-white/10"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-sky-500 shadow-[0_2px_8px_rgba(14,165,233,0.12)] transition-transform group-active:scale-95 dark:bg-white/10 dark:text-sky-400">
              {isUploadingTemplate ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <UploadCloud size={18} />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <span className="block text-[15px] font-semibold text-slate-800 dark:text-slate-100">
                {isUploadingTemplate ? "模板解析上传中..." : "上传新的模板"}
              </span>
              <span className="mt-0.5 block text-[13px] text-slate-500 dark:text-slate-400">
                支持 .docx, .xlsx 格式文件
              </span>
            </div>
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
              <div className="py-6 text-center text-[13px] font-medium text-slate-400 dark:text-slate-500">
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
            className="group flex w-full items-center gap-3 rounded-[24px] bg-slate-50/80 px-5 py-4 text-left transition-colors active:bg-slate-100 dark:bg-white/5 dark:active:bg-white/10"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-indigo-500 shadow-[0_2px_8px_rgba(99,102,241,0.12)] transition-transform group-active:scale-95 dark:bg-white/10 dark:text-indigo-400">
              {isUploadingDocset ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <FolderOpen size={18} />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <span className="block text-[15px] font-semibold text-slate-800 dark:text-slate-100">
                {isUploadingDocset ? "文档集上传中..." : "上传文档集文件"}
              </span>
              <span className="mt-0.5 block text-[13px] text-slate-500 dark:text-slate-400">
                支持多选 .pdf, .docx 等文件
              </span>
            </div>
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
              <div className="py-6 text-center text-[13px] font-medium text-slate-400 dark:text-slate-500">
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
        <div className="fixed inset-0 z-[70] flex flex-col bg-[#f6f9fc]" data-mobile-overlay="true">
          <div className="flex-1 overflow-y-auto">
            <div className="h-full overflow-hidden bg-neutral-50 dark:bg-slate-950">
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
                  onBack={() => setPreviewDocument(null)}
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
                  onBack={() => setPreviewDocument(null)}
                />
              ) : (
                <div className="flex flex-col h-full">
                  <div className="sticky top-0 z-10 border-b border-slate-100 bg-white/80 px-4 pb-3 pt-[max(12px,var(--mobile-safe-top))] backdrop-blur-md shadow-sm dark:border-white/5 dark:bg-slate-900/80">
                    <div className="flex items-center justify-between gap-3 pt-2">
                      <button
                        type="button"
                        onClick={() => setPreviewDocument(null)}
                        className="group relative flex h-9 items-center justify-center gap-1.5 overflow-hidden rounded-full bg-slate-50 px-3.5 text-[14px] font-bold text-slate-700 shadow-[0_2px_8px_rgba(15,23,42,0.04)] ring-1 ring-slate-900/5 transition-all active:scale-95 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10"
                      >
                        <div className="absolute inset-0 bg-slate-900/0 transition-colors group-hover:bg-slate-900/5 group-active:bg-slate-900/10 dark:group-hover:bg-white/5 dark:group-active:bg-white/10" />
                        <ArrowLeft size={16} className="relative z-10" />
                        <span className="relative z-10">返回</span>
                      </button>
                      <div className="min-w-0 flex-1 text-center">
                        <p className="truncate text-[16px] font-bold text-slate-900 dark:text-slate-100">
                          {previewDocument.name}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center justify-end gap-2">
                        <div className="h-9 min-w-[76px] shrink-0" aria-hidden="true" />
                      </div>
                    </div>
                  </div>
                  <PlainPreview
                    title={previewDocument.name}
                    content={previewContent}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {isSidebarOpen ? (
        <BottomSheet
          title="任务中心"
          subtitle="在这里查看和打开任务结果。"
          onClose={() => {
            setIsSidebarOpen(false);
            setIsSidebarFullWidth(false);
          }}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "总任务", value: stats.total, tone: "bg-slate-50 dark:bg-white/5" },
                { label: "已完成", value: stats.done, tone: "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" },
                { label: "失败", value: stats.failed, tone: "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400" },
              ].map((item) => (
                <div
                  key={item.label}
                  className={cn("rounded-2xl px-3 py-2 text-center", item.tone)}
                >
                  <div className={cn("text-[20px] font-bold leading-tight", item.label === "总任务" ? "text-slate-900 dark:text-white" : "")}>
                    {item.value}
                  </div>
                  <div className={cn("mt-0.5 text-[11px]", item.label === "总任务" ? "text-slate-500" : "opacity-70")}>{item.label}</div>
                </div>
              ))}
            </div>
            <div className="space-y-3">
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
                    "w-full rounded-[24px] p-4 text-left transition-all active:scale-[0.98] border-none",
                    gridState.selectedTaskId === task.id
                      ? "bg-white shadow-[0_8px_24px_rgba(0,0,0,0.06)] ring-1 ring-slate-900/5 dark:bg-slate-800 dark:ring-white/10"
                      : "bg-white shadow-sm ring-1 ring-slate-900/5 dark:bg-white/5 dark:ring-0",
                  )}
                  aria-label={`任务 ${getTaskOutputName(task)}，状态 ${label}`}
                >
                  <div className="flex items-start gap-3">
                    <FileTypeIcon
                      type={getDocumentType(getTaskOutputName(task))}
                      className="mt-0.5 shrink-0"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <p className="truncate text-[15px] font-bold text-slate-900 dark:text-slate-100">
                          {getTaskOutputName(task)}
                        </p>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            removeTask(task.id);
                          }}
                          className="shrink-0 rounded-full p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500 active:scale-95 transition-colors dark:hover:bg-red-500/10"
                          aria-label="删除任务"
                          title="删除任务"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                      
                      <div className="mt-1 flex items-center gap-2 text-[12px] text-slate-500">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium",
                            badge,
                          )}
                        >
                          {icon}
                          {label}
                        </span>
                        {task.fillRate !== undefined && <span className="font-medium">{task.fillRate}%</span>}
                        <span className="text-slate-200 dark:text-slate-700">|</span>
                        <span className="text-[11px] text-slate-400">{task.createdAt}</span>
                      </div>

                      <div className="mt-3.5 flex flex-wrap gap-2">
                        {task.status === "running" ? (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleCancelTask(task.id);
                            }}
                            disabled={cancellingTaskIds.includes(task.id)}
                            className="inline-flex h-[32px] items-center gap-1.5 rounded-full bg-amber-50 px-3.5 text-xs font-bold text-amber-700 disabled:opacity-50 dark:bg-amber-500/10 dark:text-amber-400"
                            aria-label="取消任务"
                            title="取消任务"
                          >
                            {cancellingTaskIds.includes(task.id) ? (
                              <Loader2 size={13} className="animate-spin" />
                            ) : (
                              <X size={13} />
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
                              className="inline-flex h-[32px] items-center gap-1.5 rounded-full bg-slate-100 px-3.5 text-xs font-bold text-slate-700 transition-colors active:bg-slate-200 dark:bg-white/10 dark:text-slate-300 dark:active:bg-white/20"
                              aria-label="预览结果"
                              title="预览结果"
                            >
                              <Eye size={13} />
                              预览
                            </button>
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleDownloadTask(task);
                              }}
                              className="inline-flex h-[32px] items-center gap-1.5 rounded-full bg-emerald-50 px-3.5 text-xs font-bold text-emerald-600 transition-colors active:bg-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-400 dark:active:bg-emerald-500/20"
                              aria-label="下载结果"
                              title="下载结果"
                            >
                              <Download size={13} />
                              下载
                            </button>
                          </>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
            </div>
          </div>
        </BottomSheet>
      ) : null}

      <div className="mx-auto flex min-h-[var(--app-visual-height,100dvh)] w-full max-w-none flex-col overflow-hidden bg-gradient-to-b from-[#C5F1F3] via-[#E6F7F9] to-[#F2F5F8] shadow-2xl ring-1 ring-slate-900/5 dark:from-slate-900 dark:via-slate-900 dark:to-slate-950 min-[480px]:max-w-[430px] min-[600px]:my-6 min-[600px]:min-h-[min(var(--app-visual-height,100dvh),860px)] min-[600px]:max-w-[560px] min-[600px]:rounded-[32px] lg:my-8 lg:h-[667px] lg:min-h-0 lg:max-w-[375px] relative">
        <div className="flex-1 overflow-y-auto px-[var(--mobile-page-x)] pb-[var(--mobile-content-bottom)] pt-[max(16px,var(--mobile-safe-top))] lg:pb-[120px]">
          <header className="relative z-20 flex items-center justify-between gap-2 pb-6 pt-1 min-[390px]:gap-3">
            <div className="min-w-0 flex flex-col gap-1">
              <h1 className="flex items-center text-[var(--mobile-title-size)] font-bold tracking-tight text-slate-900 dark:text-white">
                自定义
                <span className="relative ml-1 inline-block">
                  <span className="relative z-10 text-transparent bg-clip-text bg-gradient-to-r from-[#3B82F6] via-[#6366F1] to-[#D946EF] dark:from-[#60A5FA] dark:via-[#818CF8] dark:to-[#E879F9]">
                    智能填表
                  </span>
                  <img
                    src={colorCursorUrl}
                    alt=""
                    aria-hidden="true"
                    className="pointer-events-none absolute -right-[14px] -top-[7px] z-20 h-7 w-7 select-none object-contain drop-shadow-[0_1px_2px_rgba(15,23,42,0.32)] max-[359px]:-right-[10px] max-[359px]:-top-[6px] max-[359px]:h-6 max-[359px]:w-6"
                  />
                </span>
              </h1>
              <p className="text-[clamp(12px,3.5vw,14px)] text-slate-500/90 dark:text-slate-400">
                多源文档数据融合与结构化提取
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => setIsHelpOpen(true)}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-white/60 text-slate-600 shadow-sm backdrop-blur-md transition-all active:scale-95 dark:bg-white/10 dark:text-slate-300 dark:shadow-none max-[359px]:h-9 max-[359px]:w-9"
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
                className="flex h-10 w-10 items-center justify-center rounded-full bg-white/60 text-slate-600 shadow-sm backdrop-blur-md transition-all active:scale-95 dark:bg-white/10 dark:text-slate-300 dark:shadow-none max-[359px]:h-9 max-[359px]:w-9"
                aria-label="打开任务中心"
                title="打开任务中心"
              >
                <PanelLeft size={18} />
              </button>
            </div>
          </header>

        <div className="space-y-4">
          <section className="mb-8">
            <div className="mb-4">
              <h2 className="text-[var(--mobile-section-title-size)] font-bold text-slate-900 dark:text-slate-100">
                资源准备
              </h2>
            </div>
            <div className="grid grid-cols-1 gap-3 min-[360px]:grid-cols-2">
              <button
                type="button"
                onClick={() => setIsTemplatePanelOpen(true)}
                className="group relative flex min-h-[64px] w-full items-center overflow-hidden rounded-[20px] bg-white/60 p-3 text-left backdrop-blur-xl ring-1 ring-white/50 transition-all active:scale-[0.98] dark:bg-white/5 dark:ring-white/10 min-[390px]:min-h-[68px]"
              >
                <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-cyan-400/10 blur-2xl transition-colors group-hover:bg-cyan-400/20 dark:bg-cyan-900/20" />
                <div className="relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-white shadow-[0_2px_8px_rgba(15,23,42,0.04)] text-cyan-600 transition-colors group-hover:text-cyan-500 dark:bg-cyan-500/20 dark:text-cyan-300 dark:group-hover:bg-cyan-500/30">
                  {isUploadingTemplate ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <UploadCloud size={18} />
                  )}
                </div>
                <div className="relative z-10 ml-3 min-w-0 flex-1">
                  <p className="truncate text-[clamp(14px,3.8vw,15px)] font-bold text-slate-800 dark:text-slate-100">
                    模板管理
                  </p>
                </div>
              </button>
              
              <button
                type="button"
                onClick={() => setIsDocsetPanelOpen(true)}
                className="group relative flex min-h-[64px] w-full items-center overflow-hidden rounded-[20px] bg-white/60 p-3 text-left backdrop-blur-xl ring-1 ring-white/50 transition-all active:scale-[0.98] dark:bg-white/5 dark:ring-white/10 min-[390px]:min-h-[68px]"
              >
                <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-indigo-400/10 blur-2xl transition-colors group-hover:bg-indigo-400/20 dark:bg-indigo-900/20" />
                <div className="relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-white shadow-[0_2px_8px_rgba(15,23,42,0.04)] text-indigo-600 transition-colors group-hover:text-indigo-500 dark:bg-indigo-500/20 dark:text-indigo-300 dark:group-hover:bg-indigo-500/30">
                  {isUploadingDocset ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <FolderOpen size={18} />
                  )}
                </div>
                <div className="relative z-10 ml-3 min-w-0 flex-1">
                  <p className="truncate text-[clamp(14px,3.8vw,15px)] font-bold text-slate-800 dark:text-slate-100">
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
                  className="flex w-full items-center justify-between gap-3 overflow-hidden rounded-[20px] bg-white shadow-sm ring-1 ring-slate-900/5 px-4 py-3.5 text-left transition-all active:scale-[0.98] dark:bg-white/5 dark:ring-0"
                  aria-label={`查看模板 ${selectedTemplate.name}`}
                >
                  <FileTypeIcon type={getDocumentType(selectedTemplate.name)} className="shrink-0 h-8 w-8" />
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <p className="truncate text-[14px] font-semibold text-slate-900 dark:text-slate-100">
                      {selectedTemplate.name}
                    </p>
                    <p className="mt-0.5 text-[12px] text-slate-500">
                      {selectedTemplate.size} · {selectedTemplate.fields.length} 个字段
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      removeTemplate(selectedTemplate.id);
                    }}
                    className="shrink-0 rounded-full p-2 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors dark:hover:bg-red-500/10 dark:hover:text-red-400"
                    aria-label="删除已选模板"
                    title="删除已选模板"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ) : null}
              {selectedDocset ? (
                <div className="overflow-hidden rounded-[20px] bg-white shadow-sm ring-1 ring-slate-900/5 dark:bg-white/5 dark:ring-0">
                  <div className="flex items-center justify-between gap-3 px-4 py-3.5">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-indigo-50 text-indigo-500 dark:bg-indigo-500/20 dark:text-indigo-400">
                      <FolderOpen size={18} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[14px] font-semibold text-slate-900 dark:text-slate-100">
                        当前文档集
                      </p>
                      <p className="mt-0.5 text-[12px] text-slate-500">
                        {selectedDocset.count} 个文件 · {selectedDocset.uploadTime.split(' ')[0]}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setIsCurrentDocsetOpen((current) => !current)}
                      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-50 text-slate-500 transition-colors active:bg-slate-100 dark:bg-white/10 dark:text-slate-400"
                      aria-label={isCurrentDocsetOpen ? "收起文档集" : "展开文档集"}
                      title={isCurrentDocsetOpen ? "收起文档集" : "展开文档集"}
                      aria-expanded={isCurrentDocsetOpen}
                    >
                      <ChevronDown
                        size={16}
                        className={cn(
                          "transition-transform duration-200",
                          isCurrentDocsetOpen && "rotate-180"
                        )}
                      />
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </section>

          <section className="mt-8">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-[var(--mobile-section-title-size)] font-bold text-slate-900 dark:text-slate-100">用户要求</h2>
              <button
                type="button"
                onClick={handleStartRun}
                disabled={!canStartRun}
                className="group relative flex h-[36px] items-center justify-center gap-1.5 overflow-hidden rounded-full bg-cyan-50 px-4 text-[13px] font-bold text-cyan-600 transition-all hover:bg-cyan-100 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-slate-50 disabled:text-slate-400 dark:bg-cyan-500/10 dark:text-cyan-400 dark:hover:bg-cyan-500/20 dark:disabled:bg-slate-900 dark:disabled:text-slate-500"
              >
                {isRunning ? (
                  <Loader2 size={14} className="relative z-10 animate-spin" />
                ) : (
                  <Play size={14} className="relative z-10 fill-current" />
                )}
                <span className="relative z-10">{isRunning ? "创建中" : "开始填充"}</span>
              </button>
            </div>
            
            <div className="relative w-full overflow-hidden rounded-[24px] bg-white shadow-sm ring-1 ring-slate-900/5 focus-within:ring-2 focus-within:ring-cyan-500/30 focus-within:shadow-[0_8px_30px_rgba(6,182,212,0.08)] transition-all duration-300 dark:bg-white/5 dark:ring-white/10 dark:focus-within:ring-cyan-400/40">
              <textarea
                ref={requirementsTextareaRef}
                value={gridState.draftRequirements}
                onChange={(event) =>
                  setGridState((current) => ({
                    ...current,
                    draftRequirements: event.target.value,
                  }))
                }
                maxLength={600}
                placeholder="例如：只保留 2025 年山东相关数据，金额统一保留两位小数。"
                className="block h-[120px] w-full resize-none overflow-y-auto bg-transparent px-5 py-4 pb-10 text-[15px] leading-relaxed text-slate-700 outline-none placeholder:text-slate-400 dark:text-slate-200 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-slate-200/70 hover:[&::-webkit-scrollbar-thumb]:bg-slate-300/80 dark:[&::-webkit-scrollbar-thumb]:bg-slate-700/50 dark:hover:[&::-webkit-scrollbar-thumb]:bg-slate-600/80 [&::-webkit-scrollbar-track]:bg-transparent"
                aria-label="用户要求"
                title="用户要求"
              />
              <div className="absolute bottom-3 right-4 select-none pointer-events-none">
                <span className="text-[11px] font-medium text-slate-400">
                  {gridState.draftRequirements.length}
                  <span className="opacity-50">/600</span>
                </span>
              </div>
            </div>
            <div
              className={cn(
                "mt-3 rounded-[18px] px-4 py-3 text-[12px] leading-5",
                missingStartRequirements.length > 0
                  ? "bg-white/58 text-slate-500 ring-1 ring-white/70 dark:bg-white/5 dark:text-slate-400 dark:ring-white/10"
                  : "bg-cyan-50/80 text-cyan-700 ring-1 ring-cyan-100/80 dark:bg-cyan-500/10 dark:text-cyan-300 dark:ring-cyan-500/20",
              )}
            >
              {missingStartRequirements.length > 0 ? (
                <>
                  开始填充前还需要：
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    {missingStartRequirements.join("、")}
                  </span>
                  。用户要求可以为空，但填写得越具体，填表结果越稳定。
                </>
              ) : gridState.draftRequirements.trim() ? (
                "资源已就绪，可以开始填充；系统会按当前用户要求生成结果。"
              ) : (
                "模板和文档集已就绪。建议补充筛选、格式或填充规则，让结果更符合预期。"
              )}
            </div>
            {errorMessage ? (
              <p className="mt-2 rounded-2xl bg-red-50 px-3 py-2 text-xs text-red-600">
                {errorMessage}
              </p>
            ) : null}
          </section>
        </div>
      </div>
    </div>
    </MobilePageShell>
  );
};
