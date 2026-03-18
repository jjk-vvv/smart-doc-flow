import React, { useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowRight, CheckCircle2, Download, Search, Table, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  readExtractionDocuments,
  readExtractionUpdatedAt,
  subscribeExtractionUpdates,
  type ExtractionDocument,
  type ExtractionEntity,
} from "../lib/extractionStore";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type RowStatus = "VERIFIED" | "MISMATCH" | "PENDING";
type SortBy = "CONF_DESC" | "CONF_ASC" | "FIELD";

type GridRow = {
  id: string;
  item: string;
  valueText: string;
  numericValue: number | null;
  dateText: string;
  sourceDoc: string;
  confidence: number;
  status: RowStatus;
};

const currencySymbols = /[¥￥$€£]/g;
const thousandsSeparators = /[,，\s]/g;
const nonNumeric = /[^0-9.\-()]/g;

const toNumeric = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;

  const raw = value.trim();
  if (!raw) return null;

  const isNegativeWrapped = raw.startsWith("(") && raw.endsWith(")");
  const cleaned = raw.replace(currencySymbols, "").replace(thousandsSeparators, "").replace(nonNumeric, "");
  if (!cleaned) return null;

  const parsed = Number(cleaned.replace(/[()]/g, ""));
  if (!Number.isFinite(parsed)) return null;
  return isNegativeWrapped ? -Math.abs(parsed) : parsed;
};

const toDateText = (value: unknown): string => {
  const text = typeof value === "string" ? value : String(value ?? "");
  const trimmed = text.trim();
  if (!trimmed) return "--";
  const hit = trimmed.match(/\d{4}[-/]\d{1,2}[-/]\d{1,2}/);
  return hit ? hit[0] : "--";
};

const toRows = (documents: ExtractionDocument[]): GridRow[] => {
  const rows: GridRow[] = [];

  for (const doc of documents) {
    const fileBase = doc.file_name || "未知文档";
    for (const [fieldName, entity] of Object.entries(doc.result || {})) {
      const e = entity as ExtractionEntity;
      const value = e.value;
      const numericValue = toNumeric(value);
      const confidence = Number(e.confidence || 0);
      const status: RowStatus =
        value == null ? "PENDING" : confidence >= 0.8 && Boolean(e.source_ref_id) ? "VERIFIED" : "MISMATCH";

      rows.push({
        id: `${doc.file_hash || fileBase}-${fieldName}`,
        item: fieldName,
        valueText: value == null ? "空值" : String(value),
        numericValue,
        dateText: toDateText(value),
        sourceDoc: fileBase,
        confidence,
        status,
      });
    }
  }

  return rows;
};

const statusLabel = (status: RowStatus): string => {
  if (status === "VERIFIED") return "已校验";
  if (status === "MISMATCH") return "待复核";
  return "待补全";
};

const sortRows = (rows: GridRow[], sortBy: SortBy): GridRow[] => {
  const list = [...rows];
  if (sortBy === "FIELD") {
    list.sort((a, b) => a.item.localeCompare(b.item));
    return list;
  }
  if (sortBy === "CONF_ASC") {
    list.sort((a, b) => a.confidence - b.confidence);
    return list;
  }
  list.sort((a, b) => b.confidence - a.confidence);
  return list;
};

export const FusionGrid: React.FC = () => {
  const [selectedRows, setSelectedRows] = useState<string[]>([]);
  const [documents, setDocuments] = useState<ExtractionDocument[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [filter, setFilter] = useState<"ALL" | RowStatus>("ALL");
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortBy>("CONF_DESC");

  useEffect(() => {
    const load = () => {
      setDocuments(readExtractionDocuments());
      setUpdatedAt(readExtractionUpdatedAt());
    };
    load();
    return subscribeExtractionUpdates(load);
  }, []);

  const allRows = useMemo(() => toRows(documents), [documents]);

  const searchedRows = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return allRows;
    return allRows.filter((row) => {
      return row.item.toLowerCase().includes(keyword) || row.valueText.toLowerCase().includes(keyword) || row.sourceDoc.toLowerCase().includes(keyword);
    });
  }, [allRows, query]);

  const filteredRows = useMemo(
    () => (filter === "ALL" ? searchedRows : searchedRows.filter((row) => row.status === filter)),
    [filter, searchedRows]
  );

  const rows = useMemo(() => sortRows(filteredRows, sortBy), [filteredRows, sortBy]);
  const latestDocName = useMemo(() => (documents[0]?.file_name ? documents[0].file_name : "暂无文档"), [documents]);
  const updatedAtText = useMemo(() => (updatedAt ? new Date(updatedAt).toLocaleString() : "--"), [updatedAt]);
  const totalAmount = useMemo(() => rows.reduce((acc, row) => acc + (row.numericValue == null ? 0 : row.numericValue), 0), [rows]);
  const verifiedCount = useMemo(() => rows.filter((row) => row.status === "VERIFIED").length, [rows]);

  const visibleRowIds = useMemo(() => rows.map((row) => row.id), [rows]);
  const selectedCount = selectedRows.length;
  const allVisibleSelected = useMemo(
    () => visibleRowIds.length > 0 && visibleRowIds.every((id) => selectedRows.includes(id)),
    [selectedRows, visibleRowIds]
  );

  useEffect(() => {
    setSelectedRows((prev) => prev.filter((id) => rows.some((row) => row.id === id)));
  }, [rows]);

  const toggleRow = (id: string) => {
    setSelectedRows((prev) => (prev.includes(id) ? prev.filter((rowId) => rowId !== id) : [...prev, id]));
  };

  const toggleSelectAllVisible = () => {
    if (allVisibleSelected) {
      setSelectedRows((prev) => prev.filter((id) => !visibleRowIds.includes(id)));
      return;
    }
    setSelectedRows((prev) => Array.from(new Set([...prev, ...visibleRowIds])));
  };

  const downloadJson = () => {
    const selectedSet = new Set(selectedRows);
    const exportRows = selectedSet.size > 0 ? rows.filter((row) => selectedSet.has(row.id)) : rows;
    const payload = {
      documents,
      rows: exportRows,
      exportedAt: new Date().toISOString(),
      selectionMode: selectedSet.size > 0 ? "selected_rows" : "visible_rows",
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `fusion-grid-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-[calc(100vh-2rem)] flex flex-col rounded-xl overflow-hidden glass-card shadow-2xl relative border border-white/10">
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[100px] pointer-events-none z-0" />

      <div className="h-16 border-b border-white/10 dark:border-white/10 flex items-center px-4 justify-between bg-white/40 dark:bg-white/5 backdrop-blur-md relative z-10 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 bg-gradient-to-br from-emerald-500/20 to-teal-500/20 rounded-lg border border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
            <Table size={18} className="text-emerald-500 dark:text-emerald-400" />
          </div>
          <div className="min-w-0">
            <h2 className="font-bold font-sans text-sm tracking-wide text-foreground flex items-center gap-2 truncate">
              {latestDocName}
              <span className={cn("w-1.5 h-1.5 rounded-full", rows.length > 0 ? "bg-emerald-500" : "bg-slate-500")} />
            </h2>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] text-muted-foreground font-mono font-bold">最近更新：{updatedAtText}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索字段 / 值 / 来源文档"
              className="h-8 w-56 rounded-lg border border-white/20 bg-white/30 dark:bg-white/5 pl-7 pr-2 text-xs text-foreground outline-none focus:border-primary/50"
            />
          </div>

          <select
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value as SortBy)}
            className="h-8 rounded-lg border border-white/20 bg-white/30 dark:bg-white/5 px-2 text-xs text-foreground outline-none focus:border-primary/50"
          >
            <option value="CONF_DESC">置信度降序</option>
            <option value="CONF_ASC">置信度升序</option>
            <option value="FIELD">字段名排序</option>
          </select>

          <button
            className="p-2 text-muted-foreground hover:text-primary transition-colors hover:bg-white/20 dark:hover:bg-white/5 rounded-lg border border-transparent hover:border-white/20 dark:hover:border-white/10"
            onClick={downloadJson}
            title="导出结构化数据"
          >
            <Download size={18} />
          </button>
        </div>
      </div>

      <div className="h-11 border-b border-white/10 dark:border-white/10 px-4 flex items-center justify-between bg-white/20 dark:bg-white/5 relative z-10">
        <div className="flex items-center rounded-lg border border-white/20 dark:border-white/10 overflow-hidden">
          <button className={cn("px-2 py-1.5 text-[10px] font-bold font-sans", filter === "ALL" ? "bg-primary/20 text-primary" : "text-muted-foreground")} onClick={() => setFilter("ALL")}>
            全部
          </button>
          <button className={cn("px-2 py-1.5 text-[10px] font-bold font-sans", filter === "VERIFIED" ? "bg-emerald-500/20 text-emerald-500" : "text-muted-foreground")} onClick={() => setFilter("VERIFIED")}>
            已校验
          </button>
          <button className={cn("px-2 py-1.5 text-[10px] font-bold font-sans", filter === "MISMATCH" ? "bg-red-500/20 text-red-500" : "text-muted-foreground")} onClick={() => setFilter("MISMATCH")}>
            待复核
          </button>
          <button className={cn("px-2 py-1.5 text-[10px] font-bold font-sans", filter === "PENDING" ? "bg-slate-500/20 text-slate-300" : "text-muted-foreground")} onClick={() => setFilter("PENDING")}>
            待补全
          </button>
        </div>

        <div className="flex items-center gap-2">
          {selectedCount > 0 && (
            <button onClick={() => setSelectedRows([])} className="h-7 px-2 rounded-md text-[10px] text-muted-foreground border border-white/20 hover:bg-white/10 flex items-center gap-1">
              <X size={12} />
              清空选择
            </button>
          )}
          <span className="text-[10px] text-muted-foreground font-mono">行数：{rows.length}</span>
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-slate-50/50 dark:bg-slate-900/30 relative z-10 custom-scrollbar pb-24">
        <table className="w-full text-left border-collapse">
          <thead className="sticky top-0 z-20 bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl text-[10px] uppercase font-bold text-muted-foreground tracking-wider shadow-sm border-b border-border/10 dark:border-white/10 font-sans">
            <tr>
              <th className="p-4 w-16 text-center">
                <button
                  className={cn(
                    "w-4 h-4 border rounded mx-auto flex items-center justify-center",
                    allVisibleSelected ? "bg-primary border-primary text-black" : "border-muted-foreground/20"
                  )}
                  onClick={toggleSelectAllVisible}
                  title={allVisibleSelected ? "取消全选当前可见行" : "全选当前可见行"}
                >
                  {allVisibleSelected && <CheckCircle2 size={10} />}
                </button>
              </th>
              <th className="p-4 font-bold">字段</th>
              <th className="p-4 font-bold">值</th>
              <th className="p-4 font-bold">日期</th>
              <th className="p-4 font-bold">来源文档</th>
              <th className="p-4 font-bold">置信度</th>
              <th className="p-4 font-bold">状态</th>
              <th className="p-4 w-10" />
            </tr>
          </thead>

          <tbody className="text-sm font-mono">
            <AnimatePresence>
              {rows.map((row, index) => (
                <motion.tr
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(0.3, index * 0.01) }}
                  key={row.id}
                  onClick={() => toggleRow(row.id)}
                  className={cn("group border-b border-white/5 transition-colors cursor-pointer relative", selectedRows.includes(row.id) ? "bg-primary/5" : "hover:bg-white/5")}
                >
                  <td className="p-4 text-center relative">
                    {selectedRows.includes(row.id) && <motion.div layoutId="active-row-indicator" className="absolute left-0 top-0 bottom-0 w-1 bg-primary shadow-[0_0_10px_#38bdf8]" />}
                    <div
                      className={cn(
                        "w-4 h-4 border rounded mx-auto transition-colors flex items-center justify-center",
                        selectedRows.includes(row.id) ? "bg-primary border-primary text-black" : "border-white/20 group-hover:border-white/40"
                      )}
                    >
                      {selectedRows.includes(row.id) && <CheckCircle2 size={10} />}
                    </div>
                  </td>
                  <td className="p-4 font-medium font-sans font-bold text-foreground group-hover:text-primary transition-colors">{row.item}</td>
                  <td className="p-4 text-muted-foreground font-bold font-sans max-w-[300px] truncate">
                    {row.numericValue == null ? row.valueText : row.numericValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </td>
                  <td className="p-4 text-muted-foreground/70 font-bold font-sans">{row.dateText}</td>
                  <td className="p-4">
                    <span className="flex items-center gap-2 px-2 py-1 rounded-md bg-white/5 border border-white/10 text-[10px] font-bold font-sans text-muted-foreground group-hover:border-primary/30 transition-colors w-fit max-w-[260px]">
                      <span className="w-1 h-4 bg-indigo-500/50 rounded-full" />
                      <span className="truncate">{row.sourceDoc}</span>
                    </span>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden w-24">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${row.confidence * 100}%` }}
                          transition={{ duration: 0.5, delay: Math.min(0.25, index * 0.01) }}
                          className={cn("h-full rounded-full shadow-[0_0_10px_currentColor]", row.confidence > 0.9 ? "bg-emerald-500" : row.confidence > 0.8 ? "bg-amber-500" : "bg-red-500")}
                        />
                      </div>
                      <span className={cn("text-xs font-bold font-sans", row.confidence > 0.9 ? "text-emerald-500" : row.confidence > 0.8 ? "text-amber-500" : "text-red-500")}>
                        {Math.floor(row.confidence * 100)}%
                      </span>
                    </div>
                  </td>
                  <td className="p-4">
                    {row.status === "VERIFIED" ? (
                      <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-bold font-sans text-emerald-500 w-fit">
                        <CheckCircle2 size={12} /> {statusLabel(row.status)}
                      </div>
                    ) : row.status === "MISMATCH" ? (
                      <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-red-500/10 border border-red-500/20 text-[10px] font-bold font-sans text-red-500 w-fit">
                        <AlertCircle size={12} /> {statusLabel(row.status)}
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-slate-500/10 border border-slate-500/20 text-[10px] font-bold font-sans text-slate-400 w-fit">
                        {statusLabel(row.status)}
                      </div>
                    )}
                  </td>
                  <td className="p-4 text-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <button className="p-1 hover:bg-white/10 rounded text-muted-foreground hover:text-foreground">
                      <ArrowRight size={14} />
                    </button>
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>

            {rows.length === 0 && (
              <tr className="border-b border-white/5">
                <td colSpan={8} className="p-10 text-center text-sm text-muted-foreground">
                  暂无可展示的融合结果，请先完成文档抽取。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border border-white/20 dark:border-white/10 shadow-2xl rounded-full px-6 py-2.5 flex items-center gap-6 z-20 hover:scale-105 transition-transform duration-300">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[10px] text-muted-foreground font-bold font-sans">融合引擎在线</span>
        </div>
        <div className="w-px h-4 bg-white/20 dark:bg-white/10" />
        <div className="flex items-center gap-4 text-[10px] font-mono font-bold font-sans text-muted-foreground">
          <span>
            已选：<span className="text-foreground">{selectedCount}</span>
          </span>
          <span>
            已校验：<span className="text-foreground">{verifiedCount}</span>
          </span>
        </div>
        <div className="w-px h-4 bg-white/20 dark:bg-white/10" />
        <div className="flex gap-4 text-[10px] font-mono font-bold font-sans">
          <span className="text-muted-foreground">
            合计：<span className="text-foreground">{totalAmount.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
          </span>
          <span className="text-slate-400">行数：{rows.length}</span>
        </div>
      </div>
    </div>
  );
};
