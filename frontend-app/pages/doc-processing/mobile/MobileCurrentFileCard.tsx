import React from 'react';
import { Eye, FileText } from 'lucide-react';

type MobileWorkbenchFile = {
  id: string;
  name: string;
  size: number;
  status: string;
};

type MobileCurrentFileCardProps = {
  currentFile: MobileWorkbenchFile | null;
  hasReport: boolean;
  formatFileSize: (bytes: number) => string;
  renderFileIcon: (file: MobileWorkbenchFile) => React.ReactNode;
  onOpenPreview: () => void;
  onOpenReport: () => void;
  primaryButtonClassName: string;
  secondaryButtonClassName: string;
  softPanelClassName: string;
};

export const MobileCurrentFileCard: React.FC<MobileCurrentFileCardProps> = ({
  currentFile,
  hasReport,
  formatFileSize,
  renderFileIcon,
  onOpenPreview,
  onOpenReport,
  primaryButtonClassName,
  secondaryButtonClassName,
  softPanelClassName,
}) => {
  if (!currentFile) {
    return null;
  }

  return (
    <div className={`mb-4 rounded-[26px] bg-white p-4 shadow-[0_8px_30px_rgba(0,0,0,0.04)] dark:bg-slate-900/80`}>
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3.5">
          <div className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-[16px] bg-slate-50 dark:bg-slate-800/80">
            {renderFileIcon(currentFile)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold text-slate-400 dark:text-slate-500">当前任务文件</p>
            <p className="mt-0.5 truncate text-[16px] font-bold text-slate-800 dark:text-slate-100">{currentFile.name}</p>
            <p className="mt-0.5 text-[12px] text-slate-500 dark:text-slate-400">
              {formatFileSize(currentFile.size)} · {currentFile.status === 'completed' ? '已完成处理' : currentFile.status === 'processing' ? '处理中' : '已就绪'}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onOpenPreview}
            className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-[16px] bg-slate-50 text-[14px] font-semibold text-slate-700 transition-colors hover:bg-slate-100 active:scale-[0.98] dark:bg-slate-800 dark:text-slate-300"
          >
            <Eye size={16} />
            查看预览
          </button>
          <button
            type="button"
            onClick={onOpenReport}
            disabled={!hasReport}
            className={`inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-[16px] text-[14px] font-semibold transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 ${
              hasReport
                ? 'bg-blue-500 text-white shadow-md shadow-blue-500/20 hover:bg-blue-600'
                : 'bg-slate-50 text-slate-400 dark:bg-slate-800 dark:text-slate-500'
            }`}
          >
            <FileText size={16} />
            查看报告
          </button>
        </div>
      </div>
    </div>
  );
};
