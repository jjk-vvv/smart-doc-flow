import type { ReactNode } from 'react';

import { cn } from '../../lib/utils';

type MobilePageShellProps = {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  withBottomNav?: boolean;
  constrain?: 'none' | 'phone' | 'tablet';
};

export const MobilePageShell = ({
  children,
  className,
  contentClassName,
  withBottomNav = true,
  constrain = 'phone',
}: MobilePageShellProps) => {
  return (
    <div className={cn('mobile-page-shell', className)}>
      <div
        className={cn(
          'mobile-page-content',
          constrain === 'phone' && 'mobile-page-content-phone',
          constrain === 'tablet' && 'mobile-page-content-tablet',
          withBottomNav && 'mobile-page-content-with-nav',
          contentClassName,
        )}
      >
        {children}
      </div>
    </div>
  );
};
