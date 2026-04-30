import { buildApiUrl, ensureOk, requestRaw, resolveApiBase } from './client';

const MODULE1_ROUTE_PREFIX = '/module1';
const ENV_MODULE1_API_URL =
  typeof import.meta.env.VITE_MODULE1_API_URL === 'string' ? import.meta.env.VITE_MODULE1_API_URL : '';
const ENV_BACKEND_ENTRY_URL =
  typeof import.meta.env.VITE_BACKEND_ENTRY_URL === 'string' ? import.meta.env.VITE_BACKEND_ENTRY_URL : '';

const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1', '::1']);

const isLocalRuntime = (): boolean => {
  if (typeof window === 'undefined') return false;
  return window.location.protocol === 'file:' || LOCAL_HOSTNAMES.has(window.location.hostname);
};

const isLocalAbsoluteUrl = (value: string): boolean => {
  try {
    const url = new URL(value);
    return LOCAL_HOSTNAMES.has(url.hostname);
  } catch {
    return false;
  }
};

const normalizePath = (path: string): string => {
  const normalized = String(path || '').trim();
  if (!normalized) return '/';
  return normalized.startsWith('/') ? normalized : `/${normalized}`;
};

export const resolveModule1ApiBase = (preferredBase = ''): string => {
  const explicitBase = resolveApiBase(preferredBase);
  if (explicitBase) return explicitBase;

  const envBase = resolveApiBase(ENV_MODULE1_API_URL || ENV_BACKEND_ENTRY_URL);
  if (!envBase) return '';

  // In desktop/local development the renderer should talk to the colocated
  // gateway (or Vite proxy) instead of accidentally crossing a stale FRP URL.
  if (isLocalRuntime() && !isLocalAbsoluteUrl(envBase)) {
    return '';
  }

  return envBase;
};

export const buildModule1ApiUrl = (path: string, preferredBase = ''): string => {
  const normalizedBase = resolveModule1ApiBase(preferredBase);
  const normalizedPath = `${MODULE1_ROUTE_PREFIX}${normalizePath(path)}`;
  return buildApiUrl(normalizedPath, normalizedBase).url;
};

export const requestModule1Raw = async (
  path: string,
  init: RequestInit = {},
  preferredBase = '',
) =>
  requestRaw(`${MODULE1_ROUTE_PREFIX}${normalizePath(path)}`, init, resolveModule1ApiBase(preferredBase));

export type Module1HealthResponse = {
  status: string;
  timestamp?: string;
  libreoffice_available?: boolean;
  ai_available?: boolean;
  modules?: Record<string, boolean>;
};

export const fetchModule1Health = async (preferredBase = ''): Promise<Module1HealthResponse> => {
  const { response } = await requestModule1Raw('/health', { method: 'GET' }, preferredBase);
  await ensureOk(response);
  return (await response.json()) as Module1HealthResponse;
};
