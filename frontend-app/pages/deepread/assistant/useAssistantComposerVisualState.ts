import { useEffect, useRef, useState } from 'react';

import type { AssistantComposerVisualState } from './thinkingState';

const PHASE_MIN_VISIBLE_MS: Record<AssistantComposerVisualState['phase'], number> = {
    idle: 0,
    thinking: 260,
    generating: 360,
};

const IDLE_TRANSITION_MIN_VISIBLE_MS = 420;

export function useAssistantComposerVisualState(
    targetState: AssistantComposerVisualState,
): AssistantComposerVisualState {
    const [renderState, setRenderState] = useState<AssistantComposerVisualState>(targetState);
    const visibleSinceRef = useRef<number>(targetState.phase === 'idle' ? 0 : Date.now());
    const pendingTargetRef = useRef<AssistantComposerVisualState>(targetState);
    const timerRef = useRef<number | null>(null);

    useEffect(() => {
        pendingTargetRef.current = targetState;

        if (timerRef.current !== null) {
            window.clearTimeout(timerRef.current);
            timerRef.current = null;
        }

        const commit = (nextState: AssistantComposerVisualState) => {
            visibleSinceRef.current = nextState.phase === 'idle' ? 0 : Date.now();
            setRenderState(nextState);
        };

        if (renderState.phase === targetState.phase) {
            if (renderState.label !== targetState.label) {
                setRenderState(targetState);
            }
            return;
        }

        if (renderState.phase === 'idle') {
            commit(targetState);
            return;
        }

        const elapsed = Date.now() - visibleSinceRef.current;
        const currentPhaseMin = PHASE_MIN_VISIBLE_MS[renderState.phase] || 0;
        const holdForTargetIdle = targetState.phase === 'idle'
            ? Math.max(currentPhaseMin, IDLE_TRANSITION_MIN_VISIBLE_MS)
            : currentPhaseMin;
        const remaining = Math.max(0, holdForTargetIdle - elapsed);

        if (remaining === 0) {
            commit(targetState);
            return;
        }

        timerRef.current = window.setTimeout(() => {
            timerRef.current = null;
            commit(pendingTargetRef.current);
        }, remaining);

        return () => {
            if (timerRef.current !== null) {
                window.clearTimeout(timerRef.current);
                timerRef.current = null;
            }
        };
    }, [renderState, targetState]);

    return renderState;
}
