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
    ref_id?: unknown;
    page?: unknown;
    snippet?: unknown;
    locator?: unknown;
};

type AssistantContextLock = {
    lock_type?: unknown;
    lock_quality?: unknown;
    object_id?: unknown;
    label?: unknown;
    page?: unknown;
    ref_id?: unknown;
    table_id?: unknown;
    row_index?: unknown;
    source_row_index?: unknown;
    metadata?: unknown;
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

type CompactTablePayload = {
    headers: string[];
    rows: string[][];
    rowCount: number;
    colCount: number;
};

type StructuredTableRow = {
    row_index: number;
    source_row_index?: number;
    ref_id?: string;
    cells: string[];
};

const toCellText = (value: unknown): string => {
    if (value && typeof value === 'object') {
        const obj = value as Record<string, unknown>;
        return String(obj.text ?? obj.value ?? obj.label ?? '').trim();
    }
    return String(value ?? '').trim();
};

const toStructuredTableRows = (value: unknown): StructuredTableRow[] => {
    const obj = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
    const rowsRaw = Array.isArray(obj.rows) ? obj.rows : [];
    const rows: StructuredTableRow[] = [];

    rowsRaw.forEach((row, rowIndex) => {
        let cells: string[] = [];
        let rowIndexValue = rowIndex + 1;
        let sourceRowIndexValue: number | undefined;
        let rowRefId: string | undefined;

        if (Array.isArray(row)) {
            cells = row.map((cell) => toCellText(cell));
        } else if (row && typeof row === 'object') {
            const rowObj = row as Record<string, unknown>;
            const rowCells = Array.isArray(rowObj.cells)
                ? rowObj.cells
                : Array.isArray(rowObj.values)
                    ? rowObj.values
                    : [];
            cells = rowCells.map((cell) => toCellText(cell));

            const rowIndexRaw = Number(rowObj.row_index);
            if (Number.isFinite(rowIndexRaw) && rowIndexRaw > 0) {
                rowIndexValue = Math.trunc(rowIndexRaw);
            }

            const sourceRowIndexRaw = Number(rowObj.source_row_index);
            if (Number.isFinite(sourceRowIndexRaw) && sourceRowIndexRaw > 0) {
                sourceRowIndexValue = Math.trunc(sourceRowIndexRaw);
            }

            const refId = String(rowObj.ref_id ?? rowObj.row_ref_id ?? '').trim();
            if (refId) {
                rowRefId = refId;
            }
        }

        if (!cells.some((cell) => cell.length > 0)) return;
        rows.push({
            row_index: rowIndexValue,
            source_row_index: sourceRowIndexValue,
            ref_id: rowRefId,
            cells,
        });
    });

    return rows;
};

const toCompactTablePayload = (value: unknown): CompactTablePayload => {
    const obj = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
    const headers = Array.isArray(obj.headers)
        ? obj.headers.map((item) => String(item ?? '').trim()).filter(Boolean)
        : [];
    const rows = Array.isArray(obj.rows)
        ? obj.rows
            .map((row) => (Array.isArray(row) ? row.map((cell) => String(cell ?? '').trim()) : []))
            .filter((row) => row.some((cell) => cell.length > 0))
        : [];
    const rowCountRaw = Number(obj.row_count ?? rows.length);
    const colCountRaw = Number(obj.col_count ?? Math.max(headers.length, ...rows.map((row) => row.length), 0));
    return {
        headers,
        rows,
        rowCount: Number.isFinite(rowCountRaw) && rowCountRaw > 0 ? Math.round(rowCountRaw) : rows.length,
        colCount: Number.isFinite(colCountRaw) && colCountRaw > 0
            ? Math.round(colCountRaw)
            : Math.max(headers.length, ...rows.map((row) => row.length), 0),
    };
};

const scoreCompactTablePayload = (payload: CompactTablePayload): number => {
    const headerCount = payload.headers.length;
    const rowCount = payload.rows.length;
    const colCount = Math.max(payload.colCount, ...payload.rows.map((row) => row.length), headerCount, 0);
    const nonEmptyCellCount = payload.rows.reduce(
        (count, row) => count + row.filter((cell) => String(cell || '').trim().length > 0).length,
        0,
    );
    return (rowCount * 10_000) + (colCount * 100) + (headerCount * 10) + nonEmptyCellCount;
};

const pickBestCompactTablePayload = (...values: unknown[]): CompactTablePayload => {
    let bestPayload = toCompactTablePayload(null);
    let bestScore = -1;
    values.forEach((value) => {
        const candidate = toCompactTablePayload(value);
        const score = scoreCompactTablePayload(candidate);
        if (score > bestScore) {
            bestPayload = candidate;
            bestScore = score;
        }
    });
    return bestPayload;
};

const hasTableLikePayload = (value: unknown): boolean => {
    const compact = toCompactTablePayload(value);
    if (compact.headers.length > 0) return true;
    if (compact.rows.length > 0) return true;
    const structuredRows = toStructuredTableRows(value);
    return structuredRows.length > 0;
};

const getTraceConfidence = (hit: AssistantContextTrace): number => {
    const confidenceRaw = Number((hit as Record<string, unknown>).confidence ?? 0);
    if (!Number.isFinite(confidenceRaw)) return 0;
    return confidenceRaw;
};

const isTableLikeTraceHit = (hit: AssistantContextTrace): boolean => {
    const objectType = String(hit.object_type || '').trim().toLowerCase();
    if (objectType === 'table') return true;

    const locator = hit.locator && typeof hit.locator === 'object'
        ? (hit.locator as Record<string, unknown>)
        : {};
    if (hasTableLikePayload(locator.table_preview)) return true;
    if (hasTableLikePayload(locator.dataframe)) return true;
    return false;
};

const prioritizeTraceHits = <TTrace extends AssistantContextTrace>(traceHits: TTrace[]): TTrace[] => {
    return [...traceHits].sort((a, b) => {
        const aTableLike = isTableLikeTraceHit(a) ? 1 : 0;
        const bTableLike = isTableLikeTraceHit(b) ? 1 : 0;
        if (aTableLike !== bTableLike) return bTableLike - aTableLike;
        return getTraceConfidence(b) - getTraceConfidence(a);
    });
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

    const diagnostics = activeDoc.diagnostics && typeof activeDoc.diagnostics === 'object'
        ? (activeDoc.diagnostics as Record<string, unknown>)
        : {};
    const workbookManifestPath = trimAssistantContextText(diagnostics.xlsx_workbook_manifest_path, 320);
    const workbookManifestUrl = trimAssistantContextText(diagnostics.xlsx_workbook_manifest_url, 320);
    const sheetRowsArtifactVersion = trimAssistantContextText(diagnostics.xlsx_sheet_rows_artifact_version, 64);

    const topFields = fieldItems.slice(0, 12).map((item) => ({
        key: String(item.key || '').trim(),
        label: trimAssistantContextText(item.label, 80),
        value: trimAssistantContextText(item.valueText, 180),
        confidence: Math.round(Math.max(0, Math.min(1, Number(item.confidence || 0))) * 100),
        page: item.pageNumber ?? undefined,
    }));

    const prioritizedTraceHits = prioritizeTraceHits(traceHits);

    const tracePreview = prioritizedTraceHits.slice(0, 8).map((hit) => ({
        object_type: String(hit.object_type || '').trim() || undefined,
        object_id: String(hit.object_id || '').trim() || undefined,
        ref_id: String(hit.ref_id || '').trim() || undefined,
        page: typeof hit.page === 'number' ? hit.page : undefined,
        snippet: trimAssistantContextText(hit.snippet, 180) || undefined,
    }));

    const tableColumnHeaders: string[] = [];
    const tableRowSamples: Array<Record<string, unknown>> = [];
    for (const hit of prioritizedTraceHits.slice(0, 12)) {
        const locator = (hit.locator ?? {}) as Record<string, unknown>;
        const tablePreview = (locator.table_preview ?? {}) as Record<string, unknown>;
        const dataframePayload = locator.dataframe;
        const headers = Array.isArray(tablePreview.headers)
            ? (tablePreview.headers as unknown[]).map((h) => String(h || '').trim()).filter(Boolean)
            : [];
        for (const h of headers) {
            if (!tableColumnHeaders.includes(h)) tableColumnHeaders.push(h);
            if (tableColumnHeaders.length >= 20) break;
        }

        const compactTable = pickBestCompactTablePayload(dataframePayload, tablePreview);
        const structuredRows = (() => {
            const dataframeRows = toStructuredTableRows(dataframePayload);
            if (dataframeRows.length > 0) return dataframeRows;
            return toStructuredTableRows(tablePreview);
        })();
        const effectiveHeaders = compactTable.headers.length > 0 ? compactTable.headers : headers;
        if (effectiveHeaders.length === 0) continue;
        if (structuredRows.length === 0 && compactTable.rows.length === 0) continue;

        const sampledRows = (structuredRows.length > 0
            ? structuredRows.slice(0, 20).map((row) => ({
                row_index: row.row_index,
                source_row_index: row.source_row_index ?? row.row_index,
                ref_id: row.ref_id || undefined,
                cells: row.cells.slice(0, 24),
            }))
            : compactTable.rows.slice(0, 20).map((cells, rowIndex) => ({
                row_index: rowIndex + 1,
                source_row_index: rowIndex + 1,
                cells: cells.slice(0, 24),
            })));
        tableRowSamples.push({
            object_type: String(hit.object_type || '').trim() || undefined,
            table_id: String(hit.object_id || '').trim() || undefined,
            ref_id: String(hit.ref_id || '').trim() || undefined,
            page: typeof hit.page === 'number' ? hit.page : undefined,
            headers: effectiveHeaders.slice(0, 24),
            rows: sampledRows,
            row_count: compactTable.rowCount > 0 ? compactTable.rowCount : structuredRows.length,
            col_count: compactTable.colCount > 0
                ? compactTable.colCount
                : Math.max(effectiveHeaders.length, ...sampledRows.map((row) => row.cells.length), 0),
        });
        if (tableRowSamples.length >= 4) break;
    }

    const figureKeyPoints: string[] = [];
    for (const hit of prioritizedTraceHits.slice(0, 12)) {
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
            diagnostics: {
                xlsx_workbook_manifest_path: workbookManifestPath || undefined,
                xlsx_workbook_manifest_url: workbookManifestUrl || undefined,
                xlsx_sheet_rows_artifact_version: sheetRowsArtifactVersion || undefined,
            },
            table_column_headers: tableColumnHeaders.length > 0 ? tableColumnHeaders : undefined,
            table_row_samples: tableRowSamples.length > 0 ? tableRowSamples : undefined,
            figure_key_points: figureKeyPoints.length > 0 ? figureKeyPoints : undefined,
            current_locked_object: currentObjectLock
                ? {
                      lock_type: currentObjectLock.lock_type,
                      lock_quality: currentObjectLock.lock_quality,
                      object_id: String(currentObjectLock.object_id || '').trim() || undefined,
                      label: String(currentObjectLock.label || '').trim() || undefined,
                      page: (currentObjectLock.page as number | undefined) ?? undefined,
                      ref_id: String(currentObjectLock.ref_id || '').trim() || undefined,
                      table_id: (currentObjectLock.table_id as string | undefined) ?? undefined,
                      row_index: (currentObjectLock.row_index as number | undefined) ?? undefined,
                      source_row_index: (currentObjectLock.source_row_index as number | undefined) ?? undefined,
                      metadata:
                          currentObjectLock.metadata && typeof currentObjectLock.metadata === 'object'
                              ? (currentObjectLock.metadata as Record<string, unknown>)
                              : undefined,
                  }
                : undefined,
        },
    };
};
