import React from 'react';
import { Send, X, Plus, Mic } from 'lucide-react';

type MobileComposerFile = {
  id: string;
  name: string;
  selected: boolean;
};

type MobileComposerProps = {
  files: MobileComposerFile[];
  inputText: string;
  placeholder: string;
  disabled: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  secondaryButtonClassName: string;
  primaryButtonClassName: string;
  renderFileIcon: (file: MobileComposerFile) => React.ReactNode;
  onSelectFile: (fileId: string) => void;
  onRemoveFile: (fileId: string) => void;
  onInputChange: (value: string) => void;
  onKeyPress: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onUpload: () => void;
  onOpenUtilityDrawer: () => void;
  onStop: () => void;
  onSend: () => void;
};

export const MobileComposer: React.FC<MobileComposerProps> = ({
  files,
  inputText,
  placeholder,
  disabled,
  textareaRef,
  secondaryButtonClassName,
  primaryButtonClassName,
  renderFileIcon,
  onSelectFile,
  onRemoveFile,
  onInputChange,
  onKeyPress,
  onUpload,
  onOpenUtilityDrawer,
  onStop,
  onSend,
}) => (
  <div className="shrink-0 bg-white px-3 py-3 dark:bg-slate-950">
    <div className="flex flex-col rounded-[26px] bg-[#f4f4f5] dark:bg-[#212121]">
      {files.length > 0 && (
        <div className="custom-scrollbar overflow-x-auto px-4 pt-3">
          <div className="flex min-w-max gap-2 pb-1">
            {files.map((file) => (
              <button
                key={file.id}
                type="button"
                onClick={() => onSelectFile(file.id)}
                className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors ${
                  file.selected
                    ? 'bg-cyan-50 text-cyan-700 ring-1 ring-cyan-500/20 dark:bg-cyan-500/10 dark:text-cyan-300 dark:ring-cyan-500/30'
                    : 'bg-white text-slate-600 shadow-[0_2px_8px_rgba(0,0,0,0.04)] ring-1 ring-slate-200/60 dark:bg-slate-800 dark:text-slate-300 dark:ring-white/10'
                }`}
              >
                {renderFileIcon(file)}
                <span className="max-w-[140px] truncate">{file.name}</span>
                <span
                  className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-slate-200/50 dark:hover:bg-slate-700/50"
                  onClick={(event) => {
                    event.stopPropagation();
                    onRemoveFile(file.id);
                  }}
                >
                  <X size={12} strokeWidth={2.5} />
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="flex items-end gap-2 px-2 pb-2 pt-2 min-h-[52px]">
        <div className="flex shrink-0 items-center pl-1">
          <button
            type="button"
            onClick={onOpenUtilityDrawer}
            className="flex h-[36px] w-[36px] items-center justify-center rounded-full text-slate-400 transition-all hover:bg-slate-200/60 active:scale-95 dark:text-slate-300 dark:hover:bg-slate-800/60"
            title="更多操作"
            aria-label="更多操作"
          >
            <Plus size={26} strokeWidth={2} />
          </button>
        </div>

        <textarea
          ref={textareaRef}
          value={inputText}
          onChange={(event) => onInputChange(event.target.value)}
          onKeyPress={onKeyPress}
          placeholder={placeholder}
          className="min-h-[36px] max-h-[140px] w-full flex-1 resize-none bg-transparent px-2 pt-[10px] pb-[6px] text-[16px] leading-[20px] text-slate-900 outline-none placeholder:text-slate-500 dark:text-slate-100 dark:placeholder:text-[#9ca3af]"
          rows={1}
          disabled={disabled}
        />

        <div className="flex shrink-0 items-center gap-1">
          {disabled ? (
            <button
              type="button"
              onClick={onStop}
              className="flex h-[36px] w-[36px] items-center justify-center rounded-full bg-slate-900 text-white transition-colors hover:bg-slate-800 active:scale-95 dark:bg-white dark:text-slate-900"
              title="停止生成"
            >
              <X size={20} strokeWidth={2.5} />
            </button>
          ) : inputText.trim() ? (
            <button
              type="button"
              onClick={onSend}
              className="flex h-[36px] w-[36px] items-center justify-center rounded-full bg-slate-900 text-white transition-all hover:bg-slate-800 active:scale-95 dark:bg-white dark:text-slate-900"
              title="发送"
              aria-label="发送"
            >
              <Send size={18} strokeWidth={2} className="-ml-0.5" />
            </button>
          ) : (
            <button
              type="button"
              disabled
              className="flex h-[36px] w-[36px] items-center justify-center rounded-full text-slate-400 transition-all dark:text-slate-300"
              title="语音输入"
              aria-label="语音输入"
            >
              <Mic size={22} strokeWidth={2} />
            </button>
          )}
        </div>
      </div>
    </div>
  </div>
);
