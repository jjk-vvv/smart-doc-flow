import React from 'react';
import { RotateCw, Sparkles } from 'lucide-react';

type FollowUpItem = {
  label: string;
  prompt: string;
  icon: React.ComponentType<{ size?: number }>;
};

type MobileFollowUpSuggestionsProps = {
  items: FollowUpItem[];
  showBatchSwitcher: boolean;
  onRotate: () => void;
  onPick: (prompt: string) => void;
  disabled: boolean;
};

export const MobileFollowUpSuggestions: React.FC<MobileFollowUpSuggestionsProps> = ({
  items,
  showBatchSwitcher,
  onRotate,
  onPick,
  disabled,
}) => {
  if (items.length === 0) return null;

  return (
    <div className="rounded-[22px] border border-[#e7effc] bg-white/92 p-3 shadow-[0_12px_28px_-24px_rgba(42,100,246,0.12)] dark:border-slate-800 dark:bg-slate-950/72 dark:shadow-[0_16px_32px_-24px_rgba(2,6,23,0.84)]">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[#5d7390] dark:text-slate-400">
          <Sparkles size={13} className="text-[#1d4ed8] dark:text-sky-300" />
          猜你想做
        </div>
        {showBatchSwitcher && (
          <button
            type="button"
            onClick={onRotate}
            className="inline-flex items-center gap-1.5 rounded-full border border-[#dbe8fd] bg-white px-2.5 py-1 text-[11px] font-medium text-[#35516d] transition-colors hover:border-[#c8dcff] hover:bg-[#f7faff] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:bg-slate-800"
          >
            <RotateCw size={12} />
            换一批
          </button>
        )}
      </div>
      <div className="custom-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={`${item.label}-${item.prompt}`}
              type="button"
              onClick={() => onPick(item.prompt)}
              disabled={disabled}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[#dbe8fd] bg-white px-3 py-1.5 text-xs font-medium text-[#35516d] transition-all hover:-translate-y-0.5 hover:border-[#c8dcff] hover:bg-[#f7faff] hover:text-[#234a79] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:bg-slate-800 dark:hover:text-sky-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Icon size={13} />
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};
