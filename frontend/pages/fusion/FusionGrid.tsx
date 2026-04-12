import React, { useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowRight, CheckCircle2, Download, Search, Table, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "../../lib/utils";
import {
  readExtractionDocuments,
  readExtractionUpdatedAt,
  subscribeExtractionUpdates,
  type ExtractionDocument,
  type ExtractionEntity,
} from "../../shared/state/extractionDocuments";

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
  const cleaned = raw
    .replace(currencySymbols, "")
    .replace(thousandsSeparators, "")
    .replace(nonNumeric, "");
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
        value == null
          ? "PENDING"
          : confidence >= 0.8 && Boolean(e.source_ref_id)
            ? "VERIFIED"
            : "MISMATCH";

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
      return (
        row.item.toLowerCase().includes(keyword) ||
        row.valueText.toLowerCase().includes(keyword) ||
        row.sourceDoc.toLowerCase().includes(keyword)
      );
    });
  }, [allRows, query]);

  const filteredRows = useMemo(
    () => (filter === "ALL" ? searchedRows : searchedRows.filter((row) => row.status === filter)),
    [filter, searchedRows]
  );

  const rows = useMemo(() => sortRows(filteredRows, sortBy), [filteredRows, sortBy]);
  const latestDocName = useMemo(
    () => (documents[0]?.file_name ? documents[0].file_name : "暂无文档"),
    [documents]
  );
  const updatedAtText = useMemo(
    () => (updatedAt ? new Date(updatedAt).toLocaleString() : "--"),
    [updatedAt]
  );
  const totalAmount = useMemo(
    () => rows.reduce((acc, row) => acc + (row.numericValue == null ? 0 : row.numericValue), 0),
    [rows]
  );
  const verifiedCount = useMemo(
    () => rows.filter((row) => row.status === "VERIFIED").length,
    [rows]
  );

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
    setSelectedRows((prev) =>
      prev.includes(id) ? prev.filter((rowId) => rowId !== id) : [...prev, id]
    );
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

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `fusion-grid-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative flex h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-xl border border-white/10 shadow-2xl glass-card">
      <div className="pointer-events-none absolute right-0 top-0 z-0 h-[500px] w-[500px] rounded-full bg-primary/5 blur-[100px]" />

      <div className="relative z-10 flex h-16 items-center justify-between gap-3 border-b border-white/10 bg-white/40 px-4 backdrop-blur-md dark:border-white/10 dark:bg-white/5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="rounded-lg border border-emerald-500/30 bg-gradient-to-br from-emerald-500/20 to-teal-500/20 p-2 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
            <Table size={18} className="text-emerald-500 dark:text-emerald-400" />
          </div>
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 truncate font-sans text-sm font-bold tracking-wide text-foreground">
              {latestDocName}
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  rows.length > 0 ? "bg-emerald-500" : "bg-slate-500"
                )}
              />
            </h2>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="font-mono text-[10px] font-bold text-muted-foreground">
                最近更新：{updatedAtText}
              </span>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <div className="relative">
            <Search
              size={13}
              className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索字段 / 值 / 来源文档"
              className="h-8 w-56 rounded-lg border border-white/20 bg-white/30 pl-7 pr-2 text-xs text-foreground outline-none focus:border-primary/50 dark:bg-white/5"
            />
          </div>

          <select
            value={sortBy}
            title="选择排序方式"
            aria-label="选择排序方式"
            onChange={(event) => setSortBy(event.target.value as SortBy)}
            className="h-8 rounded-lg border border-white/20 bg-white/30 px-2 text-xs text-foreground outline-none focus:border-primary/50 dark:bg-white/5"
          >
            <option value="CONF_DESC">置信度降序</option>
            <option value="CONF_ASC">置信度升序</option>
            <option value="FIELD">字段名排序</option>
          </select>

          <button
            className="rounded-lg border border-transparent p-2 text-muted-foreground transition-colors hover:border-white/20 hover:bg-white/20 hover:text-primary dark:hover:border-white/10 dark:hover:bg-white/5"
            onClick={downloadJson}
            title="导出结构化数据"
          >
            <Download size={18} />
          </button>
        </div>
      </div>

      <div className="relative z-10 flex h-11 items-center justify-between border-b border-white/10 bg-white/20 px-4 dark:border-white/10 dark:bg-white/5">
        <div className="flex items-center overflow-hidden rounded-lg border border-white/20 dark:border-white/10">
          <button
            className={cn(
              "px-2 py-1.5 font-sans text-[10px] font-bold",
              filter === "ALL" ? "bg-primary/20 text-primary" : "text-muted-foreground"
            )}
            onClick={() => setFilter("ALL")}
          >
            全部
          </button>
          <button
            className={cn(
              "px-2 py-1.5 font-sans text-[10px] font-bold",
              filter === "VERIFIED"
                ? "bg-emerald-500/20 text-emerald-500"
                : "text-muted-foreground"
            )}
            onClick={() => setFilter("VERIFIED")}
          >
            已校验
          </button>
          <button
            className={cn(
              "px-2 py-1.5 font-sans text-[10px] font-bold",
              filter === "MISMATCH" ? "bg-red-500/20 text-red-500" : "text-muted-foreground"
            )}
            onClick={() => setFilter("MISMATCH")}
          >
            待复核
          </button>
          <button
            className={cn(
              "px-2 py-1.5 font-sans text-[10px] font-bold",
              filter === "PENDING" ? "bg-slate-500/20 text-slate-300" : "text-muted-foreground"
            )}
            onClick={() => setFilter("PENDING")}
          >
            待补全
          </button>
        </div>

        <div className="flex items-center gap-2">
          {selectedCount > 0 && (
            <button
              onClick={() => setSelectedRows([])}
              className="flex h-7 items-center gap-1 rounded-md border border-white/20 px-2 text-[10px] text-muted-foreground hover:bg-white/10"
            >
              <X size={12} />
              清空选择
            </button>
          )}
          <span className="font-mono text-[10px] text-muted-foreground">行数：{rows.length}</span>
        </div>
      </div>

      <div className="relative z-10 flex-1 overflow-auto bg-slate-50/50 pb-24 dark:bg-slate-900/30 custom-scrollbar">
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 z-20 border-b border-border/10 bg-white/90 font-sans text-[10px] font-bold uppercase tracking-wider text-muted-foreground shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/90">
            <tr>
              <th className="w-16 p-4 text-center">
                <button
                  className={cn(
                    "mx-auto flex h-4 w-4 items-center justify-center rounded border",
                    allVisibleSelected
                      ? "border-primary bg-primary text-black"
                      : "border-muted-foreground/20"
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
              <th className="w-10 p-4" />
            </tr>
          </thead>

          <tbody className="font-mono text-sm">
            <AnimatePresence>
              {rows.map((row, index) => (
                <motion.tr
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(0.3, index * 0.01) }}
                  key={row.id}
                  onClick={() => toggleRow(row.id)}
                  className={cn(
                    "group relative cursor-pointer border-b border-white/5 transition-colors",
                    selectedRows.includes(row.id) ? "bg-primary/5" : "hover:bg-white/5"
                  )}
                >
                  <td className="relative p-4 text-center">
                    {selectedRows.includes(row.id) && (
                      <motion.div
                        layoutId="active-row-indicator"
                        className="absolute bottom-0 left-0 top-0 w-1 bg-primary shadow-[0_0_10px_#38bdf8]"
                      />
                    )}
                    <div
                      className={cn(
                        "mx-auto flex h-4 w-4 items-center justify-center rounded border transition-colors",
                        selectedRows.includes(row.id)
                          ? "border-primary bg-primary text-black"
                          : "border-white/20 group-hover:border-white/40"
                      )}
                    >
                      {selectedRows.includes(row.id) && <CheckCircle2 size={10} />}
                    </div>
                  </td>
                  <td className="p-4 font-sans font-bold font-medium text-foreground transition-colors group-hover:text-primary">
                    {row.item}
                  </td>
                  <td className="max-w-[300px] truncate p-4 font-sans font-bold text-muted-foreground">
                    {row.numericValue == null
                      ? row.valueText
                      : row.numericValue.toLocaleString(undefined, {
                          maximumFractionDigits: 2,
                        })}
                  </td>
                  <td className="p-4 font-sans font-bold text-muted-foreground/70">
                    {row.dateText}
                  </td>
                  <td className="p-4">
                    <span className="flex max-w-[260px] w-fit items-center gap-2 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-bold text-muted-foreground transition-colors group-hover:border-primary/30 font-sans">
                      <span className="h-4 w-1 rounded-full bg-indigo-500/50" />
                      <span className="truncate">{row.sourceDoc}</span>
                    </span>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="h-1.5 w-24 flex-1 overflow-hidden rounded-full bg-white/10">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${row.confidence * 100}%` }}
                          transition={{ duration: 0.5, delay: Math.min(0.25, index * 0.01) }}
                          className={cn(
                            "h-full rounded-full shadow-[0_0_10px_currentColor]",
                            row.confidence > 0.9
                              ? "bg-emerald-500"
                              : row.confidence > 0.8
                                ? "bg-amber-500"
                                : "bg-red-500"
                          )}
                        />
                      </div>
                      <span
                        className={cn(
                          "font-sans text-xs font-bold",
                          row.confidence > 0.9
                            ? "text-emerald-500"
                            : row.confidence > 0.8
                              ? "text-amber-500"
                              : "text-red-500"
                        )}
                      >
                        {Math.floor(row.confidence * 100)}%
                      </span>
                    </div>
                  </td>
                  <td className="p-4">
                    {row.status === "VERIFIED" ? (
                      <div className="flex w-fit items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 font-sans text-[10px] font-bold text-emerald-500">
                        <CheckCircle2 size={12} /> {statusLabel(row.status)}
                      </div>
                    ) : row.status === "MISMATCH" ? (
                      <div className="flex w-fit items-center gap-1.5 rounded-full border border-red-500/20 bg-red-500/10 px-2 py-1 font-sans text-[10px] font-bold text-red-500">
                        <AlertCircle size={12} /> {statusLabel(row.status)}
                      </div>
                    ) : (
                      <div className="flex w-fit items-center gap-1.5 rounded-full border border-slate-500/20 bg-slate-500/10 px-2 py-1 font-sans text-[10px] font-bold text-slate-400">
                        {statusLabel(row.status)}
                      </div>
                    )}
                  </td>
                  <td className="p-4 text-center opacity-0 transition-opacity group-hover:opacity-100">
                    <button 
                      title="查看详情"
                      aria-label="查看详情"
                      className="rounded p-1 text-muted-foreground hover:bg-white/10 hover:text-foreground"
                    >
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

      <div className="absolute bottom-6 left-1/2 z-20 flex -translate-x-1/2 items-center gap-6 rounded-full border border-white/20 bg-white/80 px-6 py-2.5 shadow-2xl backdrop-blur-xl transition-transform duration-300 hover:scale-105 dark:border-white/10 dark:bg-slate-900/80">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          <span className="font-sans text-[10px] font-bold text-muted-foreground">
            融合引擎在线
          </span>
        </div>
        <div className="h-4 w-px bg-white/20 dark:bg-white/10" />
        <div className="flex items-center gap-4 font-sans font-mono text-[10px] font-bold text-muted-foreground">
          <span>
            已选：<span className="text-foreground">{selectedCount}</span>
          </span>
          <span>
            已校验：<span className="text-foreground">{verifiedCount}</span>
          </span>
        </div>
        <div className="h-4 w-px bg-white/20 dark:bg-white/10" />
        <div className="flex gap-4 font-sans font-mono text-[10px] font-bold">
          <span className="text-muted-foreground">
            合计：
            <span className="text-foreground">
              {totalAmount.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          </span>
          <span className="text-slate-400">行数：{rows.length}</span>
        </div>
      </div>
    </div>
  );
};
