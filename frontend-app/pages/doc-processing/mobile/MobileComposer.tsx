import React, { useState } from 'react';
import { CornerDownLeft, X, Plus } from 'lucide-react';

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
}) => {
  const [isFocused, setIsFocused] = useState(false);
  
  // 核心状态：是否有内容或者是否处于焦点状态
  const isExpanded = isFocused || inputText.trim().length > 0 || files.length > 0;

  return (
    <div className="absolute bottom-0 left-0 right-0 z-50 px-4 pb-[calc(16px+env(safe-area-inset-bottom))] pt-8 bg-gradient-to-t from-white/95 via-white/80 to-transparent dark:from-[#0B1120]/95 dark:via-[#0B1120]/80 dark:to-transparent pointer-events-none">
      <div 
        className={`pointer-events-auto flex flex-col relative transition-all duration-300 ease-[cubic-bezier(0.23,1,0.32,1)] bg-white dark:bg-slate-900 border border-slate-200/80 shadow-[0_8px_30px_rgba(0,0,0,0.06)] dark:border-white/10 dark:shadow-[0_8px_30px_rgba(0,0,0,0.3)] ${
          isExpanded ? 'rounded-[20px] min-h-[90px]' : 'rounded-[24px] min-h-[48px]'
        }`}
      >
        {files.length > 0 && (
          <div className="custom-scrollbar overflow-x-auto px-2 pt-2.5 pb-1">
            <div className="flex min-w-max gap-2 pb-0.5 pl-2">
              {files.map((file) => (
                <button
                  key={file.id}
                  type="button"
                  onClick={() => onSelectFile(file.id)}
                  className={`inline-flex items-center gap-1.5 rounded-[12px] px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                    file.selected
                      ? 'bg-blue-50 text-blue-700 shadow-sm ring-1 ring-blue-500/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/30'
                      : 'bg-slate-50 text-slate-600 ring-1 ring-slate-200/60 dark:bg-slate-800/60 dark:text-slate-300 dark:ring-white/10'
                  }`}
                >
                  <div className="flex items-center justify-center opacity-90 scale-90">
                    {renderFileIcon(file)}
                  </div>
                  <span className="max-w-[120px] truncate leading-none pt-[1px]">{file.name}</span>
                  <span
                    className="ml-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-slate-200/80 text-slate-500 transition-colors hover:bg-slate-300 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
                    onClick={(event) => {
                      event.stopPropagation();
                      onRemoveFile(file.id);
                    }}
                  >
                    <X size={10} strokeWidth={3} />
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        
        <div className="relative flex flex-1 w-full">
          {/* 左侧绝对定位：+ 号 */}
          <div 
            className={`absolute z-10 transition-all duration-300 ease-[cubic-bezier(0.23,1,0.32,1)] ${
              isExpanded ? 'bottom-[6px] left-[6px]' : 'top-1/2 -translate-y-1/2 left-[6px]'
            }`}
          >
            <button
              type="button"
              onClick={onUpload}
              className="relative flex h-[36px] w-[36px] items-center justify-center rounded-full text-slate-500 transition-all active:scale-95 dark:text-slate-400"
              title="上传文件"
              aria-label="上传文件"
            >
              <Plus size={26} strokeWidth={2} />
            </button>
          </div>

          {/* 输入框主体 */}
          <textarea
            ref={textareaRef}
            value={inputText}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyPress={onKeyPress}
            placeholder={placeholder}
            className={`w-full resize-none bg-transparent text-[16px] leading-[22px] text-slate-900 outline-none placeholder:text-slate-500 dark:text-slate-100 dark:placeholder:text-[#9ca3af] transition-all duration-300 ease-[cubic-bezier(0.23,1,0.32,1)] ${
              isExpanded 
                ? 'min-h-[48px] max-h-[140px] px-3 pt-3 pb-[42px]' 
                : 'h-[48px] px-[46px] py-[13px] whitespace-nowrap overflow-hidden text-ellipsis'
            }`}
            rows={1}
            disabled={disabled}
          />

          {/* 右侧绝对定位：麦克风 / 发送按钮 */}
          <div 
            className={`absolute z-10 transition-all duration-300 ease-[cubic-bezier(0.23,1,0.32,1)] ${
              isExpanded ? 'bottom-[6px] right-[6px]' : 'top-1/2 -translate-y-1/2 right-[6px]'
            }`}
          >
            {disabled ? (
              <button
                type="button"
                onClick={onStop}
                className="flex h-[36px] w-[36px] items-center justify-center rounded-full bg-slate-900 text-white transition-colors hover:bg-slate-800 active:scale-95 dark:bg-white dark:text-slate-900"
                title="停止生成"
              >
                <X size={18} strokeWidth={2.5} />
              </button>
            ) : (
              <button
                type="button"
                onClick={onSend}
                disabled={!inputText.trim() && files.length === 0}
                className="flex h-[36px] w-[36px] items-center justify-center rounded-full transition-all disabled:text-slate-400 enabled:bg-slate-900 enabled:text-white enabled:active:scale-95 dark:disabled:text-slate-500 dark:enabled:bg-white dark:enabled:text-slate-900"
                title="发送"
                aria-label="发送"
              >
                <CornerDownLeft size={18} strokeWidth={2} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
