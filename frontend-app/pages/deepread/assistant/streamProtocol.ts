import {
  toAssistantActionPreview,
  toAssistantCitations,
  toAssistantObjectLock,
  toAssistantPayloadRecord,
  toAssistantToolEvents,
  filterAssistantWarnings,
  humanizeAssistantToolEvent,
} from './helpers';
import type {
  AssistantActionPreview,
  AssistantCitation,
  AssistantCompanionState,
  AssistantToolEvent,
  Assistant1SseEnvelope,
} from './types';

export const toAssistant1Envelope = (value: unknown): Assistant1SseEnvelope | null => {
    if (!value || typeof value !== 'object') return null;
    const record = value as Record<string, unknown>;
    const type = String(record.type || '').trim();
    if (!type) return null;
    const payload = record.payload && typeof record.payload === 'object'
        ? record.payload as Record<string, unknown>
        : undefined;
    return {
        type,
        payload,
        seq: typeof record.seq === 'number' ? record.seq : undefined,
        run_id: typeof record.run_id === 'string' ? record.run_id : undefined,
        turn_id: typeof record.turn_id === 'string' ? record.turn_id : undefined,
        visibility: typeof record.visibility === 'string' ? record.visibility : undefined,
        phase: typeof record.phase === 'string' ? record.phase : undefined,
    };
};

export const toAssistantActionPreviewFromAssistant1 = (value: unknown): AssistantActionPreview | null => {
    if (!value || typeof value !== 'object') return null;
    const payload = value as Record<string, unknown>;
    const title = String(payload.title || '').trim();
    const actionKind = String(payload.action_kind || payload.action_type || '').trim();
    const confirmationToken = String(payload.confirmation_token || payload.action_id || '').trim();
    const sqlPreview = String(payload.sql_preview || '').trim();
    const notes = String(payload.notes || '').trim();
    const summary = String(payload.summary || payload.description || '').trim();
    const target = String(payload.target || actionKind || '').trim();
    if (!title && !summary && !sqlPreview) {
        return null;
    }
    return {
        action_id: confirmationToken || `assistant1-action-${Date.now()}`,
        action_type: actionKind || 'sql_preview',
        title: title || '动作预览',
        description: summary || notes,
        target,
        requires_confirmation: Boolean(payload.requires_confirmation ?? true),
        payload: {
            ...payload,
            preview_status: 'ready',
            operation_type: actionKind.includes('sql') ? 'alter' : actionKind,
            sql_ready: Boolean(sqlPreview),
            sql_preview_text: sqlPreview,
            confirmation_checklist: notes ? [notes] : [],
        },
    };
};

export const toAssistantCitationsFromEvidenceBundle = (value: unknown): AssistantCitation[] => {
    if (!Array.isArray(value)) return [];
    return value
        .filter((item) => item && typeof item === 'object')
        .map((item, index) => {
            const record = item as Record<string, unknown>;
            const unitType = String(record.unit_type || record.kind || '').trim().toLowerCase();
            const citationType =
                unitType.includes('table')
                    ? 'table'
                    : unitType.includes('figure') || unitType.includes('image')
                        ? 'figure'
                        : 'field';
            const snippet = String(record.snippet || record.content_preview || '').trim();
            const title = String(record.title || record.label || '').trim();
            const objectId = String(record.unit_id || record.object_id || `evidence-${index + 1}`).trim();
            const pageStart = Number(record.page_start ?? record.page);
            return {
                citation_type: citationType,
                title: title || objectId || '引用依据',
                page: Number.isFinite(pageStart) && pageStart > 0 ? pageStart : null,
                ref_id: typeof record.ref_id === 'string' ? record.ref_id : null,
                object_id: objectId,
                snippet,
                payload: {
                    ...record,
                    key_points: snippet ? [snippet] : [],
                },
            };
        })
        .filter((item) => item.object_id || item.title || item.snippet);
};

export const toAssistantCompanionState = (payloadRaw: unknown): AssistantCompanionState => {
    const payload = toAssistantPayloadRecord(payloadRaw);
    return {
        citations: toAssistantCitations(payload.citations),
        actionPreview: toAssistantActionPreview(payload.action_preview),
        toolEvents: toAssistantToolEvents(payload.tool_events),
    };
};

export const toAssistantVisibleWarnings = (payloadRaw: unknown): string[] => {
    const payload = toAssistantPayloadRecord(payloadRaw);
    const userVisible = payload.user_visible_warnings;
    return filterAssistantWarnings(Array.isArray(userVisible) ? userVisible : payload.warnings);
};

export const toAssistantToolEvent = (payload: Record<string, unknown>): AssistantToolEvent => ({
    tool_name: String(payload.tool_name || '').trim(),
    status: String(payload.status || '').trim(),
    message: String(payload.message || '').trim(),
    detail: String(payload.detail || payload.summary || '').trim(),
    human_label: humanizeAssistantToolEvent(payload),
});

export const parseAssistantEnvelopePayload = (rawData: string): {
    eventName: string;
    payload: Record<string, unknown>;
    envelope: Assistant1SseEnvelope | null;
} => {
    let normalizedEvent = 'message';
    let parsed: Record<string, unknown> = {};
    if (rawData.trim()) {
        try {
            const value = JSON.parse(rawData);
            parsed = value && typeof value === 'object' ? value as Record<string, unknown> : { value };
        } catch {
            parsed = { raw: rawData };
        }
    }
    const envelope = toAssistant1Envelope(parsed);
    if (envelope) {
        normalizedEvent = String(envelope.type || normalizedEvent).trim() || normalizedEvent;
        parsed = envelope.payload || {};
    }
    return {
        eventName: normalizedEvent,
        payload: parsed,
        envelope,
    };
};

export {
    toAssistantActionPreview,
    toAssistantCitations,
    toAssistantObjectLock,
};
