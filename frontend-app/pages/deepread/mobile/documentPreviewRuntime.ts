import {
  resolveExtractArtifactUrlFromTraceHit,
  resolveExtractBase,
  toAbsoluteExtractUrl,
} from '../../../shared/api/extraction';
import type {
  PersistedWorkbenchFile,
  PersistedOfficePreviewState,
  WorkbenchSessionSnapshot,
} from '../../../shared/state/workbenchSession';

const restoredFileCache = new Map<string, File>();

const normalizeFileName = (value: string): string => String(value || '').trim().toLowerCase();

const toProxyableExtractPath = (value: string): string => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (raw.startsWith('/extract/')) return raw;
  if (!/^https?:\/\//i.test(raw)) return '';
  try {
    const parsed = new URL(raw);
    return parsed.pathname.startsWith('/extract/')
      ? `${parsed.pathname}${parsed.search || ''}${parsed.hash || ''}`
      : '';
  } catch {
    return '';
  }
};

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
  const directUrl = String(item.artifactUrl || '').trim();
  const directRelative = toProxyableExtractPath(directUrl);
  const directAbsolute = directUrl ? toAbsoluteExtractUrl(directUrl, resolvedBase) : '';
  const pathRelative = item.artifactPath
    ? resolveExtractArtifactUrlFromTraceHit({ artifact_path: item.artifactPath }, '')
    : '';
  const pathAbsolute = pathRelative ? toAbsoluteExtractUrl(pathRelative, resolvedBase) : '';

  return Array.from(
    new Set(
      [
        directRelative,
        pathRelative,
        directAbsolute,
        pathAbsolute,
        directUrl,
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
