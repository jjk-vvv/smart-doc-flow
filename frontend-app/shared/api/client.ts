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
    const normalizedText = text.toLowerCase();
    if (
      normalizedText.startsWith('<!doctype')
      || normalizedText.startsWith('<html')
      || normalizedText.includes('server is powered by frp')
    ) {
      return `请求没有到达后端服务（HTTP ${response.status}）。请检查 API 地址或内网穿透配置。请求地址：${response.url}`;
    }
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
  try {
    const response = await fetch(url, {
      credentials: 'include',
      ...init,
    });
    return { response, usedBase, url };
  } catch (error) {
    const runtimeProtocol =
      typeof window !== 'undefined' ? String(window.location?.protocol || '').trim().toLowerCase() : '';
    const targetIsHttp = /^http:\/\//i.test(String(url || '').trim());
    const hints: string[] = [];

    if (runtimeProtocol === 'https:' && targetIsHttp) {
      hints.push('possible mixed-content block: https page requesting http api');
    }
    if (String(url || '').includes('localhost')) {
      hints.push('check api base url / native env injection');
    }

    const reason = error instanceof Error ? error.message : String(error || 'unknown fetch error');
    const hintText = hints.length > 0 ? ` (${hints.join('; ')})` : '';
    throw new Error(`Failed to fetch ${url}: ${reason}${hintText}`);
  }
};
