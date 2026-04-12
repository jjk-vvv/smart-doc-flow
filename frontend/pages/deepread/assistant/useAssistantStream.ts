import type React from 'react';

import {
    buildAssistant1HistoryFromDialog,
    mergeAssistantFinalAnswer,
    normalizeAssistantDisplayText,
    normalizeAssistantWarningMessage,
    toAssistantObjectLock,
    toAssistantPayloadRecord,
    toAssistantVisibleWarnings,
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
    AssistantSessionMessagePayload,
    AssistantSessionResponse,
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
    const recoverAssistantTurnFromSession = async ({
        sessionId,
        instruction,
        preferredBase,
        expectedRunId,
    }: {
        sessionId: string;
        instruction: string;
        preferredBase: string;
        expectedRunId: string;
    }): Promise<{
        content: string;
        payload: Record<string, unknown>;
        currentObjectLock: Record<string, unknown> | null;
    } | null> => {
        const normalizedSessionId = String(sessionId || '').trim();
        if (!normalizedSessionId) return null;
        try {
            const fetchResult = await fetchExtractWithFallback(
                `/extract/assistant1/sessions/${encodeURIComponent(normalizedSessionId)}?limit=40`,
                {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                    },
                },
                preferredBase,
            );
            extractionJobApiBaseRef.current = fetchResult.usedBase || preferredBase;
            const response = fetchResult.response;
            if (!response.ok) {
                return null;
            }
            const data = await response.json() as AssistantSessionResponse & {
                current_object_lock?: Record<string, unknown> | null;
            };
            const messages = Array.isArray(data.messages)
                ? data.messages.filter((item): item is AssistantSessionMessagePayload => Boolean(item && typeof item === 'object'))
                : [];
            if (messages.length === 0) return null;

            const normalizedInstruction = normalizeAssistantDisplayText(instruction);
            let matchedUserMessage: AssistantSessionMessagePayload | null = null;
            for (let index = messages.length - 1; index >= 0; index -= 1) {
                const current = messages[index];
                if (String(current.role || '').trim().toLowerCase() !== 'user') continue;
                if (normalizeAssistantDisplayText(current.content) !== normalizedInstruction) continue;
                matchedUserMessage = current;
                break;
            }
            if (!matchedUserMessage) return null;

            const matchesRunId = (payload: Record<string, unknown>): boolean => {
                const payloadRunId = String(payload.run_id || '').trim();
                if (!expectedRunId) return true;
                return !payloadRunId || payloadRunId === expectedRunId;
            };

            let matchedAssistantMessage: AssistantSessionMessagePayload | null = null;
            for (let index = messages.length - 1; index >= 0; index -= 1) {
                const current = messages[index];
                if (String(current.role || '').trim().toLowerCase() !== 'assistant') continue;
                const payload = toAssistantPayloadRecord(current.payload);
                if (String(payload.user_message_id || '').trim() !== String(matchedUserMessage.message_id || '').trim()) continue;
                if (!matchesRunId(payload)) continue;
                if (!normalizeAssistantDisplayText(current.content)) continue;
                matchedAssistantMessage = current;
                break;
            }

            if (!matchedAssistantMessage) {
                const userIndex = messages.findIndex((item) => item.message_id === matchedUserMessage?.message_id);
                if (userIndex >= 0) {
                    for (let index = userIndex + 1; index < messages.length; index += 1) {
                        const current = messages[index];
                        if (String(current.role || '').trim().toLowerCase() !== 'assistant') continue;
                        const payload = toAssistantPayloadRecord(current.payload);
                        if (!matchesRunId(payload)) continue;
                        if (!normalizeAssistantDisplayText(current.content)) continue;
                        matchedAssistantMessage = current;
                        break;
                    }
                }
            }

            if (!matchedAssistantMessage) return null;
            return {
                content: normalizeAssistantDisplayText(matchedAssistantMessage.content),
                payload: toAssistantPayloadRecord(matchedAssistantMessage.payload),
                currentObjectLock:
                    data.current_object_lock && typeof data.current_object_lock === 'object'
                        ? data.current_object_lock
                        : null,
            };
        } catch {
            return null;
        }
    };

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
        let currentSessionId = String(assistantSessionId || restoredSessionId || '').trim();
        const assistant1History = buildAssistant1HistoryFromDialog(assistantDialog);
        const requestedResumeRunId =
            typeof assistantExtraContext.resume_run_id === 'string'
                ? String(assistantExtraContext.resume_run_id || '').trim()
                : '';
        const requestedAfterSeqRaw =
            typeof assistantExtraContext.after_seq === 'number'
                ? assistantExtraContext.after_seq
                : Number(assistantExtraContext.after_seq ?? 0);
        const requestedAfterSeq = Number.isFinite(requestedAfterSeqRaw)
            ? Math.max(0, Math.trunc(requestedAfterSeqRaw))
            : 0;
        let streamMessageId = pendingAssistantId;
        let streamedCompanionCitations: AssistantCitation[] = [];
        let streamedActionPreview: AssistantActionPreview | null = null;
        let latestAssistantContent = '';
        let firstAssistantDeltaAt = 0;
        let pendingDoneEvent: { eventName: string; payload: Record<string, any> } | null = null;
        let streamRunId = '';
        let lastStreamSeq = 0;
        const MIN_GENERATING_VISIBLE_MS = 320;
        const applyStreamEnvelopeMetadata = (payload: Record<string, unknown> = {}) => ({
            ...payload,
            ...(streamRunId ? { stream_run_id: streamRunId } : {}),
            ...(lastStreamSeq > 0 ? { last_stream_seq: lastStreamSeq } : {}),
        });

        const applyAssistantDone = (eventName: string, payload: Record<string, any>) => {
            const citations = eventName === 'assistant.done'
                ? streamedCompanionCitations
                : toAssistantCitations(payload.citations);
            const actionPreview = eventName === 'assistant.done'
                ? (toAssistantActionPreviewFromAssistant1(payload.action_preview) || streamedActionPreview)
                : toAssistantActionPreview(payload.action_preview);
            const nextLock = toAssistantObjectLock(payload.current_object_lock);
            const nextAnswer = normalizeAssistantDisplayText(payload.final_text || payload.answer || '') || '助手已完成处理。';
            const nextWarnings = toAssistantVisibleWarnings(payload);
            const nextRequiresFollowup = Boolean(payload.requires_followup);
            const nextFinishReason = String(payload.finish_reason || '').trim();
            latestAssistantContent = nextAnswer;
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
                payload: applyStreamEnvelopeMetadata({
                    ...(current.payload || {}),
                    route: payload.route,
                    ui_state: nextRequiresFollowup ? 'awaiting_input' : 'idle',
                    finish_reason: nextFinishReason,
                    requires_followup: nextRequiresFollowup,
                }),
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
                        session_id: currentSessionId || undefined,
                        file_hash: activeDocFileHash || '',
                        history: assistant1History,
                        top_k: 5,
                        max_steps: 6,
                        resume_run_id: requestedResumeRunId || undefined,
                        after_seq: requestedResumeRunId ? requestedAfterSeq : undefined,
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
                const { eventName, payload, envelope } = parseAssistantEnvelopePayload(rawData);
                if (envelope?.run_id) {
                    streamRunId = String(envelope.run_id || '').trim();
                }
                if (typeof envelope?.seq === 'number' && Number.isFinite(envelope.seq)) {
                    lastStreamSeq = Math.max(lastStreamSeq, envelope.seq);
                }

                if (eventName === 'stream.open' || eventName === 'assistant.start' || eventName === 'assistant_start') {
                    const nextSessionId = String(payload.session_id || '').trim();
                    const nextAssistantId = String(payload.assistant_message_id || '').trim();
                    if (nextSessionId) {
                        currentSessionId = nextSessionId;
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
                    updateAssistantDialogMessage(streamMessageId, (current) => ({
                        ...current,
                        payload: applyStreamEnvelopeMetadata(current.payload || {}),
                    }));
                    return;
                }

                if (eventName === 'status') {
                    const nextLabel = String(payload.label || '').trim();
                    const nextDetail = String(payload.detail || '').trim();
                    updateAssistantDialogMessage(streamMessageId, (current) => ({
                        ...current,
                        status: 'streaming',
                        payload: applyStreamEnvelopeMetadata({
                            ...(current.payload || {}),
                            progress_label: nextLabel,
                            progress_detail: nextDetail,
                            progress_code: String(payload.code || '').trim(),
                            ui_state: String(payload.ui_state || '').trim(),
                            thinking_label: String(payload.thinking_label || '').trim(),
                            accent: String(payload.accent || '').trim(),
                        }),
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
                    const nextWarning = normalizeAssistantWarningMessage(payload.message || payload.code || '');
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
                    latestAssistantContent = normalizeAssistantDisplayText(`${latestAssistantContent || ''}${deltaText}`);
                    updateAssistantDialogMessage(streamMessageId, (current) => ({
                        ...current,
                        content: normalizeAssistantDisplayText(`${current.content || ''}${deltaText}`),
                        status: 'streaming',
                        payload: applyStreamEnvelopeMetadata({
                            ...(current.payload || {}),
                            progress_label: '',
                            ui_state: String(current.payload?.ui_state || 'answering'),
                        }),
                    }));
                    return;
                }

                if (eventName === 'assistant.replace') {
                    const nextText = normalizeAssistantDisplayText(payload.text || '');
                    latestAssistantContent = nextText || latestAssistantContent;
                    updateAssistantDialogMessage(streamMessageId, (current) => ({
                        ...current,
                        content: nextText || current.content,
                        status: 'streaming',
                        payload: applyStreamEnvelopeMetadata(current.payload || {}),
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
                const recoverySessionId = String(currentSessionId || '').trim();
                const preferredBase = extractionJobApiBaseRef.current || resolveExtractBase();
                const recoveredTurn = await recoverAssistantTurnFromSession({
                    sessionId: recoverySessionId,
                    instruction,
                    preferredBase,
                    expectedRunId: streamRunId,
                });

                if (recoveredTurn?.content) {
                    const recoveredAnswer = normalizeAssistantDisplayText(recoveredTurn.content);
                    const recoveredWarnings = toAssistantVisibleWarnings(recoveredTurn.payload);
                    const recoveredRequiresFollowup = Boolean(recoveredTurn.payload.requires_followup);
                    const recoveredFinishReason = String(recoveredTurn.payload.finish_reason || '').trim();
                    const recoveredActionPreview =
                        toAssistantActionPreviewFromAssistant1(recoveredTurn.payload.action_preview)
                        || toAssistantActionPreview(recoveredTurn.payload.action_preview);
                    const recoveredLock = toAssistantObjectLock(recoveredTurn.currentObjectLock);

                    latestAssistantContent = recoveredAnswer;
                    setAssistantWarnings((prev) => {
                        const next = recoveredWarnings.length > 0
                            ? recoveredWarnings
                            : [...prev, '连接中断后，已从会话记录中恢复本轮回答。'];
                        return Array.from(new Set(next.filter(Boolean)));
                    });
                    setAssistantAnswer(recoveredAnswer);
                    setAssistantMessage(recoveredAnswer);
                    if (recoveredActionPreview) {
                        setAssistantCompanionActionPreview(recoveredActionPreview);
                        setAssistantCompanionOpen(true);
                    }
                    updateAssistantDialogMessage(streamMessageId, (current) => ({
                        ...current,
                        content: mergeAssistantFinalAnswer(String(current.content || ''), recoveredAnswer),
                        messageType: 'assistant_text',
                        status: 'done',
                        payload: applyStreamEnvelopeMetadata({
                            ...(current.payload || {}),
                            finish_reason: recoveredFinishReason || 'session_recovered',
                            requires_followup: recoveredRequiresFollowup,
                            ui_state: recoveredRequiresFollowup ? 'awaiting_input' : 'idle',
                            recovered_from_session: true,
                        }),
                    }));
                    syncAssistantEvidence(streamedCompanionCitations, recoveredLock);
                    return;
                }

                const hasPartialAnswer = Boolean(normalizeAssistantDisplayText(latestAssistantContent));
                const failedAnswer = hasPartialAnswer
                    ? normalizeAssistantDisplayText(latestAssistantContent)
                    : "助手处理失败，请检查问题后重试。";
                const nextWarnings = hasPartialAnswer
                    ? [message, '连接中断，已保留本轮已生成内容。']
                    : [message];
                setAssistantWarnings(Array.from(new Set(nextWarnings.filter(Boolean))));
                setAssistantAnswer(failedAnswer);
                setAssistantMessage(failedAnswer);
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
                                status: hasPartialAnswer ? 'done' : 'error',
                                payload: applyStreamEnvelopeMetadata({
                                    recoverable_error: true,
                                }),
                            },
                        ];
                    }
                    return prev.map((item) =>
                        item.id === streamMessageId
                            ? {
                                ...item,
                                content: failedAnswer,
                                messageType: 'assistant_text',
                                status: hasPartialAnswer ? 'done' : 'error',
                                payload: applyStreamEnvelopeMetadata({
                                    ...(item.payload || {}),
                                    recoverable_error: true,
                                }),
                            }
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
