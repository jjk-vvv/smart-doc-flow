import type {
  PlatformAssistantBootstrapAction,
  PlatformAssistantBootstrapCard,
  PlatformAssistantBootstrapPage,
  PlatformAssistantBootstrapPrompt,
} from '../../../shared/api/platformAssistant';

export type PlatformTabId =
  | 'dashboard'
  | 'deepread'
  | 'doc-processing'
  | 'deepread_extraction'
  | 'fusion'
  | 'nexus'
  | 'mine';

export type AssistantCardAction = {
  label: string;
  targetTab: PlatformTabId;
  variant?: 'primary' | 'secondary';
};

export type GuidedAnswerCard = {
  title: string;
  summary: string;
  steps: string[];
  primaryAction: AssistantCardAction;
  secondaryAction?: AssistantCardAction;
};

export type AssistantPrompt = {
  id: string;
  question: string;
  keywords: string[];
  answer: GuidedAnswerCard;
};

export type AssistantPageConfig = {
  tab: PlatformTabId;
  label: string;
  cue: string;
  starter: GuidedAnswerCard;
  prompts: AssistantPrompt[];
  primaryPromptCount?: number;
};

export type AssistantPageCatalog = Partial<Record<PlatformTabId, AssistantPageConfig>>;

const usageQuestionKeywords = [
  'how',
  'start',
  'upload',
  'page',
  'module',
  'difference',
  'next step',
  'use',
  'workflow',
  'guide me',
];

const createAction = (
  label: string,
  targetTab: PlatformTabId,
  variant: 'primary' | 'secondary' = 'primary',
): AssistantCardAction => ({
  label,
  targetTab,
  variant,
});

const createFallbackPageConfig = (
  tab: PlatformTabId,
  label: string,
  cue: string,
  primaryLabel: string,
  secondaryAction: AssistantCardAction,
): AssistantPageConfig => ({
  tab,
  label,
  cue,
  starter: {
    title: `${label} usage`,
    summary:
      'The platform assistant prefers server-provided page guidance and falls back to a local minimal helper when remote guidance is unavailable.',
    steps: [
      'Continue the standard flow in the current module.',
      'Ask the assistant for the next step if you need cross-module coordination.',
    ],
    primaryAction: createAction(primaryLabel, tab),
    secondaryAction,
  },
  prompts: [],
  primaryPromptCount: 0,
});

const pageConfigs: Record<PlatformTabId, AssistantPageConfig> = {
  dashboard: createFallbackPageConfig(
    'dashboard',
    'Dashboard',
    'You are on the dashboard. Pick the module that matches the current task.',
    'Stay on this page',
    createAction('Back to dashboard', 'dashboard', 'secondary'),
  ),
  deepread: createFallbackPageConfig(
    'deepread',
    'DeepRead',
    'You are on the DeepRead entry page.',
    'Stay on this page',
    createAction('Back to dashboard', 'dashboard', 'secondary'),
  ),
  'doc-processing': createFallbackPageConfig(
    'doc-processing',
    'Doc Processing',
    'You are in the document processing module.',
    'Continue here',
    createAction('Back to dashboard', 'dashboard', 'secondary'),
  ),
  deepread_extraction: createFallbackPageConfig(
    'deepread_extraction',
    'AI Extraction',
    'You are in the AI extraction module.',
    'Continue here',
    createAction('Back to dashboard', 'dashboard', 'secondary'),
  ),
  fusion: createFallbackPageConfig(
    'fusion',
    'Fusion',
    'You are in the smart form filling module.',
    'Continue here',
    createAction('Back to dashboard', 'dashboard', 'secondary'),
  ),
  nexus: createFallbackPageConfig(
    'nexus',
    'Knowledge Nexus',
    'You are in the knowledge graph module.',
    'Continue here',
    createAction('Back to dashboard', 'dashboard', 'secondary'),
  ),
  mine: createFallbackPageConfig(
    'mine',
    'Profile',
    'You are in the profile module.',
    'Stay on this page',
    createAction('Back to dashboard', 'dashboard', 'secondary'),
  ),
};

const normalizeQuestion = (question: string): string =>
  question.replace(/\s+/g, '').replace(/[，。！？,.!?]/g, '').toLowerCase();

const hasPageConfigTab = (value: string | null | undefined): value is PlatformTabId => {
  const raw = String(value || '').trim();
  return Object.prototype.hasOwnProperty.call(pageConfigs, raw);
};

export const normalizePlatformTab = (tab: string | null | undefined): PlatformTabId => {
  const raw = String(tab || '').trim();
  if (hasPageConfigTab(raw)) return raw;
  return 'dashboard';
};

export const getAssistantPageConfig = (tab: PlatformTabId): AssistantPageConfig =>
  pageConfigs[tab] || pageConfigs.dashboard;

const normalizeActionTarget = (targetTab: string | null | undefined, fallback: PlatformTabId): PlatformTabId => {
  const raw = String(targetTab || '').trim();
  if (hasPageConfigTab(raw)) return raw;
  return fallback;
};

const normalizeRemoteAction = (
  action: PlatformAssistantBootstrapAction | undefined,
  fallback: AssistantCardAction,
): AssistantCardAction => ({
  label: typeof action?.label === 'string' && action.label.trim() ? action.label.trim() : fallback.label,
  targetTab: normalizeActionTarget(action?.targetTab, fallback.targetTab),
  variant: action?.variant === 'secondary' ? 'secondary' : fallback.variant,
});

const normalizeSteps = (steps: string[] | undefined, fallback: string[]): string[] => {
  const normalized = Array.isArray(steps)
    ? steps.map((step) => String(step || '').trim()).filter(Boolean)
    : [];
  return normalized.length ? normalized : fallback;
};

const normalizeRemoteCard = (
  card: PlatformAssistantBootstrapCard | undefined,
  fallback: GuidedAnswerCard,
): GuidedAnswerCard => ({
  title: typeof card?.title === 'string' && card.title.trim() ? card.title.trim() : fallback.title,
  summary:
    typeof card?.summary === 'string' && card.summary.trim() ? card.summary.trim() : fallback.summary,
  steps: normalizeSteps(card?.steps, fallback.steps),
  primaryAction: normalizeRemoteAction(card?.primaryAction, fallback.primaryAction),
  secondaryAction: card?.secondaryAction
    ? normalizeRemoteAction(card.secondaryAction, fallback.secondaryAction || fallback.primaryAction)
    : fallback.secondaryAction,
});

const normalizeRemotePrompt = (
  prompt: PlatformAssistantBootstrapPrompt,
  fallbackTab: PlatformTabId,
): AssistantPrompt | null => {
  const id = String(prompt?.id || '').trim();
  const question = String(prompt?.question || '').trim();
  if (!id || !question) return null;

  return {
    id,
    question,
    keywords: Array.isArray(prompt?.keywords)
      ? prompt.keywords.map((keyword) => String(keyword || '').trim()).filter(Boolean)
      : [],
    answer: normalizeRemoteCard(prompt?.answer, {
      title: question,
      summary: '',
      steps: [],
      primaryAction: createAction('Stay on this page', fallbackTab),
    }),
  };
};

export const hydrateAssistantPageConfig = (
  tab: PlatformTabId,
  remotePage?: PlatformAssistantBootstrapPage | null,
  catalogOverride?: AssistantPageCatalog | null,
): AssistantPageConfig => {
  const fallback = catalogOverride?.[tab] || getAssistantPageConfig(tab);
  if (!remotePage) return fallback;

  const prompts = Array.isArray(remotePage.prompts)
    ? remotePage.prompts
        .map((prompt) => normalizeRemotePrompt(prompt, fallback.tab))
        .filter((prompt): prompt is AssistantPrompt => Boolean(prompt))
    : fallback.prompts;

  return {
    tab: fallback.tab,
    label:
      typeof remotePage.label === 'string' && remotePage.label.trim() ? remotePage.label.trim() : fallback.label,
    cue: typeof remotePage.cue === 'string' && remotePage.cue.trim() ? remotePage.cue.trim() : fallback.cue,
    starter: normalizeRemoteCard(remotePage.starter, fallback.starter),
    prompts,
    primaryPromptCount:
      Number.isFinite(remotePage.primaryPromptCount) && Number(remotePage.primaryPromptCount) >= 0
        ? Math.trunc(Number(remotePage.primaryPromptCount))
        : (fallback.primaryPromptCount ?? 0),
  };
};

export const buildAssistantPageCatalog = (
  remotePages?: PlatformAssistantBootstrapPage[] | null,
): AssistantPageCatalog | null => {
  if (!Array.isArray(remotePages) || remotePages.length === 0) return null;

  const catalog: AssistantPageCatalog = {};
  for (const remotePage of remotePages) {
    const rawTab = String(remotePage?.tab || '').trim();
    if (!hasPageConfigTab(rawTab)) continue;
    catalog[rawTab] = hydrateAssistantPageConfig(rawTab, remotePage);
  }

  return Object.keys(catalog).length > 0 ? catalog : null;
};

export const getPagePromptGroups = (tab: PlatformTabId, configOverride?: AssistantPageConfig | null) => {
  const config = configOverride || getAssistantPageConfig(tab);
  const primaryPromptCount = Math.max(0, config.primaryPromptCount ?? 2);
  return {
    primary: config.prompts.slice(0, primaryPromptCount),
    secondary: config.prompts.slice(primaryPromptCount),
  };
};

export const looksLikeUsageQuestion = (question: string): boolean => {
  const normalized = normalizeQuestion(question);
  return usageQuestionKeywords.some((keyword) => normalized.includes(normalizeQuestion(keyword)));
};

export const findGuidedPrompt = (
  question: string,
  tab: PlatformTabId,
  configOverride?: AssistantPageConfig | null,
  catalogOverride?: AssistantPageCatalog | null,
): AssistantPrompt | null => {
  const normalized = normalizeQuestion(question);
  const currentConfig = configOverride || catalogOverride?.[tab] || getAssistantPageConfig(tab);
  const promptPool = [...currentConfig.prompts];
  const configSource = catalogOverride
    ? Object.values(catalogOverride).filter((config): config is AssistantPageConfig => Boolean(config))
    : Object.values(pageConfigs);

  for (const config of configSource) {
    if (config.tab === currentConfig.tab) continue;
    promptPool.push(...config.prompts);
  }

  for (const prompt of promptPool) {
    const exact = normalizeQuestion(prompt.question);
    if (normalized === exact) return prompt;
    if (prompt.keywords.some((keyword) => normalized.includes(normalizeQuestion(keyword)))) {
      return prompt;
    }
  }

  return null;
};

export const buildUsageFallbackCard = (
  tab: PlatformTabId,
  question: string,
  configOverride?: AssistantPageConfig | null,
): GuidedAnswerCard => {
  const config = configOverride || getAssistantPageConfig(tab);
  const starter = config.starter;
  return {
    ...starter,
    summary: `${starter.summary}${question ? ' The assistant can keep narrowing down the next step based on your current goal.' : ''}`,
  };
};

export const guidedCardToText = (card: GuidedAnswerCard): string => {
  const lines = [
    card.title,
    card.summary,
    ...card.steps.map((step, index) => `${index + 1}. ${step}`),
    `Recommended action: ${card.primaryAction.label}`,
  ];

  if (card.secondaryAction) {
    lines.push(`Optional action: ${card.secondaryAction.label}`);
  }

  return lines.join('\n');
};
