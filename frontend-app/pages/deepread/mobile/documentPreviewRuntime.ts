import {
  resolveExtractArtifactUrlFromTraceHit,
  resolveExtractBase,
  toAbsoluteExtractUrl,
} from '../../../shared/api/extraction';
import type {
  PersistedExtractionJobFile,
  PersistedWorkbenchFile,
  PersistedOfficePreviewState,
  WorkbenchSessionSnapshot,
} from '../../../shared/state/workbenchSession';

const restoredFileCache = new Map<string, File>();

const normalizeFileName = (value: string): string => String(value || '').trim().toLowerCase();

const previewFileNameFromKey = (key: string): string => {
  const raw = String(key || '');
  const separatorIndex = raw.indexOf(':');
  return normalizeFileName(separatorIndex >= 0 ? raw.slice(0, separatorIndex) : raw);
};

export const getFileExtension = (fileName: string): string => {
  const normalized = normalizeFileName(fileName);
  const dotIndex = normalized.lastIndexOf('.');
  if (dotIndex < 0) return '';
  return normalized.slice(dotIndex + 1);
};

export const formatPreviewMetric = (value: unknown): string => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return '0';
  return new Intl.NumberFormat('zh-CN').format(Math.round(numeric));
};

export const toRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

export const pickPersistedWorkbenchFile = (
  session: WorkbenchSessionSnapshot | null,
  fileName: string,
): PersistedWorkbenchFile | null => {
  const target = normalizeFileName(fileName);
  if (!session || !target) return null;
  const candidates = Array.isArray(session.selectedFiles) ? session.selectedFiles : [];
  return candidates.find((item) => normalizeFileName(item.name) === target) ?? null;
};

const hasArtifactPointer = (
  item: Pick<
    PersistedExtractionJobFile,
    'artifact_by_file_url' | 'artifact_file_id' | 'artifact_url'
  >,
): boolean => {
  const directArtifactUrl = String(item.artifact_url || '').trim();
  const normalizedDirectUrl = directArtifactUrl
    ? resolveExtractArtifactUrlFromTraceHit({ artifact_url: directArtifactUrl }, '')
    : '';
  return Boolean(
    String(item.artifact_by_file_url || '').trim()
    || String(item.artifact_file_id || '').trim()
    || normalizedDirectUrl
  );
};

const pickExtractionJobFile = (
  session: WorkbenchSessionSnapshot | null,
  fileName: string,
  fileHash = '',
): PersistedExtractionJobFile | null => {
  const targetName = normalizeFileName(fileName);
  const targetHash = String(fileHash || '').trim();
  const files = Array.isArray(session?.extractionJob?.files)
    ? (session?.extractionJob?.files as PersistedExtractionJobFile[])
    : [];
  if (files.length === 0) return null;

  if (targetHash) {
    const byHash = files.find((item) => String(item.file_hash || '').trim() === targetHash);
    if (byHash) return byHash;
  }

  if (targetName) {
    const byName = files.find((item) => normalizeFileName(item.file_name) === targetName);
    if (byName) return byName;
  }

  return null;
};

const toPersistedFileFromArtifactPayload = (
  payload: {
    fileName: string;
    fileHash?: string;
    artifactByFileUrl?: string;
    artifactFileId?: string;
    artifactPath?: string;
    artifactUrl?: string;
  },
): PersistedWorkbenchFile | null => {
  const fileName = String(payload.fileName || '').trim();
  if (!fileName) return null;
  const directArtifactUrl = String(payload.artifactUrl || '').trim();
  const normalizedDirectUrl = directArtifactUrl
    ? resolveExtractArtifactUrlFromTraceHit({ artifact_url: directArtifactUrl }, '')
    : '';
  const candidate: PersistedWorkbenchFile = {
    key: `artifact:${String(payload.fileHash || normalizeFileName(fileName)).trim()}`,
    name: fileName,
    size: 0,
    lastModified: Date.now(),
    ext: getFileExtension(fileName),
    artifactByFileUrl: String(payload.artifactByFileUrl || '').trim() || undefined,
    artifactFileId: String(payload.artifactFileId || '').trim() || undefined,
    artifactPath: undefined,
    artifactUrl: normalizedDirectUrl || undefined,
  };
  const hasPointer = Boolean(
    candidate.artifactByFileUrl
    || candidate.artifactFileId
    || candidate.artifactPath
    || candidate.artifactUrl,
  );
  return hasPointer ? candidate : null;
};

export const pickPersistedWorkbenchFileFromExtractionJob = (
  session: WorkbenchSessionSnapshot | null,
  fileName: string,
  fileHash = '',
): PersistedWorkbenchFile | null => {
  const matched = pickExtractionJobFile(session, fileName, fileHash);
  if (!matched || !hasArtifactPointer(matched)) return null;
  return toPersistedFileFromArtifactPayload({
    fileName: String(matched.file_name || fileName || '').trim(),
    fileHash: String(matched.file_hash || fileHash || '').trim() || undefined,
    artifactByFileUrl: String(matched.artifact_by_file_url || '').trim(),
    artifactFileId: String(matched.artifact_file_id || '').trim(),
    artifactPath: undefined,
    artifactUrl: String(matched.artifact_url || '').trim(),
  });
};

export const pickPersistedWorkbenchFileFromDiagnostics = (
  diagnostics: Record<string, unknown>,
  fileName: string,
  fileHash = '',
): PersistedWorkbenchFile | null => {
  const source = diagnostics || {};
  const direct = toPersistedFileFromArtifactPayload({
    fileName,
    fileHash,
    artifactByFileUrl: String(
      source.source_artifact_by_file_url
      || source.artifact_by_file_url
      || '',
    ).trim(),
    artifactFileId: String(
      source.source_artifact_file_id
      || source.artifact_file_id
      || '',
    ).trim(),
    artifactPath: undefined,
    artifactUrl: String(
      source.source_artifact_url
      || source.artifact_url
      || '',
    ).trim(),
  });
  if (direct) return direct;
  return null;
};

export const pickOfficePreviewByFileName = (
  previewMap: Record<string, PersistedOfficePreviewState>,
  fileName: string,
): PersistedOfficePreviewState | null => {
  const target = normalizeFileName(fileName);
  if (!target) return null;

  let fallback: PersistedOfficePreviewState | null = null;
  for (const [key, state] of Object.entries(previewMap || {})) {
    if (!state) continue;
    if (previewFileNameFromKey(key) !== target) continue;
    if (!fallback) fallback = state;
    if (state.status === 'completed' && String(state.pdfUrl || '').trim()) {
      return state;
    }
  }
  return fallback;
};

const buildRestoreCandidates = (
  item: PersistedWorkbenchFile,
  preferredBase = '',
): string[] => {
  const resolvedBase = resolveExtractBase(preferredBase);
  const byFileRelative = resolveExtractArtifactUrlFromTraceHit(
    {
      artifact_by_file_url: item.artifactByFileUrl,
      artifact_file_id: item.artifactFileId,
    },
    '',
  );
  const directUrl = String(item.artifactUrl || '').trim();
  const directRelative = resolveExtractArtifactUrlFromTraceHit({ artifact_url: directUrl }, '');
  const directAbsolute = directRelative ? toAbsoluteExtractUrl(directRelative, resolvedBase) : '';
  const byFileAbsolute = byFileRelative ? toAbsoluteExtractUrl(byFileRelative, resolvedBase) : '';

  return Array.from(
    new Set(
      [
        byFileRelative,
        byFileAbsolute,
        directRelative,
        directAbsolute,
      ].filter(Boolean),
    ),
  );
};

export const restoreWorkbenchFile = async (
  item: PersistedWorkbenchFile,
  preferredBase = '',
): Promise<File | null> => {
  const cacheKey = String(item.key || '').trim();
  if (cacheKey && restoredFileCache.has(cacheKey)) {
    return restoredFileCache.get(cacheKey) ?? null;
  }

  const candidates = buildRestoreCandidates(item, preferredBase);
  if (candidates.length === 0) return null;

  let response: Response | null = null;
  for (const candidate of candidates) {
    try {
      const fetched = await fetch(candidate, {
        credentials: 'include',
        cache: 'no-store',
      });
      if (fetched.ok) {
        response = fetched;
        break;
      }
    } catch {
      continue;
    }
  }

  if (!response) {
    throw new Error(`无法恢复源文件：${item.name}`);
  }

  const blob = await response.blob();
  const FileCtor = typeof window !== 'undefined' && typeof window.File === 'function'
    ? window.File
    : globalThis.File;
  if (typeof FileCtor !== 'function') {
    throw new Error('当前环境不支持文件恢复');
  }

  const restoredFile = new FileCtor([blob], item.name, {
    type: blob.type || 'application/octet-stream',
    lastModified: Number(item.lastModified || Date.now()),
  });

  if (cacheKey) {
    restoredFileCache.set(cacheKey, restoredFile);
  }
  return restoredFile;
};
