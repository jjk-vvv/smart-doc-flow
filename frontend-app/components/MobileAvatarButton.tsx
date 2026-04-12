import React from 'react';
import { User } from 'lucide-react';

import { cn } from '../lib/utils';

type MobileAvatarButtonProps = {
  avatarText?: string;
  onClick: () => void;
  className?: string;
  ariaLabel?: string;
};

export const MobileAvatarButton: React.FC<MobileAvatarButtonProps> = ({
  avatarText,
  onClick,
  className,
  ariaLabel = '打开个人菜单',
}) => {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      className={cn(
        'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-white/70 bg-white/92 text-slate-700 shadow-[0_12px_26px_rgba(15,23,42,0.12)] transition-transform duration-200 hover:-translate-y-0.5 dark:border-white/10 dark:bg-slate-900/92 dark:text-slate-200',
        className,
      )}
    >
      {avatarText ? (
        <span className="text-sm font-bold">{avatarText}</span>
      ) : (
        <User size={18} strokeWidth={2.3} />
      )}
    </button>
  );
};
