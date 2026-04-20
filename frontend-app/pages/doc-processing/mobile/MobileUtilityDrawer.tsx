import React from 'react';
import { X } from 'lucide-react';

type MobileWorkbenchFile = {
  id: string;
  name: string;
  size: number;
  status: string;
};

type MobileConversationItem = {
  id: string;
  title: string;
  preview: string;
  active: boolean;
};

type MobileUtilityDrawerProps = {
  visible: boolean;
  fileCount: number;
  conversationCount: number;
  files: MobileWorkbenchFile[];
  conversations: MobileConversationItem[];
  selectedFileId: string | null;
  emptyStateClassName: string;
  primaryButtonClassName: string;
  secondaryButtonClassName: string;
  renderFileIcon: (file: MobileWorkbenchFile) => React.ReactNode;
  formatFileSize: (bytes: number) => string;
  onClose: () => void;
  onSelectFile: (fileId: string) => void;
  onSelectConversation: (conversationId: string) => void;
};

export const MobileUtilityDrawer: React.FC<MobileUtilityDrawerProps> = ({
  visible,
  fileCount,
  conversationCount,
  files,
  conversations,
  selectedFileId,
  emptyStateClassName,
  primaryButtonClassName,
  secondaryButtonClassName,
  renderFileIcon,
  formatFileSize,
  onClose,
  onSelectFile,
  onSelectConversation,
}) => {
  if (!visible) return null;

  return (
    <div className="absolute inset-0 z-40 flex items-end bg-slate-950/36 backdrop-blur-[2px]">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="关闭工具抽屉"
        onClick={onClose}
      />
      <div className="relative z-10 w-full rounded-t-[28px] border border-[#d9e4f8] bg-[linear-gradient(180deg,#ffffff,#f8fbff)] px-4 pb-6 pt-3 shadow-[0_-26px_64px_-42px_rgba(42,100,246,0.22)] dark:border-slate-700 dark:bg-slate-950/96">
        <div className="mx-auto mb-3 h-1.5 w-12 rounded-full bg-[#d6e3f7] dark:bg-slate-700" />
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h3 className="text-[18px] font-bold text-slate-800 dark:text-slate-100">文件与会话</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100/80 text-slate-500 transition active:scale-95 dark:bg-slate-800/80 dark:text-slate-400"
            aria-label="关闭抽屉"
          >
            <X size={16} />
          </button>
        </div>

        <div className="mt-2 space-y-5 overflow-y-auto pb-safe max-h-[70vh]">
          <div>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[15px] font-bold text-slate-800 dark:text-slate-100">文件列表</p>
              <span className="text-[12px] font-medium text-slate-400 dark:text-slate-500">{fileCount} 个</span>
            </div>
            <div className="space-y-2">
              {files.length === 0 ? (
                <div className="rounded-[20px] bg-slate-50/80 px-4 py-4 text-center text-[13px] text-slate-500 dark:bg-slate-800/40 dark:text-slate-400">
                  还没有上传文件。
                </div>
              ) : files.map((file) => (
                <button
                  key={file.id}
                  type="button"
                  onClick={() => onSelectFile(file.id)}
                  className={`group flex w-full items-center gap-3 rounded-[20px] px-4 py-3.5 text-left transition-colors ${
                    selectedFileId === file.id
                      ? 'bg-sky-50/80 dark:bg-sky-500/10'
                      : 'bg-white shadow-[0_2px_8px_rgba(0,0,0,0.02)] ring-1 ring-slate-100 dark:bg-slate-800/40 dark:ring-white/[0.02]'
                  }`}
                >
                  <div className="shrink-0 drop-shadow-sm transition-transform group-active:scale-95">
                    {renderFileIcon(file)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className={`truncate text-[14px] font-semibold ${selectedFileId === file.id ? 'text-sky-700 dark:text-sky-300' : 'text-slate-700 dark:text-slate-200'}`}>
                      {file.name}
                    </p>
                    <p className={`mt-0.5 text-[12px] font-medium ${selectedFileId === file.id ? 'text-sky-600/70 dark:text-sky-400/70' : 'text-slate-400 dark:text-slate-500'}`}>
                      {formatFileSize(file.size)} · {file.status}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[15px] font-bold text-slate-800 dark:text-slate-100">历史会话</p>
              <span className="text-[12px] font-medium text-slate-400 dark:text-slate-500">{conversationCount} 条</span>
            </div>
            <div className="space-y-2">
              {conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => onSelectConversation(conversation.id)}
                  className={`flex w-full flex-col justify-center rounded-[20px] px-4 py-3.5 text-left transition-colors ${
                    conversation.active
                      ? 'bg-sky-50/80 dark:bg-sky-500/10'
                      : 'bg-white shadow-[0_2px_8px_rgba(0,0,0,0.02)] ring-1 ring-slate-100 dark:bg-slate-800/40 dark:ring-white/[0.02]'
                  }`}
                >
                  <p className={`truncate text-[14px] font-semibold ${conversation.active ? 'text-sky-700 dark:text-sky-300' : 'text-slate-700 dark:text-slate-200'}`}>
                    {conversation.title}
                  </p>
                  <p className={`mt-1 line-clamp-2 text-[12px] leading-relaxed ${conversation.active ? 'text-sky-600/80 dark:text-sky-400/80' : 'text-slate-500 dark:text-slate-400'}`}>
                    {conversation.preview}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
