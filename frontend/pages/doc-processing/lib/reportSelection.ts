export type ReportToolbarPlacement = 'top' | 'bottom';

export interface ReportSelectionRect {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

export interface ReportSelectionSnapshot {
  blockKey: string;
  startOffset: number;
  endOffset: number;
  selectedText: string;
  rect: ReportSelectionRect;
}

const toElement = (node: Node | null): HTMLElement | null => {
  if (!node) return null;
  if (node.nodeType === Node.ELEMENT_NODE) return node as HTMLElement;
  return node.parentElement;
};

const findReportBlock = (node: Node | null, root: HTMLElement): HTMLElement | null => {
  const element = toElement(node);
  if (!element) return null;
  const block = element.closest<HTMLElement>('[data-report-block-key]');
  if (!block || !root.contains(block)) return null;
  return block;
};

const getTextOffsetWithinBlock = (block: HTMLElement, targetNode: Node, targetOffset: number): number => {
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  let offset = 0;

  while (walker.nextNode()) {
    const currentNode = walker.currentNode;
    const currentTextLength = currentNode.textContent?.length ?? 0;

    if (currentNode === targetNode) {
      return offset + targetOffset;
    }

    offset += currentTextLength;
  }

  return offset;
};

const toSelectionRect = (rect: DOMRect): ReportSelectionRect => ({
  top: rect.top,
  left: rect.left,
  right: rect.right,
  bottom: rect.bottom,
  width: rect.width,
  height: rect.height,
});

export const clearBrowserSelection = (): void => {
  if (typeof window === 'undefined') return;
  const selection = window.getSelection();
  if (!selection) return;
  selection.removeAllRanges();
};

export const extractReportSelection = (root: HTMLElement): ReportSelectionSnapshot | null => {
  if (typeof window === 'undefined') return null;
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;

  const range = selection.getRangeAt(0);
  const commonAncestor = toElement(range.commonAncestorContainer);
  if (!commonAncestor || !root.contains(commonAncestor)) return null;

  const startBlock = findReportBlock(range.startContainer, root);
  const endBlock = findReportBlock(range.endContainer, root);
  if (!startBlock || !endBlock || startBlock !== endBlock) return null;

  const selectedText = selection.toString();
  const normalizedText = selectedText.replace(/\s+/g, ' ').trim();
  if (!normalizedText) return null;

  const startOffset = getTextOffsetWithinBlock(startBlock, range.startContainer, range.startOffset);
  const endOffset = getTextOffsetWithinBlock(startBlock, range.endContainer, range.endOffset);
  if (endOffset <= startOffset) return null;

  const rect = range.getBoundingClientRect();
  if (!(rect.width > 0 || rect.height > 0)) return null;

  return {
    blockKey: startBlock.dataset.reportBlockKey || '',
    startOffset,
    endOffset,
    selectedText,
    rect: toSelectionRect(rect),
  };
};

export const computeToolbarPosition = (
  anchorRect: ReportSelectionRect,
  toolbarWidth: number,
  toolbarHeight: number,
): { top: number; left: number; placement: ReportToolbarPlacement } => {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const sidePadding = 12;
  const gap = 12;

  const centeredLeft = anchorRect.left + (anchorRect.width / 2) - (toolbarWidth / 2);
  const left = Math.min(
    Math.max(sidePadding, centeredLeft),
    Math.max(sidePadding, viewportWidth - toolbarWidth - sidePadding),
  );

  const preferredTop = anchorRect.top - toolbarHeight - gap;
  if (preferredTop >= sidePadding) {
    return {
      top: preferredTop,
      left,
      placement: 'top',
    };
  }

  return {
    top: Math.min(anchorRect.bottom + gap, viewportHeight - toolbarHeight - sidePadding),
    left,
    placement: 'bottom',
  };
};
