import React from 'react';

import type {
    AssistantActionPreview,
    AssistantCitation,
    AssistantObjectLock,
    AssistantToolEvent,
} from './types';

type AssistantCompanionPanelProps = {
    compact?: boolean;
    open: boolean;
    onToggle: () => void;
    warnings: string[];
    currentLock: AssistantObjectLock | null;
    citations: AssistantCitation[];
    actionPreview: AssistantActionPreview | null;
    runtimeEvents: AssistantToolEvent[];
    renderLockBanner: (compact?: boolean) => React.ReactNode;
    renderCitations: (citations?: AssistantCitation[] | null, compact?: boolean) => React.ReactNode;
    renderActionPreview: (preview: AssistantActionPreview, compact?: boolean) => React.ReactNode;
};

export const AssistantCompanionPanel: React.FC<AssistantCompanionPanelProps> = () => {
    // Keep evidence/tool events available in state for compatibility, but do not
    // render the companion/toolchain panel in the end-user assistant UI.
    return null;
};
