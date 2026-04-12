import type React from 'react';

import {
    buildAssistant1HistoryFromDialog,
    filterAssistantWarnings,
    mergeAssistantFinalAnswer,
    normalizeAssistantDisplayText,
    toAssistantObjectLock,
} from './helpers';
import {
    parseAssistantEnvelopePayload,
    toAssistantActionPreview,
    toAssistantActionPreviewFromAssistant1,
    toAssistantCitations,
    toAssistantCitationsFromEvidenceBundle,
    toAssistantToolEvent,
} from './streamProtocol';
import type {
    AssistantActionPreview,
    AssistantCitation,
    AssistantDialogMessage,
    AssistantObjectLock,
    AssistantToolEvent,
} from './types';

type UseAssistantStreamArgs = {
    assistantQueryLoading: boolean;
    assistantInput: string;
    assistantDialog: AssistantDialogMessage[];
    assistantSessionId: string;
    activeAssistantSessionKey: string;
    activeDocFileHash: string;
    assistantExtraContext: Record<string, unknown>;
    extractionJobApiBaseRef: React.MutableRefObject<string>;
    assistantAbortRef: React.MutableRefObject<AbortController | null>;
    fetchExtractWithFallback: (
        path: string,
        init: RequestInit,
        preferredBase: string
    ) => Promise<{ response: Response; usedBase?: string }>;
    resolveExtractBase: () => string;
    readAssistantSessionMap: () => Record<string, string>;
    persistAssistantSessionForFile: (fileHash: string, sessionKey: string) => void;
    resetAssistantCompanionState: (keepLock?: boolean) => void;
    updateAssistantDialogMessage: (
        messageId: string,
        updater: (current: AssistantDialogMessage) => AssistantDialogMessage
    ) => void;
    syncAssistantEvidence: (citations: AssistantCitation[], nextLock?: AssistantObjectLock | null) => void;
    setAssistantDialog: React.Dispatch<React.SetStateAction<AssistantDialogMessage[]>>;
    setAssistantQueryLoading: React.Dispatch<React.SetStateAction<boolean>>;
    setAssistantWarnings: React.Dispatch<React.SetStateAction<string[]>>;
    setAssistantAnswer: React.Dispatch<React.SetStateAction<string>>;
    setAssistantInput: React.Dispatch<React.SetStateAction<string>>;
    setAssistantMessage: React.Dispatch<React.SetStateAction<string>>;
    setAssistantSessionId: React.Dispatch<React.SetStateAction<string>>;
    setAssistantCompanionCitations: React.Dispatch<React.SetStateAction<AssistantCitation[]>>;
    setAssistantCompanionActionPreview: React.Dispatch<React.SetStateAction<AssistantActionPreview | null>>;
    setAssistantCompanionOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setAssistantRuntimeEvents: React.Dispatch<React.SetStateAction<AssistantToolEvent[]>>;
};

export const useAssistantStream = ({
    assistantQueryLoading,
    assistantInput,
    assistantDialog,
    assistantSessionId,
    activeAssistantSessionKey,
    activeDocFileHash,
    assistantExtraContext,
    extractionJobApiBaseRef,
    assistantAbortRef,
    fetchExtractWithFallback,
    resolveExtractBase,
    readAssistantSessionMap,
    persistAssistantSessionForFile,
    resetAssistantCompanionState,
    updateAssistantDialogMessage,
    syncAssistantEvidence,
    setAssistantDialog,
    setAssistantQueryLoading,
    setAssistantWarnings,
    setAssistantAnswer,
    setAssistantInput,
    setAssistantMessage,
    setAssistantSessionId,
    setAssistantCompanionCitations,
    setAssistantCompanionActionPreview,
    setAssistantCompanionOpen,
    setAssistantRuntimeEvents,
}: UseAssistantStreamArgs) => {
    const runAssistantInstruction = async () => {
        if (assistantQueryLoading) {
            assistantAbortRef.current?.abort();
            return;
        }
        const instruction = assistantInput.trim();
        if (!instruction) {
            setAssistantWarnings(["请输入具体问题后再发送。"]);
            return;
        }

        const userDialogMsg: AssistantDialogMessage = {
            id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            role: 'user',
            content: instruction,
            messageType: 'user_message',
            status: 'done',
        };
        const pendingAssistantId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const pendingAssistantMsg: AssistantDialogMessage = {
            id: pendingAssistantId,
            role: 'assistant',
            content: '',
            messageType: 'assistant_text',
            status: 'streaming',
            payload: {},
        };
        setAssistantDialog((prev) => [...prev, userDialogMsg, pendingAssistantMsg]);
        setAssistantQueryLoading(true);
        setAssistantWarnings([]);
        resetAssistantCompanionState(true);
        setAssistantAnswer('');
        setAssistantInput('');

        const controller = new AbortController();
        assistantAbortRef.current = controller;
        const fileHash = activeAssistantSessionKey;
        const restoredSessionId = fileHash ? String(readAssistantSessionMap()[fileHash] || '').trim() : '';
        const assistant1History = buildAssistant1HistoryFromDialog(assistantDialog);
        let streamMessageId = pendingAssistantId;
        let streamedCompanionCitations: AssistantCitation[] = [];
        let streamedActionPreview: AssistantActionPreview | null = null;
        let firstAssistantDeltaAt = 0;
        let pendingDoneEvent: { eventName: string; payload: Record<string, any> } | null = null;
        const MIN_GENERATING_VISIBLE_MS = 320;

        const applyAssistantDone = (eventName: string, payload: Record<string, any>) => {
            const citations = eventName === 'assistant.done'
                ? streamedCompanionCitations
                : toAssistantCitations(payload.citations);
            const actionPreview = eventName === 'assistant.done'
                ? (toAssistantActionPreviewFromAssistant1(payload.action_preview) || streamedActionPreview)
                : toAssistantActionPreview(payload.action_preview);
            const nextLock = toAssistantObjectLock(payload.current_object_lock);
            const nextAnswer = normalizeAssistantDisplayText(payload.final_text || payload.answer || '') || '助手已完成处理。';
            const nextWarnings = filterAssistantWarnings(payload.warnings);
            setAssistantAnswer(nextAnswer);
            setAssistantMessage(nextAnswer);
            setAssistantWarnings((prev) => (nextWarnings.length > 0 ? nextWarnings : prev));
            setAssistantCompanionCitations(citations);
            setAssistantCompanionActionPreview(actionPreview);
            if (actionPreview) {
                setAssistantCompanionOpen(true);
            }
            updateAssistantDialogMessage(streamMessageId, (current) => ({
                ...current,
                content: mergeAssistantFinalAnswer(String(current.content || ''), nextAnswer),
                messageType: 'assistant_text',
                status: 'done',
                payload: {
                    ...(current.payload || {}),
                    route: payload.route,
                    ui_state: 'idle',
                },
            }));
            syncAssistantEvidence(citations, nextLock);
        };

        try {
            const preferredBase = extractionJobApiBaseRef.current || resolveExtractBase();
            const fetchResult = await fetchExtractWithFallback(
                '/extract/assistant1/chat/stream',
                {
                    method: 'POST',
                    headers: {
                        'Accept': 'text/event-stream',
                        'Content-Type': 'application/json',
                    },
                    signal: controller.signal,
                    body: JSON.stringify({
                        message: instruction,
                        session_id: assistantSessionId || restoredSessionId || undefined,
                        file_hash: activeDocFileHash || '',
                        history: assistant1History,
                        top_k: 5,
                        max_steps: 6,
                        extra_context: assistantExtraContext,
                        client_caps: {
                            supports_replace: true,
                        },
                    }),
                },
                preferredBase,
            );
            extractionJobApiBaseRef.current = fetchResult.usedBase || preferredBase;
            const response = fetchResult.response;
            if (!response.ok) {
                const text = await response.text();
                throw new Error(text || '助手处理失败');
            }
            if (!response.body) {
                throw new Error('助手流式响应为空');
            }

            const decoder = new TextDecoder();
            const reader = response.body.getReader();
            let buffer = '';

            const commitSseEvent = (rawData: string) => {
                const { eventName, payload } = parseAssistantEnvelopePayload(rawData);

                if (eventName === 'stream.open' || eventName === 'assistant.start' || eventName === 'assistant_start') {
                    const nextSessionId = String(payload.session_id || '').trim();
                    const nextAssistantId = String(payload.assistant_message_id || '').trim();
                    if (nextSessionId) {
                        setAssistantSessionId(nextSessionId);
                        if (fileHash) {
                            persistAssistantSessionForFile(fileHash, nextSessionId);
                        }
                    }
                    if (nextAssistantId && nextAssistantId !== streamMessageId) {
                        const previousId = streamMessageId;
                        streamMessageId = nextAssistantId;
                        setAssistantDialog((prev) =>
                            prev.map((item) => (item.id === previousId ? { ...item, id: nextAssistantId } : item))
                        );
                    }
                    return;
                }

                if (eventName === 'status') {
                    const nextLabel = String(payload.label || '').trim();
                    const nextDetail = String(payload.detail || '').trim();
                    updateAssistantDialogMessage(streamMessageId, (current) => ({
                        ...current,
                        status: 'streaming',
                        payload: {
                            ...(current.payload || {}),
                            progress_label: nextLabel,
                            progress_detail: nextDetail,
                            progress_code: String(payload.code || '').trim(),
                            ui_state: String(payload.ui_state || '').trim(),
                            thinking_label: String(payload.thinking_label || '').trim(),
                            accent: String(payload.accent || '').trim(),
                        },
                    }));
                    if (nextDetail || nextLabel) {
                        setAssistantMessage(nextDetail || nextLabel);
                    }
                    return;
                }

                if (eventName === 'tool.status' || eventName === 'tool_status') {
                    const toolEvent = toAssistantToolEvent(payload);
                    setAssistantRuntimeEvents((prev) => [...prev, toolEvent].slice(-8));
                    return;
                }

                if (eventName === 'evidence.bundle' || eventName === 'citation_bundle') {
                    const citations = eventName === 'evidence.bundle'
                        ? toAssistantCitationsFromEvidenceBundle(payload.items)
                        : toAssistantCitations(payload.citations);
                    const nextLock = toAssistantObjectLock(payload.current_object_lock);
                    streamedCompanionCitations = citations;
                    setAssistantCompanionCitations(citations);
                    syncAssistantEvidence(citations, nextLock);
                    return;
                }

                if (eventName === 'action.preview' || eventName === 'action_preview') {
                    const preview = eventName === 'action.preview'
                        ? toAssistantActionPreviewFromAssistant1(payload)
                        : toAssistantActionPreview(payload);
                    streamedActionPreview = preview;
                    setAssistantCompanionActionPreview(preview);
                    if (preview) {
                        setAssistantCompanionOpen(true);
                    }
                    return;
                }

                if (eventName === 'warning') {
                    const nextWarning = String(payload.message || '').trim();
                    if (nextWarning) {
                        setAssistantWarnings((prev) => Array.from(new Set([...prev, nextWarning])));
                    }
                    return;
                }

                if (eventName === 'assistant.delta' || eventName === 'assistant_delta') {
                    const deltaText = String(payload.text || '');
                    if (deltaText && firstAssistantDeltaAt <= 0) {
                        firstAssistantDeltaAt = Date.now();
                    }
                    updateAssistantDialogMessage(streamMessageId, (current) => ({
                        ...current,
                        content: normalizeAssistantDisplayText(`${current.content || ''}${deltaText}`),
                        status: 'streaming',
                        payload: {
                            ...(current.payload || {}),
                            progress_label: '',
                            ui_state: String(current.payload?.ui_state || 'answering'),
                        },
                    }));
                    return;
                }

                if (eventName === 'assistant.replace') {
                    const nextText = normalizeAssistantDisplayText(payload.text || '');
                    updateAssistantDialogMessage(streamMessageId, (current) => ({
                        ...current,
                        content: nextText || current.content,
                        status: 'streaming',
                    }));
                    return;
                }

                if (eventName === 'assistant.done' || eventName === 'assistant_done') {
                    if (firstAssistantDeltaAt > 0 && (Date.now() - firstAssistantDeltaAt) < MIN_GENERATING_VISIBLE_MS) {
                        pendingDoneEvent = { eventName, payload: { ...payload } };
                        return;
                    }
                    applyAssistantDone(eventName, payload);
                    return;
                }

                if (eventName === 'error' || eventName === 'assistant_error') {
                    const message = String(payload.message || payload.error || '助手处理失败').trim();
                    throw new Error(message);
                }
            };

            const flushBuffer = () => {
                const normalized = buffer.replace(/\r\n/g, '\n');
                const blocks = normalized.split('\n\n');
                buffer = blocks.pop() || '';
                blocks.forEach((block) => {
                    const lines = block.split('\n').map((line) => line.trimEnd()).filter(Boolean);
                    if (lines.length === 0) return;
                    const dataLines: string[] = [];
                    lines.forEach((line) => {
                        if (line.startsWith('data:')) {
                            dataLines.push(line.slice(5).trim());
                        }
                    });
                    commitSseEvent(dataLines.join('\n'));
                });
            };

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                flushBuffer();
            }
            buffer += decoder.decode();
            flushBuffer();
            if (buffer.trim()) {
                commitSseEvent(buffer.trim());
            }
            if (pendingDoneEvent) {
                const remaining = Math.max(0, MIN_GENERATING_VISIBLE_MS - (Date.now() - firstAssistantDeltaAt));
                if (remaining > 0) {
                    await new Promise<void>((resolve) => window.setTimeout(resolve, remaining));
                }
                applyAssistantDone(pendingDoneEvent.eventName, pendingDoneEvent.payload);
                pendingDoneEvent = null;
            }
        } catch (error) {
            if (controller.signal.aborted) {
                setAssistantWarnings(["本次回答已停止。"]);
                setAssistantDialog((prev) =>
                    prev.flatMap((item) => {
                        if (item.id !== streamMessageId) return [item];
                        if (String(item.content || '').trim()) {
                            return [{ ...item, status: 'done' }];
                        }
                        return [];
                    })
                );
            } else {
                const message = error instanceof Error ? error.message : '助手处理失败';
                setAssistantWarnings([message]);
                const failedAnswer = "助手处理失败，请检查问题后重试。";
                setAssistantAnswer(failedAnswer);
                setAssistantDialog((prev) => {
                    const hasTarget = prev.some((item) => item.id === streamMessageId);
                    if (!hasTarget) {
                        return [
                            ...prev,
                            {
                                id: streamMessageId,
                                role: 'assistant',
                                content: failedAnswer,
                                messageType: 'assistant_text',
                                status: 'error',
                            },
                        ];
                    }
                    return prev.map((item) =>
                        item.id === streamMessageId
                            ? { ...item, content: failedAnswer, messageType: 'assistant_text', status: 'error' }
                            : item
                    );
                });
            }
        } finally {
            assistantAbortRef.current = null;
            setAssistantQueryLoading(false);
        }
    };

    return { runAssistantInstruction };
};
