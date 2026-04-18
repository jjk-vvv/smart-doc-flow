import { requestRaw } from './client';

export type AssistantChatMessage = {
  role: 'user' | 'assistant';
  content: string;
};

export type PlatformAssistantBootstrapAssistantPaths = {
  chatPath: string;
  healthPath: string;
  diagnosticsPath: string;
  catalogPath: string;
  bootstrapPath: string;
};

export type PlatformAssistantBootstrapAction = {
  label: string;
  targetTab: string;
  variant?: 'primary' | 'secondary';
};

export type PlatformAssistantBootstrapCard = {
  title: string;
  summary: string;
  steps: string[];
  primaryAction: PlatformAssistantBootstrapAction;
  secondaryAction?: PlatformAssistantBootstrapAction;
};

export type PlatformAssistantBootstrapPrompt = {
  id: string;
  question: string;
  keywords: string[];
  answer: PlatformAssistantBootstrapCard;
};

export type PlatformAssistantBootstrapPage = {
  tab: string;
  label: string;
  cue: string;
  starter: PlatformAssistantBootstrapCard;
  prompts: PlatformAssistantBootstrapPrompt[];
  primaryPromptCount: number;
};

export type PlatformAssistantBootstrapResponse = {
  ok: boolean;
  assistant: PlatformAssistantBootstrapAssistantPaths;
  page: PlatformAssistantBootstrapPage;
  updatedAt: string;
};

export type PlatformAssistantCatalogResponse = {
  ok: boolean;
  assistant: PlatformAssistantBootstrapAssistantPaths;
  pages: PlatformAssistantBootstrapPage[];
  updatedAt: string;
};

export type AssistantContextEnvelope = {
  activeTab: string;
  pageCue: string;
  documents?: Array<Record<string, unknown>>;
  selection?: Record<string, unknown> | null;
  moduleStatus?: Record<string, unknown> | null;
  sessionMeta?: {
    tenantId?: string;
    userId?: string;
    requestId?: string;
  };
};

export type PlatformAssistantChatRequest = {
  messages: AssistantChatMessage[];
  context?: AssistantContextEnvelope;
};

export const requestPlatformAssistantChatStream = async (
  payload: PlatformAssistantChatRequest,
  signal?: AbortSignal,
  preferredBase = '',
) =>
  requestRaw(
    '/api/platform-assistant/chat',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal,
    },
    preferredBase,
  );

export const requestPlatformAssistantHealth = async (preferredBase = '') =>
  requestRaw('/api/platform-assistant/health', { method: 'GET' }, preferredBase);

export const requestPlatformAssistantCatalog = async (preferredBase = '') =>
  requestRaw('/api/platform-assistant/catalog', { method: 'GET' }, preferredBase);

export const requestPlatformAssistantBootstrap = async (tab: string, preferredBase = '') =>
  requestRaw(`/api/platform-assistant/bootstrap?tab=${encodeURIComponent(String(tab || '').trim())}`, { method: 'GET' }, preferredBase);
