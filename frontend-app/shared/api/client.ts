export type ApiFetchResult = {
  response: Response;
  usedBase: string;
  url: string;
};

const normalizeBase = (value = ''): string => String(value || '').trim().replace(/\/+$/, '');

export const resolveApiBase = (preferredBase = ''): string => normalizeBase(preferredBase);

export const buildApiUrl = (path: string, preferredBase = ''): { usedBase: string; url: string } => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const usedBase = resolveApiBase(preferredBase);
  return {
    usedBase,
    url: usedBase ? `${usedBase}${normalizedPath}` : normalizedPath,
  };
};

export const parseErrorMessage = async (response: Response): Promise<string> => {
  const fallback = `HTTP ${response.status}`;
  try {
    const text = (await response.text()).trim();
    if (!text) return fallback;
    try {
      const parsed = JSON.parse(text) as { error?: string; detail?: string; message?: string };
      return String(parsed.error || parsed.detail || parsed.message || text).trim() || fallback;
    } catch {
      return text;
    }
  } catch {
    return fallback;
  }
};

export const ensureOk = async (response: Response): Promise<Response> => {
  if (response.ok) return response;
  throw new Error(await parseErrorMessage(response));
};

export const requestRaw = async (
  path: string,
  init: RequestInit = {},
  preferredBase = '',
): Promise<ApiFetchResult> => {
  const { usedBase, url } = buildApiUrl(path, preferredBase);
  const response = await fetch(url, {
    credentials: 'include',
    ...init,
  });
  return { response, usedBase, url };
};

