type PersistedFileRecord = {
  fileId: string;
  blob: Blob;
  name: string;
  type: string;
  lastModified: number;
};

type PersistedBlobRecord = {
  fileId: string;
  blob: Blob;
  type: string;
};

export type Module1WorkbenchBinaryBundle = {
  fileId: string;
  file?: File | null;
  originalFile?: File | null;
  previewBlob?: Blob | null;
  convertedPdfBlob?: Blob | null;
};

const SNAPSHOT_KEY = 'module1_workbench_session_web_v1';
const BINARY_DB_NAME = 'module1_workbench_binary_store_web_v1';
const BINARY_DB_VERSION = 1;
const FILE_STORE_NAME = 'files';
const ORIGINAL_FILE_STORE_NAME = 'original_files';
const PREVIEW_BLOB_STORE_NAME = 'preview_blobs';
const CONVERTED_PDF_STORE_NAME = 'converted_pdf_blobs';

let binaryDbPromise: Promise<IDBDatabase | null> | null = null;

const isIndexedDbAvailable = (): boolean =>
  typeof window !== 'undefined' && typeof window.indexedDB !== 'undefined';

const openBinaryDb = async (): Promise<IDBDatabase | null> => {
  if (!isIndexedDbAvailable()) return null;

  if (!binaryDbPromise) {
    binaryDbPromise = new Promise<IDBDatabase | null>((resolve) => {
      try {
        const request = window.indexedDB.open(BINARY_DB_NAME, BINARY_DB_VERSION);

        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(FILE_STORE_NAME)) {
            db.createObjectStore(FILE_STORE_NAME, { keyPath: 'fileId' });
          }
          if (!db.objectStoreNames.contains(ORIGINAL_FILE_STORE_NAME)) {
            db.createObjectStore(ORIGINAL_FILE_STORE_NAME, { keyPath: 'fileId' });
          }
          if (!db.objectStoreNames.contains(PREVIEW_BLOB_STORE_NAME)) {
            db.createObjectStore(PREVIEW_BLOB_STORE_NAME, { keyPath: 'fileId' });
          }
          if (!db.objectStoreNames.contains(CONVERTED_PDF_STORE_NAME)) {
            db.createObjectStore(CONVERTED_PDF_STORE_NAME, { keyPath: 'fileId' });
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
  action: (store: IDBObjectStore) => IDBRequest<TResult>,
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
      reject(error instanceof Error ? error : new Error('module1 workbench store request failed'));
    };

    try {
      const transaction = db.transaction(storeName, mode);
      const store = transaction.objectStore(storeName);
      const request = action(store);

      request.onsuccess = () => finish((request.result as TResult | undefined) ?? null);
      request.onerror = () => fail(request.error || new Error('module1 workbench store request failed'));
      transaction.onerror = () => fail(transaction.error || new Error('module1 workbench transaction failed'));
      transaction.onabort = () => fail(transaction.error || new Error('module1 workbench transaction aborted'));
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

const deleteStoreRecord = async (storeName: string, fileId: string): Promise<void> => {
  await runStoreRequest(storeName, 'readwrite', (store) => store.delete(fileId));
};

const clearStore = async (storeName: string): Promise<void> => {
  await runStoreRequest(storeName, 'readwrite', (store) => store.clear());
};

const toPersistedFileRecord = (fileId: string, file: File): PersistedFileRecord => ({
  fileId,
  blob: file,
  name: file.name || 'restored-file',
  type: file.type || 'application/octet-stream',
  lastModified: Number.isFinite(file.lastModified) ? file.lastModified : Date.now(),
});

const restorePersistedFile = (record: PersistedFileRecord): File | null => {
  if (typeof globalThis.File !== 'function' || !record?.fileId || !(record.blob instanceof Blob)) {
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

const toPersistedBlobRecord = (fileId: string, blob: Blob, fallbackType: string): PersistedBlobRecord => ({
  fileId,
  blob,
  type: blob.type || fallbackType,
});

const restorePersistedBlob = (record: PersistedBlobRecord): Blob | null => {
  if (!record?.fileId || !(record.blob instanceof Blob)) return null;
  try {
    return record.blob.type
      ? record.blob
      : record.blob.slice(0, record.blob.size, record.type || 'application/octet-stream');
  } catch {
    return null;
  }
};

export const readModule1WorkbenchSessionSnapshot = <TSnapshot>(): TSnapshot | null => {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(SNAPSHOT_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as TSnapshot;
  } catch {
    return null;
  }
};

export const writeModule1WorkbenchSessionSnapshot = (snapshot: unknown): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot));
};

export const readModule1WorkbenchBinaryBundles = async (): Promise<Record<string, Module1WorkbenchBinaryBundle>> => {
  const [
    fileRecords,
    originalFileRecords,
    previewBlobRecords,
    convertedPdfRecords,
  ] = await Promise.all([
    getAllStoreRecords<PersistedFileRecord>(FILE_STORE_NAME),
    getAllStoreRecords<PersistedFileRecord>(ORIGINAL_FILE_STORE_NAME),
    getAllStoreRecords<PersistedBlobRecord>(PREVIEW_BLOB_STORE_NAME),
    getAllStoreRecords<PersistedBlobRecord>(CONVERTED_PDF_STORE_NAME),
  ]);

  const bundles: Record<string, Module1WorkbenchBinaryBundle> = {};
  const ensureBundle = (fileId: string): Module1WorkbenchBinaryBundle => {
    if (!bundles[fileId]) {
      bundles[fileId] = { fileId };
    }
    return bundles[fileId];
  };

  fileRecords.forEach((record) => {
    const restored = restorePersistedFile(record);
    if (!restored) return;
    ensureBundle(record.fileId).file = restored;
  });

  originalFileRecords.forEach((record) => {
    const restored = restorePersistedFile(record);
    if (!restored) return;
    ensureBundle(record.fileId).originalFile = restored;
  });

  previewBlobRecords.forEach((record) => {
    const restored = restorePersistedBlob(record);
    if (!restored) return;
    ensureBundle(record.fileId).previewBlob = restored;
  });

  convertedPdfRecords.forEach((record) => {
    const restored = restorePersistedBlob(record);
    if (!restored) return;
    ensureBundle(record.fileId).convertedPdfBlob = restored;
  });

  return bundles;
};

export const syncModule1WorkbenchBinaryBundles = async (
  bundles: Module1WorkbenchBinaryBundle[],
): Promise<void> => {
  const retainedFileIds = new Set(
    bundles.map((bundle) => String(bundle.fileId || '').trim()).filter(Boolean),
  );

  await Promise.all(
    bundles.flatMap((bundle) => {
      const fileId = String(bundle.fileId || '').trim();
      if (!fileId) return [];

      return [
        bundle.file
          ? putStoreRecord(FILE_STORE_NAME, toPersistedFileRecord(fileId, bundle.file))
          : deleteStoreRecord(FILE_STORE_NAME, fileId),
        bundle.originalFile
          ? putStoreRecord(ORIGINAL_FILE_STORE_NAME, toPersistedFileRecord(fileId, bundle.originalFile))
          : deleteStoreRecord(ORIGINAL_FILE_STORE_NAME, fileId),
        bundle.previewBlob
          ? putStoreRecord(PREVIEW_BLOB_STORE_NAME, toPersistedBlobRecord(fileId, bundle.previewBlob, bundle.previewBlob.type || 'application/octet-stream'))
          : deleteStoreRecord(PREVIEW_BLOB_STORE_NAME, fileId),
        bundle.convertedPdfBlob
          ? putStoreRecord(CONVERTED_PDF_STORE_NAME, toPersistedBlobRecord(fileId, bundle.convertedPdfBlob, 'application/pdf'))
          : deleteStoreRecord(CONVERTED_PDF_STORE_NAME, fileId),
      ];
    }),
  );

  await Promise.all(
    [
      FILE_STORE_NAME,
      ORIGINAL_FILE_STORE_NAME,
      PREVIEW_BLOB_STORE_NAME,
      CONVERTED_PDF_STORE_NAME,
    ].map(async (storeName) => {
      const storedKeys = await getAllStoreKeys(storeName);
      const orphanIds = storedKeys.filter((fileId) => !retainedFileIds.has(fileId));
      await Promise.all(orphanIds.map((fileId) => deleteStoreRecord(storeName, fileId)));
    }),
  );
};

export const clearModule1WorkbenchSession = async (): Promise<void> => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(SNAPSHOT_KEY);
  }

  await Promise.all([
    clearStore(FILE_STORE_NAME),
    clearStore(ORIGINAL_FILE_STORE_NAME),
    clearStore(PREVIEW_BLOB_STORE_NAME),
    clearStore(CONVERTED_PDF_STORE_NAME),
  ]);
};
