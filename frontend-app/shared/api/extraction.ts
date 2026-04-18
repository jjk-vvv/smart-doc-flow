import { requestRaw, resolveApiBase } from './client';

export type ExtractionApiFetchResult = {
  response: Response;
  usedBase: string;
  url: string;
};

export type ExtractionTraceHitLike = {
  artifact_file_id?: string | null;
  artifact_by_file_url?: string | null;
  artifact_download_url?: string | null;
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

const shouldRetryByStatus = (status: number): boolean =>
  status === 401 ||
  status === 403 ||
  status === 404 ||
  status === 410 ||
  status === 502 ||
  status === 503 ||
  status === 504;

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

const isLegacyExtractArtifactRoute = (rawUrl: string): boolean => {
  const value = String(rawUrl || '').trim();
  if (!value) return false;
  try {
    const parsed = /^https?:\/\//i.test(value) ? new URL(value) : new URL(value, 'http://localhost');
    const pathname = String(parsed.pathname || '');
    return pathname.startsWith('/extract/artifact/') && !pathname.startsWith('/extract/artifact/by-file/');
  } catch {
    return value.startsWith('/extract/artifact/') && !value.startsWith('/extract/artifact/by-file/');
  }
};

const toArtifactByFileRoute = (fileIdRaw: unknown): string => {
  const normalized = String(fileIdRaw || '').trim();
  if (!normalized) return '';
  return `/extract/artifact/by-file/${encodeURIComponent(normalized)}`;
};

const normalizeAllowedArtifactUrl = (rawUrl: string, preferredBase = ''): string => {
  const value = String(rawUrl || '').trim();
  if (!value) return '';
  if (isLegacyExtractArtifactRoute(value)) return '';
  return toAbsoluteExtractUrl(value, preferredBase);
};

export const resolveExtractArtifactUrlFromTraceHit = (
  hit: ExtractionTraceHitLike,
  preferredBase = '',
): string => {
  const directByFileUrl = String(hit?.artifact_by_file_url || '').trim();
  if (directByFileUrl) return toAbsoluteExtractUrl(directByFileUrl, preferredBase);

  const byFileFromId = toArtifactByFileRoute(hit?.artifact_file_id);
  if (byFileFromId) return toAbsoluteExtractUrl(byFileFromId, preferredBase);

  const directUrl = String(hit?.artifact_url || '').trim();
  if (directUrl) {
    const normalized = normalizeAllowedArtifactUrl(directUrl, preferredBase);
    if (normalized) return normalized;
  }

  const locator = toObjectRecord(hit?.locator);
  const locatorByFileUrlCandidates = [
    locator.artifact_by_file_url,
    locator.table_artifact_by_file_url,
    locator.dataframe_artifact_by_file_url,
    locator.figure_artifact_by_file_url,
    locator.screenshot_by_file_url,
    locator.image_by_file_url,
    locator.preview_by_file_url,
  ];
  for (const candidate of locatorByFileUrlCandidates) {
    const direct = String(candidate || '').trim();
    if (direct) return toAbsoluteExtractUrl(direct, preferredBase);
  }

  const locatorByFileIdCandidates = [
    locator.artifact_file_id,
    locator.table_artifact_file_id,
    locator.dataframe_artifact_file_id,
    locator.figure_artifact_file_id,
    locator.screenshot_file_id,
    locator.image_file_id,
    locator.preview_file_id,
  ];
  for (const candidate of locatorByFileIdCandidates) {
    const byFileRoute = toArtifactByFileRoute(candidate);
    if (byFileRoute) return toAbsoluteExtractUrl(byFileRoute, preferredBase);
  }

  const locatorUrlCandidates = [
    locator.image_url,
    locator.screenshot_url,
    locator.artifact_url,
    locator.table_artifact_url,
    locator.dataframe_artifact_url,
    locator.figure_artifact_url,
    locator.preview_url,
    locator.table_image_url,
  ];
  for (const candidate of locatorUrlCandidates) {
    const direct = String(candidate || '').trim();
    if (direct) {
      const normalized = normalizeAllowedArtifactUrl(direct, preferredBase);
      if (normalized) return normalized;
    }
  }
  return '';
};

export const resolveExtractTableDownloadUrlFromTraceHit = (
  hit: ExtractionTraceHitLike,
  preferredBase = '',
): string => {
  const directDownload = String(hit?.artifact_download_url || '').trim();
  if (directDownload) return toAbsoluteExtractUrl(directDownload, preferredBase);

  const locator = toObjectRecord(hit?.locator);
  const candidates = [
    locator.artifact_download_url,
    locator.table_artifact_download_url,
    locator.dataframe_artifact_download_url,
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

export const requestExtractionJobCancelFile = async (
  jobId: string,
  fileHash: string,
  fileName: string,
  preferredBase = '',
): Promise<ExtractionApiFetchResult> => {
  const normalizedJobId = String(jobId || '').trim();
  if (!normalizedJobId) {
    throw new Error('Missing extraction job id');
  }
  return requestExtraction(
    `/extract/jobs/${encodeURIComponent(normalizedJobId)}/cancel-file`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        file_hash: String(fileHash || '').trim(),
        file_name: String(fileName || '').trim(),
      }),
    },
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
