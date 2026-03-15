import React, { useEffect, useMemo, useState } from "react";
import { EntityLink, EntityNode } from "../types";
import { AnimatePresence, motion } from "framer-motion";
import { ExternalLink, Network, ShieldAlert, X } from "lucide-react";
import {
  readExtractionDocuments,
  subscribeExtractionUpdates,
  type ExtractionDocument,
} from "../lib/extractionStore";
import { ackModule4Alert, fetchModule4Alerts, fetchModule4Graph, type Module4AlertItem } from "../lib/module4Api";

type GraphMeta = {
  sourceDoc?: string;
  fieldName?: string;
  value?: string;
  confidence?: number;
  errorText?: string;
  backendNodeType?: string;
};

type GraphNode = EntityNode & {
  meta: GraphMeta;
};

type GraphData = {
  nodes: GraphNode[];
  links: EntityLink[];
  source: "module4" | "local";
};

const MAX_DOCS = 8;
const MAX_FIELDS_PER_DOC = 12;
const MAX_ERRORS_PER_DOC = 3;

const shortText = (value: string, maxLen: number): string =>
  value.length > maxLen ? `${value.slice(0, Math.max(1, maxLen - 3))}...` : value;

const toErrorText = (value: unknown): string => {
  if (value instanceof Error) return value.message || "未知错误";
  return String(value || "未知错误");
};

const formatModule4Error = (errors: string[]): string => {
  if (errors.length === 0) return "";
  const text = errors.join(" | ");
  const lower = text.toLowerCase();
  const serviceDown =
    lower.includes("http 500") ||
    lower.includes("failed to fetch") ||
    lower.includes("econnrefused") ||
    lower.includes("networkerror") ||
    lower.includes("network error");
  if (serviceDown) {
    return "模块四服务不可用，请先启动后端服务后再重试。";
  }
  return text;
};

const typeLabel = (value: EntityNode["type"]): string => {
  if (value === "Contract") return "文档";
  if (value === "Risk") return "风险";
  return "节点";
};

const backendTypeLabel = (value?: string): string => {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "document") return "文档";
  if (normalized === "field") return "字段";
  if (normalized === "table") return "表格";
  if (normalized === "figure") return "图像";
  if (normalized === "risk") return "风险";
  return "其他类型";
};

const severityLabel = (value?: string): string => {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical") return "紧急";
  if (normalized === "high") return "高";
  if (normalized === "medium") return "中";
  if (normalized === "low") return "低";
  return "未分级";
};

const alertStatusLabel = (value?: string): string => {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "open") return "待处理";
  if (normalized === "ack") return "已确认";
  if (normalized === "closed") return "已关闭";
  return "状态未知";
};

const buildGraphFromLocal = (documents: ExtractionDocument[]): GraphData => {
  const nodes: GraphNode[] = [];
  const links: EntityLink[] = [];
  const docs = documents.slice(0, MAX_DOCS);
  let fieldCounter = 0;
  let riskCounter = 0;

  docs.forEach((doc, docIndex) => {
    const docNodeId = `doc-${doc.file_hash || docIndex}`;
    const docY = 120 + docIndex * 115;
    nodes.push({
      id: docNodeId,
      label: shortText(doc.file_name || `文档_${docIndex + 1}`, 20),
      type: "Contract",
      x: 170,
      y: docY,
      meta: { sourceDoc: doc.file_name, backendNodeType: "文档" },
    });

    const fields = Object.entries(doc.result || {}).slice(0, MAX_FIELDS_PER_DOC);
    fields.forEach(([fieldName, entityRaw]) => {
      const entity = entityRaw && typeof entityRaw === "object" ? (entityRaw as Record<string, unknown>) : {};
      const nodeId = `field-${docNodeId}-${fieldName}`;
      const y = 80 + (fieldCounter % 14) * 55;
      const laneOffset = Math.floor(fieldCounter / 14) * 180;
      const confidence = Number(entity["confidence"] || 0);
      const value = entity["value"];
      const isRisky = value == null || confidence < 0.55;
      nodes.push({
        id: nodeId,
        label: shortText(fieldName, 18),
        type: isRisky ? "Risk" : "Rating",
        x: 500 + laneOffset,
        y,
        meta: {
          sourceDoc: doc.file_name,
          fieldName,
          value: value == null ? "空值" : String(value),
          confidence,
          backendNodeType: "字段",
        },
      });
      links.push({ source: docNodeId, target: nodeId, label: isRisky ? "风险" : "抽取" });
      fieldCounter += 1;
    });

    const errors = Array.isArray(doc.errors) ? doc.errors : [];
    errors.slice(0, MAX_ERRORS_PER_DOC).forEach((err) => {
      const nodeId = `risk-${docNodeId}-${riskCounter}`;
      nodes.push({
        id: nodeId,
        label: `风险_${riskCounter + 1}`,
        type: "Risk",
        x: 920,
        y: 140 + (riskCounter % 10) * 78,
        meta: { sourceDoc: doc.file_name, errorText: err, backendNodeType: "风险" },
      });
      links.push({ source: docNodeId, target: nodeId, label: "异常" });
      riskCounter += 1;
    });
  });

  return { nodes, links, source: "local" };
};

const buildGraphFromModule4 = (payload: {
  nodes: Array<{
    node_id: string;
    node_type: string;
    display_name: string;
    confidence: number;
    attrs: Record<string, unknown>;
  }>;
  edges: Array<{
    source_node_id: string;
    target_node_id: string;
    relation_type: string;
  }>;
}): GraphData => {
  const backendNodes = Array.isArray(payload.nodes) ? payload.nodes : [];
  const backendEdges = Array.isArray(payload.edges) ? payload.edges : [];
  const groups = new Map<string, typeof backendNodes>();
  backendNodes.forEach((node) => {
    const key = String(node.node_type || "Other");
    const list = groups.get(key) || [];
    list.push(node);
    groups.set(key, list);
  });

  const orderedTypes = ["Document", "Field", "Table", "Figure", "Risk"];
  const allTypes = Array.from(groups.keys()).sort((a, b) => a.localeCompare(b));
  const finalTypes = [...orderedTypes, ...allTypes.filter((t) => !orderedTypes.includes(t))];
  const typeToCol = new Map<string, number>();
  finalTypes.forEach((t, idx) => typeToCol.set(t, idx));

  const nodes: GraphNode[] = [];
  backendNodes.forEach((node) => {
    const nodeType = String(node.node_type || "Other");
    const col = typeToCol.get(nodeType) ?? 0;
    const list = groups.get(nodeType) || [];
    const row = list.findIndex((it) => it.node_id === node.node_id);
    const x = 180 + col * 240;
    const y = 100 + Math.max(0, row) * 85;
    const riskLike = nodeType.toLowerCase() === "risk";
    const uiType: EntityNode["type"] = riskLike ? "Risk" : nodeType === "Document" ? "Contract" : "Rating";
    const attrs = node.attrs || {};
    nodes.push({
      id: node.node_id,
      label: shortText(String(node.display_name || node.node_id), 22),
      type: uiType,
      x,
      y,
      meta: {
        sourceDoc: String(attrs["file_name"] || attrs["file_hash"] || ""),
        fieldName: String(attrs["field_name"] || ""),
        value: attrs["value"] == null ? undefined : String(attrs["value"]),
        confidence: Number.isFinite(node.confidence) ? Number(node.confidence) : undefined,
        errorText: String(attrs["warning"] || attrs["error"] || ""),
        backendNodeType: nodeType,
      },
    });
  });

  const links: EntityLink[] = backendEdges.map((edge) => ({
    source: edge.source_node_id,
    target: edge.target_node_id,
    label: String(edge.relation_type || "关联"),
  }));

  return { nodes, links, source: "module4" };
};

export const KnowledgeNexus: React.FC = () => {
  const [graph, setGraph] = useState<GraphData>({ nodes: [], links: [], source: "local" });
  const [alerts, setAlerts] = useState<Module4AlertItem[]>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [backendError, setBackendError] = useState("");

  const loadLocal = () => setGraph(buildGraphFromLocal(readExtractionDocuments()));

  const loadRemote = async () => {
    const errors: string[] = [];
    let graphLoadedFromModule4 = false;

    try {
      const graphRes = await fetchModule4Graph({ limitNodes: 800, limitEdges: 1500 });
      if (Array.isArray(graphRes.nodes) && graphRes.nodes.length > 0) {
        setGraph(buildGraphFromModule4(graphRes));
        graphLoadedFromModule4 = true;
      }
    } catch (error) {
      errors.push(`图谱请求失败：${toErrorText(error)}`);
    }

    try {
      const alertRes = await fetchModule4Alerts({ page: 1, pageSize: 20 });
      setAlerts(Array.isArray(alertRes.items) ? alertRes.items : []);
    } catch (error) {
      errors.push(`告警请求失败：${toErrorText(error)}`);
    }

    if (!graphLoadedFromModule4) {
      loadLocal();
    }
    setBackendError(formatModule4Error(errors));
  };

  useEffect(() => {
    loadRemote();
    const timer = window.setInterval(() => {
      void loadRemote();
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeExtractionUpdates(() => {
      if (graph.source === "local") loadLocal();
    });
    return unsubscribe;
  }, [graph.source]);

  const nodesById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const riskCount = useMemo(() => graph.nodes.filter((node) => node.type === "Risk").length, [graph.nodes]);
  const selectedLinkCount = useMemo(() => {
    if (!selectedNode) return 0;
    return graph.links.filter((link) => link.source === selectedNode.id || link.target === selectedNode.id).length;
  }, [graph.links, selectedNode]);

  const graphWidth = useMemo(() => {
    if (graph.nodes.length === 0) return 1200;
    return Math.max(1200, ...graph.nodes.map((node) => node.x + 220));
  }, [graph.nodes]);
  const graphHeight = useMemo(() => {
    if (graph.nodes.length === 0) return 760;
    return Math.max(760, ...graph.nodes.map((node) => node.y + 130));
  }, [graph.nodes]);

  const handleAckAlert = async (alertId: string) => {
    try {
      await ackModule4Alert(alertId, "user", "已在图谱页确认");
      setAlerts((prev) => prev.map((item) => (item.alert_id === alertId ? { ...item, status: "ack" } : item)));
    } catch {
      // keep silent, backend error is shown in panel top
    }
  };

  return (
    <div className="h-[calc(100vh-2rem)] rounded-xl overflow-hidden glass-card relative shadow-2xl border border-white/10 flex">
      <div className="absolute inset-0 bg-slate-50 dark:bg-[#020617] pointer-events-none" />

      <div className="absolute top-6 left-6 z-10 pointer-events-none">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-primary/10 border border-primary/20 rounded-lg backdrop-blur-md">
            <Network className="text-primary" size={24} />
          </div>
          <div>
            <h2 className="text-black dark:text-white font-bold font-['Microsoft_YaHei'] text-xl tracking-tight">全域知识图谱</h2>
            <p className="text-xs text-muted-foreground">{graph.source === "module4" ? "数据源：模块四" : "数据源：本地回退"}</p>
          </div>
        </div>
        {backendError && (
          <div className="max-w-md text-xs px-3 py-2 rounded-lg border border-amber-200 bg-amber-50 text-amber-700 pointer-events-auto">
            模块四告警：{backendError}
          </div>
        )}
      </div>

      <div className="absolute bottom-6 left-6 z-10 pointer-events-none">
        <div className="glass px-4 py-3 rounded-xl flex items-center gap-4">
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold uppercase">节点</span>
            <span className="text-lg font-mono font-bold text-foreground">{graph.nodes.length}</span>
          </div>
          <div className="w-px h-8 bg-white/10" />
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold uppercase">连线</span>
            <span className="text-lg font-mono font-bold text-foreground">{graph.links.length}</span>
          </div>
          <div className="w-px h-8 bg-white/10" />
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold uppercase">风险</span>
            <span className="text-lg font-mono font-bold text-red-500">{riskCount}</span>
          </div>
        </div>
      </div>

      <div className="absolute top-6 right-6 z-20 w-72 max-h-[45vh] overflow-auto rounded-xl border border-white/20 bg-white/75 dark:bg-slate-900/80 p-3 shadow-xl">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-bold uppercase text-muted-foreground">风险预警</h3>
          <span className="text-xs font-mono text-foreground">{alerts.length}</span>
        </div>
        <div className="space-y-2">
          {alerts.slice(0, 12).map((item) => (
            <button
              key={item.alert_id}
              className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-700 px-2 py-2 hover:border-blue-300 transition-colors"
              onClick={() => {
                const nodeId = String(item.subject_node_id || "");
                if (nodeId && nodesById.has(nodeId)) setSelectedNode(nodesById.get(nodeId) || null);
              }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-bold uppercase text-slate-500">{severityLabel(item.severity)}</span>
                <span className="text-[10px] text-slate-400">{Math.round(Number(item.risk_score || 0))}</span>
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-200 mt-1">{shortText(item.title, 40)}</p>
              <div className="mt-1 flex items-center justify-between">
                <span className="text-[10px] text-slate-400">{alertStatusLabel(item.status)}</span>
                {item.status === "open" && (
                  <span
                    role="button"
                    tabIndex={0}
                    className="text-[10px] text-blue-600 cursor-pointer"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleAckAlert(item.alert_id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        void handleAckAlert(item.alert_id);
                      }
                    }}
                  >
                    确认
                  </span>
                )}
              </div>
            </button>
          ))}
          {alerts.length === 0 && <p className="text-xs text-muted-foreground">暂无活跃预警。</p>}
        </div>
      </div>

      <div className="flex-1 relative z-0 overflow-auto custom-scrollbar">
        <svg width={graphWidth} height={graphHeight} className="min-w-full min-h-full">
          {graph.links.map((link, index) => {
            const start = nodesById.get(link.source);
            const end = nodesById.get(link.target);
            if (!start || !end) return null;
            const isRiskLink = start.type === "Risk" || end.type === "Risk";
            const pathData = `M${start.x},${start.y} C${start.x + 120},${start.y} ${end.x - 120},${end.y} ${end.x},${end.y}`;
            return (
              <path
                key={`${link.source}-${link.target}-${index}`}
                d={pathData}
                fill="none"
                stroke={isRiskLink ? "rgba(239,68,68,0.45)" : "rgba(148,163,184,0.22)"}
                strokeWidth={isRiskLink ? 2.5 : 1.4}
              />
            );
          })}

          {graph.nodes.map((node) => {
            const isRisk = node.type === "Risk";
            const isSelected = selectedNode?.id === node.id;
            return (
              <g key={node.id} onClick={() => setSelectedNode(node)} className="cursor-pointer">
                <rect
                  x={node.x - 68}
                  y={node.y - 26}
                  width="136"
                  height="52"
                  rx="12"
                  fill={isRisk ? "rgba(69, 10, 10, 0.82)" : "rgba(15, 23, 42, 0.82)"}
                  stroke={isRisk ? "#ef4444" : isSelected ? "#38bdf8" : "rgba(255,255,255,0.12)"}
                  strokeWidth={isRisk || isSelected ? 2 : 1}
                />
                <circle cx={node.x - 52} cy={node.y} r="4" fill={isRisk ? "#ef4444" : "#38bdf8"} />
                <text x={node.x + 4} y={node.y - 2} textAnchor="middle" fill="#fff" fontSize="11" className="font-bold pointer-events-none select-none">
                  {node.label}
                </text>
                <text x={node.x + 4} y={node.y + 12} textAnchor="middle" fill={isRisk ? "#fca5a5" : "#94a3b8"} fontSize="9" className="uppercase font-mono font-bold pointer-events-none select-none">
                  {typeLabel(node.type)}
                </text>
              </g>
            );
          })}
        </svg>

        {graph.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="px-5 py-3 rounded-xl border border-border/40 bg-background/70 text-sm text-muted-foreground font-bold">
              暂无图谱数据，请先执行文档抽取或接入模块四数据。
            </div>
          </div>
        )}
      </div>

      <AnimatePresence>
        {selectedNode && (
          <motion.div
            initial={{ x: "100%", opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="absolute top-0 right-0 h-full w-96 bg-slate-900/92 backdrop-blur-xl border-l border-white/10 shadow-2xl z-30"
          >
            <div className="p-6 border-b border-white/10 flex items-start justify-between">
              <div>
                <h3 className="text-xl font-bold text-white mb-1 flex items-center gap-2">
                  {selectedNode.label}
                  <ExternalLink size={14} className="text-muted-foreground" />
                </h3>
                <p className="text-xs text-muted-foreground font-mono">节点ID：{selectedNode.id}</p>
              </div>
              <button onClick={() => setSelectedNode(null)} className="text-muted-foreground hover:text-foreground p-1 hover:bg-white/10 rounded">
                <X size={18} />
              </button>
            </div>
            <div className="p-6 space-y-4 overflow-y-auto h-[calc(100%-100px)]">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-white/5 rounded-lg border border-white/5">
                  <div className="text-[10px] text-muted-foreground uppercase mb-1">节点类型</div>
                  <div className="text-xs font-mono text-white">{backendTypeLabel(selectedNode.meta.backendNodeType)}</div>
                </div>
                <div className="p-3 bg-white/5 rounded-lg border border-white/5">
                  <div className="text-[10px] text-muted-foreground uppercase mb-1">置信度</div>
                  <div className="text-xs font-mono text-white">
                    {selectedNode.meta.confidence == null ? "--" : `${Math.round(selectedNode.meta.confidence * 100)}%`}
                  </div>
                </div>
                <div className="p-3 bg-white/5 rounded-lg border border-white/5 col-span-2">
                  <div className="text-[10px] text-muted-foreground uppercase mb-1">关联连线</div>
                  <div className="text-xs font-mono text-white">{selectedLinkCount}</div>
                </div>
              </div>

              {selectedNode.meta.fieldName && (
                <div className="p-4 bg-white/5 border border-white/10 rounded-xl">
                  <h4 className="text-xs font-bold text-muted-foreground uppercase mb-2">字段详情</h4>
                  <p className="text-xs text-slate-300">
                    字段：<span className="text-white">{selectedNode.meta.fieldName}</span>
                  </p>
                  <p className="text-xs text-slate-300 mt-1">
                    值：<span className="text-white break-all">{selectedNode.meta.value || "--"}</span>
                  </p>
                </div>
              )}

              {selectedNode.meta.errorText && (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl">
                  <div className="flex items-center gap-2 mb-2 text-red-400 font-bold text-sm">
                    <ShieldAlert size={16} />
                    风险信号
                  </div>
                  <p className="text-xs text-red-300/90 leading-relaxed">{selectedNode.meta.errorText}</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
