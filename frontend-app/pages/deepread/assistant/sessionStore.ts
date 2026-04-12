export const ASSISTANT_SESSION_STORAGE_KEY = 'module2_assistant_session_map_v1';
export const GENERIC_ASSISTANT_SESSION_KEY = '__module2_no_file__';

export const readAssistantSessionMap = (): Record<string, string> => {
    if (typeof window === 'undefined') return {};
    try {
        const raw = window.localStorage.getItem(ASSISTANT_SESSION_STORAGE_KEY) || '{}';
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed as Record<string, string> : {};
    } catch {
        return {};
    }
};

export const writeAssistantSessionMap = (value: Record<string, string>) => {
    if (typeof window === 'undefined') return;
    try {
        window.localStorage.setItem(ASSISTANT_SESSION_STORAGE_KEY, JSON.stringify(value));
    } catch {
        // ignore persistence errors in the browser
    }
};

export const persistAssistantSessionForFile = (fileHash: string, sessionId: string) => {
    const fileKey = String(fileHash || '').trim();
    const sessionKey = String(sessionId || '').trim();
    if (!fileKey || !sessionKey) return;
    const current = readAssistantSessionMap();
    current[fileKey] = sessionKey;
    writeAssistantSessionMap(current);
};

export const clearAssistantSessionForFile = (fileHash: string) => {
    const fileKey = String(fileHash || '').trim();
    if (!fileKey) return;
    const current = readAssistantSessionMap();
    if (!(fileKey in current)) return;
    delete current[fileKey];
    writeAssistantSessionMap(current);
};
