import { useEffect, useRef, useState } from 'react';

const MOBILE_OVERLAY_EVENT = 'smart-doc-flow:mobile-overlay-presence-change';

let overlaySequence = 0;
const activeOverlayIds = new Set<number>();

const readOverlayActive = (): boolean => {
  if (typeof document === 'undefined') return false;
  return document.documentElement.classList.contains('mobile-overlay-active');
};

const syncOverlayState = () => {
  if (typeof document === 'undefined') return;

  const isActive = activeOverlayIds.size > 0;
  const count = String(activeOverlayIds.size);
  document.documentElement.classList.toggle('mobile-overlay-active', isActive);
  document.body.classList.toggle('mobile-overlay-active', isActive);
  document.documentElement.dataset.mobileOverlayCount = count;
  document.body.dataset.mobileOverlayCount = count;

  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent(MOBILE_OVERLAY_EVENT, {
        detail: { active: isActive, count: activeOverlayIds.size },
      }),
    );
  }
};

export const useMobileOverlayRegistration = (active: boolean) => {
  const overlayIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active || typeof document === 'undefined') return undefined;

    if (overlayIdRef.current === null) {
      overlaySequence += 1;
      overlayIdRef.current = overlaySequence;
    }

    activeOverlayIds.add(overlayIdRef.current);
    syncOverlayState();

    return () => {
      if (overlayIdRef.current !== null) {
        activeOverlayIds.delete(overlayIdRef.current);
        syncOverlayState();
      }
    };
  }, [active]);
};

export const useMobileOverlayPresence = (): boolean => {
  const [isOverlayActive, setIsOverlayActive] = useState(readOverlayActive);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return undefined;
    }

    const sync = () => setIsOverlayActive(readOverlayActive());
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'data-mobile-overlay-count'],
    });

    window.addEventListener(MOBILE_OVERLAY_EVENT, sync);
    sync();

    return () => {
      observer.disconnect();
      window.removeEventListener(MOBILE_OVERLAY_EVENT, sync);
    };
  }, []);

  return isOverlayActive;
};
