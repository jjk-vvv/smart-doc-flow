import { useEffect, useMemo, useState } from 'react';

export type ResponsiveDeviceClass =
  | 'compactPhone'
  | 'phone'
  | 'largePhone'
  | 'tabletPortrait'
  | 'desktop';

export type ResponsiveDeviceState = {
  width: number;
  height: number;
  deviceClass: ResponsiveDeviceClass;
  isMobile: boolean;
  isCompactPhone: boolean;
  isLargePhone: boolean;
  isTabletPortrait: boolean;
  isDesktop: boolean;
};

const getViewportSize = () => {
  if (typeof window === 'undefined') {
    return { width: 1024, height: 768 };
  }
  return {
    width: window.innerWidth,
    height: window.innerHeight,
  };
};

export const getResponsiveDeviceClass = (width: number): ResponsiveDeviceClass => {
  if (width < 360) return 'compactPhone';
  if (width < 430) return 'phone';
  if (width < 600) return 'largePhone';
  if (width < 1024) return 'tabletPortrait';
  return 'desktop';
};

export const useResponsiveDevice = (): ResponsiveDeviceState => {
  const [viewport, setViewport] = useState(getViewportSize);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    let frameId = 0;
    const viewportApi = window.visualViewport;

    const update = () => {
      frameId = 0;
      setViewport(getViewportSize());
    };

    const scheduleUpdate = () => {
      if (frameId !== 0) return;
      frameId = window.requestAnimationFrame(update);
    };

    scheduleUpdate();
    window.addEventListener('resize', scheduleUpdate);
    window.addEventListener('orientationchange', scheduleUpdate);
    viewportApi?.addEventListener('resize', scheduleUpdate);

    return () => {
      window.removeEventListener('resize', scheduleUpdate);
      window.removeEventListener('orientationchange', scheduleUpdate);
      viewportApi?.removeEventListener('resize', scheduleUpdate);
      if (frameId !== 0) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, []);

  return useMemo(() => {
    const deviceClass = getResponsiveDeviceClass(viewport.width);
    const isDesktop = deviceClass === 'desktop';
    return {
      ...viewport,
      deviceClass,
      isMobile: !isDesktop,
      isCompactPhone: deviceClass === 'compactPhone',
      isLargePhone: deviceClass === 'largePhone',
      isTabletPortrait: deviceClass === 'tabletPortrait',
      isDesktop,
    };
  }, [viewport]);
};
