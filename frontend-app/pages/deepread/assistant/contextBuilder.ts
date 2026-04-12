type AssistantContextDoc = {
    file_name?: unknown;
    file_hash?: unknown;
    cached?: unknown;
    soft_warnings?: unknown;
};

type AssistantContextField = {
    key?: unknown;
    label?: unknown;
    valueText?: unknown;
    confidence?: unknown;
    pageNumber?: unknown;
    refId?: unknown;
};

type AssistantContextTrace = {
    object_type?: unknown;
    object_id?: unknown;
    page?: unknown;
    snippet?: unknown;
    locator?: unknown;
};

type AssistantContextLock = {
    lock_type?: unknown;
    label?: unknown;
    page?: unknown;
    table_id?: unknown;
    row_index?: unknown;
};

type BuildAssistantExtraContextArgs<
    TDoc extends AssistantContextDoc,
    TField extends AssistantContextField,
    TTrace extends AssistantContextTrace,
> = {
    activeDoc: TDoc | null;
    activeDocIndex: number;
    documents: TDoc[];
    fieldItems: TField[];
    traceHits: TTrace[];
    activeSummaryText: string;
    smartUnitTab: string;
    currentObjectLock?: AssistantContextLock | null;
};

export const trimAssistantContextText = (value: unknown, maxLength = 220): string => {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
};

export const buildAssistantExtraContext = <
    TDoc extends AssistantContextDoc,
    TField extends AssistantContextField,
    TTrace extends AssistantContextTrace,
>({
    activeDoc,
    activeDocIndex,
    documents,
    fieldItems,
    traceHits,
    activeSummaryText,
    smartUnitTab,
    currentObjectLock,
}: BuildAssistantExtraContextArgs<TDoc, TField, TTrace>): Record<string, unknown> => {
    if (!activeDoc) return {};

    const topFields = fieldItems.slice(0, 12).map((item) => ({
        key: String(item.key || '').trim(),
        label: trimAssistantContextText(item.label, 80),
        value: trimAssistantContextText(item.valueText, 180),
        confidence: Math.round(Math.max(0, Math.min(1, Number(item.confidence || 0))) * 100),
        page: item.pageNumber ?? undefined,
    }));

    const tracePreview = traceHits.slice(0, 8).map((hit) => ({
        object_type: String(hit.object_type || '').trim() || undefined,
        object_id: String(hit.object_id || '').trim() || undefined,
        page: typeof hit.page === 'number' ? hit.page : undefined,
        snippet: trimAssistantContextText(hit.snippet, 180) || undefined,
    }));

    const tableColumnHeaders: string[] = [];
    for (const hit of traceHits.slice(0, 8)) {
        const locator = (hit.locator ?? {}) as Record<string, unknown>;
        const tablePreview = (locator.table_preview ?? {}) as Record<string, unknown>;
        const headers = Array.isArray(tablePreview.headers)
            ? (tablePreview.headers as unknown[]).map((h) => String(h || '').trim()).filter(Boolean)
            : [];
        for (const h of headers) {
            if (!tableColumnHeaders.includes(h)) tableColumnHeaders.push(h);
            if (tableColumnHeaders.length >= 20) break;
        }
    }

    const figureKeyPoints: string[] = [];
    for (const hit of traceHits.slice(0, 8)) {
        if (String(hit.object_type || '').toLowerCase() !== 'figure') continue;
        const locator = (hit.locator ?? {}) as Record<string, unknown>;
        const kp = Array.isArray(locator.key_points)
            ? (locator.key_points as unknown[]).map((x) => String(x ?? '').trim()).filter(Boolean).slice(0, 3)
            : [];
        const tb = Array.isArray(locator.text_blocks)
            ? (locator.text_blocks as unknown[]).map((x) => String(x ?? '').trim()).filter(Boolean).slice(0, 2)
            : [];
        for (const pt of kp.length > 0 ? kp : tb) {
            figureKeyPoints.push(pt);
            if (figureKeyPoints.length >= 6) break;
        }
    }

    return {
        workspace: {
            documents_count: documents.length,
            active_document_index: activeDocIndex,
            active_panel: smartUnitTab,
        },
        current_document: {
            file_name: String(activeDoc.file_name || '').trim(),
            file_hash: String(activeDoc.file_hash || '').trim(),
            cached: Boolean(activeDoc.cached),
            field_count: fieldItems.length,
            trace_hit_count: traceHits.length,
            summary: trimAssistantContextText(activeSummaryText, 600),
            top_fields: topFields,
            trace_preview: tracePreview.filter((item) => item.object_type || item.snippet),
            soft_warnings: Array.isArray(activeDoc.soft_warnings)
                ? activeDoc.soft_warnings
                    .slice(0, 6)
                    .map((item) => trimAssistantContextText(item, 120))
                    .filter(Boolean)
                : [],
            table_column_headers: tableColumnHeaders.length > 0 ? tableColumnHeaders : undefined,
            figure_key_points: figureKeyPoints.length > 0 ? figureKeyPoints : undefined,
            current_locked_object: currentObjectLock
                ? {
                      lock_type: currentObjectLock.lock_type,
                      label: String(currentObjectLock.label || '').trim() || undefined,
                      page: (currentObjectLock.page as number | undefined) ?? undefined,
                      table_id: (currentObjectLock.table_id as string | undefined) ?? undefined,
                      row_index: (currentObjectLock.row_index as number | undefined) ?? undefined,
                  }
                : undefined,
        },
    };
};
