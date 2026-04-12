import { requestRaw, resolveApiBase } from './client';

export type ExtractionApiFetchResult = {
  response: Response;
  usedBase: string;
  url: string;
};

export type ExtractionTraceHitLike = {
  artifact_url?: string | null;
  artifact_path?: string | null;
  locator?: Record<string, unknown> | null;
};

const normalizeExtractBase = (value = ''): string => {
  const normalized = resolveApiBase(value);
  if (!normalized) return '';
  return normalized.endsWith('/extract') ? normalized.slice(0, -8) : normalized;
};

const getViteExtractBase = (): string => {
  try {
    const env = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
    return String(env?.VITE_MODULE2_API_BASE || env?.VITE_EXTRACT_API_BASE || env?.VITE_BACKEND_ENTRY_URL || '').trim();
  } catch {
    return '';
  }
};

const getLocalStorageExtractBase = (): string => {
  if (typeof window === 'undefined') return '';
  try {
    return String(window.localStorage.getItem('module2_api_base_override') || '').trim();
  } catch {
    return '';
  }
};

const buildExtractBaseCandidates = (preferredBase = ''): string[] => {
  const candidates: string[] = [];
  const push = (value = '') => {
    const normalized = normalizeExtractBase(value);
    if (candidates.includes(normalized)) return;
    candidates.push(normalized);
  };

  push(preferredBase);
  push(getLocalStorageExtractBase());
  push(getViteExtractBase());
  push('');

  return candidates.length > 0 ? candidates : [''];
};

const shouldRetryByStatus = (status: number): boolean => status === 404 || status === 502 || status === 503 || status === 504;

const shouldRetryByError = (error: unknown): boolean => {
  if (!(error instanceof Error)) return false;
  const normalized = String(error.message || '').trim().toLowerCase();
  if (!normalized) return true;
  if (normalized.includes('aborterror') || normalized.includes('aborted')) return false;
  return true;
};

export const resolveExtractBase = (preferredBase = ''): string => {
  const normalizedPreferred = normalizeExtractBase(preferredBase);
  if (normalizedPreferred) return normalizedPreferred;
  const candidates = buildExtractBaseCandidates(preferredBase).filter(Boolean);
  return candidates[0] || '';
};

export const toAbsoluteExtractUrl = (value: string, preferredBase = ''): string => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (/^https?:\/\//i.test(raw)) return raw;
  const normalized = raw.startsWith('/') ? raw : `/${raw}`;
  const usedBase = resolveExtractBase(preferredBase);
  return usedBase ? `${usedBase}${normalized}` : normalized;
};

const toObjectRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const toArtifactRouteFromPath = (artifactPathRaw: string): string => {
  let normalized = String(artifactPathRaw || '').trim().replace(/\\/g, '/');
  if (!normalized) return '';
  const markerIndex = normalized.toLowerCase().lastIndexOf('/artifacts/');
  if (markerIndex >= 0) {
    normalized = normalized.slice(markerIndex + '/artifacts/'.length);
  }
  const encoded = normalized
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  return encoded ? `/extract/artifact/${encoded}` : '';
};

export const resolveExtractArtifactUrlFromTraceHit = (
  hit: ExtractionTraceHitLike,
  preferredBase = '',
): string => {
  const directUrl = String(hit?.artifact_url || '').trim();
  if (directUrl) return toAbsoluteExtractUrl(directUrl, preferredBase);

  const locator = toObjectRecord(hit?.locator);
  const locatorUrlCandidates = [
    locator.image_url,
    locator.screenshot_url,
    locator.artifact_url,
    locator.table_artifact_url,
    locator.dataframe_artifact_url,
  ];
  for (const candidate of locatorUrlCandidates) {
    const direct = String(candidate || '').trim();
    if (direct) return toAbsoluteExtractUrl(direct, preferredBase);
  }

  const pathCandidates = [
    hit?.artifact_path,
    locator.image_path,
    locator.screenshot_path,
    locator.artifact_path,
    locator.table_artifact_path,
    locator.dataframe_artifact_path,
  ];
  for (const candidate of pathCandidates) {
    const path = String(candidate || '').trim();
    if (!path) continue;
    const route = toArtifactRouteFromPath(path);
    if (route) return toAbsoluteExtractUrl(route, preferredBase);
  }
  return '';
};

export const resolveExtractTableDownloadUrlFromTraceHit = (
  hit: ExtractionTraceHitLike,
  preferredBase = '',
): string => {
  const locator = toObjectRecord(hit?.locator);
  const candidates = [
    locator.table_download_url,
    locator.dataframe_download_url,
    locator.table_csv_url,
    locator.dataframe_csv_url,
    locator.table_artifact_url,
    locator.dataframe_artifact_url,
  ];
  for (const candidate of candidates) {
    const raw = String(candidate || '').trim();
    if (!raw) continue;
    return toAbsoluteExtractUrl(raw, preferredBase);
  }
  return '';
};

const requestExtraction = (
  path: string,
  init: RequestInit = {},
  preferredBase = '',
): Promise<ExtractionApiFetchResult> =>
  (async () => {
    const candidates = buildExtractBaseCandidates(preferredBase);
    let lastResult: ExtractionApiFetchResult | null = null;
    let lastError: unknown = null;

    for (let index = 0; index < candidates.length; index += 1) {
      const base = candidates[index];
      const isLast = index === candidates.length - 1;
      try {
        const result = await requestRaw(path, init, base);
        lastResult = result;
        if (result.response.ok) return result;
        if (isLast || !shouldRetryByStatus(result.response.status)) return result;
      } catch (error) {
        lastError = error;
        if (isLast || !shouldRetryByError(error)) {
          throw error;
        }
      }
    }

    if (lastResult) return lastResult;
    throw lastError instanceof Error ? lastError : new Error('Failed to request extraction API');
  })();

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
