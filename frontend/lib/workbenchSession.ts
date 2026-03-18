export type PersistedWorkbenchFile = {
  key: string;
  name: string;
  size: number;
  lastModified: number;
  ext: string;
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
  };
  files: PersistedExtractionJobFile[];
  errors: string[];
};

export type WorkbenchSessionSnapshot = {
  version: 1;
  activeDocIndex: number;
  activeDocFileHash?: string;
  selectedFiles: PersistedWorkbenchFile[];
  officePreviewMap: Record<string, PersistedOfficePreviewState>;
  extractionJob: PersistedExtractionJob | null;
};

const STORAGE_KEY = 'module2_workbench_session_v1';

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

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
};

export const clearWorkbenchSession = (): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(STORAGE_KEY);
};
