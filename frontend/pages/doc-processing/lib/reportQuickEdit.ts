export type ReportQuickEditAction = 'rewrite' | 'expand' | 'condense' | 'polish';

const normalizeText = (value: string): string => (
  String(value || '')
    .replace(/\r/g, '')
    .replace(/\s+/g, ' ')
    .replace(/[，。；！？]{2,}/g, (match) => match.slice(0, 1))
    .trim()
);

const ensureSentenceEnd = (value: string): string => (
  /[。！？；]$/.test(value) ? value : `${value}。`
);

const applyFormalReplacements = (value: string): string => {
  let next = value;
  const replacements: Array<[RegExp, string]> = [
    [/比较明显/g, '较为明显'],
    [/比较清楚/g, '较为清晰'],
    [/这个/g, '该'],
    [/那个/g, '该'],
    [/然后/g, '随后'],
    [/比较/g, '相对'],
    [/很多/g, '较多'],
    [/挺/g, '较为'],
    [/有点/g, '略有'],
    [/特别/g, '较为'],
    [/就是/g, '即'],
    [/所以/g, '因此'],
    [/的话/g, '时'],
    [/非常非常/g, '显著'],
    [/非常/g, '较为'],
    [/看起来/g, '呈现出'],
  ];

  replacements.forEach(([pattern, replacement]) => {
    next = next.replace(pattern, replacement);
  });

  return next
    .replace(/并\s+且/g, '并且')
    .replace(/而\s+且/g, '而且')
    .replace(/，\s*因此/g, '，因此')
    .replace(/，\s*随后/g, '，随后')
    .replace(/([，。；！？])\s+/g, '$1')
    .replace(/\s+([，。；！？])/g, '$1')
    .trim();
};

const condenseText = (value: string): string => (
  normalizeText(value)
    .replace(/(整体来看|总体来看|总的来看|可以看出|需要注意的是)[，,]?/g, '')
    .replace(/(相对|较为|基本|进一步|持续|明显)(?=\1)/g, '')
    .replace(/(十分|非常|极为|特别)/g, '')
    .replace(/，(并且|而且)/g, '，')
    .replace(/(已经|目前)已/g, '已')
    .replace(/，{2,}/g, '，')
    .replace(/\s+/g, ' ')
    .replace(/^[，、\s]+|[，、\s]+$/g, '')
);

const polishText = (value: string): string => (
  applyFormalReplacements(
    normalizeText(value)
      .replace(/(，){2,}/g, '，')
      .replace(/，\s*并/g, '，并')
      .replace(/，\s*且/g, '，且')
  )
);

const rewriteText = (value: string): string => {
  const polished = polishText(value);
  if (!polished) return '';

  const sentence = ensureSentenceEnd(polished);
  if (/^(该|上述|相关|本次|当前)/.test(sentence)) {
    return sentence;
  }
  return `该内容表明，${sentence.replace(/^[，、\s]+/, '')}`;
};

const expandText = (value: string): string => {
  const polished = polishText(value);
  if (!polished) return '';

  const sentence = ensureSentenceEnd(polished).replace(/[。！？；]$/, '');
  return `${sentence}，相关表述可结合上下文进一步补充说明。`;
};

export const applyReportQuickEdit = (
  action: ReportQuickEditAction,
  input: string,
): string => {
  const text = normalizeText(input);
  if (!text) return '';

  switch (action) {
    case 'rewrite':
      return rewriteText(text);
    case 'expand':
      return expandText(text);
    case 'condense':
      return condenseText(text);
    case 'polish':
      return polishText(text);
    default:
      return text;
  }
};
