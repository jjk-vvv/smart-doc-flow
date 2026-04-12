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
    <div className="relative flex h-[calc(100vh-4.5rem)] flex-col overflow-hidden rounded-[32px] bg-white shadow-[0_4px_24px_rgba(0,0,0,0.03)] dark:bg-slate-900">
      <div className="pointer-events-none absolute -right-20 -top-20 z-0 h-[300px] w-[300px] rounded-full bg-[#C5F1F3]/40 blur-[80px] dark:bg-cyan-500/10" />
      <div className="pointer-events-none absolute -left-20 top-40 z-0 h-[250px] w-[250px] rounded-full bg-blue-100/40 blur-[80px] dark:bg-blue-500/10" />

      <div className="relative z-10 flex h-20 shrink-0 items-center justify-between gap-3 border-b border-slate-100/60 bg-white/60 px-5 backdrop-blur-xl dark:border-slate-800/60 dark:bg-slate-900/60">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-[18px] bg-gradient-to-br from-emerald-50 to-teal-50 text-emerald-500 shadow-[0_2px_10px_rgba(16,185,129,0.05)] dark:from-emerald-500/20 dark:to-teal-500/20 dark:text-emerald-400">
            <Table size={20} strokeWidth={2.5} />
          </div>
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 truncate text-[17px] font-bold tracking-tight text-[#11323B] dark:text-slate-100">
              {latestDocName}
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  rows.length > 0 ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" : "bg-slate-300"
                )}
              />
            </h2>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-[12px] font-medium text-[#64748B] dark:text-slate-400">
                最近更新：{updatedAtText}
              </span>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <div className="relative hidden sm:block">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748B] dark:text-slate-400"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索字段 / 值 / 来源文档"
              className="h-10 w-64 rounded-full border-none bg-[#F2F5F8] pl-9 pr-4 text-[13px] text-[#11323B] outline-none transition-all focus:bg-[#E6F7F9] focus:ring-2 focus:ring-cyan-500/20 dark:bg-slate-800 dark:text-slate-200 dark:focus:bg-slate-700"
            />
          </div>

          <select
            value={sortBy}
            title="选择排序方式"
            aria-label="选择排序方式"
            onChange={(event) => setSortBy(event.target.value as SortBy)}
            className="h-10 rounded-full border-none bg-[#F2F5F8] px-4 text-[13px] font-medium text-[#11323B] outline-none transition-all hover:bg-[#E6F7F9] dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 cursor-pointer"
          >
            <option value="CONF_DESC">置信度降序</option>
            <option value="CONF_ASC">置信度升序</option>
            <option value="FIELD">字段名排序</option>
          </select>

          <button
            className="flex h-10 w-10 items-center justify-center rounded-full bg-[#F2F5F8] text-[#64748B] transition-all hover:bg-emerald-50 hover:text-emerald-600 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-emerald-500/20 dark:hover:text-emerald-400"
            onClick={downloadJson}
            title="导出结构化数据"
          >
            <Download size={18} strokeWidth={2.5} />
          </button>
        </div>
      </div>

      <div className="relative z-10 flex shrink-0 items-center justify-between border-b border-slate-100/60 bg-white/40 px-5 py-3 backdrop-blur-md dark:border-slate-700/60 dark:bg-slate-900/40">
        <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
          <button
            className={cn(
              "whitespace-nowrap rounded-full px-4 py-2 text-[13px] font-bold transition-all",
              filter === "ALL" ? "bg-[#11323B] text-white shadow-md dark:bg-cyan-500 dark:text-white" : "bg-[#F2F5F8] text-[#64748B] hover:bg-[#E6F7F9] dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
            )}
            onClick={() => setFilter("ALL")}
          >
            全部
          </button>
          <button
            className={cn(
              "whitespace-nowrap rounded-full px-4 py-2 text-[13px] font-bold transition-all",
              filter === "VERIFIED"
                ? "bg-emerald-50 text-emerald-600 shadow-sm dark:bg-emerald-500/20 dark:text-emerald-300"
                : "bg-[#F2F5F8] text-[#64748B] hover:bg-[#E6F7F9] dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
            )}
            onClick={() => setFilter("VERIFIED")}
          >
            已校验
          </button>
          <button
            className={cn(
              "whitespace-nowrap rounded-full px-4 py-2 text-[13px] font-bold transition-all",
              filter === "MISMATCH" ? "bg-amber-50 text-amber-600 shadow-sm dark:bg-amber-500/20 dark:text-amber-300" : "bg-[#F2F5F8] text-[#64748B] hover:bg-[#E6F7F9] dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
            )}
            onClick={() => setFilter("MISMATCH")}
          >
            待复核
          </button>
          <button
            className={cn(
              "whitespace-nowrap rounded-full px-4 py-2 text-[13px] font-bold transition-all",
              filter === "PENDING" ? "bg-slate-100 text-slate-600 shadow-sm dark:bg-slate-700 dark:text-slate-300" : "bg-[#F2F5F8] text-[#64748B] hover:bg-[#E6F7F9] dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
            )}
            onClick={() => setFilter("PENDING")}
          >
            待补全
          </button>
        </div>

        <div className="flex items-center gap-3">
          {selectedCount > 0 && (
            <button
              onClick={() => setSelectedRows([])}
              className="flex h-8 items-center gap-1.5 rounded-full bg-rose-50 px-3 text-[12px] font-semibold text-rose-600 transition hover:bg-rose-100 dark:bg-rose-500/10 dark:text-rose-400 dark:hover:bg-rose-500/20"
            >
              <X size={14} />
              清空选择
            </button>
          )}
          <span className="rounded-full bg-[#F2F5F8] px-3 py-1.5 text-[12px] font-semibold text-[#64748B] dark:bg-slate-800 dark:text-slate-400">
            行数：{rows.length}
          </span>
        </div>
      </div>

      <div className="relative z-10 flex-1 overflow-auto bg-slate-50/30 pb-28 dark:bg-slate-900/30 custom-scrollbar">
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 z-20 border-b border-slate-100 bg-white/90 text-[12px] font-bold uppercase tracking-wider text-[#64748B] shadow-sm backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/90 dark:text-slate-400">
            <tr>
              <th className="w-16 p-4 text-center">
                <button
                  className={cn(
                    "mx-auto flex h-5 w-5 items-center justify-center rounded-md border-2 transition-colors",
                    allVisibleSelected
                      ? "border-cyan-500 bg-cyan-500 text-white"
                      : "border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-800"
                  )}
                  onClick={toggleSelectAllVisible}
                  title={allVisibleSelected ? "取消全选当前可见行" : "全选当前可见行"}
                >
                  {allVisibleSelected && <CheckCircle2 size={14} strokeWidth={3} />}
                </button>
              </th>
              <th className="p-4">字段</th>
              <th className="p-4">值</th>
              <th className="p-4">日期</th>
              <th className="p-4">来源文档</th>
              <th className="p-4">置信度</th>
              <th className="p-4">状态</th>
              <th className="w-10 p-4" />
            </tr>
          </thead>

          <tbody className="text-[14px]">
            <AnimatePresence>
              {rows.map((row, index) => (
                <motion.tr
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(0.3, index * 0.01) }}
                  key={row.id}
                  onClick={() => toggleRow(row.id)}
                  className={cn(
                    "group relative cursor-pointer border-b border-slate-100/60 transition-all hover:bg-[#F2F5F8]/50 dark:border-slate-800/60 dark:hover:bg-slate-800/40",
                    selectedRows.includes(row.id) && "bg-cyan-50/40 dark:bg-cyan-900/10"
                  )}
                >
                  <td className="relative p-4 text-center">
                    {selectedRows.includes(row.id) && (
                      <motion.div
                        layoutId="active-row-indicator"
                        className="absolute bottom-2 left-0 top-2 w-1.5 rounded-r-full bg-cyan-500"
                      />
                    )}
                    <div
                      className={cn(
                        "mx-auto flex h-5 w-5 items-center justify-center rounded-md border-2 transition-colors",
                        selectedRows.includes(row.id)
                          ? "border-cyan-500 bg-cyan-500 text-white"
                          : "border-slate-300 bg-white group-hover:border-cyan-300 dark:border-slate-600 dark:bg-slate-800 dark:group-hover:border-cyan-700"
                      )}
                    >
                      {selectedRows.includes(row.id) && <CheckCircle2 size={14} strokeWidth={3} />}
                    </div>
                  </td>
                  <td className="p-4 font-semibold text-[#11323B] transition-colors group-hover:text-cyan-700 dark:text-slate-200 dark:group-hover:text-cyan-400">
                    {row.item}
                  </td>
                  <td className="max-w-[300px] truncate p-4 font-semibold text-[#64748B] dark:text-slate-300">
                    {row.numericValue == null
                      ? row.valueText
                      : row.numericValue.toLocaleString(undefined, {
                          maximumFractionDigits: 2,
                        })}
                  </td>
                  <td className="p-4 font-medium text-[#64748B] dark:text-slate-400">
                    {row.dateText}
                  </td>
                  <td className="p-4">
                    <span className="flex max-w-[260px] w-fit items-center gap-2 rounded-[10px] bg-[#F2F5F8] px-2.5 py-1.5 text-[12px] font-semibold text-[#64748B] transition-colors group-hover:bg-blue-50 group-hover:text-blue-600 dark:bg-slate-800 dark:text-slate-400 dark:group-hover:bg-blue-500/10 dark:group-hover:text-blue-300">
                      <span className="h-4 w-1.5 rounded-full bg-blue-400/50" />
                      <span className="truncate">{row.sourceDoc}</span>
                    </span>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="h-2 w-24 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${row.confidence * 100}%` }}
                          transition={{ duration: 0.5, delay: Math.min(0.25, index * 0.01) }}
                          className={cn(
                            "h-full rounded-full shadow-sm",
                            row.confidence > 0.9
                              ? "bg-emerald-400"
                              : row.confidence > 0.8
                                ? "bg-amber-400"
                                : "bg-rose-400"
                          )}
                        />
                      </div>
                      <span
                        className={cn(
                          "text-[12px] font-bold",
                          row.confidence > 0.9
                            ? "text-emerald-600 dark:text-emerald-400"
                            : row.confidence > 0.8
                              ? "text-amber-600 dark:text-amber-400"
                              : "text-rose-600 dark:text-rose-400"
                        )}
                      >
                        {Math.floor(row.confidence * 100)}%
                      </span>
                    </div>
                  </td>
                  <td className="p-4">
                    {row.status === "VERIFIED" ? (
                      <div className="flex w-fit items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400">
                        <CheckCircle2 size={14} /> {statusLabel(row.status)}
                      </div>
                    ) : row.status === "MISMATCH" ? (
                      <div className="flex w-fit items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-1 text-[11px] font-bold text-rose-600 dark:bg-rose-500/10 dark:text-rose-400">
                        <AlertCircle size={14} /> {statusLabel(row.status)}
                      </div>
                    ) : (
                      <div className="flex w-fit items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                        {statusLabel(row.status)}
                      </div>
                    )}
                  </td>
                  <td className="p-4 text-center opacity-0 transition-opacity group-hover:opacity-100">
                    <button 
                      title="查看详情"
                      aria-label="查看详情"
                      className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-[#64748B] shadow-sm hover:text-[#11323B] dark:bg-slate-700 dark:text-slate-300 dark:hover:text-white"
                    >
                      <ArrowRight size={16} strokeWidth={2.5} />
                    </button>
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>

            {rows.length === 0 && (
              <tr className="border-b border-slate-100/60 dark:border-slate-800/60">
                <td colSpan={8} className="p-16 text-center">
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[#F2F5F8] dark:bg-slate-800">
                    <Table size={28} className="text-[#64748B] dark:text-slate-500" />
                  </div>
                  <p className="text-[15px] font-medium text-[#11323B] dark:text-slate-200">暂无融合结果</p>
                  <p className="mt-1 text-[13px] text-[#64748B] dark:text-slate-400">请先在“解析”页完成文档抽取</p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="absolute bottom-6 left-1/2 z-20 flex -translate-x-1/2 items-center gap-6 rounded-full bg-white/80 px-6 py-3 shadow-[0_8px_30px_rgba(0,0,0,0.06)] backdrop-blur-2xl transition-transform duration-300 hover:-translate-y-1 dark:bg-slate-800/90">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
          </span>
          <span className="text-[12px] font-bold tracking-wide text-[#11323B] dark:text-slate-200">
            引擎在线
          </span>
        </div>
        <div className="h-5 w-[1.5px] bg-slate-200 dark:bg-slate-700" />
        <div className="flex items-center gap-5 text-[12px] font-semibold text-[#64748B] dark:text-slate-400">
          <span>
            已选：<span className="text-[#11323B] dark:text-slate-100">{selectedCount}</span>
          </span>
          <span>
            已校验：<span className="text-emerald-600 dark:text-emerald-400">{verifiedCount}</span>
          </span>
        </div>
        <div className="h-5 w-[1.5px] bg-slate-200 dark:bg-slate-700" />
        <div className="flex gap-5 text-[12px] font-semibold text-[#64748B] dark:text-slate-400">
          <span>
            合计：
            <span className="text-[#11323B] dark:text-slate-100">
              {totalAmount.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          </span>
          <span>行数：{rows.length}</span>
        </div>
      </div>
    </div>
  );
};
