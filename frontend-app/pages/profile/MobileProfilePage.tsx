import React from 'react';
import {
  Bell,
  ChevronRight,
  HelpCircle,
  LogOut,
  Moon,
  Settings,
  Shield,
  Sun,
  User,
  Wallet,
} from 'lucide-react';

import { cn } from '../../lib/utils';
import type { AuthUser } from '../../shared/api/auth';

type MobileProfilePageProps = {
  user: AuthUser;
  onOpenAccountSecurity: () => void;
  onToggleTheme: () => void;
  isDark: boolean;
  onLogout: () => void;
};

type ProfileActionRowProps = {
  icon: React.ElementType;
  label: string;
  rightContent?: React.ReactNode;
  onClick: () => void;
  showChevron?: boolean;
  className?: string;
  iconClassName?: string;
  labelClassName?: string;
  isDestructive?: boolean;
};

const ProfileActionRow: React.FC<ProfileActionRowProps> = ({
  icon: Icon,
  label,
  rightContent,
  onClick,
  showChevron = true,
  className,
  iconClassName,
  labelClassName,
  isDestructive = false,
}) => {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'group relative flex w-full items-center gap-4 bg-white px-5 py-[18px] text-left transition-colors active:bg-slate-50 dark:bg-transparent dark:active:bg-white/[0.02]',
        className,
      )}
    >
      <div
        className={cn(
          'flex h-[32px] w-[32px] shrink-0 items-center justify-center rounded-[10px] transition-colors',
          isDestructive
            ? 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400'
            : 'bg-slate-50 text-slate-500 ring-1 ring-slate-900/5 dark:bg-white/[0.04] dark:text-slate-300 dark:ring-white/10',
          iconClassName,
        )}
      >
        <Icon size={16} strokeWidth={2.2} />
      </div>
      <span
        className={cn(
          'flex-1 text-[15px] font-medium tracking-wide',
          isDestructive ? 'text-red-600 dark:text-red-400' : 'text-slate-800 dark:text-slate-100',
          labelClassName,
        )}
      >
        {label}
      </span>
      {rightContent ? (
        <div className="mr-0.5 text-[13px] font-medium text-slate-400 dark:text-slate-500">{rightContent}</div>
      ) : null}
      {showChevron && !isDestructive ? (
        <ChevronRight size={16} strokeWidth={2.5} className="ml-1 text-slate-300 dark:text-slate-600" />
      ) : null}
    </button>
  );
};

export const MobileProfilePage: React.FC<MobileProfilePageProps> = ({
  user,
  onOpenAccountSecurity,
  onToggleTheme,
  isDark,
  onLogout,
}) => {
  const avatarText = user?.name
    ? user.name.slice(0, 1).toUpperCase()
    : user?.email
      ? user.email.slice(0, 1).toUpperCase()
      : 'U';

  return (
    <div className="min-h-[var(--app-visual-height,100dvh)] bg-[#F8FAFC] pb-[calc(var(--mobile-content-bottom)+24px)] dark:bg-[#0B1120]">
      <div className="relative overflow-hidden px-6 pb-6 pt-[max(3.5rem,var(--mobile-safe-top))]">
        <div className="absolute inset-0 bg-white dark:bg-[#0B1120]" />
        <div className="pointer-events-none absolute right-0 top-0 h-64 w-64 -translate-y-1/3 translate-x-1/3 rounded-full bg-cyan-100/20 blur-3xl dark:bg-cyan-900/10" />

        <div className="relative z-10 flex items-center gap-5">
          <div className="relative flex h-[64px] w-[64px] shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-cyan-500 text-[24px] font-bold text-white shadow-lg shadow-blue-500/20 dark:shadow-none">
            {user ? avatarText : <User size={28} strokeWidth={2} />}
            {user ? (
              <div className="absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full border-[2.5px] border-white bg-emerald-500 dark:border-[#0B1120]" />
            ) : null}
          </div>

          <div className="flex min-w-0 flex-1 flex-col justify-center">
            {user ? (
              <>
                <div className="flex min-w-0 items-center gap-2">
                  <h1 className="min-w-0 truncate text-[20px] font-bold tracking-tight text-slate-900 dark:text-white">
                    {user.name || 'DocFlow 用户'}
                  </h1>
                  <div className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400">
                    <Shield size={10} strokeWidth={2.5} />
                    已认证
                  </div>
                </div>
                <p className="mt-1 truncate text-[13px] text-slate-500 dark:text-slate-400">
                  {user.email || '完善个人信息可获取更多能力'}
                </p>
              </>
            ) : (
              <>
                <h1 className="text-[20px] font-bold tracking-tight text-slate-900 dark:text-white">未登录</h1>
                <p className="mt-1 text-[13px] text-slate-500 dark:text-slate-400">
                  登录后可同步你的文档、记录与偏好设置
                </p>
                <button
                  type="button"
                  onClick={onOpenAccountSecurity}
                  className="mt-3.5 inline-flex h-[32px] w-fit items-center justify-center rounded-full bg-slate-900 px-5 text-[13px] font-medium text-white transition-colors active:bg-slate-800 dark:bg-white dark:text-slate-900 dark:active:bg-slate-200"
                >
                  立即登录
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-5 px-4 pt-1">
        <section>
          <h2 className="mb-3.5 ml-2 text-[12px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            账户与安全
          </h2>
          <div className="overflow-hidden rounded-[24px] bg-white shadow-[0_8px_30px_rgba(0,0,0,0.04)] ring-1 ring-slate-900/5 dark:bg-white/[0.02] dark:ring-white/[0.05]">
            <div className="divide-y divide-slate-50 dark:divide-white/[0.02]">
              <ProfileActionRow
                icon={User}
                label="账号资料"
                onClick={onOpenAccountSecurity}
                rightContent={user ? '已完善' : '去完善'}
              />
              <ProfileActionRow icon={Shield} label="安全设置" onClick={onOpenAccountSecurity} />
              <ProfileActionRow icon={Wallet} label="我的订阅" onClick={() => {}} rightContent="免费版" />
            </div>
          </div>
        </section>

        <section>
          <h2 className="mb-3.5 ml-2 text-[12px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            偏好设置
          </h2>
          <div className="overflow-hidden rounded-[24px] bg-white shadow-[0_8px_30px_rgba(0,0,0,0.04)] ring-1 ring-slate-900/5 dark:bg-white/[0.02] dark:ring-white/[0.05]">
            <div className="divide-y divide-slate-50 dark:divide-white/[0.02]">
              <ProfileActionRow
                icon={isDark ? Moon : Sun}
                label="外观模式"
                onClick={onToggleTheme}
                rightContent={isDark ? '深色模式' : '浅色模式'}
              />
              <ProfileActionRow icon={Bell} label="消息通知" onClick={() => {}} rightContent="已开启" />
            </div>
          </div>
        </section>

        <section>
          <h2 className="mb-3.5 ml-2 text-[12px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            关于与帮助
          </h2>
          <div className="overflow-hidden rounded-[24px] bg-white shadow-[0_8px_30px_rgba(0,0,0,0.04)] ring-1 ring-slate-900/5 dark:bg-white/[0.02] dark:ring-white/[0.05]">
            <div className="divide-y divide-slate-50 dark:divide-white/[0.02]">
              <ProfileActionRow icon={HelpCircle} label="帮助与反馈" onClick={() => {}} />
              <ProfileActionRow icon={Settings} label="关于 DocFlow" onClick={() => {}} rightContent="v1.0.0" />
            </div>
          </div>
        </section>

        {user ? (
          <section className="pb-4 pt-6">
            <button
              type="button"
              onClick={onLogout}
              className="flex w-full items-center justify-center gap-2 rounded-full bg-red-50 py-4 text-[15px] font-medium tracking-wide text-red-600 transition-colors active:bg-red-100 dark:bg-red-500/10 dark:text-red-400 dark:active:bg-red-500/20"
            >
              <LogOut size={18} strokeWidth={2.2} />
              退出登录
            </button>
          </section>
        ) : null}
      </div>
    </div>
  );
};
