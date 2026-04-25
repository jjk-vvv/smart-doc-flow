import { buildApiUrl, requestRaw, resolveApiBase } from './client';

const MODULE1_ROUTE_PREFIX = '/module1';
const ENV_MODULE1_API_URL =
  typeof import.meta.env.VITE_MODULE1_API_URL === 'string' ? import.meta.env.VITE_MODULE1_API_URL : '';
const ENV_BACKEND_ENTRY_URL =
  typeof import.meta.env.VITE_BACKEND_ENTRY_URL === 'string' ? import.meta.env.VITE_BACKEND_ENTRY_URL : '';

const normalizePath = (path: string): string => {
  const normalized = String(path || '').trim();
  if (!normalized) return '/';
  return normalized.startsWith('/') ? normalized : `/${normalized}`;
};

export const resolveModule1ApiBase = (preferredBase = ''): string =>
  resolveApiBase(preferredBase || ENV_MODULE1_API_URL || ENV_BACKEND_ENTRY_URL);

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
