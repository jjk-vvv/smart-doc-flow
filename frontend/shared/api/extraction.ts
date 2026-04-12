import { requestRaw, resolveApiBase } from './client';

export type ExtractionApiFetchResult = {
  response: Response;
  usedBase: string;
  url: string;
};

export const resolveExtractBase = (preferredBase = ''): string => resolveApiBase(preferredBase);

export const toAbsoluteExtractUrl = (value: string, preferredBase = ''): string => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (/^https?:\/\//i.test(raw)) return raw;
  const normalized = raw.startsWith('/') ? raw : `/${raw}`;
  const usedBase = resolveExtractBase(preferredBase);
  return usedBase ? `${usedBase}${normalized}` : normalized;
};

const requestExtraction = (
  path: string,
  init: RequestInit = {},
  preferredBase = '',
): Promise<ExtractionApiFetchResult> => requestRaw(path, init, preferredBase);

export const requestExtractionJobCreateWithRetry = async (
  files: File[],
  schemaJson: string,
  maxAttempts = 2,
  preferredBase = '',
): Promise<ExtractionApiFetchResult> => {
  let lastError: unknown = null;
  const attempts = Math.max(1, Number(maxAttempts) || 1);

  for (let index = 0; index < attempts; index += 1) {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    formData.append('schema', schemaJson);
    try {
      return await requestExtraction(
        '/extract/jobs/create',
        {
          method: 'POST',
          body: formData,
        },
        preferredBase,
      );
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Failed to create extraction job');
};

export const requestExtractionJobStatus = async (
  jobId: string,
  preferredBase = '',
  includeDocuments = false,
): Promise<ExtractionApiFetchResult> => {
  const query = new URLSearchParams();
  if (includeDocuments) query.set('include_documents', 'true');
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return requestExtraction(
    `/extract/jobs/status/${encodeURIComponent(jobId)}${suffix}`,
    { method: 'GET' },
    preferredBase,
  );
};

export const requestExtractionSummary = async (
  payload: Record<string, unknown>,
  preferredBase = '',
): Promise<ExtractionApiFetchResult> =>
  requestExtraction(
    '/extract/summarize',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    preferredBase,
  );

export const requestTraceLocate = async (
  payload: Record<string, unknown>,
  preferredBase = '',
): Promise<ExtractionApiFetchResult> =>
  requestExtraction(
    '/extract/trace/locate',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    preferredBase,
  );

export const requestOfficePreviewStart = async (
  file: File,
  preferredBase = '',
): Promise<ExtractionApiFetchResult> => {
  const formData = new FormData();
  formData.append('file', file);
  return requestExtraction(
    '/extract/preview/office/start',
    {
      method: 'POST',
      body: formData,
    },
    preferredBase,
  );
};

export const requestOfficePreviewStatus = async (
  jobId: string,
  preferredBase = '',
): Promise<ExtractionApiFetchResult> =>
  requestExtraction(
    `/extract/preview/office/status/${encodeURIComponent(jobId)}`,
    { method: 'GET' },
    preferredBase,
  );

export const requestAssistant1ChatStream = async (
  payload: Record<string, unknown>,
  signal?: AbortSignal,
  preferredBase = '',
): Promise<ExtractionApiFetchResult> =>
  requestExtraction(
    '/extract/assistant1/chat/stream',
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

