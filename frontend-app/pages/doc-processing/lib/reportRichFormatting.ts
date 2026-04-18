import type { ReportSelectionSnapshot } from './reportSelection';

export type ReportBlockType = 'heading1' | 'heading2' | 'heading3' | 'paragraph';
export type ReportTextAlign = 'left' | 'center' | 'justify';

export type ReportInlineFormat = {
  start: number;
  end: number;
  color?: string;
  fontSize?: string;
};

export type ReportInlineStyleUpdate = {
  color?: string | null;
  fontSize?: string | null;
};

export type ReportBlockFormat = {
  type?: ReportBlockType;
  align?: ReportTextAlign;
  inlineFormats?: ReportInlineFormat[];
};

export type ReportFormattingState = Record<string, ReportBlockFormat>;

export type ReportHistorySnapshot = {
  text: string;
  formatting: ReportFormattingState;
};

export const DEFAULT_REPORT_TEXT_COLOR = '#111827';
export const DEFAULT_REPORT_TEXT_ALIGN: ReportTextAlign = 'left';

export const REPORT_TEXT_COLOR_OPTIONS: Array<{ label: string; value: string | null; swatch: string }> = [
  { label: '默认黑', value: null, swatch: '#111827' },
  { label: '蓝色', value: '#2563eb', swatch: '#2563eb' },
  { label: '青灰', value: '#475569', swatch: '#475569' },
  { label: '绿色', value: '#15803d', swatch: '#15803d' },
  { label: '橙色', value: '#c2410c', swatch: '#c2410c' },
  { label: '红色', value: '#b91c1c', swatch: '#b91c1c' },
];

export const REPORT_FONT_SIZE_OPTIONS: Array<{ label: string; value: string | null }> = [
  { label: '跟随段落', value: null },
  { label: '14 px', value: '14px' },
  { label: '16 px', value: '16px' },
  { label: '18 px', value: '18px' },
  { label: '20 px', value: '20px' },
];

export const REPORT_BLOCK_TYPE_OPTIONS: Array<{ label: string; value: ReportBlockType }> = [
  { label: '正文', value: 'paragraph' },
  { label: '一级标题', value: 'heading1' },
  { label: '二级标题', value: 'heading2' },
  { label: '三级标题', value: 'heading3' },
];

export const REPORT_TEXT_ALIGN_OPTIONS: Array<{ label: string; value: ReportTextAlign }> = [
  { label: '左对齐', value: 'left' },
  { label: '居中', value: 'center' },
  { label: '两端', value: 'justify' },
];

type ReportTextSegment = {
  text: string;
  color?: string;
  fontSize?: string;
};

const cloneInlineFormats = (inlineFormats: ReportInlineFormat[] | undefined): ReportInlineFormat[] => (
  (inlineFormats ?? []).map((format) => ({ ...format }))
);

const cloneBlockFormat = (format: ReportBlockFormat | undefined): ReportBlockFormat => ({
  ...(format ?? {}),
  inlineFormats: cloneInlineFormats(format?.inlineFormats),
});

const sortInlineFormats = (inlineFormats: ReportInlineFormat[]): ReportInlineFormat[] => (
  [...inlineFormats]
    .filter((format) => format.end > format.start && (format.color || format.fontSize))
    .sort((left, right) => {
      if (left.start !== right.start) return left.start - right.start;
      return left.end - right.end;
    })
);

const stylesEqual = (
  left: Pick<ReportInlineFormat, 'color' | 'fontSize'>,
  right: Pick<ReportInlineFormat, 'color' | 'fontSize'>,
): boolean => (
  (left.color ?? '') === (right.color ?? '')
  && (left.fontSize ?? '') === (right.fontSize ?? '')
);

const mergeAdjacentInlineFormats = (inlineFormats: ReportInlineFormat[]): ReportInlineFormat[] => {
  const sorted = sortInlineFormats(inlineFormats);
  if (sorted.length <= 1) return sorted;

  const merged: ReportInlineFormat[] = [];

  sorted.forEach((format) => {
    const previous = merged[merged.length - 1];
    if (
      previous
      && previous.end >= format.start
      && stylesEqual(previous, format)
    ) {
      previous.end = Math.max(previous.end, format.end);
      return;
    }
    merged.push({ ...format });
  });

  return merged;
};

const compactInlineFormat = (
  format: Pick<ReportInlineFormat, 'start' | 'end' | 'color' | 'fontSize'>,
): ReportInlineFormat | null => {
  const next: ReportInlineFormat = {
    start: format.start,
    end: format.end,
  };

  if (format.color) {
    next.color = format.color;
  }
  if (format.fontSize) {
    next.fontSize = format.fontSize;
  }

  return next.end > next.start && (next.color || next.fontSize) ? next : null;
};

const applyInlineStylePatch = (
  format: Pick<ReportInlineFormat, 'start' | 'end' | 'color' | 'fontSize'>,
  patch: ReportInlineStyleUpdate,
): ReportInlineFormat | null => {
  const nextColor = patch.color === undefined ? format.color : patch.color || undefined;
  const nextFontSize = patch.fontSize === undefined ? format.fontSize : patch.fontSize || undefined;

  return compactInlineFormat({
    start: format.start,
    end: format.end,
    color: nextColor,
    fontSize: nextFontSize,
  });
};

const pruneBlockFormat = (format: ReportBlockFormat): ReportBlockFormat | null => {
  const inlineFormats = mergeAdjacentInlineFormats(format.inlineFormats ?? []);
  const next: ReportBlockFormat = {};

  if (format.type) {
    next.type = format.type;
  }
  if (format.align) {
    next.align = format.align;
  }
  if (inlineFormats.length > 0) {
    next.inlineFormats = inlineFormats;
  }

  return Object.keys(next).length > 0 ? next : null;
};

const applyInlineStyleToRange = (
  inlineFormats: ReportInlineFormat[],
  start: number,
  end: number,
  patch: ReportInlineStyleUpdate,
): ReportInlineFormat[] => {
  if (end <= start) {
    return mergeAdjacentInlineFormats(inlineFormats);
  }

  const sorted = mergeAdjacentInlineFormats(inlineFormats);
  const next: ReportInlineFormat[] = [];
  let cursor = start;

  sorted.forEach((format) => {
    if (format.end <= start || format.start >= end) {
      next.push({ ...format });
      return;
    }

    if (format.start < start) {
      next.push({ ...format, end: start });
    }

    const overlapStart = Math.max(format.start, start);
    const overlapEnd = Math.min(format.end, end);

    if (cursor < overlapStart) {
      const created = applyInlineStylePatch(
        { start: cursor, end: overlapStart },
        patch,
      );
      if (created) {
        next.push(created);
      }
    }

    const updated = applyInlineStylePatch(
      { ...format, start: overlapStart, end: overlapEnd },
      patch,
    );
    if (updated) {
      next.push(updated);
    }

    cursor = Math.max(cursor, overlapEnd);

    if (format.end > end) {
      next.push({ ...format, start: end });
    }
  });

  if (cursor < end) {
    const created = applyInlineStylePatch({ start: cursor, end }, patch);
    if (created) {
      next.push(created);
    }
  }

  return mergeAdjacentInlineFormats(next);
};

const getInlineStyleForOffset = (
  inlineFormats: ReportInlineFormat[] | undefined,
  offset: number,
): ReportInlineStyleUpdate => {
  const activeFormat = (inlineFormats ?? []).find((format) => offset >= format.start && offset < format.end);
  if (!activeFormat) {
    return {};
  }

  return {
    color: activeFormat.color,
    fontSize: activeFormat.fontSize,
  };
};

const shiftInlineFormatsAfterReplacement = (
  inlineFormats: ReportInlineFormat[] | undefined,
  start: number,
  end: number,
  replacementLength: number,
): ReportInlineFormat[] => {
  const current = mergeAdjacentInlineFormats(inlineFormats ?? []);
  if (!current.length) return [];

  const delta = replacementLength - (end - start);
  const inheritedStyle = getInlineStyleForOffset(current, start);
  const next: ReportInlineFormat[] = [];

  current.forEach((format) => {
    if (format.end <= start) {
      next.push({ ...format });
      return;
    }

    if (format.start >= end) {
      next.push({
        ...format,
        start: format.start + delta,
        end: format.end + delta,
      });
      return;
    }

    if (format.start < start) {
      next.push({ ...format, end: start });
    }

    if (format.end > end) {
      next.push({
        ...format,
        start: start + replacementLength,
        end: start + replacementLength + (format.end - end),
      });
    }
  });

  if (replacementLength > 0 && (inheritedStyle.color || inheritedStyle.fontSize)) {
    const inherited = compactInlineFormat({
      start,
      end: start + replacementLength,
      color: inheritedStyle.color || undefined,
      fontSize: inheritedStyle.fontSize || undefined,
    });
    if (inherited) {
      next.push(inherited);
    }
  }

  return mergeAdjacentInlineFormats(next);
};

export const cloneReportFormatting = (formatting: ReportFormattingState | undefined): ReportFormattingState => {
  const next: ReportFormattingState = {};
  Object.entries(formatting ?? {}).forEach(([blockKey, format]) => {
    const cloned = pruneBlockFormat(cloneBlockFormat(format));
    if (cloned) {
      next[blockKey] = cloned;
    }
  });
  return next;
};

export const buildReportTextSegments = (
  text: string,
  inlineFormats: ReportInlineFormat[] | undefined,
): ReportTextSegment[] => {
  const formats = mergeAdjacentInlineFormats(inlineFormats ?? []);
  if (!formats.length) {
    return [{ text }];
  }

  const boundaries = Array.from(new Set([
    0,
    text.length,
    ...formats.flatMap((format) => [format.start, format.end]),
  ]))
    .filter((offset) => offset >= 0 && offset <= text.length)
    .sort((left, right) => left - right);

  const segments: ReportTextSegment[] = [];

  for (let index = 0; index < boundaries.length - 1; index += 1) {
    const start = boundaries[index];
    const end = boundaries[index + 1];
    if (end <= start) continue;

    const segmentText = text.slice(start, end);
    if (!segmentText) continue;

    const style = getInlineStyleForOffset(formats, start);
    segments.push({
      text: segmentText,
      color: style.color || undefined,
      fontSize: style.fontSize || undefined,
    });
  }

  return segments.length > 0 ? segments : [{ text }];
};

export const getReportBlockFormat = (
  formatting: ReportFormattingState | undefined,
  blockKey: string,
): ReportBlockFormat => cloneBlockFormat(formatting?.[blockKey]);

export const getInlineStyleForSelection = (
  formatting: ReportFormattingState | undefined,
  selection: Pick<ReportSelectionSnapshot, 'blockKey' | 'startOffset'> | null,
): ReportInlineStyleUpdate => {
  if (!selection) return {};
  return getInlineStyleForOffset(formatting?.[selection.blockKey]?.inlineFormats, selection.startOffset);
};

export const applyInlineFormatToSelection = (
  formatting: ReportFormattingState | undefined,
  selection: Pick<ReportSelectionSnapshot, 'blockKey' | 'startOffset' | 'endOffset'>,
  patch: ReportInlineStyleUpdate,
): ReportFormattingState => {
  const next = cloneReportFormatting(formatting);
  const blockFormat = cloneBlockFormat(next[selection.blockKey]);

  blockFormat.inlineFormats = applyInlineStyleToRange(
    blockFormat.inlineFormats ?? [],
    selection.startOffset,
    selection.endOffset,
    patch,
  );

  const pruned = pruneBlockFormat(blockFormat);
  if (pruned) {
    next[selection.blockKey] = pruned;
  } else {
    delete next[selection.blockKey];
  }

  return next;
};

export const applyBlockFormatPatch = (
  formatting: ReportFormattingState | undefined,
  blockKey: string,
  patch: {
    type?: ReportBlockType | null;
    align?: ReportTextAlign | null;
  },
): ReportFormattingState => {
  const next = cloneReportFormatting(formatting);
  const blockFormat = cloneBlockFormat(next[blockKey]);

  if (patch.type !== undefined) {
    blockFormat.type = patch.type || undefined;
  }
  if (patch.align !== undefined) {
    blockFormat.align = patch.align || undefined;
  }

  const pruned = pruneBlockFormat(blockFormat);
  if (pruned) {
    next[blockKey] = pruned;
  } else {
    delete next[blockKey];
  }

  return next;
};

export const adjustReportFormattingAfterTextReplacement = (
  formatting: ReportFormattingState | undefined,
  selection: Pick<ReportSelectionSnapshot, 'blockKey' | 'startOffset' | 'endOffset'>,
  replacementText: string,
): ReportFormattingState => {
  const next = cloneReportFormatting(formatting);
  const blockFormat = cloneBlockFormat(next[selection.blockKey]);

  blockFormat.inlineFormats = shiftInlineFormatsAfterReplacement(
    blockFormat.inlineFormats,
    selection.startOffset,
    selection.endOffset,
    replacementText.length,
  );

  const pruned = pruneBlockFormat(blockFormat);
  if (pruned) {
    next[selection.blockKey] = pruned;
  } else {
    delete next[selection.blockKey];
  }

  return next;
};
