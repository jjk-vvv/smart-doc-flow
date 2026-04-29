import { useEffect, useMemo, useState } from 'react';

export type VisualViewportState = {
  width: number;
  height: number;
  offsetTop: number;
  offsetLeft: number;
  keyboardInset: number;
};

const getVisualViewportState = (): VisualViewportState => {
  if (typeof window === 'undefined') {
    return {
      width: 1024,
      height: 768,
      offsetTop: 0,
      offsetLeft: 0,
      keyboardInset: 0,
    };
  }

  const visualViewport = window.visualViewport;
  const width = visualViewport?.width ?? window.innerWidth;
  const height = visualViewport?.height ?? window.innerHeight;
  const offsetTop = visualViewport?.offsetTop ?? 0;
  const offsetLeft = visualViewport?.offsetLeft ?? 0;
  const keyboardInset = Math.max(0, window.innerHeight - height - offsetTop);

  return {
    width,
    height,
    offsetTop,
    offsetLeft,
    keyboardInset,
  };
};

const setViewportCssVariables = (state: VisualViewportState) => {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.style.setProperty('--app-visual-width', `${state.width}px`);
  root.style.setProperty('--app-visual-height', `${state.height}px`);
  root.style.setProperty('--app-visual-offset-top', `${state.offsetTop}px`);
  root.style.setProperty('--app-keyboard-inset', `${state.keyboardInset}px`);
};

export const useVisualViewport = (): VisualViewportState => {
  const [viewport, setViewport] = useState(getVisualViewportState);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    let frameId = 0;
    const visualViewport = window.visualViewport;

    const update = () => {
      frameId = 0;
      const next = getVisualViewportState();
      setViewport(next);
      setViewportCssVariables(next);
    };

    const scheduleUpdate = () => {
      if (frameId !== 0) return;
      frameId = window.requestAnimationFrame(update);
    };

    scheduleUpdate();
    window.addEventListener('resize', scheduleUpdate);
    window.addEventListener('orientationchange', scheduleUpdate);
    visualViewport?.addEventListener('resize', scheduleUpdate);
    visualViewport?.addEventListener('scroll', scheduleUpdate);

    return () => {
      window.removeEventListener('resize', scheduleUpdate);
      window.removeEventListener('orientationchange', scheduleUpdate);
      visualViewport?.removeEventListener('resize', scheduleUpdate);
      visualViewport?.removeEventListener('scroll', scheduleUpdate);
      if (frameId !== 0) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, []);

  return useMemo(() => viewport, [viewport]);
};
