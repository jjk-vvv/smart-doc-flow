import React, { useMemo } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';

import { cn } from '../../../lib/utils';
import { deriveAssistantComposerState, type AssistantComposerVisualState } from './thinkingState';
import type { AssistantDialogMessage } from './types';
import { useAssistantComposerVisualState } from './useAssistantComposerVisualState';

const PHASE_TRANSITION = {
    duration: 0.28,
    ease: [0.22, 1, 0.36, 1] as const,
};
const LABEL_TRANSITION = {
    duration: 0.22,
    ease: [0.25, 1, 0.5, 1] as const,
};

const STATUS_STYLES: Record<
    Exclude<AssistantComposerVisualState['phase'], 'idle'>,
    {
        textClassName: string;
        textStyle?: React.CSSProperties;
        signalCoreClassName: string;
        signalGlowClassName: string;
        signalRingClassName: string;
        dotClassName: string;
        railClassName: string;
        pulseDuration: number;
        dotDelayStep: number;
        shimmerText?: boolean;
    }
> = {
    thinking: {
        textClassName: 'text-slate-600 dark:text-slate-300',
        signalCoreClassName: 'bg-gradient-to-br from-slate-400 via-slate-300 to-slate-500 dark:from-slate-300 dark:via-slate-200 dark:to-slate-400',
        signalGlowClassName: 'bg-slate-300/75 dark:bg-slate-200/70',
        signalRingClassName: 'border-slate-400/35 dark:border-slate-100/35',
        dotClassName: 'bg-slate-500/80 dark:bg-slate-100/90',
        railClassName: 'from-slate-400/80 via-slate-300/40 to-transparent dark:from-slate-100/85 dark:via-slate-100/35 dark:to-transparent',
        pulseDuration: 1.8,
        dotDelayStep: 0.14,
    },
    generating: {
        textClassName:
            'bg-gradient-to-r from-slate-600 via-slate-500 to-slate-700 bg-clip-text text-transparent dark:from-slate-200 dark:via-slate-300 dark:to-slate-100',
        textStyle: {
            backgroundSize: '200% 100%',
        },
        signalCoreClassName: 'bg-gradient-to-br from-slate-500 via-slate-400 to-slate-600 dark:from-slate-200 dark:via-slate-300 dark:to-slate-100',
        signalGlowClassName: 'bg-slate-400/80 dark:bg-slate-300/80',
        signalRingClassName: 'border-slate-500/40 dark:border-slate-200/40',
        dotClassName: 'bg-slate-600/90 dark:bg-slate-100/90',
        railClassName: 'from-slate-500/90 via-slate-400/50 to-transparent dark:from-slate-200/90 dark:via-slate-200/40 dark:to-transparent',
        pulseDuration: 1.4,
        dotDelayStep: 0.1,
        shimmerText: true,
    },
};

type AssistantComposerStatusProps = {
    isLoading: boolean;
    streamingMessage?: AssistantDialogMessage | null;
    className?: string;
};

export const AssistantComposerStatus: React.FC<AssistantComposerStatusProps> = ({
    isLoading,
    streamingMessage,
    className,
}) => {
    const prefersReducedMotion = useReducedMotion();
    const targetState = useMemo(
        () => deriveAssistantComposerState({ isLoading, message: streamingMessage }),
        [isLoading, streamingMessage],
    );
    const renderState = useAssistantComposerVisualState(targetState);

    const activeStyle =
        renderState.phase === 'idle'
            ? null
            : STATUS_STYLES[renderState.phase];
    const showStatus = renderState.phase !== 'idle' && activeStyle;

    return (
        <div
            aria-live="polite"
            aria-atomic="true"
            className={cn(
                'min-h-[18px] px-1 pb-1 text-left',
                className,
            )}
        >
            <AnimatePresence initial={false}>
                {showStatus ? (
                    <motion.div
                        layout
                        initial={prefersReducedMotion ? false : { opacity: 0, y: 3 }}
                        animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
                        exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: -2 }}
                        transition={PHASE_TRANSITION}
                        className="inline-flex min-h-[18px] items-center gap-2 overflow-visible pl-0.5"
                    >
                        <span className="relative inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center">
                            <motion.span
                                aria-hidden="true"
                                className={cn(
                                    'absolute inset-0 rounded-full blur-[7px]',
                                    activeStyle.signalGlowClassName,
                                )}
                                animate={
                                    prefersReducedMotion
                                        ? { opacity: 0.26, scale: 1 }
                                        : { opacity: [0.14, 0.42, 0.14], scale: [0.82, 1.52, 0.82] }
                                }
                                transition={{
                                    duration: activeStyle.pulseDuration,
                                    repeat: Number.POSITIVE_INFINITY,
                                    ease: [0.16, 1, 0.3, 1],
                                }}
                            />
                            <motion.span
                                aria-hidden="true"
                                className={cn(
                                    'absolute h-[11px] w-[11px] rounded-full border',
                                    activeStyle.signalRingClassName,
                                )}
                                animate={
                                    prefersReducedMotion
                                        ? { opacity: 0.32, scale: 1 }
                                        : {
                                            opacity: [0.2, 0.46, 0.2],
                                            scale: [0.88, 1.08, 0.88],
                                            rotate: renderState.phase === 'generating' ? [0, 8, 0] : 0,
                                        }
                                }
                                transition={{
                                    duration: activeStyle.pulseDuration + 0.08,
                                    repeat: Number.POSITIVE_INFINITY,
                                    ease: [0.25, 1, 0.5, 1],
                                }}
                            />
                            <motion.span
                                aria-hidden="true"
                                className={cn(
                                    'absolute h-[6px] w-[6px] rounded-full shadow-[0_0_0_1px_rgba(255,255,255,0.22)]',
                                    activeStyle.signalCoreClassName,
                                )}
                                animate={
                                    prefersReducedMotion
                                        ? { scale: 1 }
                                        : renderState.phase === 'generating'
                                            ? { scale: [1, 1.14, 1], rotate: [0, 10, 0] }
                                            : { scale: [1, 1.06, 1] }
                                }
                                transition={{
                                    duration: activeStyle.pulseDuration * 0.9,
                                    repeat: Number.POSITIVE_INFINITY,
                                    ease: [0.22, 1, 0.36, 1],
                                }}
                            />
                        </span>

                        <div className="inline-flex min-w-0 flex-col">
                            <div className="inline-flex items-center gap-1.5">
                                <AnimatePresence initial={false} mode="popLayout">
                                    <motion.span
                                        key={renderState.label}
                                        layout="position"
                                        initial={prefersReducedMotion ? false : { opacity: 0, y: 2, filter: 'blur(3px)' }}
                                        animate={
                                            prefersReducedMotion
                                                ? {
                                                    opacity: 1,
                                                    y: 0,
                                                    filter: 'blur(0px)',
                                                    backgroundPosition: '0% 50%',
                                                }
                                                : {
                                                    opacity: 1,
                                                    y: 0,
                                                    filter: 'blur(0px)',
                                                    backgroundPosition: activeStyle.shimmerText
                                                        ? ['0% 50%', '100% 50%', '0% 50%']
                                                        : '0% 50%',
                                                }
                                        }
                                        exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: -2, filter: 'blur(3px)' }}
                                        transition={{
                                            ...LABEL_TRANSITION,
                                            backgroundPosition: activeStyle.shimmerText
                                                ? {
                                                    duration: 1.9,
                                                    repeat: Number.POSITIVE_INFINITY,
                                                    ease: 'linear',
                                                }
                                                : undefined,
                                        }}
                                        className={cn(
                                            'text-[11px] font-medium tracking-[0.01em]',
                                            activeStyle.textClassName,
                                        )}
                                        style={activeStyle.textStyle}
                                    >
                                        {renderState.label}
                                    </motion.span>
                                </AnimatePresence>

                                <span aria-hidden="true" className="inline-flex items-center gap-[4px] pt-[1px]">
                                    {[0, 1, 2].map((index) => (
                                        <motion.span
                                            key={`${renderState.phase}-${index}`}
                                            className={cn('h-[3px] w-[3px] rounded-full', activeStyle.dotClassName)}
                                            animate={
                                                prefersReducedMotion
                                                    ? { opacity: 0.72, scale: 1 }
                                                    : {
                                                        opacity: [0.22, 1, 0.22],
                                                        scale: [0.7, 1.05, 0.7],
                                                        y: [0, -0.8, 0],
                                                    }
                                            }
                                            transition={{
                                                duration: activeStyle.pulseDuration * 0.72,
                                                repeat: Number.POSITIVE_INFINITY,
                                                ease: [0.25, 1, 0.5, 1],
                                                delay: index * activeStyle.dotDelayStep,
                                            }}
                                        />
                                    ))}
                                </span>
                            </div>

                            <motion.span
                                aria-hidden="true"
                                className={cn(
                                    'mt-[3px] block h-px origin-left rounded-full bg-gradient-to-r',
                                    activeStyle.railClassName,
                                )}
                                animate={
                                    prefersReducedMotion
                                        ? { opacity: 0.82, scaleX: 1, x: 0 }
                                        : { opacity: [0.44, 0.92, 0.44], scaleX: [0.9, 1, 0.9], x: [0, 4, 0] }
                                }
                                transition={{
                                    duration: activeStyle.pulseDuration + 0.28,
                                    repeat: Number.POSITIVE_INFINITY,
                                    ease: [0.22, 1, 0.36, 1],
                                }}
                            />
                        </div>
                    </motion.div>
                ) : (
                    <span className="sr-only">Assistant idle</span>
                )}
            </AnimatePresence>
        </div>
    );
};
