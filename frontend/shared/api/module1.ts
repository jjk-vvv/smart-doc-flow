import { buildApiUrl, ensureOk, requestRaw, resolveApiBase } from './client';

const MODULE1_ROUTE_PREFIX = '/module1';
const ENV_MODULE1_API_URL =
  typeof import.meta.env.VITE_MODULE1_API_URL === 'string' ? import.meta.env.VITE_MODULE1_API_URL : '';

const normalizePath = (path: string): string => {
  const normalized = String(path || '').trim();
  if (!normalized) return '/';
  return normalized.startsWith('/') ? normalized : `/${normalized}`;
};

export const resolveModule1ApiBase = (preferredBase = ''): string =>
  resolveApiBase(preferredBase || ENV_MODULE1_API_URL);

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
