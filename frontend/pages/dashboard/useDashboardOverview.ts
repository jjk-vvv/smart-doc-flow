import { useEffect, useMemo, useState } from 'react';

import type { AuthUser } from '../../shared/api/auth';
import { fetchModule1Health, type Module1HealthResponse } from '../../shared/api/module1';
import {
  requestPlatformAssistantBootstrap,
  type PlatformAssistantBootstrapResponse,
} from '../../shared/api/platformAssistant';
import {
  requestExtractionHealth,
} from '../../shared/api/extraction';
import {
  readExtractionDocuments,
  readExtractionUpdatedAt,
  subscribeExtractionUpdates,
  type ExtractionDocument,
} from '../../shared/state/extractionDocuments';
import { fetchModule3Overview, type Module3OverviewResponse } from '../../lib/module3Api';
import {
  fetchModule4Alerts,
  fetchModule4GraphFiles,
  fetchModule4Healthz,
  type Module4AlertListResponse,
  type Module4GraphFileListResponse,
  type Module4HealthzResponse,
} from '../../shared/api/knowledgeGraph';

export type DashboardTabId =
  | 'dashboard'
  | 'doc-processing'
  | 'deepread_extraction'
  | 'fusion'
  | 'nexus'
  | 'guide';

export type DashboardTone = 'neutral' | 'good' | 'warn' | 'danger' | 'info';

export type DashboardStripItem = {
  id: string;
  label: string;
  value: string;
  detail: string;
  tone: DashboardTone;
};

export type DashboardWorkflowStage = {
  id: string;
  label: string;
  summary: string;
  metric: string;
  subMetric: string;
  tone: DashboardTone;
  targetTab: DashboardTabId;
};

export type DashboardActionItem = {
  id: string;
  label: string;
  summary: string;
  targetTab: DashboardTabId;
  variant: 'primary' | 'secondary' | 'ghost';
};

export type DashboardWorkItem = {
  id: string;
  title: string;
  summary: string;
  meta: string;
  tone: DashboardTone;
  targetTab: DashboardTabId;
};

export type DashboardModuleCard = {
  id: string;
  label: string;
  summary: string;
  targetTab: DashboardTabId;
  tone: DashboardTone;
  primaryMetric: string;
  secondaryMetric: string;
  highlights: string[];
};

export type DashboardActivityItem = {
  id: string;
  title: string;
  summary: string;
  timestamp: string;
  tone: DashboardTone;
  targetTab: DashboardTabId;
};

export type DashboardOverviewModel = {
  loading: boolean;
  refreshedAt: string | null;
  error: string | null;
  title: string;
  subtitle: string;
  strip: DashboardStripItem[];
  workflowStages: DashboardWorkflowStage[];
  continueWork: DashboardWorkItem[];
  pendingItems: DashboardWorkItem[];
  quickActions: DashboardActionItem[];
  moduleCards: DashboardModuleCard[];
  recentActivity: DashboardActivityItem[];
  attentionItems: DashboardWorkItem[];
};

type Module2HealthPayload = {
  ok?: boolean;
  status?: string;
  provider_ready?: boolean;
  provider_status?: string;
  assistant1_enabled?: boolean;
  runtime_mode?: string;
  [key: string]: unknown;
};

type RemoteState = {
  bootstrap: PlatformAssistantBootstrapResponse | null;
  module1: Module1HealthResponse | null;
  module2Health: Module2HealthPayload | null;
  module3: Module3OverviewResponse | null;
  module4Health: Module4HealthzResponse | null;
  module4Files: Module4GraphFileListResponse | null;
  module4Alerts: Module4AlertListResponse | null;
  loading: boolean;
  error: string | null;
  refreshedAt: string | null;
};

const EMPTY_REMOTE_STATE: RemoteState = {
  bootstrap: null,
  module1: null,
  module2Health: null,
  module3: null,
  module4Health: null,
  module4Files: null,
  module4Alerts: null,
  loading: true,
  error: null,
  refreshedAt: null,
};

const formatDateTime = (value: string | null | undefined): string => {
  const raw = String(value || '').trim();
  if (!raw) return '刚刚';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const averageConfidence = (documents: ExtractionDocument[]): number => {
  const values = documents.flatMap((document) =>
    Object.values(document.result || {}).map((entity) => Number(entity.confidence || 0)),
  );
  if (values.length === 0) return 0;
  return Math.round((values.reduce((sum, item) => sum + item, 0) / values.length) * 100);
};

const countTraceableEntities = (documents: ExtractionDocument[]): number =>
  documents.reduce((sum, document) => (
    sum
    + Object.values(document.result || {}).filter((entity) => Boolean(entity.source_ref_id)).length
  ), 0);

const safeJsonFromApiResult = async <T>(
  loader: () => Promise<{ response: Response }>,
): Promise<T | null> => {
  try {
    const { response } = await loader();
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
};

const sortActivities = <T extends { timestamp: string }>(items: T[]): T[] =>
  [...items].sort((left, right) => {
    const leftTime = new Date(left.timestamp).getTime();
    const rightTime = new Date(right.timestamp).getTime();
    return rightTime - leftTime;
  });

const moduleStatusTone = (status: string): DashboardTone => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'ok' || normalized === 'done' || normalized === 'success') return 'good';
  if (normalized === 'running' || normalized === 'queued' || normalized === 'cancel_requested') return 'info';
  if (normalized === 'failed' || normalized === 'cancelled' || normalized === 'error') return 'danger';
  return 'neutral';
};

export const useDashboardOverview = (user: AuthUser): DashboardOverviewModel => {
  const [documents, setDocuments] = useState<ExtractionDocument[]>([]);
  const [documentsUpdatedAt, setDocumentsUpdatedAt] = useState<string | null>(null);
  const [remoteState, setRemoteState] = useState<RemoteState>(EMPTY_REMOTE_STATE);

  useEffect(() => {
    const loadLocal = () => {
      setDocuments(readExtractionDocuments());
      setDocumentsUpdatedAt(readExtractionUpdatedAt());
    };
    loadLocal();
    return subscribeExtractionUpdates(loadLocal);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadRemote = async () => {
      setRemoteState((current) => ({ ...current, loading: true, error: null }));

      const [
        bootstrapResult,
        module1Result,
        module2HealthResult,
        module3Result,
        module4HealthResult,
        module4FilesResult,
        module4AlertsResult,
      ] = await Promise.allSettled([
        safeJsonFromApiResult<PlatformAssistantBootstrapResponse>(() =>
          requestPlatformAssistantBootstrap('dashboard'),
        ),
        fetchModule1Health().catch(() => null),
        safeJsonFromApiResult<Module2HealthPayload>(() => requestExtractionHealth()),
        user ? fetchModule3Overview(6).catch(() => null) : Promise.resolve(null),
        user ? fetchModule4Healthz({ probe: 'basic' }).catch(() => null) : Promise.resolve(null),
        user ? fetchModule4GraphFiles({ limit: 6 }).catch(() => null) : Promise.resolve(null),
        user ? fetchModule4Alerts({ status: 'open', pageSize: 6 }).catch(() => null) : Promise.resolve(null),
      ]);

      if (cancelled) return;

      const bootstrap = bootstrapResult.status === 'fulfilled' ? bootstrapResult.value : null;
      const module1 = module1Result.status === 'fulfilled' ? module1Result.value : null;
      const module2Health = module2HealthResult.status === 'fulfilled' ? module2HealthResult.value : null;
      const module3 = module3Result.status === 'fulfilled' ? module3Result.value : null;
      const module4Health = module4HealthResult.status === 'fulfilled' ? module4HealthResult.value : null;
      const module4Files = module4FilesResult.status === 'fulfilled' ? module4FilesResult.value : null;
      const module4Alerts = module4AlertsResult.status === 'fulfilled' ? module4AlertsResult.value : null;

      const hasAnyData = Boolean(
        bootstrap || module1 || module2Health || module3 || module4Health || module4Files || module4Alerts,
      );

      setRemoteState({
        bootstrap,
        module1,
        module2Health,
        module3,
        module4Health,
        module4Files,
        module4Alerts,
        loading: false,
        error: hasAnyData ? null : '首页总览数据暂时不可用，已使用本地运行态继续展示。',
        refreshedAt: new Date().toISOString(),
      });
    };

    void loadRemote();
    return () => {
      cancelled = true;
    };
  }, [user]);

  return useMemo<DashboardOverviewModel>(() => {
    const bootstrapStarter = remoteState.bootstrap?.page?.starter;
    const module2DocCount = documents.length;
    const module2ErrorCount = documents.filter((document) => document.errors.length > 0).length;
    const module2AvgConfidence = averageConfidence(documents);
    const module2Traceable = countTraceableEntities(documents);

    const module3Summary = remoteState.module3?.summary;
    const module4Files = remoteState.module4Files?.items ?? [];
    const module4Alerts = remoteState.module4Alerts?.items ?? [];
    const module4OpenAlerts = module4Alerts.length;
    const module4ReadyFiles = module4Files.filter((item) => String(item.status || '').trim().toLowerCase() === 'ready').length;
    const module4RunningFiles = module4Files.filter((item) => {
      const status = String(item.status || '').trim().toLowerCase();
      return status === 'running' || status === 'queued';
    }).length;

    const module1Good = Boolean(remoteState.module1?.ai_available) && Boolean(remoteState.module1?.libreoffice_available);
    const module2Good = Boolean(remoteState.module2Health || documents.length > 0);
    const module3Good = Boolean(remoteState.module3);
    const module4Good = String(remoteState.module4Health?.status || '').trim().toLowerCase() === 'ok';
    const onlineModuleCount = [module1Good, module2Good, module3Good, module4Good].filter(Boolean).length;

    const title = user?.name
      ? `${user.name}，今天先从最关键的工作开始`
      : (bootstrapStarter?.title || '整个平台的今日工作总览');
    const subtitle = bootstrapStarter?.summary
      || '先确认平台态势，再继续最近任务、处理待办事项，并从正确模块进入下一步。';

    const strip: DashboardStripItem[] = [
      {
        id: 'platform',
        label: '平台状态',
        value: `${onlineModuleCount}/4 模块在线`,
        detail: '模块一到模块四的首页级摘要状态',
        tone: onlineModuleCount >= 3 ? 'good' : 'warn',
      },
      {
        id: 'tasks',
        label: '运行任务',
        value: `${Number(module3Summary?.runningCount || 0) + Number(remoteState.module4Health?.jobs_in_queue || 0)} 项`,
        detail: '模块三运行中任务 + 模块四队列任务',
        tone: Number(module3Summary?.runningCount || 0) > 0 ? 'info' : 'neutral',
      },
      {
        id: 'risk',
        label: '待处理风险',
        value: `${module2ErrorCount + module4OpenAlerts} 项`,
        detail: '抽取异常与知识图谱开放告警',
        tone: module2ErrorCount + module4OpenAlerts > 0 ? 'warn' : 'good',
      },
      {
        id: 'evidence',
        label: '可追溯证据',
        value: `${module2Traceable} 条`,
        detail: '最近抽取结果中的可回溯实体证据',
        tone: module2Traceable > 0 ? 'good' : 'neutral',
      },
      {
        id: 'updated',
        label: '最近刷新',
        value: formatDateTime(remoteState.refreshedAt || documentsUpdatedAt),
        detail: '首页摘要与本地运行态的最近更新时间',
        tone: 'neutral',
      },
    ];

    const workflowStages: DashboardWorkflowStage[] = [
      {
        id: 'ingest',
        label: '文档接入',
        summary: '从文档处理工作台发起新一轮理解、预览与入口确认。',
        metric: remoteState.module1?.ai_available ? 'AI 问答可用' : '等待 AI 能力',
        subMetric: remoteState.module1?.libreoffice_available ? 'Office 预览已就绪' : 'Office 预览待检查',
        tone: module1Good ? 'good' : 'warn',
        targetTab: 'doc-processing',
      },
      {
        id: 'extract',
        label: '解析与提取',
        summary: '承接最近抽取结果，重点关注字段覆盖、异常与原文证据。',
        metric: module2DocCount > 0 ? `${module2DocCount} 份最近抽取文档` : '等待新的抽取结果',
        subMetric: module2DocCount > 0 ? `${module2ErrorCount} 份需复核，平均置信度 ${module2AvgConfidence}%` : '可从 AI 信息提取开始',
        tone: module2ErrorCount > 0 ? 'warn' : (module2DocCount > 0 ? 'good' : 'neutral'),
        targetTab: 'deepread_extraction',
      },
      {
        id: 'fusion',
        label: '智能填表',
        summary: '把模板、资料集与运行结果汇总到 owner 级任务视图中。',
        metric: module3Summary ? `${module3Summary.runningCount} 运行中 / ${module3Summary.doneCount} 已完成` : '等待登录后查看任务',
        subMetric: module3Summary ? `${module3Summary.outputReadyCount} 份可下载输出` : '登录后可继续最近填表任务',
        tone: Number(module3Summary?.failedCount || 0) > 0 ? 'warn' : (module3Summary ? 'good' : 'neutral'),
        targetTab: 'fusion',
      },
      {
        id: 'graph',
        label: '图谱入库',
        summary: '从图谱文件与运行健康中判断知识图谱链路是否可继续下钻。',
        metric: `${module4ReadyFiles} 个 ready 图谱文件`,
        subMetric: module4RunningFiles > 0 ? `${module4RunningFiles} 个文件仍在处理中` : '图谱侧无积压任务',
        tone: module4RunningFiles > 0 ? 'info' : (module4ReadyFiles > 0 ? 'good' : 'neutral'),
        targetTab: 'nexus',
      },
      {
        id: 'risk',
        label: '风险分析',
        summary: '优先处理开放告警，把首页作为风险发现到处置的分发入口。',
        metric: `${module4OpenAlerts} 条开放告警`,
        subMetric: module4Alerts[0]?.summary || '暂无新的图谱告警',
        tone: module4OpenAlerts > 0 ? 'danger' : 'good',
        targetTab: 'nexus',
      },
    ];

    const continueWork: DashboardWorkItem[] = [];
    const recentDocument = documents[0];
    if (recentDocument) {
      continueWork.push({
        id: 'continue-extraction',
        title: `继续查看《${recentDocument.file_name}》的提取结果`,
        summary: `当前轨道 ${recentDocument.track}，已提取 ${Object.keys(recentDocument.result || {}).length} 个字段。`,
        meta: documentsUpdatedAt ? `最近更新 ${formatDateTime(documentsUpdatedAt)}` : '来自最近一次本地抽取结果',
        tone: recentDocument.errors.length > 0 ? 'warn' : 'good',
        targetTab: 'deepread_extraction',
      });
    }
    if (remoteState.module3?.activeRun) {
      continueWork.push({
        id: 'continue-fusion',
        title: '继续最近一次智能填表任务',
        summary: `运行状态 ${remoteState.module3.activeRun.status}，进度 ${remoteState.module3.activeRun.filled}/${remoteState.module3.activeRun.total}。`,
        meta: remoteState.module3.activeRun.updatedAt ? `最近更新 ${formatDateTime(remoteState.module3.activeRun.updatedAt)}` : '可进入模块三继续处理',
        tone: moduleStatusTone(remoteState.module3.activeRun.status),
        targetTab: 'fusion',
      });
    }
    if (module4OpenAlerts > 0) {
      continueWork.push({
        id: 'continue-graph-risk',
        title: '优先处理图谱告警与风险解释',
        summary: module4Alerts[0]?.title || '知识图谱侧存在待处理风险告警。',
        meta: `${module4OpenAlerts} 条告警待处理`,
        tone: 'danger',
        targetTab: 'nexus',
      });
    }
    if (continueWork.length === 0) {
      continueWork.push({
        id: 'continue-default',
        title: bootstrapStarter?.title || '从文档处理开始一轮完整工作流',
        summary: bootstrapStarter?.summary || '先进入 AI 文档处理，再根据结果转向提取、填表或图谱。',
        meta: '首页默认推荐路径',
        tone: 'info',
        targetTab: 'doc-processing',
      });
    }

    const pendingItems: DashboardWorkItem[] = [];
    if (module2ErrorCount > 0) {
      pendingItems.push({
        id: 'pending-extraction-errors',
        title: '复核最近抽取中的异常文档',
        summary: `最近结果里有 ${module2ErrorCount} 份文档带有错误或不完整信号。`,
        meta: module2DocCount > 0 ? `平均置信度 ${module2AvgConfidence}%` : '建议优先检查字段与原文定位',
        tone: 'warn',
        targetTab: 'deepread_extraction',
      });
    }
    if (Number(module3Summary?.failedCount || 0) > 0) {
      pendingItems.push({
        id: 'pending-fusion-failed',
        title: '处理模块三失败或中断的运行',
        summary: `最近存在 ${module3Summary?.failedCount || 0} 次失败运行。`,
        meta: '建议优先打开融合工作台检查模板、资料集与输出。',
        tone: 'warn',
        targetTab: 'fusion',
      });
    }
    if (module4OpenAlerts > 0) {
      pendingItems.push({
        id: 'pending-graph-alerts',
        title: '处理知识图谱开放告警',
        summary: `${module4OpenAlerts} 条告警仍处于 open 状态。`,
        meta: module4Alerts[0]?.title || '可以从知识图谱页面进一步解释与处置',
        tone: 'danger',
        targetTab: 'nexus',
      });
    }

    const quickActions: DashboardActionItem[] = [
      {
        id: 'action-doc',
        label: bootstrapStarter?.primaryAction.label || '打开 AI 文档处理',
        summary: '从文档问答、预览和交互理解开始。',
        targetTab: 'doc-processing',
        variant: 'primary',
      },
      {
        id: 'action-extract',
        label: '进入 AI 信息提取',
        summary: '查看字段结果、原文定位与结构化摘要。',
        targetTab: 'deepread_extraction',
        variant: 'secondary',
      },
      {
        id: 'action-fusion',
        label: '进入自定义智能填表',
        summary: '继续模板填充、输出下载与结果校验。',
        targetTab: 'fusion',
        variant: 'secondary',
      },
      {
        id: 'action-graph',
        label: '打开全域知识图谱',
        summary: '查看图谱结构、告警与解释分析。',
        targetTab: 'nexus',
        variant: 'ghost',
      },
    ];

    const moduleCards: DashboardModuleCard[] = [
      {
        id: 'module1',
        label: 'AI 文档处理',
        summary: '负责文档接入、预览、交互问答和上游工作流入口。',
        targetTab: 'doc-processing',
        tone: module1Good ? 'good' : 'warn',
        primaryMetric: remoteState.module1?.ai_available ? 'AI 问答已就绪' : 'AI 问答待检查',
        secondaryMetric: remoteState.module1?.libreoffice_available ? 'Office 预览已就绪' : 'Office 预览待检查',
        highlights: [
          remoteState.module1?.modules?.python_docx ? 'DOCX 处理能力可用' : 'DOCX 处理待确认',
          remoteState.module1?.modules?.office_pdf ? '预览转换链路可用' : '预览转换链路待确认',
        ],
      },
      {
        id: 'module2',
        label: 'AI 信息提取',
        summary: '承接最近抽取文档、字段覆盖、置信度与原文证据定位。',
        targetTab: 'deepread_extraction',
        tone: module2ErrorCount > 0 ? 'warn' : (module2DocCount > 0 ? 'good' : 'neutral'),
        primaryMetric: module2DocCount > 0 ? `${module2DocCount} 份最近抽取文档` : '等待新的抽取任务',
        secondaryMetric: module2DocCount > 0 ? `平均置信度 ${module2AvgConfidence}%` : '可从模块二开始新的结构化任务',
        highlights: [
          module2ErrorCount > 0 ? `${module2ErrorCount} 份文档需复核` : '最近抽取结果无明显异常',
          module2Traceable > 0 ? `${module2Traceable} 条实体带原文证据` : '等待新的原文证据链',
        ],
      },
      {
        id: 'module3',
        label: '自定义智能填表',
        summary: '按 owner 维度串联模板、资料集、运行状态和最近输出。',
        targetTab: 'fusion',
        tone: Number(module3Summary?.failedCount || 0) > 0 ? 'warn' : (module3Summary ? 'good' : 'neutral'),
        primaryMetric: module3Summary ? `${module3Summary.runCount} 次累计运行` : '登录后查看个人填表任务',
        secondaryMetric: module3Summary ? `${module3Summary.outputReadyCount} 份输出已生成` : '模板与资料集摘要待加载',
        highlights: [
          module3Summary ? `${module3Summary.templateCount} 套模板 / ${module3Summary.docsetCount} 组资料集` : '等待 owner 范围内概览数据',
          module3Summary ? `${module3Summary.runningCount} 运行中，${module3Summary.failedCount} 失败` : '可继续最近一次运行',
        ],
      },
      {
        id: 'module4',
        label: '全域知识图谱',
        summary: '从图谱文件、健康状态、开放告警和解释分析看整体下游态势。',
        targetTab: 'nexus',
        tone: module4OpenAlerts > 0 ? 'danger' : (module4Good ? 'good' : 'neutral'),
        primaryMetric: `${module4ReadyFiles} 个 ready 图谱文件`,
        secondaryMetric: module4Good ? `图谱运行正常，队列 ${remoteState.module4Health?.jobs_in_queue ?? 0}` : '图谱运行状态待确认',
        highlights: [
          module4RunningFiles > 0 ? `${module4RunningFiles} 个文件正在处理中` : '当前无图谱积压任务',
          module4OpenAlerts > 0 ? `${module4OpenAlerts} 条开放告警待处置` : '当前无开放告警',
        ],
      },
    ];

    const recentActivity: DashboardActivityItem[] = sortActivities([
      ...documents.slice(0, 3).map((document, index) => ({
        id: `m2-${document.file_hash}-${index}`,
        title: document.file_name,
        summary: `${document.track} 轨道，提取 ${Object.keys(document.result || {}).length} 个字段${document.errors.length ? `，异常 ${document.errors.length} 项` : ''}`,
        timestamp: documentsUpdatedAt || new Date().toISOString(),
        tone: (document.errors.length > 0 ? 'warn' : 'good') as DashboardTone,
        targetTab: 'deepread_extraction' as DashboardTabId,
      })),
      ...(remoteState.module3?.recentOutputs || []).slice(0, 2).map((output) => ({
        id: `m3-output-${output.outputFileId}`,
        title: output.outputName,
        summary: '最近生成的智能填表输出，可继续下载或预览。',
        timestamp: output.updatedAt || remoteState.module3?.generatedAt || new Date().toISOString(),
        tone: 'good' as DashboardTone,
        targetTab: 'fusion' as DashboardTabId,
      })),
      ...module4Files.slice(0, 2).map((item) => ({
        id: `m4-file-${item.graph_file_id}`,
        title: item.file_name,
        summary: `图谱文件状态 ${item.status}，节点 ${item.node_count} / 边 ${item.edge_count}`,
        timestamp: item.updated_at || item.created_at || new Date().toISOString(),
        tone: moduleStatusTone(item.status),
        targetTab: 'nexus' as DashboardTabId,
      })),
    ]).slice(0, 6);

    const attentionItems: DashboardWorkItem[] = [
      ...pendingItems,
      ...module4Alerts.slice(0, 2).map((item) => ({
        id: `alert-${item.alert_id}`,
        title: item.title,
        summary: item.summary,
        meta: `风险分 ${Math.round(Number(item.risk_score || 0))}`,
        tone: (item.severity === 'red' ? 'danger' : 'warn') as DashboardTone,
        targetTab: 'nexus' as DashboardTabId,
      })),
    ].slice(0, 5);

    return {
      loading: remoteState.loading,
      refreshedAt: remoteState.refreshedAt || documentsUpdatedAt,
      error: remoteState.error,
      title,
      subtitle,
      strip,
      workflowStages,
      continueWork,
      pendingItems,
      quickActions,
      moduleCards,
      recentActivity,
      attentionItems,
    };
  }, [documents, documentsUpdatedAt, remoteState, user]);
};
