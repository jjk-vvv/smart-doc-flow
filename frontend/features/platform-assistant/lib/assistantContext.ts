import type { AssistantContextEnvelope } from '../../../shared/api/platformAssistant';
import {
  readExtractionDocuments,
  readExtractionUpdatedAt,
  subscribeExtractionUpdates,
  type ExtractionDocument,
} from '../../../shared/state/extractionDocuments';

import type { PlatformTabId } from './platformAssistant';

export type ContextDocument = {
  id: string;
  name: string;
  track: string;
  fieldCount: number;
  warningCount: number;
};

export type AssistantExtractionSnapshot = {
  documents: ContextDocument[];
  updatedAt: string | null;
};

export const summarizeAssistantDocuments = (
  documents: ExtractionDocument[],
): ContextDocument[] =>
  documents.slice(0, 3).map((document) => ({
    id: `${document.file_hash}-${document.track}`,
    name: document.file_name,
    track: document.track,
    fieldCount: Object.keys(document.result || {}).length,
    warningCount: Array.isArray(document.soft_warnings) ? document.soft_warnings.length : 0,
  }));

export const readAssistantExtractionSnapshot = (): AssistantExtractionSnapshot => ({
  documents: summarizeAssistantDocuments(readExtractionDocuments()),
  updatedAt: readExtractionUpdatedAt(),
});

export const subscribeAssistantExtractionSnapshot = (
  handler: (snapshot: AssistantExtractionSnapshot) => void,
): (() => void) =>
  subscribeExtractionUpdates(() => {
    handler(readAssistantExtractionSnapshot());
  });

export const buildAssistantRequestContext = (
  activeTab: PlatformTabId,
  pageCue: string,
  documents: ContextDocument[],
): AssistantContextEnvelope => ({
  activeTab,
  pageCue,
  documents: documents.map((document) => ({
    fileName: document.name,
    track: document.track,
    fieldCount: document.fieldCount,
    warningCount: document.warningCount,
  })),
});
