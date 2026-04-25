import { ensureOk, parseErrorMessage, requestRaw, resolveApiBase } from './client';

export type AuthUser =
  | {
      id?: string;
      name: string;
      email: string;
      phone?: string;
      status?: string;
      tenantId?: string;
    }
  | null;

export type AuthUserPayload = {
  user: {
    id?: string;
    name: string;
    email: string;
    phone?: string;
    status?: string;
    tenantId?: string;
  };
};

export type LoginPayload = {
  account: string;
  password: string;
};

export type RegisterPayload = {
  name: string;
  email: string;
  phone: string;
  password: string;
  code: string;
};

export type SendCodePayload = {
  message?: string;
  maskedContact?: string;
  devCode?: string;
};

export type AuthSessionItem = {
  sessionId: string;
  current: boolean;
  ipAddress: string;
  userAgent: string;
  createdAt?: string | null;
  lastSeenAt?: string | null;
  expiresAt?: string | null;
  revokedAt?: string | null;
  status: string;
};

export type AuthSessionListPayload = {
  sessions: AuthSessionItem[];
  supportsPersistentSessions: boolean;
};

export type SessionRevokePayload = {
  message?: string;
  revokedCount?: number;
};

const jsonHeaders = {
  'Content-Type': 'application/json',
};

type AuthHealthPayload = {
  ok?: boolean;
  notifierMode?: string;
  databaseConnected?: boolean;
};

const AUTH_HEALTH_PATH = '/api/auth/health';
const AUTH_SESSION_HINT_KEY = 'smart_doc_flow.auth.session_hint';
const AUTH_BACKEND_FALLBACKS_KEY = 'smart_doc_flow.backend_entry_fallbacks';

let authApiBasePromise: Promise<string> | null = null;

const readSessionHint = (): boolean => {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(AUTH_SESSION_HINT_KEY) === '1';
  } catch {
    return false;
  }
};

const writeSessionHint = (value: boolean): void => {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(AUTH_SESSION_HINT_KEY, value ? '1' : '0');
  } catch {
    // Ignore storage write failures in restricted environments.
  }
};

const parseBaseCandidates = (raw: string): string[] =>
  String(raw || '')
    .split(/[,\n;]/)
    .map((item) => resolveApiBase(item))
    .filter(Boolean);

const readStoredBackendFallbacks = (): string[] => {
  if (typeof window === 'undefined') return [];
  try {
    return parseBaseCandidates(window.localStorage.getItem(AUTH_BACKEND_FALLBACKS_KEY) || '');
  } catch {
    return [];
  }
};

const buildAuthApiBaseCandidates = (): string[] => {
  const buildMode = String(import.meta.env.MODE || '').trim().toLowerCase();
  const isNativeMode = buildMode === 'native';
  const explicitBase = resolveApiBase(import.meta.env.VITE_BACKEND_ENTRY_URL || '');
  const envFallbackBases = parseBaseCandidates(import.meta.env.VITE_BACKEND_ENTRY_URL_FALLBACKS || '');
  const storedFallbackBases = readStoredBackendFallbacks();
  const hasConfiguredBase = Boolean(explicitBase) || envFallbackBases.length > 0 || storedFallbackBases.length > 0;
  const candidates: string[] = [];
  const push = (value = '') => {
    const normalized = resolveApiBase(value);
    if (!candidates.includes(normalized)) {
      candidates.push(normalized);
    }
  };

  if (explicitBase) {
    push(explicitBase);
  }
  envFallbackBases.forEach((item) => push(item));
  storedFallbackBases.forEach((item) => push(item));
  // Native builds should not silently fall back to relative /api routes, because
  // that can route to WebView local html instead of the gateway.
  if (!isNativeMode || !hasConfiguredBase) {
    push('');
  }

  if (candidates.length === 0) {
    push('');
  }

  return candidates;
};

const parseJsonResponse = async <T>(response: Response, path: string, url: string): Promise<T> => {
  const raw = await response.text();
  const payload = String(raw || '').trim();
  if (!payload) {
    throw new Error(`Empty response body from auth endpoint: ${path} (${url})`);
  }

  try {
    return JSON.parse(payload) as T;
  } catch {
    const preview = payload.slice(0, 120).replace(/\s+/g, ' ');
    throw new Error(
      `Non-JSON response from auth endpoint: ${path} (${url}). Preview: ${preview}`,
    );
  }
};

const detectAuthApiBase = async (): Promise<string> => {
  const candidates = buildAuthApiBaseCandidates();
  const explicitBase = resolveApiBase(import.meta.env.VITE_BACKEND_ENTRY_URL || '');
  let firstReachableBase = '';

  for (const candidate of candidates) {
    try {
      const { response, url } = await requestRaw(AUTH_HEALTH_PATH, { method: 'GET' }, candidate);
      if (!response.ok) {
        continue;
      }

      const payload = await parseJsonResponse<AuthHealthPayload>(response, AUTH_HEALTH_PATH, url);
      if (!firstReachableBase) {
        firstReachableBase = candidate;
      }

      const notifierMode = String(payload.notifierMode || '').trim().toLowerCase();
      if (payload.databaseConnected && notifierMode === 'smtp') {
        return candidate;
      }
    } catch {
      // Fall through to the next candidate until we find a healthy auth backend.
    }
  }

  if (explicitBase) {
    return explicitBase;
  }
  return firstReachableBase;
};

const getAuthApiBase = async (): Promise<string> => {
  if (!authApiBasePromise) {
    authApiBasePromise = detectAuthApiBase();
  }
  return authApiBasePromise;
};

const requestAuthJson = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
  const preferredBase = await getAuthApiBase();
  const { response, url } = await requestRaw(path, init, preferredBase);
  await ensureOk(response);
  return await parseJsonResponse<T>(response, path, url);
};

const requestCurrentUserAtBase = async (preferredBase = ''): Promise<AuthUserPayload | null> => {
  const { response } = await requestRaw(
    '/api/me',
    {
      method: 'GET',
    },
    preferredBase,
  );
  if (response.status === 401 || response.status === 403) {
    writeSessionHint(false);
    return null;
  }
  await ensureOk(response);
  const payload = (await response.json()) as AuthUserPayload;
  writeSessionHint(Boolean(payload?.user));
  return payload;
};

export const loginAuth = async (payload: LoginPayload): Promise<AuthUserPayload> => {
  const response = await requestAuthJson<AuthUserPayload>('/api/login', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  writeSessionHint(true);
  return response;
};

export const registerAuth = async (payload: RegisterPayload): Promise<AuthUserPayload> => {
  const response = await requestAuthJson<AuthUserPayload>('/api/register', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  writeSessionHint(true);
  return response;
};

export const logoutAuth = async (): Promise<{ message?: string }> => {
  const response = await requestAuthJson<{ message?: string }>('/api/logout', {
    method: 'POST',
  });
  writeSessionHint(false);
  return response;
};

export const getCurrentUser = async (): Promise<AuthUserPayload | null> => {
  const hasSessionHint = readSessionHint();
  try {
    return await requestCurrentUserAtBase('');
  } catch {
    if (!hasSessionHint) {
      // Even without a local hint, probe the backend once so a persisted auth cookie
      // can restore the session after localStorage is cleared or in fresh browser contexts.
    }
    const preferredBase = await getAuthApiBase();
    return await requestCurrentUserAtBase(preferredBase);
  }
};

export const sendForgotCode = async (contact: string): Promise<SendCodePayload> =>
  requestAuthJson<SendCodePayload>('/api/forgot/send-code', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ contact }),
  });

export const resetForgotPassword = async (payload: {
  contact: string;
  code: string;
  newPassword: string;
}): Promise<{ message?: string }> =>
  requestAuthJson<{ message?: string }>('/api/forgot/reset', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });

export const sendRegisterCode = async (contact: string): Promise<SendCodePayload> =>
  requestAuthJson<SendCodePayload>('/api/register/send-code', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ contact }),
  });

export const listAuthSessions = async (): Promise<AuthSessionListPayload> =>
  requestAuthJson<AuthSessionListPayload>('/api/sessions', {
    method: 'GET',
  });

export const revokeOtherAuthSessions = async (): Promise<SessionRevokePayload> =>
  requestAuthJson<SessionRevokePayload>('/api/sessions/revoke-others', {
    method: 'POST',
  });

export const revokeAuthSession = async (sessionId: string): Promise<SessionRevokePayload> =>
  requestAuthJson<SessionRevokePayload>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });

export const authErrorMessage = async (response: Response): Promise<string> => parseErrorMessage(response);
