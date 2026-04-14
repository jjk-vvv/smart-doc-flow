export type PersistedWorkbenchFile = {
  key: string;
  name: string;
  size: number;
  lastModified: number;
  ext: string;
  artifactFileId?: string;
  artifactByFileUrl?: string;
  artifactUrl?: string;
  artifactPath?: string;
};

export type PersistedOfficePreviewState = {
  status: 'idle' | 'queued' | 'running' | 'completed' | 'failed';
  jobId?: string;
  pdfUrl?: string;
  error?: string;
};

export type PersistedExtractionJobFile = {
  file_name: string;
  file_hash: string;
  status: string;
  stage: string;
  progress_ratio: number;
  message: string;
  artifact_file_id?: string | null;
  artifact_download_url?: string | null;
  artifact_by_file_url?: string | null;
  artifact_path?: string | null;
  artifact_url?: string | null;
  error?: string;
  track?: string;
  cached?: boolean;
};

export type PersistedExtractionJob = {
  job_id: string;
  status: string;
  terminal: boolean;
  created_at: number;
  updated_at: number;
  progress: {
    total_files: number;
    completed_files: number;
    failed_files: number;
    current_file_index: number;
    current_file_name: string;
    current_stage: string;
    progress_ratio: number;
    queued_files?: number;
    running_files?: Array<{
      file_index?: number;
      file_name: string;
      stage: string;
      status?: string;
      progress_ratio: number;
    }>;
    active_stages?: Record<string, number>;
    parallel_workers?: number;
  };
  files: PersistedExtractionJobFile[];
  errors: string[];
};

export type PersistedSmartUnitTab = 'results' | 'assistant';

export type WorkbenchSessionSnapshot = {
  version: 1;
  activeDocIndex: number;
  activeDocFileHash?: string;
  smartUnitTab?: PersistedSmartUnitTab;
  selectedFiles: PersistedWorkbenchFile[];
  officePreviewMap: Record<string, PersistedOfficePreviewState>;
  extractionJob: PersistedExtractionJob | null;
};

const STORAGE_KEY = 'module2_workbench_session_v1';
export const WORKBENCH_SESSION_UPDATED_EVENT = 'module2-workbench-session-updated';

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

const normalizeSmartUnitTab = (value: unknown): PersistedSmartUnitTab =>
  value === 'assistant' ? 'assistant' : 'results';

export const readWorkbenchSession = (): WorkbenchSessionSnapshot | null => {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<WorkbenchSessionSnapshot>;
    if (!parsed || parsed.version !== 1) return null;
    return {
      version: 1,
      activeDocIndex: Math.max(0, Number(parsed.activeDocIndex || 0)),
      activeDocFileHash: String(parsed.activeDocFileHash || '').trim(),
      smartUnitTab: normalizeSmartUnitTab(parsed.smartUnitTab),
      selectedFiles: Array.isArray(parsed.selectedFiles) ? parsed.selectedFiles : [],
      officePreviewMap: isObjectRecord(parsed.officePreviewMap) ? (parsed.officePreviewMap as Record<string, PersistedOfficePreviewState>) : {},
      extractionJob: parsed.extractionJob && isObjectRecord(parsed.extractionJob)
        ? (parsed.extractionJob as PersistedExtractionJob)
        : null,
    };
  } catch {
    return null;
  }
};

export const writeWorkbenchSession = (snapshot: WorkbenchSessionSnapshot): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  window.dispatchEvent(new Event(WORKBENCH_SESSION_UPDATED_EVENT));
};

export const clearWorkbenchSession = (): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(WORKBENCH_SESSION_UPDATED_EVENT));
};

export const subscribeWorkbenchSessionUpdates = (handler: () => void): (() => void) => {
  if (typeof window === 'undefined') return () => undefined;
  const onCustom = () => handler();
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      handler();
    }
  };
  window.addEventListener(WORKBENCH_SESSION_UPDATED_EVENT, onCustom);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(WORKBENCH_SESSION_UPDATED_EVENT, onCustom);
    window.removeEventListener('storage', onStorage);
  };
};
