export type AssistantCitation = {
    citation_type: string;
    title: string;
    page?: number | null;
    ref_id?: string | null;
    object_id: string;
    snippet: string;
    payload: Record<string, unknown>;
};

export type AssistantObjectLock = {
    lock_type: string;
    lock_quality?: string;
    object_id: string;
    label: string;
    page?: number | null;
    ref_id?: string | null;
    table_id?: string | null;
    row_index?: number | null;
    source_row_index?: number | null;
    metadata?: Record<string, unknown>;
};

export type AssistantActionPreview = {
    action_id: string;
    action_type: string;
    title: string;
    description: string;
    target: string;
    requires_confirmation: boolean;
    payload: Record<string, unknown>;
};

export type Assistant1HistoryMessage = {
    role: 'system' | 'user' | 'assistant' | 'developer';
    content: string;
};

export type Assistant1SseEnvelope = {
    type?: string;
    payload?: Record<string, unknown>;
    seq?: number;
    run_id?: string;
    turn_id?: string;
    visibility?: string;
    phase?: string;
};

export type AssistantToolEvent = {
    tool_name: string;
    status: string;
    message: string;
    detail: string;
    human_label: string;
};

export type AssistantSessionMessagePayload = {
    message_id: string;
    role: string;
    message_type: string;
    content: string;
    payload: Record<string, unknown>;
    created_at: string;
};

export type AssistantSessionResponse = {
    session_id: string;
    summary_used: string;
    current_object_lock?: AssistantObjectLock | null;
    messages: AssistantSessionMessagePayload[];
};

export type AssistantDialogMessage = {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    messageType?: 'user_message' | 'assistant_text' | 'tool_status' | 'action_preview' | 'system_notice';
    citations?: AssistantCitation[];
    actionPreview?: AssistantActionPreview | null;
    toolEvents?: AssistantToolEvent[];
    status?: 'streaming' | 'done' | 'error';
    payload?: Record<string, unknown>;
};

export type AssistantCompanionState = {
    citations: AssistantCitation[];
    actionPreview: AssistantActionPreview | null;
    toolEvents: AssistantToolEvent[];
};

export const EMPTY_ASSISTANT_COMPANION_STATE: AssistantCompanionState = {
    citations: [],
    actionPreview: null,
    toolEvents: [],
};
