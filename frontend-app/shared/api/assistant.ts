import { requestRaw } from './client';

export type AssistantChatMessage = {
  role: 'user' | 'assistant';
  content: string;
};

export type AssistantChatRequest = {
  messages: AssistantChatMessage[];
  platformContext?: string;
};

export const requestAssistantChatStream = async (
  payload: AssistantChatRequest,
  signal?: AbortSignal,
  preferredBase = '',
) =>
  requestRaw(
    '/api/chat',
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

export const requestAssistantHealth = async (preferredBase = '') =>
  requestRaw('/api/chat/health', { method: 'GET' }, preferredBase);

