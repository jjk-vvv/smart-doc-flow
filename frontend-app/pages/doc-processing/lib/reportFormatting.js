const REPORT_MARKDOWN_HEADING_RE = /^(#{1,3})\s*(.+)$/;
const REPORT_HEADING1_RE = /^[一二三四五六七八九十百千]+、\s*/;
const REPORT_HEADING2_RE = /^\d+[.、．]\s*/;
const REPORT_HEADING3_RE = /^[（(]\d+[）)]\s*/;
const REPORT_BULLET_RE = /^[-*+•]\s+(.+)$/;
const REPORT_SEPARATOR_RE = /^[-=_]{3,}$/;
const REPORT_ANALYSIS_KEYWORDS = ['结论', '建议', '趋势', '影响', '原因', '归纳', '研判', '洞察', '评估', '摘要', '概况', '判断', '策略'];
const REPORT_EXTRACTION_KEYWORDS = ['提取', '字段', '清单', '编号', '金额', '日期', '表格', '数据', '明细', '结构化', '键值', '工作表', '列名', '样本', '统计', '识别'];
const REPORT_RISK_KEYWORDS = ['风险', '异常', '问题', '隐患', '整改', '合规', '违约', '争议', '告警', '波动', '缺口', '处置', '漏洞', '偏差', '预警'];

const toChineseSectionNumber = (value) => {
  const digits = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
  if (value <= 0) return '一';
  if (value < 10) return digits[value];
  if (value === 10) return '十';
  if (value < 20) return `十${digits[value - 10]}`;
  if (value < 100) {
    const tens = Math.floor(value / 10);
    const units = value % 10;
    return `${digits[tens]}十${units === 0 ? '' : digits[units]}`;
  }
  return String(value);
};

const normalizeReportInlineText = (value) => (
  String(value || '')
    .replace(/\r/g, '')
    .replace(/\u200b/g, '')
    .replace(/\u0000/g, '')
    .replace(/\uFFFD/g, '')
    .replace(/```+/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/~~([^~]+)~~/g, '$1')
    .replace(/^\s*>\s?/, '')
    .replace(/\s+/g, ' ')
    .trim()
);

const stripReportHeadingPrefix = (value) => {
  let text = normalizeReportInlineText(value);
  if (!text) return '';

  let changed = true;
  while (changed) {
    changed = false;
    for (const pattern of [REPORT_HEADING1_RE, REPORT_HEADING2_RE, REPORT_HEADING3_RE]) {
      if (pattern.test(text)) {
        text = text.replace(pattern, '').trim();
        changed = true;
      }
    }
  }
  return text;
};

const joinReportParagraphSegments = (segments) => {
  let combined = '';
  for (const segment of segments) {
    const part = normalizeReportInlineText(segment);
    if (!part) continue;
    if (!combined) {
      combined = part;
      continue;
    }
    const needsSpace = /[A-Za-z0-9)]$/.test(combined) && /^[A-Za-z0-9(]/.test(part);
    combined = `${combined}${needsSpace ? ' ' : ''}${part}`;
  }
  return combined.trim();
};

const countKeywordHits = (text, keywords) => (
  keywords.reduce((total, keyword) => total + (text.includes(keyword) ? 1 : 0), 0)
);

export const inferReportVisualTone = (content) => {
  const text = normalizeReportInlineText(content);
  if (!text) return 'analysis';

  const riskScore = countKeywordHits(text, REPORT_RISK_KEYWORDS);
  const extractionScore = countKeywordHits(text, REPORT_EXTRACTION_KEYWORDS);
  const analysisScore = countKeywordHits(text, REPORT_ANALYSIS_KEYWORDS);

  if (riskScore > 0 && riskScore >= extractionScore && riskScore >= analysisScore) {
    return 'risk';
  }
  if (extractionScore > 0 && extractionScore >= analysisScore) {
    return 'extraction';
  }
  return 'analysis';
};

export const prepareReportContent = (content) => {
  const blocks = [];
  const paragraphBuffer = [];
  let level1Index = 0;
  let level2Index = 0;
  let level3Index = 0;

  const pushBlock = (type, text) => {
    const normalizedText = normalizeReportInlineText(text);
    if (!normalizedText) return;
    blocks.push({
      key: `report-${type}-${blocks.length}`,
      type,
      text: normalizedText,
    });
  };

  const flushParagraph = () => {
    if (!paragraphBuffer.length) return;
    const paragraph = joinReportParagraphSegments(paragraphBuffer);
    paragraphBuffer.length = 0;
    pushBlock('paragraph', paragraph);
  };

  const pushHeading = (level, text) => {
    const normalizedTitle = stripReportHeadingPrefix(text);
    if (!normalizedTitle) return;

    flushParagraph();

    if (level === 1) {
      level1Index += 1;
      level2Index = 0;
      level3Index = 0;
      pushBlock('heading1', `${toChineseSectionNumber(level1Index)}、${normalizedTitle}`);
      return;
    }

    if (level === 2) {
      level2Index += 1;
      level3Index = 0;
      pushBlock('heading2', `${level2Index}. ${normalizedTitle}`);
      return;
    }

    level3Index += 1;
    pushBlock('heading3', `(${level3Index}) ${normalizedTitle}`);
  };

  for (const rawLine of String(content || '').split('\n')) {
    const cleanedLine = normalizeReportInlineText(rawLine);

    if (!cleanedLine || REPORT_SEPARATOR_RE.test(cleanedLine)) {
      flushParagraph();
      continue;
    }

    const markdownHeading = cleanedLine.match(REPORT_MARKDOWN_HEADING_RE);
    if (markdownHeading) {
      const level = Math.min(markdownHeading[1].length, 3);
      pushHeading(level, markdownHeading[2]);
      continue;
    }

    if (REPORT_HEADING1_RE.test(cleanedLine)) {
      pushHeading(1, cleanedLine);
      continue;
    }

    if (REPORT_HEADING2_RE.test(cleanedLine)) {
      pushHeading(2, cleanedLine);
      continue;
    }

    if (REPORT_HEADING3_RE.test(cleanedLine)) {
      pushHeading(3, cleanedLine);
      continue;
    }

    const bulletMatch = cleanedLine.match(REPORT_BULLET_RE);
    if (bulletMatch) {
      pushHeading(3, bulletMatch[1]);
      continue;
    }

    paragraphBuffer.push(cleanedLine);
  }

  flushParagraph();

  return {
    text: blocks.map((block) => block.text).join('\n\n'),
    blocks,
    visualTone: inferReportVisualTone(blocks.map((block) => block.text).join('\n')),
  };
};
