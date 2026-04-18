export type HomeWorkbenchView =
  | { kind: 'home' }
  | { kind: 'recent' }
  | { kind: 'favorites' }
  | { kind: 'recycle' }
  | { kind: 'folder'; folderId: string };

export type HomeWorkbenchFolder = {
  id: string;
  name: string;
  parentId: string | null;
  createdAt: string;
  updatedAt: string;
};

export type HomeWorkbenchItemStatus =
  | 'ready'
  | 'converting'
  | 'converted'
  | 'missing'
  | 'error';

export type HomeWorkbenchItem = {
  id: string;
  name: string;
  originalName: string;
  ext: string;
  mime: string;
  size: number;
  folderId: string | null;
  createdAt: string;
  updatedAt: string;
  starred: boolean;
  trashed: boolean;
  source: 'upload';
  status: HomeWorkbenchItemStatus;
  errorMessage?: string | null;
  convertedPdfReady?: boolean;
};

export type HomeWorkbenchSession = {
  version: 1;
  folders: HomeWorkbenchFolder[];
  items: HomeWorkbenchItem[];
  activeView: HomeWorkbenchView;
  selectedItemId: string | null;
};

type ModuleItemDraft = {
  itemIds: string[];
  createdAt: string;
};

type Module1Draft = ModuleItemDraft & {
  prompt: string;
};

type PersistedFileRecord = {
  itemId: string;
  blob: Blob;
  name: string;
  type: string;
  lastModified: number;
};

type PersistedConvertedPdfRecord = {
  itemId: string;
  blob: Blob;
  type: string;
};

type HomeWorkbenchBinaryListener = () => void;

const SESSION_KEY = 'home_workbench_session_v1';
const MODULE1_DRAFT_KEY = 'home_workbench_module1_draft_v1';
const MODULE2_DRAFT_KEY = 'home_workbench_module2_draft_v1';
const MODULE4_DRAFT_KEY = 'home_workbench_module4_draft_v1';

const HOME_WORKBENCH_BINARY_DB_NAME = 'home_workbench_binary_store_v1';
const HOME_WORKBENCH_BINARY_DB_VERSION = 1;
const FILE_STORE_NAME = 'files';
const CONVERTED_PDF_STORE_NAME = 'converted_pdf';

const liveFileStore = new Map<string, File>();
const liveConvertedPdfStore = new Map<string, Blob>();
const pendingFileLoads = new Map<string, Promise<File | null>>();
const pendingConvertedPdfLoads = new Map<string, Promise<Blob | null>>();
const binaryListeners = new Set<HomeWorkbenchBinaryListener>();

let binaryDbPromise: Promise<IDBDatabase | null> | null = null;
let binaryStoreHydrationPromise: Promise<void> | null = null;
let binaryStoreReady = typeof window === 'undefined';
let scheduledPruneItemIds: string[] | null = null;
let pruneTimerId: number | null = null;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

const isString = (value: unknown): value is string => typeof value === 'string';

const isHomeWorkbenchView = (value: unknown): value is HomeWorkbenchView => {
  if (!isRecord(value) || !isString(value.kind)) return false;
  if (value.kind === 'folder') return isString(value.folderId);
  return value.kind === 'home' || value.kind === 'recent' || value.kind === 'favorites' || value.kind === 'recycle';
};

const isHomeWorkbenchFolder = (value: unknown): value is HomeWorkbenchFolder => {
  if (!isRecord(value)) return false;
  return (
    isString(value.id)
    && isString(value.name)
    && (value.parentId === null || isString(value.parentId))
    && isString(value.createdAt)
    && isString(value.updatedAt)
  );
};

const isHomeWorkbenchItem = (value: unknown): value is HomeWorkbenchItem => {
  if (!isRecord(value)) return false;
  return (
    isString(value.id)
    && isString(value.name)
    && isString(value.originalName)
    && isString(value.ext)
    && isString(value.mime)
    && typeof value.size === 'number'
    && (value.folderId === null || isString(value.folderId))
    && isString(value.createdAt)
    && isString(value.updatedAt)
    && typeof value.starred === 'boolean'
    && typeof value.trashed === 'boolean'
    && value.source === 'upload'
    && isString(value.status)
  );
};

const isModuleItemDraft = (value: unknown): value is ModuleItemDraft => {
  if (!isRecord(value)) return false;
  return Array.isArray(value.itemIds) && value.itemIds.every(isString) && isString(value.createdAt);
};

const isModule1Draft = (value: unknown): value is Module1Draft =>
  isModuleItemDraft(value) && isString((value as Module1Draft).prompt);

export const HOME_WORKBENCH_ROOT_FOLDER_ID = 'root-home-folder';

const isIndexedDbAvailable = (): boolean =>
  typeof window !== 'undefined' && typeof window.indexedDB !== 'undefined';

const notifyBinaryListeners = (): void => {
  binaryListeners.forEach((listener) => {
    try {
      listener();
    } catch {
      // ignore listener errors
    }
  });
};

const openBinaryDb = async (): Promise<IDBDatabase | null> => {
  if (!isIndexedDbAvailable()) return null;

  if (!binaryDbPromise) {
    binaryDbPromise = new Promise<IDBDatabase | null>((resolve) => {
      try {
        const request = window.indexedDB.open(
          HOME_WORKBENCH_BINARY_DB_NAME,
          HOME_WORKBENCH_BINARY_DB_VERSION
        );

        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(FILE_STORE_NAME)) {
            db.createObjectStore(FILE_STORE_NAME, { keyPath: 'itemId' });
          }
          if (!db.objectStoreNames.contains(CONVERTED_PDF_STORE_NAME)) {
            db.createObjectStore(CONVERTED_PDF_STORE_NAME, { keyPath: 'itemId' });
          }
        };

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => resolve(null);
        request.onblocked = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }

  return binaryDbPromise;
};

const runStoreRequest = async <TResult>(
  storeName: string,
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => IDBRequest<TResult>
): Promise<TResult | null> => {
  const db = await openBinaryDb();
  if (!db) return null;

  return new Promise<TResult | null>((resolve, reject) => {
    let settled = false;
    const finish = (value: TResult | null) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    const fail = (error: unknown) => {
      if (settled) return;
      settled = true;
      reject(error instanceof Error ? error : new Error('homeWorkbench binary store request failed'));
    };

    try {
      const transaction = db.transaction(storeName, mode);
      const store = transaction.objectStore(storeName);
      const request = action(store);

      request.onsuccess = () => finish((request.result as TResult | undefined) ?? null);
      request.onerror = () => fail(request.error || new Error('homeWorkbench binary store request failed'));
      transaction.onerror = () => fail(transaction.error || new Error('homeWorkbench binary transaction failed'));
      transaction.onabort = () => fail(transaction.error || new Error('homeWorkbench binary transaction aborted'));
    } catch (error) {
      fail(error);
    }
  }).catch(() => null);
};

const getAllStoreRecords = async <TRecord>(storeName: string): Promise<TRecord[]> => {
  const records = await runStoreRequest<TRecord[]>(storeName, 'readonly', (store) => store.getAll());
  return Array.isArray(records) ? records : [];
};

const getAllStoreKeys = async (storeName: string): Promise<string[]> => {
  const keys = await runStoreRequest<IDBValidKey[]>(storeName, 'readonly', (store) => store.getAllKeys());
  return Array.isArray(keys)
    ? keys.map((key) => String(key || '').trim()).filter(Boolean)
    : [];
};

const putStoreRecord = async <TRecord>(storeName: string, record: TRecord): Promise<void> => {
  await runStoreRequest(storeName, 'readwrite', (store) => store.put(record));
};

const getStoreRecord = async <TRecord>(storeName: string, itemId: string): Promise<TRecord | null> => {
  return runStoreRequest<TRecord>(storeName, 'readonly', (store) => store.get(itemId));
};

const deleteStoreRecord = async (storeName: string, itemId: string): Promise<void> => {
  await runStoreRequest(storeName, 'readwrite', (store) => store.delete(itemId));
};

const toPersistedFileRecord = (itemId: string, file: File): PersistedFileRecord => ({
  itemId,
  blob: file,
  name: file.name || 'restored-file',
  type: file.type || 'application/octet-stream',
  lastModified: Number.isFinite(file.lastModified) ? file.lastModified : Date.now(),
});

const restorePersistedFile = (record: PersistedFileRecord): File | null => {
  if (typeof globalThis.File !== 'function' || !record?.itemId || !(record.blob instanceof Blob)) {
    return null;
  }

  try {
    return new globalThis.File([record.blob], record.name || 'restored-file', {
      type: record.type || record.blob.type || 'application/octet-stream',
      lastModified: Number.isFinite(record.lastModified) ? record.lastModified : Date.now(),
    });
  } catch {
    return null;
  }
};

const toPersistedConvertedPdfRecord = (itemId: string, blob: Blob): PersistedConvertedPdfRecord => ({
  itemId,
  blob,
  type: blob.type || 'application/pdf',
});

const restorePersistedConvertedPdf = (record: PersistedConvertedPdfRecord): Blob | null => {
  if (!record?.itemId || !(record.blob instanceof Blob)) return null;
  try {
    return record.blob.type
      ? record.blob
      : record.blob.slice(0, record.blob.size, record.type || 'application/pdf');
  } catch {
    return null;
  }
};

const syncMemoryCacheWithRetainedIds = (retainedItemIds: Set<string>): boolean => {
  let changed = false;

  Array.from(liveFileStore.keys()).forEach((itemId) => {
    if (retainedItemIds.has(itemId)) return;
    liveFileStore.delete(itemId);
    changed = true;
  });

  Array.from(liveConvertedPdfStore.keys()).forEach((itemId) => {
    if (retainedItemIds.has(itemId)) return;
    liveConvertedPdfStore.delete(itemId);
    changed = true;
  });

  return changed;
};

const flushScheduledBinaryPrune = async (): Promise<void> => {
  const nextItemIds = scheduledPruneItemIds;
  scheduledPruneItemIds = null;

  if (!nextItemIds) return;

  const retainedItemIds = new Set(nextItemIds);
  const cacheChanged = syncMemoryCacheWithRetainedIds(retainedItemIds);

  const db = await openBinaryDb();
  if (!db) {
    if (cacheChanged) notifyBinaryListeners();
    return;
  }

  const pruneStore = async (storeName: string): Promise<boolean> => {
    const keys = await getAllStoreKeys(storeName);
    const orphanItemIds = keys.filter((itemId) => itemId && !retainedItemIds.has(itemId));
    if (orphanItemIds.length === 0) return false;
    await Promise.all(orphanItemIds.map((itemId) => deleteStoreRecord(storeName, itemId)));
    return true;
  };

  const [fileStoreChanged, convertedStoreChanged] = await Promise.all([
    pruneStore(FILE_STORE_NAME),
    pruneStore(CONVERTED_PDF_STORE_NAME),
  ]);

  if (cacheChanged || fileStoreChanged || convertedStoreChanged) {
    notifyBinaryListeners();
  }

  if (scheduledPruneItemIds) {
    await flushScheduledBinaryPrune();
  }
};

const scheduleBinaryStorePrune = (retainedItemIds: string[]): void => {
  if (typeof window === 'undefined') return;

  scheduledPruneItemIds = [...retainedItemIds];

  if (pruneTimerId !== null) {
    window.clearTimeout(pruneTimerId);
  }

  pruneTimerId = window.setTimeout(() => {
    pruneTimerId = null;
    void flushScheduledBinaryPrune();
  }, 120);
};

const hydrateBinaryStores = async (): Promise<void> => {
  if (typeof window === 'undefined') {
    binaryStoreReady = true;
    return;
  }

  const db = await openBinaryDb();
  if (!db) {
    binaryStoreReady = true;
    notifyBinaryListeners();
    return;
  }

  const [fileRecords, convertedPdfRecords] = await Promise.all([
    getAllStoreRecords<PersistedFileRecord>(FILE_STORE_NAME),
    getAllStoreRecords<PersistedConvertedPdfRecord>(CONVERTED_PDF_STORE_NAME),
  ]);

  liveFileStore.clear();
  fileRecords.forEach((record) => {
    const restored = restorePersistedFile(record);
    if (restored) {
      liveFileStore.set(record.itemId, restored);
    }
  });

  liveConvertedPdfStore.clear();
  convertedPdfRecords.forEach((record) => {
    const restored = restorePersistedConvertedPdf(record);
    if (restored) {
      liveConvertedPdfStore.set(record.itemId, restored);
    }
  });

  binaryStoreReady = true;
  notifyBinaryListeners();
};

export const subscribeHomeWorkbenchBinaryStore = (
  listener: HomeWorkbenchBinaryListener
): (() => void) => {
  binaryListeners.add(listener);
  return () => {
    binaryListeners.delete(listener);
  };
};

export const isHomeWorkbenchPersistenceReady = (): boolean => binaryStoreReady;

export const ensureHomeWorkbenchPersistenceReady = async (): Promise<void> => {
  if (typeof window === 'undefined') {
    binaryStoreReady = true;
    return;
  }

  if (binaryStoreReady) return;

  if (!binaryStoreHydrationPromise) {
    binaryStoreHydrationPromise = hydrateBinaryStores().finally(() => {
      binaryStoreHydrationPromise = null;
    });
  }

  await binaryStoreHydrationPromise;
};

const loadFileFromPersistence = async (itemId: string): Promise<File | null> => {
  if (!itemId) return null;
  const cached = liveFileStore.get(itemId);
  if (cached) return cached;

  const pending = pendingFileLoads.get(itemId);
  if (pending) return pending;

  const request = (async () => {
    await ensureHomeWorkbenchPersistenceReady();
    const record = await getStoreRecord<PersistedFileRecord>(FILE_STORE_NAME, itemId);
    const restored = record ? restorePersistedFile(record) : null;
    if (restored) {
      liveFileStore.set(itemId, restored);
      notifyBinaryListeners();
    }
    return restored;
  })().finally(() => {
    pendingFileLoads.delete(itemId);
  });

  pendingFileLoads.set(itemId, request);
  return request;
};

const loadConvertedPdfFromPersistence = async (itemId: string): Promise<Blob | null> => {
  if (!itemId) return null;
  const cached = liveConvertedPdfStore.get(itemId);
  if (cached) return cached;

  const pending = pendingConvertedPdfLoads.get(itemId);
  if (pending) return pending;

  const request = (async () => {
    await ensureHomeWorkbenchPersistenceReady();
    const record = await getStoreRecord<PersistedConvertedPdfRecord>(CONVERTED_PDF_STORE_NAME, itemId);
    const restored = record ? restorePersistedConvertedPdf(record) : null;
    if (restored) {
      liveConvertedPdfStore.set(itemId, restored);
      notifyBinaryListeners();
    }
    return restored;
  })().finally(() => {
    pendingConvertedPdfLoads.delete(itemId);
  });

  pendingConvertedPdfLoads.set(itemId, request);
  return request;
};

export const resolveHomeWorkbenchFile = async (itemId: string): Promise<File | null> =>
  loadFileFromPersistence(itemId);

export const resolveHomeWorkbenchConvertedPdf = async (itemId: string): Promise<Blob | null> =>
  loadConvertedPdfFromPersistence(itemId);

export const HOME_WORKBENCH_BINARY_READY_PROMISE = ensureHomeWorkbenchPersistenceReady();

export const createDefaultHomeWorkbenchSession = (): HomeWorkbenchSession => {
  const now = new Date().toISOString();
  return {
    version: 1,
    folders: [
      {
        id: HOME_WORKBENCH_ROOT_FOLDER_ID,
        name: '我的文件',
        parentId: null,
        createdAt: now,
        updatedAt: now,
      },
    ],
    items: [],
    activeView: { kind: 'home' },
    selectedItemId: null,
  };
};

export const readHomeWorkbenchSession = (): HomeWorkbenchSession => {
  if (typeof window === 'undefined') return createDefaultHomeWorkbenchSession();
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return createDefaultHomeWorkbenchSession();
    const parsed = JSON.parse(raw) as Partial<HomeWorkbenchSession>;
    if (!parsed || parsed.version !== 1) return createDefaultHomeWorkbenchSession();

    const folders = Array.isArray(parsed.folders) ? parsed.folders.filter(isHomeWorkbenchFolder) : [];
    const items = Array.isArray(parsed.items) ? parsed.items.filter(isHomeWorkbenchItem) : [];
    const hasRoot = folders.some((folder) => folder.id === HOME_WORKBENCH_ROOT_FOLDER_ID);
    const normalizedFolders = hasRoot
      ? folders
      : [...createDefaultHomeWorkbenchSession().folders, ...folders];

    return {
      version: 1,
      folders: normalizedFolders,
      items,
      activeView: isHomeWorkbenchView(parsed.activeView) ? parsed.activeView : { kind: 'home' },
      selectedItemId: isString(parsed.selectedItemId) ? parsed.selectedItemId : null,
    };
  } catch {
    return createDefaultHomeWorkbenchSession();
  }
};

export const writeHomeWorkbenchSession = (session: HomeWorkbenchSession): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  scheduleBinaryStorePrune(session.items.map((item) => item.id));
};

export const registerHomeWorkbenchFile = (itemId: string, file: File): void => {
  if (!itemId || !file) return;

  liveFileStore.set(itemId, file);
  notifyBinaryListeners();

  void putStoreRecord(FILE_STORE_NAME, toPersistedFileRecord(itemId, file));
};

export const registerHomeWorkbenchFiles = (
  entries: Array<{ itemId: string; file: File }>
): void => {
  entries.forEach((entry) => registerHomeWorkbenchFile(entry.itemId, entry.file));
};

export const getHomeWorkbenchFile = (itemId: string): File | null => {
  const cached = liveFileStore.get(itemId) ?? null;
  if (!cached) {
    void loadFileFromPersistence(itemId);
  }
  return cached;
};

export const deleteHomeWorkbenchFile = (itemId: string): void => {
  if (!itemId) return;

  const hadFile = liveFileStore.delete(itemId);
  const hadConverted = liveConvertedPdfStore.delete(itemId);

  if (hadFile || hadConverted) {
    notifyBinaryListeners();
  }

  void Promise.all([
    deleteStoreRecord(FILE_STORE_NAME, itemId),
    deleteStoreRecord(CONVERTED_PDF_STORE_NAME, itemId),
  ]);
};

export const registerHomeWorkbenchConvertedPdf = (itemId: string, blob: Blob): void => {
  if (!itemId || !blob) return;

  liveConvertedPdfStore.set(itemId, blob);
  notifyBinaryListeners();

  void putStoreRecord(CONVERTED_PDF_STORE_NAME, toPersistedConvertedPdfRecord(itemId, blob));
};

export const getHomeWorkbenchConvertedPdf = (itemId: string): Blob | null => {
  const cached = liveConvertedPdfStore.get(itemId) ?? null;
  if (!cached) {
    void loadConvertedPdfFromPersistence(itemId);
  }
  return cached;
};

const writeStorageJson = (key: string, value: unknown): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(key, JSON.stringify(value));
};

const readStorageJson = (key: string): unknown => {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

const clearStorageKey = (key: string): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(key);
};

export const writeModule1DraftFromHomeWorkbench = (payload: {
  prompt: string;
  itemIds: string[];
}): void => {
  writeStorageJson(MODULE1_DRAFT_KEY, {
    prompt: payload.prompt,
    itemIds: payload.itemIds,
    createdAt: new Date().toISOString(),
  } satisfies Module1Draft);
};

export const consumeModule1DraftFromHomeWorkbench = async (): Promise<{
  prompt: string;
  files: File[];
  itemIds: string[];
} | null> => {
  const raw = readStorageJson(MODULE1_DRAFT_KEY);
  clearStorageKey(MODULE1_DRAFT_KEY);
  if (!isModule1Draft(raw)) return null;

  const files = (await Promise.all(raw.itemIds.map((itemId) => resolveHomeWorkbenchFile(itemId))))
    .filter((file): file is File => file instanceof globalThis.File);

  return {
    prompt: raw.prompt,
    itemIds: raw.itemIds,
    files,
  };
};

const writeModuleItemDraft = (key: string, itemIds: string[]): void => {
  writeStorageJson(key, {
    itemIds,
    createdAt: new Date().toISOString(),
  } satisfies ModuleItemDraft);
};

const consumeModuleItemDraft = async (key: string): Promise<{
  itemIds: string[];
  files: File[];
} | null> => {
  const raw = readStorageJson(key);
  clearStorageKey(key);
  if (!isModuleItemDraft(raw)) return null;

  const files = (await Promise.all(raw.itemIds.map((itemId) => resolveHomeWorkbenchFile(itemId))))
    .filter((file): file is File => file instanceof globalThis.File);

  return {
    itemIds: raw.itemIds,
    files,
  };
};

export const writeModule2DraftFromHomeWorkbench = (itemIds: string[]): void => {
  writeModuleItemDraft(MODULE2_DRAFT_KEY, itemIds);
};

export const consumeModule2DraftFromHomeWorkbench = async () =>
  consumeModuleItemDraft(MODULE2_DRAFT_KEY);

export const writeModule4DraftFromHomeWorkbench = (itemIds: string[]): void => {
  writeModuleItemDraft(MODULE4_DRAFT_KEY, itemIds);
};

export const readModule4DraftFromHomeWorkbench = (): { itemIds: string[] } | null => {
  const raw = readStorageJson(MODULE4_DRAFT_KEY);
  if (!isModuleItemDraft(raw)) return null;
  return { itemIds: raw.itemIds };
};

export const clearModule4DraftFromHomeWorkbench = (): void => {
  clearStorageKey(MODULE4_DRAFT_KEY);
};

if (typeof window !== 'undefined') {
  void ensureHomeWorkbenchPersistenceReady();
}
