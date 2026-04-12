import React, {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  ChevronDown,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";
import { FixedSizeList, type ListChildComponentProps } from "react-window";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  applyModule3WordDiff,
  parseModule3WordJson,
  type Module3WordApplyDiffRequest,
  type Module3WordCell,
  type Module3WordCellDiff,
  type Module3WordParagraph,
  type Module3WordParagraphDiff,
  type Module3WordSection,
  type Module3WordSectionDiff,
  type Module3WordStructureAction,
  type Module3WordStyle,
  type Module3WordTableSection,
  type Module3WordTextSection,
} from "../lib/module3Api";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type WordPreviewDocument = {
  id: string;
  name: string;
};

type Module3WordPreviewProps = {
  document: WordPreviewDocument;
  fallbackContent: string;
};

type LocalWordCell = Module3WordCell & {
  _id: string;
};

type LocalWordTableRow = {
  id: string;
  cells: LocalWordCell[];
};

type LocalWordTableSection = Omit<Module3WordTableSection, "rows"> & {
  rows: LocalWordTableRow[];
};

type LocalWordSection = Module3WordTextSection | LocalWordTableSection;

type PendingEditingValue = {
  id: string;
  data:
    | {
        type: "text";
        sectionId: string;
        paragraphIndex: number;
        text: string;
      }
    | {
        type: "table";
        sectionId: string;
        row: number;
        col: number;
        value: string;
      };
};

const VIRTUAL_TABLE_THRESHOLD = 500;
const VIRTUAL_ROW_HEIGHT = 44;
const VIRTUAL_OVERSCAN = 6;
const ROW_HANDLE_WIDTH = 56;
let localWordNodeCounter = 0;

const highlightColorMap: Record<string, string> = {
  yellow: "#fef08a",
  green: "#86efac",
  turquoise: "#67e8f9",
  pink: "#f9a8d4",
  blue: "#93c5fd",
  red: "#fca5a5",
  darkblue: "#60a5fa",
  teal: "#5eead4",
  gray25: "#e5e7eb",
  gray50: "#d1d5db",
};

const mapWordStyleToPresentation = (
  style?: Module3WordStyle,
): { className: string; style: CSSProperties } => {
  const classNames: string[] = [];
  const inlineStyle: CSSProperties = {};
  const styleId = String(style?.style_id ?? "").toLowerCase();

  if (style?.["w:b"]) classNames.push("font-semibold");
  if (style?.["w:i"]) classNames.push("italic");
  if (style?.["w:u"]) classNames.push("underline");
  if (style?.["w:strike"]) classNames.push("line-through");

  if (styleId === "heading1") classNames.push("text-3xl", "font-bold");
  if (styleId === "heading2") classNames.push("text-2xl", "font-bold");
  if (styleId === "heading3") classNames.push("text-xl", "font-semibold");
  if (styleId === "heading4") classNames.push("text-lg", "font-semibold");

  if (style?.alignment === "center") classNames.push("text-center");
  if (style?.alignment === "right") classNames.push("text-right");
  if (style?.alignment === "justify") classNames.push("text-justify");

  if (typeof style?.["w:sz"] === "number" && Number.isFinite(style["w:sz"])) {
    inlineStyle.fontSize = `${Math.max(10, (style["w:sz"] / 2) * (96 / 72))}px`;
    inlineStyle.lineHeight = 1.5;
  }
  if (style?.color) {
    inlineStyle.color = `#${style.color.replace(/^#/, "")}`;
  }
  if (style?.highlight) {
    const key = style.highlight.replace(/\s|\(.+\)/g, "").toLowerCase();
    if (highlightColorMap[key]) {
      inlineStyle.backgroundColor = highlightColorMap[key];
    }
  }
  if (style?.font) {
    inlineStyle.fontFamily = style.font;
  }

  return { className: classNames.join(" "), style: inlineStyle };
};

const nextLocalWordNodeId = (prefix: string): string => {
  localWordNodeCounter += 1;
  return `${prefix}-${localWordNodeCounter}`;
};

const withStableWordCellId = (cell: Module3WordCell): LocalWordCell => ({
  ...cell,
  _id: nextLocalWordNodeId("cell"),
});

const toLocalWordSections = (
  sections: Module3WordSection[],
): LocalWordSection[] =>
  sections.map((section) => {
    if (section.type !== "table") {
      return section;
    }

    return {
      ...section,
      rows: section.rows.map((row) => ({
        id: nextLocalWordNodeId("row"),
        cells: row.map(withStableWordCellId),
      })),
    };
  });

const pruneEmptyWordSections = (
  sections: Module3WordSection[],
): Module3WordSection[] =>
  sections
    .map((section) => {
      if (section.type === "text") {
        const paragraphs = section.paragraphs.filter((paragraph) =>
          paragraph.text.trim(),
        );
        return paragraphs.length > 0 ? { ...section, paragraphs } : null;
      }

      const hasMeaningfulCell = section.rows.some((row) =>
        row.some((cell) => cell.text.trim()),
      );
      return hasMeaningfulCell ? section : null;
    })
    .filter((section): section is Module3WordSection => section !== null);

const collapseParagraphRuns = (
  paragraph: Module3WordParagraph,
  text: string,
): Module3WordParagraph => {
  const firstRunStyle = paragraph.runs[0]?.style ?? paragraph.style ?? {};
  return {
    ...paragraph,
    text,
    runs: [{ text, style: firstRunStyle }],
  };
};

const buildDiffPayload = (
  diffMap: Record<string, Module3WordSectionDiff>,
): Module3WordApplyDiffRequest["sections"] => Object.values(diffMap);

const buildActionPayload = (
  actions: Module3WordStructureAction[],
): Module3WordStructureAction[] => actions;

const mergePendingEditingValue = (
  current: Record<string, Module3WordSectionDiff>,
  pending: PendingEditingValue | null,
): Record<string, Module3WordSectionDiff> => {
  if (!pending) {
    return current;
  }

  if (pending.data.type === "text") {
    return mergeTextDiff(current, pending.data.sectionId, {
      paragraph_index: pending.data.paragraphIndex,
      text: pending.data.text,
    });
  }

  return mergeCellDiff(current, pending.data.sectionId, {
    row: pending.data.row,
    col: pending.data.col,
    value: pending.data.value,
  });
};

const mergeTextDiff = (
  current: Record<string, Module3WordSectionDiff>,
  sectionId: string,
  paragraphDiff: Module3WordParagraphDiff,
): Record<string, Module3WordSectionDiff> => {
  const existing = current[sectionId];
  const nextParagraphs =
    existing && existing.type === "text"
      ? existing.paragraphs.filter(
          (item) => item.paragraph_index !== paragraphDiff.paragraph_index,
        )
      : [];

  return {
    ...current,
    [sectionId]: {
      section_id: sectionId,
      type: "text",
      paragraphs: [...nextParagraphs, paragraphDiff].sort(
        (left, right) => left.paragraph_index - right.paragraph_index,
      ),
    },
  };
};

const mergeCellDiff = (
  current: Record<string, Module3WordSectionDiff>,
  sectionId: string,
  cellDiff: Module3WordCellDiff,
): Record<string, Module3WordSectionDiff> => {
  const existing = current[sectionId];
  const nextCells =
    existing && existing.type === "table"
      ? existing.cells.filter(
          (item) => !(item.row === cellDiff.row && item.col === cellDiff.col),
        )
      : [];

  return {
    ...current,
    [sectionId]: {
      section_id: sectionId,
      type: "table",
      cells: [...nextCells, cellDiff].sort((left, right) =>
        left.row === right.row ? left.col - right.col : left.row - right.row,
      ),
    },
  };
};

const clearSectionDiff = (
  current: Record<string, Module3WordSectionDiff>,
  sectionId: string,
): Record<string, Module3WordSectionDiff> => {
  if (!(sectionId in current)) {
    return current;
  }
  const next = { ...current };
  delete next[sectionId];
  return next;
};

const cloneEmptyCell = (cell?: LocalWordCell): LocalWordCell => ({
  text: "",
  style: cell?.style ? { ...cell.style } : undefined,
  _id: nextLocalWordNodeId("cell"),
});

const cloneEmptyRow = (
  row: LocalWordTableRow | undefined,
  columnCount: number,
) : LocalWordTableRow => {
  const templateRow = row?.cells ?? [];
  const resolvedCount = Math.max(columnCount, templateRow.length, 1);
  return {
    id: nextLocalWordNodeId("row"),
    cells: Array.from({ length: resolvedCount }, (_, index) =>
      cloneEmptyCell(templateRow[index]),
    ),
  };
};

const applyStructureActionToSection = (
  section: LocalWordTableSection,
  action: Module3WordStructureAction,
): LocalWordTableSection => {
  const nextRows = section.rows.map((row) => ({
    ...row,
    cells: row.cells.map((cell) => ({ ...cell })),
  }));
  const nextWidths = [...section.column_widths];

  if (action.action_type === "delete_row") {
    nextRows.splice(action.index, action.count);
    return { ...section, rows: nextRows, row_count: nextRows.length };
  }

  if (action.action_type === "insert_row") {
    const insertIndex = Math.min(Math.max(action.index, 0), nextRows.length);
    const templateRow =
      nextRows[Math.min(insertIndex, Math.max(nextRows.length - 1, 0))];
    const emptyRows = Array.from({ length: action.count }, () =>
      cloneEmptyRow(templateRow, section.column_count),
    );
    nextRows.splice(insertIndex, 0, ...emptyRows);
    return { ...section, rows: nextRows, row_count: nextRows.length };
  }

  if (action.action_type === "delete_col") {
    nextRows.forEach((row) => row.cells.splice(action.index, action.count));
    nextWidths.splice(action.index, action.count);
    return {
      ...section,
      rows: nextRows,
      row_count: nextRows.length,
      column_count: Math.max(0, section.column_count - action.count),
      column_widths: nextWidths,
    };
  }

  const insertIndex = Math.min(Math.max(action.index, 0), section.column_count);
  nextRows.forEach((row) => {
    const templateCell =
      row.cells[Math.min(insertIndex, Math.max(row.cells.length - 1, 0))] ??
      row.cells[row.cells.length - 1];
    const newCells = Array.from({ length: action.count }, () =>
      cloneEmptyCell(templateCell),
    );
    row.cells.splice(insertIndex, 0, ...newCells);
  });
  const templateWidth =
    nextWidths[Math.min(insertIndex, Math.max(nextWidths.length - 1, 0))] ?? 160;
  nextWidths.splice(
    insertIndex,
    0,
    ...Array.from({ length: action.count }, () => templateWidth),
  );
  return {
    ...section,
    rows: nextRows,
    row_count: nextRows.length,
    column_count: section.column_count + action.count,
    column_widths: nextWidths,
  };
};

const SectionBadge = ({ text }: { text: string }) => (
  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500 dark:bg-slate-800 dark:text-slate-300">
    {text}
  </span>
);

const resolveWordCellVerticalAlign = (
  style?: Module3WordStyle,
): "top" | "middle" | "bottom" => {
  const rawAlign = String(
    (style as Module3WordStyle & { verticalAlign?: string | null })
      ?.verticalAlign ?? "",
  )
    .trim()
    .toLowerCase();

  if (rawAlign === "center" || rawAlign === "middle") {
    return "middle";
  }
  if (rawAlign === "bottom") {
    return "bottom";
  }
  return "top";
};

const RowActionMenu = ({
  onInsertAbove,
  onInsertBelow,
  onDelete,
}: {
  onInsertAbove: () => void;
  onInsertBelow: () => void;
  onDelete: () => void;
}) => (
  <div className="absolute left-0 top-full z-20 mt-1 w-40 rounded-lg border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
    <button
      type="button"
      onClick={onInsertAbove}
      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
    >
      <Plus size={14} />
      上方插入行
    </button>
    <button
      type="button"
      onClick={onInsertBelow}
      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
    >
      <Plus size={14} />
      下方插入行
    </button>
    <button
      type="button"
      onClick={onDelete}
      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-red-600 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/30"
    >
      <Trash2 size={14} />
      删除此行
    </button>
  </div>
);

const ColumnActionMenu = ({
  onInsertLeft,
  onInsertRight,
  onDelete,
}: {
  onInsertLeft: () => void;
  onInsertRight: () => void;
  onDelete: () => void;
}) => (
  <div className="absolute right-0 top-full z-20 mt-1 w-40 rounded-lg border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
    <button
      type="button"
      onClick={onInsertLeft}
      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
    >
      <Plus size={14} />
      左侧插入列
    </button>
    <button
      type="button"
      onClick={onInsertRight}
      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
    >
      <Plus size={14} />
      右侧插入列
    </button>
    <button
      type="button"
      onClick={onDelete}
      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-red-600 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/30"
    >
      <Trash2 size={14} />
      删除此列
    </button>
  </div>
);

const normalizeColumnWidths = (
  widths: number[],
  columnCount: number,
): number[] => {
  if (columnCount <= 0) return [];
  return Array.from({ length: columnCount }, (_, index) => {
    const width = widths[index];
    return typeof width === "number" && Number.isFinite(width) && width > 0
      ? width
      : 160;
  });
};

const WordCellFrame = ({
  cell,
  width,
  selected,
  isEditable,
  children,
}: {
  cell: Module3WordCell;
  width?: number;
  selected: boolean;
  isEditable: boolean;
  children: React.ReactNode;
}) => {
  const presentation = mapWordStyleToPresentation(cell.style);

  return (
    <div
      className="table-cell h-full border-r border-b border-slate-200 align-middle dark:border-slate-700"
      style={{
        width: width ? `${width}px` : undefined,
        minWidth: width ? `${width}px` : undefined,
        maxWidth: width ? `${width}px` : undefined,
        verticalAlign: resolveWordCellVerticalAlign(cell.style),
      }}
    >
      <div
        className={cn(
          "flex h-full min-h-[44px] items-center px-2 py-0 text-sm text-slate-700 dark:text-slate-200",
          selected
            ? "bg-blue-50 dark:bg-blue-950/30"
            : "bg-white dark:bg-slate-950",
          presentation.className,
        )}
        style={presentation.style}
      >
        {children}
      </div>
    </div>
  );
};

const WordCellInput = memo(function WordCellInput({
  cell,
  rowIndex,
  colIndex,
  onChange,
  onBlur,
}: {
  cell: LocalWordCell;
  rowIndex: number;
  colIndex: number;
  onChange: (row: number, col: number, value: string) => void;
  onBlur: (row: number, col: number, value: string) => void;
}) {
  const presentation = mapWordStyleToPresentation(cell.style);
  return (
    <input
      value={cell.text}
      onChange={(event) =>
        onChange(rowIndex, colIndex, event.currentTarget.value)
      }
      onBlur={(event) => onBlur(rowIndex, colIndex, event.currentTarget.value)}
      className={cn(
        "h-full min-h-[44px] w-full border-0 bg-transparent px-0 text-sm text-slate-700 outline-none transition-shadow focus:ring-2 focus:ring-blue-500 dark:text-slate-200",
        presentation.className,
      )}
      style={presentation.style}
    />
  );
});

type WordTableRowRendererData = {
  rows: LocalWordTableRow[];
  widths: number[];
  totalWidth: number;
  isEditable: boolean;
  selectedRow: number | null;
  rowActionMenu: number | null;
  onSelectRow: (row: number) => void;
  onToggleRowMenu: (row: number | null) => void;
  onInsertRow: (index: number) => void;
  onDeleteRow: (index: number) => void;
  onCellChange?: (row: number, col: number, value: string) => void;
  onCellBlur?: (row: number, col: number, value: string) => void;
};

const TableRow = memo(function TableRow({
  row,
  rowIndex,
  widths,
  selected = false,
  style,
  isEditable = true,
  rowMenuOpen = false,
  onSelectRow,
  onToggleRowMenu,
  onInsertRow,
  onDeleteRow,
  onCellChange,
  onCellBlur,
}: {
  row: LocalWordTableRow;
  rowIndex: number;
  widths: number[];
  selected?: boolean;
  style?: CSSProperties;
  isEditable?: boolean;
  rowMenuOpen?: boolean;
  onSelectRow?: (row: number) => void;
  onToggleRowMenu?: (row: number | null) => void;
  onInsertRow?: (index: number) => void;
  onDeleteRow?: (index: number) => void;
  onCellChange?: (row: number, col: number, value: string) => void;
  onCellBlur?: (row: number, col: number, value: string) => void;
}) {
  const resolvedWidths = useMemo(
    () => normalizeColumnWidths(widths, row.cells.length),
    [widths, row.cells.length],
  );

  return (
    <div style={style}>
      <div className="table w-full table-fixed border-collapse">
        <div
          className={cn(
            "table-row cursor-pointer transition-colors",
            selected && "bg-blue-50 dark:bg-blue-950/30",
          )}
          onClick={() => onSelectRow?.(rowIndex)}
        >
          {isEditable ? (
            <div
              className={cn(
                "table-cell h-full border-r border-b border-slate-200 align-middle dark:border-slate-700",
                selected
                  ? "bg-blue-50 dark:bg-blue-950/30"
                  : "bg-slate-50 dark:bg-slate-900",
              )}
              style={{
                width: `${ROW_HANDLE_WIDTH}px`,
                minWidth: `${ROW_HANDLE_WIDTH}px`,
                maxWidth: `${ROW_HANDLE_WIDTH}px`,
              }}
            >
              <div className="relative flex h-full min-h-[44px] items-center justify-center">
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onToggleRowMenu?.(rowMenuOpen ? null : rowIndex);
                  }}
                  className="inline-flex items-center gap-1 rounded-md border border-transparent px-1.5 py-1 text-[11px] text-slate-500 hover:border-slate-200 hover:bg-white hover:text-slate-700 dark:text-slate-400 dark:hover:border-slate-700 dark:hover:bg-slate-950 dark:hover:text-slate-200"
                >
                  {rowIndex + 1}
                  <ChevronDown size={12} />
                </button>
                {rowMenuOpen ? (
                  <RowActionMenu
                    onInsertAbove={() => onInsertRow?.(rowIndex)}
                    onInsertBelow={() => onInsertRow?.(rowIndex + 1)}
                    onDelete={() => onDeleteRow?.(rowIndex)}
                  />
                ) : null}
              </div>
            </div>
          ) : null}
          {row.cells.map((cell, colIndex) => (
            <WordCellFrame
              key={cell._id}
              cell={cell}
              width={resolvedWidths[colIndex]}
              selected={selected}
              isEditable={isEditable}
            >
              {isEditable && onCellChange && onCellBlur ? (
                <WordCellInput
                  cell={cell}
                  rowIndex={rowIndex}
                  colIndex={colIndex}
                  onChange={onCellChange}
                  onBlur={onCellBlur}
                />
              ) : (
                cell.text || "\u00a0"
              )}
            </WordCellFrame>
          ))}
        </div>
      </div>
    </div>
  );
});

const VirtualizedWordTableRow = ({
  index,
  style,
  data,
}: ListChildComponentProps<WordTableRowRendererData>) => (
  <TableRow
    row={data.rows[index]}
    rowIndex={index}
    widths={data.widths}
    selected={data.selectedRow === index}
    rowMenuOpen={data.rowActionMenu === index}
    style={{ ...style, width: data.totalWidth }}
    isEditable={data.isEditable}
    onSelectRow={data.onSelectRow}
    onToggleRowMenu={data.onToggleRowMenu}
    onInsertRow={data.onInsertRow}
    onDeleteRow={data.onDeleteRow}
    onCellChange={data.onCellChange}
    onCellBlur={data.onCellBlur}
  />
);

const VirtualizedWordTable = ({
  section,
  isEditable = true,
  onCellChange,
  onCellBlur,
  onInsertRow,
  onDeleteRow,
  onInsertCol,
  onDeleteCol,
}: {
  section: LocalWordTableSection;
  isEditable?: boolean;
  onCellChange?: (row: number, col: number, value: string) => void;
  onCellBlur?: (row: number, col: number, value: string) => void;
  onInsertRow?: (index: number) => void;
  onDeleteRow?: (index: number) => void;
  onInsertCol?: (index: number) => void;
  onDeleteCol?: (index: number) => void;
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const tableRootRef = useRef<HTMLDivElement>(null);
  const [viewportHeight, setViewportHeight] = useState(480);
  const [viewportWidth, setViewportWidth] = useState(0);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [rowActionMenu, setRowActionMenu] = useState<number | null>(null);
  const [columnActionMenu, setColumnActionMenu] = useState<number | null>(null);
  const widths = useMemo(
    () => normalizeColumnWidths(section.column_widths, section.column_count),
    [section.column_count, section.column_widths],
  );
  const totalWidth = useMemo(
    () => widths.reduce((sum, width) => sum + width, 0),
    [widths],
  );
  const listData = useMemo<WordTableRowRendererData>(
    () => ({
      rows: section.rows,
      widths,
      totalWidth: totalWidth + (isEditable ? ROW_HANDLE_WIDTH : 0),
      isEditable,
      selectedRow,
      rowActionMenu,
      onSelectRow: setSelectedRow,
      onToggleRowMenu: setRowActionMenu,
      onInsertRow: onInsertRow ?? (() => undefined),
      onDeleteRow: onDeleteRow ?? (() => undefined),
      onCellChange,
      onCellBlur,
    }),
    [
      section.rows,
      widths,
      totalWidth,
      isEditable,
      selectedRow,
      rowActionMenu,
      onInsertRow,
      onDeleteRow,
      onCellChange,
      onCellBlur,
    ],
  );
  const getItemKey = useCallback(
    (index: number, data: WordTableRowRendererData) =>
      data.rows[index]?.id ?? index,
    [],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      setViewportHeight(entry.contentRect.height || 480);
      setViewportWidth(entry.contentRect.width || 0);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (tableRootRef.current?.contains(target)) return;
      setRowActionMenu(null);
      setColumnActionMenu(null);
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  return (
    <div
      ref={tableRootRef}
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800"
    >
      <div className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
        已启用虚拟渲染，仅渲染当前视口附近的行。总行数 {section.row_count}
      </div>
      <div
        ref={containerRef}
        className="min-h-0 flex-1 overflow-x-auto overflow-y-hidden bg-white dark:bg-slate-950"
      >
        {viewportWidth > 0 ? (
          <div
            className="border-l border-t border-slate-200 dark:border-slate-700"
            style={{
              width: Math.max(
                viewportWidth,
                totalWidth + (isEditable ? ROW_HANDLE_WIDTH : 0),
              ),
            }}
          >
            {isEditable ? (
              <div className="table w-full table-fixed border-collapse">
                <div className="table-row bg-slate-50 dark:bg-slate-900">
                  <div
                    className="table-cell border-r border-b border-slate-200 align-middle dark:border-slate-700"
                    style={{
                      width: `${ROW_HANDLE_WIDTH}px`,
                      minWidth: `${ROW_HANDLE_WIDTH}px`,
                      maxWidth: `${ROW_HANDLE_WIDTH}px`,
                    }}
                  >
                    <div className="flex min-h-[40px] items-center justify-center text-[11px] font-medium text-slate-400 dark:text-slate-500">
                      行
                    </div>
                  </div>
                  {widths.map((width, columnIndex) => (
                    <div
                      key={`column-header-${columnIndex}`}
                      className="table-cell border-r border-b border-slate-200 align-middle dark:border-slate-700"
                      style={{
                        width: `${width}px`,
                        minWidth: `${width}px`,
                        maxWidth: `${width}px`,
                      }}
                    >
                      <div className="relative flex min-h-[40px] items-center justify-between gap-2 bg-slate-50 px-2 text-xs font-medium text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                        <span>列 {columnIndex + 1}</span>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setColumnActionMenu(
                              columnActionMenu === columnIndex ? null : columnIndex,
                            );
                          }}
                          className="inline-flex items-center rounded-md px-1 py-1 text-slate-500 hover:bg-white hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                        >
                          <ChevronDown size={12} />
                        </button>
                        {columnActionMenu === columnIndex ? (
                          <ColumnActionMenu
                            onInsertLeft={() => onInsertCol?.(columnIndex)}
                            onInsertRight={() => onInsertCol?.(columnIndex + 1)}
                            onDelete={() => onDeleteCol?.(columnIndex)}
                          />
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <FixedSizeList
              height={Math.max(0, viewportHeight - (isEditable ? 40 : 0))}
              width={Math.max(
                viewportWidth,
                totalWidth + (isEditable ? ROW_HANDLE_WIDTH : 0),
              )}
              itemCount={section.rows.length}
              itemSize={VIRTUAL_ROW_HEIGHT}
              overscanCount={VIRTUAL_OVERSCAN}
              itemData={listData}
              itemKey={getItemKey}
            >
              {VirtualizedWordTableRow}
            </FixedSizeList>
          </div>
        ) : null}
      </div>
    </div>
  );
};

const StandardWordTable = ({
  section,
  isEditable = true,
  onCellChange,
  onCellBlur,
  onInsertRow,
  onDeleteRow,
  onInsertCol,
  onDeleteCol,
}: {
  section: LocalWordTableSection;
  isEditable?: boolean;
  onCellChange?: (row: number, col: number, value: string) => void;
  onCellBlur?: (row: number, col: number, value: string) => void;
  onInsertRow?: (index: number) => void;
  onDeleteRow?: (index: number) => void;
  onInsertCol?: (index: number) => void;
  onDeleteCol?: (index: number) => void;
}) => {
  const tableRootRef = useRef<HTMLDivElement>(null);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [rowActionMenu, setRowActionMenu] = useState<number | null>(null);
  const [columnActionMenu, setColumnActionMenu] = useState<number | null>(null);
  const widths = useMemo(
    () => normalizeColumnWidths(section.column_widths, section.column_count),
    [section.column_count, section.column_widths],
  );
  const totalWidth = useMemo(
    () => widths.reduce((sum, width) => sum + width, 0),
    [widths],
  );

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (tableRootRef.current?.contains(target)) return;
      setRowActionMenu(null);
      setColumnActionMenu(null);
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  if (section.row_count > VIRTUAL_TABLE_THRESHOLD || section.virtualized) {
    return (
      <VirtualizedWordTable
        section={section}
        isEditable={isEditable}
        onCellChange={onCellChange}
        onCellBlur={onCellBlur}
        onInsertRow={onInsertRow}
        onDeleteRow={onDeleteRow}
        onInsertCol={onInsertCol}
        onDeleteCol={onDeleteCol}
      />
    );
  }

  return (
    <div
      ref={tableRootRef}
      className="min-h-0 flex-1 overflow-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
    >
      {isEditable ? (
        <div
          className="border-l border-t border-slate-200 dark:border-slate-700"
          style={{
            minWidth: totalWidth + ROW_HANDLE_WIDTH,
            width: "100%",
          }}
        >
          <div className="table w-full table-fixed border-collapse">
            <div className="table-row bg-slate-50 dark:bg-slate-900">
              <div
                className="table-cell border-r border-b border-slate-200 align-middle dark:border-slate-700"
                style={{
                  width: `${ROW_HANDLE_WIDTH}px`,
                  minWidth: `${ROW_HANDLE_WIDTH}px`,
                  maxWidth: `${ROW_HANDLE_WIDTH}px`,
                }}
              >
                <div className="flex min-h-[40px] items-center justify-center text-[11px] font-medium text-slate-400 dark:text-slate-500">
                  行
                </div>
              </div>
              {widths.map((width, columnIndex) => (
                <div
                  key={`column-header-${columnIndex}`}
                  className="table-cell border-r border-b border-slate-200 align-middle dark:border-slate-700"
                  style={{
                    width: `${width}px`,
                    minWidth: `${width}px`,
                    maxWidth: `${width}px`,
                  }}
                >
                  <div className="relative flex min-h-[40px] items-center justify-between gap-2 bg-slate-50 px-2 text-xs font-medium text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                    <span>列 {columnIndex + 1}</span>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setColumnActionMenu(
                          columnActionMenu === columnIndex ? null : columnIndex,
                        );
                      }}
                      className="inline-flex items-center rounded-md px-1 py-1 text-slate-500 hover:bg-white hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                    >
                      <ChevronDown size={12} />
                    </button>
                    {columnActionMenu === columnIndex ? (
                      <ColumnActionMenu
                        onInsertLeft={() => onInsertCol?.(columnIndex)}
                        onInsertRight={() => onInsertCol?.(columnIndex + 1)}
                        onDelete={() => onDeleteCol?.(columnIndex)}
                      />
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}
      <div
        className="border-l border-t border-slate-200 dark:border-slate-700"
        style={{
          minWidth: totalWidth + (isEditable ? ROW_HANDLE_WIDTH : 0),
          width: "100%",
        }}
      >
        {section.rows.map((row, rowIndex) => (
          <TableRow
            key={row.id}
            row={row}
            rowIndex={rowIndex}
            widths={widths}
            selected={selectedRow === rowIndex}
            isEditable={isEditable}
            rowMenuOpen={rowActionMenu === rowIndex}
            onSelectRow={setSelectedRow}
            onToggleRowMenu={setRowActionMenu}
            onInsertRow={onInsertRow}
            onDeleteRow={onDeleteRow}
            onCellChange={onCellChange}
            onCellBlur={onCellBlur}
          />
        ))}
      </div>
    </div>
  );
};

export const Module3WordPreview: React.FC<Module3WordPreviewProps> = ({
  document,
  fallbackContent,
}) => {
  const [isEditMode, setIsEditMode] = useState(false);
  const [isLoadingEditor, setIsLoadingEditor] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [sections, setSections] = useState<LocalWordSection[]>([]);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [dirtySections, setDirtySections] = useState<
    Record<string, Module3WordSectionDiff>
  >({});
  const [structureChanges, setStructureChanges] = useState<
    Module3WordStructureAction[]
  >([]);
  const [loadError, setLoadError] = useState("");
  const [syncFeedback, setSyncFeedback] = useState<{
    text: string;
    type: "success" | "error";
  } | null>(null);
  const loadedRunIdRef = useRef<string | null>(null);
  const currentEditingValueRef = useRef<PendingEditingValue | null>(null);

  const activeSection = useMemo<LocalWordSection | null>(
    () =>
      sections.find((section) => section.id === activeSectionId) ??
      sections[0] ??
      null,
    [activeSectionId, sections],
  );

  const hasDirtyChanges = Object.keys(dirtySections).length > 0;
  const hasStructureChanges = structureChanges.length > 0;

  const loadStructuredWord = useCallback(async () => {
    setIsLoadingEditor(true);
    setLoadError("");
    setSyncFeedback(null);

    try {
      const response = await parseModule3WordJson(document.id);
      const nextSections = toLocalWordSections(
        pruneEmptyWordSections(response.sections),
      );
      setSections(nextSections);
      setActiveSectionId(nextSections[0]?.id ?? null);
      setDirtySections({});
      setStructureChanges([]);
      loadedRunIdRef.current = document.id;
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "Word 结构化解析失败",
      );
    } finally {
      setIsLoadingEditor(false);
    }
  }, [document.id]);

  useEffect(() => {
    setIsEditMode(false);
    setSections([]);
    setActiveSectionId(null);
    setDirtySections({});
    setStructureChanges([]);
    setLoadError("");
    setSyncFeedback(null);
    loadedRunIdRef.current = null;
    currentEditingValueRef.current = null;
  }, [document.id]);

  useEffect(() => {
    if (loadedRunIdRef.current === document.id && sections.length > 0) return;
    void loadStructuredWord();
  }, [document.id, loadStructuredWord, sections.length]);

  const handleParagraphBlur = useCallback(
    (sectionId: string, paragraphIndex: number, nextText: string) => {
      currentEditingValueRef.current = null;
      setSections((current) =>
        current.map((section) => {
          if (section.id !== sectionId || section.type !== "text") {
            return section;
          }

          const nextParagraphs = section.paragraphs.map((paragraph, index) =>
            index === paragraphIndex
              ? collapseParagraphRuns(paragraph, nextText)
              : paragraph,
          );
          return { ...section, paragraphs: nextParagraphs };
        }),
      );

      setDirtySections((current) =>
        mergeTextDiff(current, sectionId, {
          paragraph_index: paragraphIndex,
          text: nextText,
        }),
      );
    },
    [],
  );

  const handleParagraphChange = useCallback(
    (sectionId: string, paragraphIndex: number, nextText: string) => {
      currentEditingValueRef.current = {
        id: `${sectionId}:paragraph:${paragraphIndex}`,
        data: {
          type: "text",
          sectionId,
          paragraphIndex,
          text: nextText,
        },
      };
    },
    [],
  );

  const handleTableCellChange = useCallback(
    (sectionId: string, rowIndex: number, colIndex: number, value: string) => {
      currentEditingValueRef.current = {
        id: `${sectionId}:cell:${rowIndex}:${colIndex}`,
        data: {
          type: "table",
          sectionId,
          row: rowIndex,
          col: colIndex,
          value,
        },
      };

      setSections((current) =>
        current.map((section) => {
          if (section.id !== sectionId || section.type !== "table") {
            return section;
          }

          const rows = section.rows.map((row, currentRowIndex) => {
            if (currentRowIndex !== rowIndex) return row;
            return {
              ...row,
              cells: row.cells.map((cell, currentColIndex) =>
                currentColIndex === colIndex ? { ...cell, text: value } : cell,
              ),
            };
          });
          return { ...section, rows };
        }),
      );
    },
    [],
  );

  const handleTableCellBlur = useCallback(
    (sectionId: string, rowIndex: number, colIndex: number, value: string) => {
      currentEditingValueRef.current = null;
      setSections((current) =>
        current.map((section) => {
          if (section.id !== sectionId || section.type !== "table") {
            return section;
          }

          const rows = section.rows.map((row, currentRowIndex) => {
            if (currentRowIndex !== rowIndex) return row;
            return {
              ...row,
              cells: row.cells.map((cell, currentColIndex) =>
                currentColIndex === colIndex ? { ...cell, text: value } : cell,
              ),
            };
          });
          return { ...section, rows };
        }),
      );

      setDirtySections((current) =>
        mergeCellDiff(current, sectionId, {
          row: rowIndex,
          col: colIndex,
          value,
        }),
      );
    },
    [],
  );

  const handleStructureChange = useCallback(
    (
      sectionId: string,
      actionType: Module3WordStructureAction["action_type"],
      index: number,
      count = 1,
    ) => {
      const action: Module3WordStructureAction = {
        section_id: sectionId,
        action_type: actionType,
        index,
        count,
      };

      currentEditingValueRef.current = null;
      setSections((current) =>
        current.map((section) => {
          if (section.id !== sectionId || section.type !== "table") {
            return section;
          }
          return applyStructureActionToSection(section, action);
        }),
      );
      setStructureChanges((current) => [...current, action]);
      setDirtySections((current) => clearSectionDiff(current, sectionId));
      setSyncFeedback(null);
    },
    [],
  );

  const handleSave = useCallback(async () => {
    const mergedDirtySections = mergePendingEditingValue(
      dirtySections,
      currentEditingValueRef.current,
    );
    const mergedDiffPayload = buildDiffPayload(mergedDirtySections);
    const mergedActionPayload = buildActionPayload(structureChanges);

    if (mergedDiffPayload.length === 0 && mergedActionPayload.length === 0) {
      setSyncFeedback({ text: "未检测到修改", type: "success" });
      return;
    }

    setIsSaving(true);
    setSyncFeedback(null);

    try {
      const payload: Module3WordApplyDiffRequest = {
        run_id: document.id,
        sections: mergedDiffPayload,
        actions: mergedActionPayload,
      };
      const result = await applyModule3WordDiff(payload);
      currentEditingValueRef.current = null;
      setDirtySections({});
      setStructureChanges([]);
      setSections([]);
      setActiveSectionId(null);
      loadedRunIdRef.current = null;
      setIsEditMode(false);
      setSyncFeedback({
        text: `同步成功，已应用 ${result.applied} 处修改。`,
        type: "success",
      });
    } catch (error) {
      setSyncFeedback({
        text: error instanceof Error ? error.message : "同步失败",
        type: "error",
      });
    } finally {
      setIsSaving(false);
    }
  }, [dirtySections, document.id, structureChanges]);

  const fallbackPreview = useMemo(() => {
    const trimmed = fallbackContent.trim();
    return trimmed || "文件内容为空或无法预览。";
  }, [fallbackContent]);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-900 dark:text-white">
            Word预览
          </div>
          <div className="truncate text-xs text-slate-500 dark:text-slate-400">
            {document.name}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => void loadStructuredWord()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300"
          >
            <RefreshCw size={14} />
            刷新
          </button>
          <button
            type="button"
            onClick={() => setIsEditMode((current) => !current)}
            className={cn(
              "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
              isEditMode
                ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300",
            )}
          >
            <span
              className={cn(
                "h-2.5 w-2.5 rounded-full",
                isEditMode ? "bg-blue-500" : "bg-slate-300 dark:bg-slate-600",
              )}
            />
            在线编辑
          </button>
          {isEditMode ? (
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={isSaving || isLoadingEditor}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSaving ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Save size={16} />
              )}
              保存
            </button>
          ) : null}
        </div>
      </div>

      {syncFeedback ? (
        <div
          className={cn(
            "border-b px-4 py-2 text-xs",
            syncFeedback.type === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300"
              : "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300",
          )}
        >
          {syncFeedback.text}
        </div>
      ) : null}

      {isLoadingEditor ? (
        <div className="flex min-h-0 flex-1 items-center justify-center gap-3 text-sm text-slate-500 dark:text-slate-400">
          <Loader2 size={18} className="animate-spin" />
          正在从后端加载Word 数据...
        </div>
      ) : loadError ? (
        <div className="flex min-h-0 flex-1 items-center justify-center px-6 text-center text-sm text-red-600 dark:text-red-400">
          {loadError}
        </div>
      ) : sections.length === 0 ? (
        <div className="flex min-h-0 flex-1 items-center justify-center px-6 text-center text-sm text-slate-500 dark:text-slate-400">
          当前没有可编辑的内容。
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <aside className="w-64 shrink-0 border-r border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
            <div className="space-y-2 overflow-auto p-3">
              {sections.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveSectionId(section.id)}
                  className={cn(
                    "w-full rounded-xl border px-3 py-3 text-left transition-colors",
                    activeSection?.id === section.id
                      ? "border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-900/30"
                      : "border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-800/60",
                  )}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                      {section.name}
                    </span>
                    <SectionBadge
                      text={section.type === "text" ? "文本" : "表格"}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                    {section.type === "text" ? (
                      <SectionBadge text={`${section.paragraphs.length} 段`} />
                    ) : (
                      <>
                        <SectionBadge text={`${section.row_count} 行`} />
                        <SectionBadge text={`${section.column_count} 列`} />
                        {section.row_count > VIRTUAL_TABLE_THRESHOLD ? (
                          <SectionBadge text="虚拟渲染" />
                        ) : null}
                      </>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </aside>

          <main className="min-h-0 flex-1 overflow-auto bg-white p-4 dark:bg-slate-950">
            {activeSection?.type === "text" ? (
              <div className="space-y-4">
                {(activeSection as Module3WordTextSection).paragraphs.map(
                  (paragraph, paragraphIndex) => {
                    const paragraphPresentation = mapWordStyleToPresentation(
                      paragraph.style,
                    );

                    return (
                      <div
                        key={`${paragraph.index}-${paragraph.text}`}
                        contentEditable={isEditMode}
                        suppressContentEditableWarning={isEditMode}
                        onInput={
                          isEditMode
                            ? (event) =>
                                handleParagraphChange(
                                  activeSection.id,
                                  paragraphIndex,
                                  event.currentTarget.innerText,
                                )
                            : undefined
                        }
                        onBlur={
                          isEditMode
                            ? (event) =>
                                handleParagraphBlur(
                                  activeSection.id,
                                  paragraphIndex,
                                  event.currentTarget.innerText,
                                )
                            : undefined
                        }
                        className={cn(
                          "rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-800 outline-none transition-colors focus:border-blue-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100",
                          !isEditMode &&
                            "cursor-default focus:border-slate-200",
                          paragraphPresentation.className,
                        )}
                        style={paragraphPresentation.style}
                      >
                        {paragraph.runs.map((run, runIndex) => {
                          const runPresentation = mapWordStyleToPresentation(
                            run.style,
                          );
                          return (
                            <span
                              key={`${paragraph.index}-${runIndex}`}
                              className={runPresentation.className}
                              style={runPresentation.style}
                            >
                              {run.text}
                            </span>
                          );
                        })}
                      </div>
                    );
                  },
                )}
              </div>
            ) : activeSection?.type === "table" ? (
              isEditMode ? (
                <StandardWordTable
                  section={activeSection}
                  isEditable
                  onInsertRow={(index) =>
                    handleStructureChange(activeSection.id, "insert_row", index)
                  }
                  onDeleteRow={(index) =>
                    handleStructureChange(activeSection.id, "delete_row", index)
                  }
                  onInsertCol={(index) =>
                    handleStructureChange(activeSection.id, "insert_col", index)
                  }
                  onDeleteCol={(index) =>
                    handleStructureChange(activeSection.id, "delete_col", index)
                  }
                  onCellChange={(row, col, value) =>
                    handleTableCellChange(activeSection.id, row, col, value)
                  }
                  onCellBlur={(row, col, value) =>
                    handleTableCellBlur(activeSection.id, row, col, value)
                  }
                />
              ) : (
                <StandardWordTable section={activeSection} isEditable={false} />
              )
            ) : null}
          </main>
        </div>
      )}
    </div>
  );
};
