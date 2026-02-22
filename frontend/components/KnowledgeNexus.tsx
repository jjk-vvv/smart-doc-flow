import React, { useEffect, useMemo, useState } from "react";
import { EntityLink, EntityNode } from "../types";
import { AnimatePresence, motion } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { ExternalLink, Network, Share2, ShieldAlert, X, Zap } from "lucide-react";
import { readExtractionDocuments, subscribeExtractionUpdates, type ExtractionDocument } from "../lib/extractionStore";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type GraphMeta = {
  sourceDoc?: string;
  fieldName?: string;
  value?: string;
  confidence?: number;
  errorText?: string;
};

type GraphNode = EntityNode & {
  meta: GraphMeta;
};

type GraphData = {
  nodes: GraphNode[];
  links: EntityLink[];
};

const MAX_DOCS = 8;
const MAX_FIELDS_PER_DOC = 12;
const MAX_ERRORS_PER_DOC = 3;

const shortText = (value: string, maxLen: number): string =>
  value.length > maxLen ? `${value.slice(0, Math.max(1, maxLen - 3))}...` : value;

const typeLabel = (value: EntityNode["type"]): string => {
  if (value === "Contract") return "Document";
  if (value === "Risk") return "Risk";
  return "Field";
};

const buildGraph = (documents: ExtractionDocument[]): GraphData => {
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
      label: shortText(doc.file_name || `document_${docIndex + 1}`, 20),
      type: "Contract",
      x: 170,
      y: docY,
      meta: {
        sourceDoc: doc.file_name,
      },
    });

    const fields = Object.entries(doc.result || {}).slice(0, MAX_FIELDS_PER_DOC);
    fields.forEach(([fieldName, entity]) => {
      const nodeId = `field-${docNodeId}-${fieldName}`;
      const y = 80 + (fieldCounter % 14) * 55;
      const laneOffset = Math.floor(fieldCounter / 14) * 180;
      const confidence = Number(entity.confidence || 0);
      const isRisky = entity.value == null || confidence < 0.55;
      nodes.push({
        id: nodeId,
        label: shortText(fieldName, 18),
        type: isRisky ? "Risk" : "Rating",
        x: 500 + laneOffset,
        y,
        meta: {
          sourceDoc: doc.file_name,
          fieldName,
          value: entity.value == null ? "null" : String(entity.value),
          confidence,
        },
      });
      links.push({
        source: docNodeId,
        target: nodeId,
        label: isRisky ? "risk" : "extract",
      });
      fieldCounter += 1;
    });

    doc.errors.slice(0, MAX_ERRORS_PER_DOC).forEach((err) => {
      const nodeId = `risk-${docNodeId}-${riskCounter}`;
      nodes.push({
        id: nodeId,
        label: `error_${riskCounter + 1}`,
        type: "Risk",
        x: 920,
        y: 140 + (riskCounter % 10) * 78,
        meta: {
          sourceDoc: doc.file_name,
          errorText: err,
        },
      });
      links.push({
        source: docNodeId,
        target: nodeId,
        label: "error",
      });
      riskCounter += 1;
    });
  });

  return { nodes, links };
};

export const KnowledgeNexus: React.FC = () => {
  const [documents, setDocuments] = useState<ExtractionDocument[]>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  useEffect(() => {
    const load = () => setDocuments(readExtractionDocuments());
    load();
    return subscribeExtractionUpdates(load);
  }, []);

  const { nodes, links } = useMemo(() => buildGraph(documents), [documents]);
  const nodesById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const riskCount = useMemo(() => nodes.filter((node) => node.type === "Risk").length, [nodes]);

  const graphWidth = useMemo(() => {
    if (nodes.length === 0) return 1200;
    return Math.max(1200, ...nodes.map((node) => node.x + 220));
  }, [nodes]);

  const graphHeight = useMemo(() => {
    if (nodes.length === 0) return 760;
    return Math.max(760, ...nodes.map((node) => node.y + 130));
  }, [nodes]);

  const selectedLinkCount = useMemo(() => {
    if (!selectedNode) return 0;
    return links.filter((link) => link.source === selectedNode.id || link.target === selectedNode.id).length;
  }, [links, selectedNode]);

  useEffect(() => {
    if (!selectedNode) return;
    const fresh = nodesById.get(selectedNode.id) ?? null;
    setSelectedNode(fresh);
  }, [nodesById, selectedNode]);

  useEffect(() => {
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedNode(null);
      }
    };
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  return (
    <div className="h-[calc(100vh-2rem)] rounded-xl overflow-hidden glass-card relative shadow-2xl border border-white/10 flex">
      <div className="absolute inset-0 bg-slate-50 dark:bg-[#020617] pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(#cbd5e1_1px,transparent_1px)] dark:bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:20px_20px] opacity-5" />
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-[120px] animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-red-500/10 rounded-full blur-[120px] animate-pulse delay-1000" />
      </div>

      <div className="absolute top-6 left-6 z-10 pointer-events-none">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-primary/10 border border-primary/20 rounded-lg backdrop-blur-md">
            <Network className="text-primary" size={24} />
          </div>
          <div>
            <h2 className="text-black dark:text-white font-bold font-['Microsoft_YaHei'] text-xl tracking-tight">Knowledge Nexus</h2>
          </div>
        </div>
      </div>

      <div className="absolute bottom-6 left-6 z-10 pointer-events-none">
        <div className="glass px-4 py-3 rounded-xl flex items-center gap-4">
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold font-['Microsoft_YaHei'] uppercase">Nodes</span>
            <span className="text-lg font-mono font-bold text-foreground">{nodes.length}</span>
          </div>
          <div className="w-px h-8 bg-white/10" />
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold font-['Microsoft_YaHei'] uppercase">Links</span>
            <span className="text-lg font-mono font-bold text-foreground">{links.length}</span>
          </div>
          <div className="w-px h-8 bg-white/10" />
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold font-['Microsoft_YaHei'] uppercase">Risks</span>
            <span className="text-lg font-mono font-bold text-red-500">{riskCount}</span>
          </div>
        </div>
      </div>

      <div className="absolute top-6 right-6 z-10 glass-panel p-4 rounded-xl flex flex-col gap-3 w-52 backdrop-blur-xl border border-white/20 dark:border-white/10 bg-white/60 dark:bg-slate-900/60 shadow-2xl">
        <h3 className="text-xs font-bold font-['Microsoft_YaHei'] text-muted-foreground uppercase tracking-wider mb-1">Legend</h3>
        <div className="flex items-center gap-2 text-xs text-muted-foreground font-bold font-['Microsoft_YaHei']">
          <span className="w-3 h-3 bg-primary/20 border border-primary rounded-sm shadow-[0_0_10px_rgba(56,189,248,0.3)]" />
          <span className="text-foreground font-bold font-['Microsoft_YaHei']">Document / Field</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground font-bold font-['Microsoft_YaHei']">
          <span className="w-3 h-3 bg-red-500/20 border border-red-500 rounded-sm shadow-[0_0_10px_rgba(239,68,68,0.4)] animate-pulse" />
          <span className="text-red-500 dark:text-red-400 font-bold font-['Microsoft_YaHei']">Risk</span>
        </div>
        <p className="text-[10px] text-muted-foreground font-['Microsoft_YaHei']">Use mouse wheel / scrollbars to navigate large graphs.</p>
      </div>

      <div className="flex-1 relative z-0 overflow-auto custom-scrollbar">
        <svg width={graphWidth} height={graphHeight} className="min-w-full min-h-full">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--muted-foreground))" />
            </marker>
            <marker id="arrow-risk" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#ef4444" />
            </marker>
          </defs>

          {links.map((link, index) => {
            const start = nodesById.get(link.source);
            const end = nodesById.get(link.target);
            if (!start || !end) return null;

            const isRiskLink = start.type === "Risk" || end.type === "Risk";
            const isSelectedLink = Boolean(selectedNode && (selectedNode.id === link.source || selectedNode.id === link.target));
            const pathData = `M${start.x},${start.y} C${start.x + 120},${start.y} ${end.x - 120},${end.y} ${end.x},${end.y}`;

            return (
              <g key={`${link.source}-${link.target}-${index}`} className="group">
                <path
                  d={pathData}
                  fill="none"
                  stroke={isRiskLink ? "rgba(239,68,68,0.45)" : "rgba(148,163,184,0.2)"}
                  strokeWidth={isSelectedLink ? 3 : isRiskLink ? 2.6 : 1.6}
                  markerEnd={isRiskLink ? "url(#arrow-risk)" : "url(#arrow)"}
                  className="transition-all duration-300 group-hover:stroke-primary group-hover:stroke-[2px]"
                />
                <text
                  x={(start.x + end.x) / 2}
                  y={(start.y + end.y) / 2 - 4}
                  fill={isRiskLink ? "#fca5a5" : "#94a3b8"}
                  fontSize="9"
                  textAnchor="middle"
                  fontFamily="Microsoft YaHei"
                  fontWeight="bold"
                  className="pointer-events-none select-none"
                >
                  {link.label}
                </text>
              </g>
            );
          })}

          {nodes.map((node) => {
            const isRisk = node.type === "Risk";
            const isSelected = selectedNode?.id === node.id;

            return (
              <g
                key={node.id}
                onClick={() => setSelectedNode(node)}
                className="cursor-pointer transition-all duration-300"
                style={{ transformBox: "fill-box", transformOrigin: "center" }}
              >
                {isSelected && (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r="44"
                    fill="none"
                    stroke={isRisk ? "#ef4444" : "#38bdf8"}
                    strokeWidth="1"
                    strokeDasharray="4,4"
                    className="animate-[spin_10s_linear_infinite]"
                  />
                )}
                <rect
                  x={node.x - 68}
                  y={node.y - 26}
                  width="136"
                  height="52"
                  rx="12"
                  fill={isRisk ? "rgba(69, 10, 10, 0.82)" : "rgba(15, 23, 42, 0.82)"}
                  stroke={isRisk ? "#ef4444" : isSelected ? "#38bdf8" : "rgba(255,255,255,0.12)"}
                  strokeWidth={isRisk || isSelected ? 2 : 1}
                  className={cn("transition-all duration-300 shadow-[0_0_20px_rgba(0,0,0,0.45)] backdrop-blur-sm", isSelected && "shadow-[0_0_30px_rgba(56,189,248,0.3)]")}
                />
                <circle cx={node.x - 52} cy={node.y} r="4" fill={isRisk ? "#ef4444" : "#38bdf8"} className={isRisk ? "animate-pulse" : ""} />
                <text x={node.x + 4} y={node.y - 2} textAnchor="middle" fill="#fff" fontSize="11" className="font-bold font-['Microsoft_YaHei'] tracking-wide pointer-events-none select-none">
                  {node.label}
                </text>
                <text x={node.x + 4} y={node.y + 12} textAnchor="middle" fill={isRisk ? "#fca5a5" : "#94a3b8"} fontSize="9" className="uppercase font-mono font-bold font-['Microsoft_YaHei'] tracking-wider pointer-events-none select-none">
                  {typeLabel(node.type)}
                </text>
              </g>
            );
          })}
        </svg>

        {nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="px-5 py-3 rounded-xl border border-border/40 bg-background/70 text-sm text-muted-foreground font-bold font-['Microsoft_YaHei']">
              No extraction graph yet. Run DeepRead first.
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
            className="absolute top-0 right-0 h-full w-96 bg-slate-900/90 backdrop-blur-xl border-l border-white/10 shadow-2xl z-20"
          >
            <div className="flex flex-col h-full">
              <div className="p-6 border-b border-white/10 relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent pointer-events-none" />
                <div className="flex justify-between items-start mb-4 relative z-10">
                  <span
                    className={cn(
                      "px-2 py-1 rounded-md text-[10px] font-bold font-['Microsoft_YaHei'] uppercase tracking-wider border",
                      selectedNode.type === "Risk" ? "bg-red-500/10 text-red-400 border-red-500/20" : "bg-primary/10 text-primary border-primary/20"
                    )}
                  >
                    {typeLabel(selectedNode.type)}
                  </span>
                  <button onClick={() => setSelectedNode(null)} className="text-muted-foreground hover:text-foreground p-1 hover:bg-white/10 rounded transition-colors">
                    <X size={18} />
                  </button>
                </div>
                <h3 className="text-xl font-bold font-['Microsoft_YaHei'] text-white mb-1 relative z-10 flex items-center gap-2">
                  {selectedNode.label}
                  <ExternalLink size={14} className="text-muted-foreground" />
                </h3>
                <p className="text-xs text-muted-foreground font-mono font-bold font-['Microsoft_YaHei'] relative z-10">ID: {selectedNode.id}</p>
              </div>

              <div className="flex-1 p-6 space-y-6 overflow-y-auto custom-scrollbar">
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 bg-white/5 rounded-lg border border-white/5">
                    <div className="text-[10px] text-muted-foreground font-bold font-['Microsoft_YaHei'] uppercase mb-1">Source</div>
                    <div className="text-xs font-mono font-bold font-['Microsoft_YaHei'] text-white">{selectedNode.meta.sourceDoc || "--"}</div>
                  </div>
                  <div className="p-3 bg-white/5 rounded-lg border border-white/5">
                    <div className="text-[10px] text-muted-foreground font-bold font-['Microsoft_YaHei'] uppercase mb-1">Confidence</div>
                    <div className="text-xs font-mono font-bold font-['Microsoft_YaHei'] text-white">
                      {selectedNode.meta.confidence == null ? "--" : `${Math.round(selectedNode.meta.confidence * 100)}%`}
                    </div>
                  </div>
                  <div className="p-3 bg-white/5 rounded-lg border border-white/5 col-span-2">
                    <div className="text-[10px] text-muted-foreground font-bold font-['Microsoft_YaHei'] uppercase mb-1">Connected links</div>
                    <div className="text-xs font-mono font-bold font-['Microsoft_YaHei'] text-white">{selectedLinkCount}</div>
                  </div>
                </div>

                {selectedNode.meta.fieldName && (
                  <div className="p-4 bg-white/5 border border-white/10 rounded-xl">
                    <h4 className="text-xs font-bold font-['Microsoft_YaHei'] text-muted-foreground uppercase mb-2 flex items-center gap-2">
                      <Share2 size={12} />
                      Field payload
                    </h4>
                    <div className="text-xs text-slate-300 space-y-2">
                      <p>
                        <span className="text-slate-500 font-bold font-['Microsoft_YaHei']">Field:</span> <span className="font-bold font-['Microsoft_YaHei']">{selectedNode.meta.fieldName}</span>
                      </p>
                      <p>
                        <span className="text-slate-500 font-bold font-['Microsoft_YaHei']">Value:</span> <span className="font-bold font-['Microsoft_YaHei'] break-all">{selectedNode.meta.value || "--"}</span>
                      </p>
                    </div>
                  </div>
                )}

                {selectedNode.meta.errorText && (
                  <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-r from-red-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="flex items-center gap-2 mb-2 text-red-400 font-bold font-['Microsoft_YaHei'] text-sm relative z-10">
                      <ShieldAlert size={16} className="animate-pulse" />
                      Risk signal
                    </div>
                    <p className="text-xs text-red-300/80 leading-relaxed relative z-10 font-bold font-['Microsoft_YaHei']">{selectedNode.meta.errorText}</p>
                  </div>
                )}

                <div className="p-4 bg-indigo-500/5 border border-dashed border-indigo-500/30 rounded-xl">
                  <div className="flex items-center gap-2 mb-2 text-indigo-400 font-bold font-['Microsoft_YaHei'] text-sm">
                    <Zap size={14} />
                    AI hint
                  </div>
                  <p className="text-xs text-indigo-300/70 leading-relaxed font-bold font-['Microsoft_YaHei']">
                    This node comes from the latest extraction payload. Run DeepRead again to refresh graph relationships.
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
