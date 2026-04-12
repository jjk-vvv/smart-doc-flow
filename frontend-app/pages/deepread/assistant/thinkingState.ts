import type { AssistantDialogMessage } from './types';

export type AssistantComposerPhase = 'idle' | 'thinking' | 'generating';

export type AssistantComposerVisualState = {
    phase: AssistantComposerPhase;
    label: string;
};

type DeriveAssistantComposerStateArgs = {
    isLoading: boolean;
    message?: AssistantDialogMessage | null;
};

const IDLE_STATE: AssistantComposerVisualState = {
    phase: 'idle',
    label: '',
};

export const deriveAssistantComposerState = ({
    isLoading,
    message,
}: DeriveAssistantComposerStateArgs): AssistantComposerVisualState => {
    if (message?.role === 'assistant' && message.status === 'streaming') {
        const payload =
            message.payload && typeof message.payload === 'object'
                ? message.payload
                : {};
        const contentText = String(message.content || '').trim();
        const uiState = String(payload.ui_state || '').trim().toLowerCase();

        if (contentText || uiState === 'answering' || uiState === 'finalizing') {
            return {
                phase: 'generating',
                label: 'Generating...',
            };
        }

        return {
            phase: 'thinking',
            label: 'Thinking...',
        };
    }

    if (isLoading) {
        return {
            phase: 'thinking',
            label: 'Thinking...',
        };
    }

    return IDLE_STATE;
};
