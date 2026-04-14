import React from 'react';
import {
  BookOpen,
  ChevronRight,
  LogIn,
  LogOut,
  Moon,
  Sun,
  User,
  Shield,
  HelpCircle,
  Settings,
  Bell,
  Wallet
} from 'lucide-react';
import { cn } from '../../lib/utils';
import type { AuthUser } from '../../shared/api/auth';

type MobileProfilePageProps = {
  user: AuthUser;
  onNavigate: (target: string) => void;
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
        'group relative flex w-full items-center gap-4 bg-white px-5 py-[18px] text-left transition-colors active:bg-slate-50 dark:bg-[#1A1D24] dark:active:bg-[#1A1D24]/80',
        className
      )}
    >
      <div className={cn(
        "flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] transition-colors",
        isDestructive 
          ? "bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400"
          : "bg-slate-100/80 text-slate-600 dark:bg-white/[0.04] dark:text-slate-300",
        iconClassName
      )}>
        <Icon size={18} strokeWidth={2.2} />
      </div>
      <span className={cn(
        "flex-1 text-[16px] font-medium tracking-wide",
        isDestructive
          ? "text-red-600 dark:text-red-400"
          : "text-slate-800 dark:text-slate-100",
        labelClassName
      )}>
        {label}
      </span>
      {rightContent && (
        <div className="text-[14px] font-medium text-slate-400 dark:text-slate-500">
          {rightContent}
        </div>
      )}
      {showChevron && !isDestructive && (
        <ChevronRight size={18} strokeWidth={2} className="ml-1.5 text-slate-300 dark:text-slate-600" />
      )}
    </button>
  );
};

export const MobileProfilePage: React.FC<MobileProfilePageProps> = ({
  user,
  onNavigate,
  onOpenAccountSecurity,
  onToggleTheme,
  isDark,
  onLogout,
}) => {
  const avatarText = user?.name ? user.name.slice(0, 1).toUpperCase() : user?.email ? user.email.slice(0, 1).toUpperCase() : 'U';

  return (
    <div className="min-h-screen bg-[#F8FAFC] pb-[calc(56px+env(safe-area-inset-bottom)+24px)] dark:bg-[#0B1120]">
      {/* Impeccable Header Area with Avatar */}
      <div className="relative overflow-hidden px-6 pb-10 pt-[max(4rem,env(safe-area-inset-top))]">
        {/* Impeccable Seamless Background */}
        <div className="absolute inset-0 bg-white dark:bg-[#0F1523]" />
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-[#F8FAFC] to-transparent dark:from-[#0B1120]" />
        
        {/* Decorative Background Elements - Subdued for better texture */}
        <div className="pointer-events-none absolute right-0 top-0 h-64 w-64 -translate-y-1/3 translate-x-1/3 rounded-full bg-cyan-100/30 blur-3xl dark:bg-cyan-900/10" />
        <div className="pointer-events-none absolute left-0 top-12 h-48 w-48 -translate-x-1/2 rounded-full bg-blue-100/30 blur-3xl dark:bg-blue-900/10" />
        
        <div className="relative z-10 flex items-center gap-5">
          {/* Avatar Container - Impeccable refinement */}
          <div className="relative flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-[28px] font-bold text-white shadow-md shadow-blue-500/20 dark:shadow-none">
            {user ? avatarText : <User size={32} strokeWidth={2} />}
            {user && (
              <div className="absolute bottom-0 right-0 h-4 w-4 rounded-full border-[2.5px] border-white bg-emerald-500 dark:border-[#0F1523]" />
            )}
          </div>
          
          {/* User Info */}
          <div className="flex flex-1 flex-col justify-center">
            {user ? (
              <>
                <h1 className="text-[22px] font-bold tracking-tight text-slate-900 dark:text-white">
                  {user.name || 'DocFlow 用户'}
                </h1>
                <p className="mt-0.5 text-[14px] text-slate-500 dark:text-slate-400">
                  {user.email || '完善个人信息获取更多权限'}
                </p>
                <div className="mt-2.5 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400 w-fit">
                  <Shield size={12} strokeWidth={2.5} />
                  已认证
                </div>
              </>
            ) : (
              <>
                <h1 className="text-[22px] font-bold tracking-tight text-slate-900 dark:text-white">
                  未登录
                </h1>
                <p className="mt-0.5 text-[14px] text-slate-500 dark:text-slate-400">
                  登录以同步您的所有文档与配置
                </p>
                <button
                  type="button"
                  onClick={onOpenAccountSecurity}
                  className="mt-3 inline-flex h-[32px] w-fit items-center justify-center rounded-full bg-slate-900 px-5 text-[13px] font-medium text-white transition-colors active:bg-slate-800 dark:bg-white dark:text-slate-900 dark:active:bg-slate-200"
                >
                  立即登录
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Settings Sections */}
      <div className="px-4 pt-4 space-y-7">
        
        {/* Account Section */}
        <section>
          <h2 className="mb-3 ml-2 text-[13px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">
            账户与安全
          </h2>
          <div className="overflow-hidden rounded-[20px] bg-white shadow-[0_2px_12px_rgba(15,23,42,0.03)] ring-1 ring-slate-100 dark:bg-[#1A1D24] dark:ring-white/[0.05]">
            <div className="divide-y divide-slate-50 dark:divide-white/[0.02]">
              <ProfileActionRow
                icon={User}
                label="账号资料"
                onClick={onOpenAccountSecurity}
                rightContent={user ? "已完善" : "去完善"}
              />
              <ProfileActionRow
                icon={Shield}
                label="安全设置"
                onClick={onOpenAccountSecurity}
              />
              <ProfileActionRow
                icon={Wallet}
                label="我的订阅"
                onClick={() => {}}
                rightContent="免费版"
              />
            </div>
          </div>
        </section>

        {/* Preferences Section */}
        <section>
          <h2 className="mb-3 ml-2 text-[13px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">
            偏好设置
          </h2>
          <div className="overflow-hidden rounded-[20px] bg-white shadow-[0_2px_12px_rgba(15,23,42,0.03)] ring-1 ring-slate-100 dark:bg-[#1A1D24] dark:ring-white/[0.05]">
            <div className="divide-y divide-slate-50 dark:divide-white/[0.02]">
              <ProfileActionRow
                icon={isDark ? Moon : Sun}
                label="外观模式"
                onClick={onToggleTheme}
                rightContent={isDark ? '深色模式' : '浅色模式'}
              />
              <ProfileActionRow
                icon={Bell}
                label="消息通知"
                onClick={() => {}}
                rightContent="已开启"
              />
            </div>
          </div>
        </section>

        {/* About Section */}
        <section>
          <h2 className="mb-3 ml-2 text-[13px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">
            关于与帮助
          </h2>
          <div className="overflow-hidden rounded-[20px] bg-white shadow-[0_2px_12px_rgba(15,23,42,0.03)] ring-1 ring-slate-100 dark:bg-[#1A1D24] dark:ring-white/[0.05]">
            <div className="divide-y divide-slate-50 dark:divide-white/[0.02]">
              <ProfileActionRow
                icon={BookOpen}
                label="操作指南"
                onClick={() => onNavigate('guide')}
              />
              <ProfileActionRow
                icon={HelpCircle}
                label="帮助与反馈"
                onClick={() => {}}
              />
              <ProfileActionRow
                icon={Settings}
                label="关于 DocFlow"
                onClick={() => {}}
                rightContent="v1.0.0"
              />
            </div>
          </div>
        </section>

        {/* Logout Section */}
        {user && (
          <section className="pt-2 pb-6">
            <button
              type="button"
              onClick={onLogout}
              className="flex w-full items-center justify-center gap-2 rounded-[20px] bg-red-50 py-4 text-[16px] font-medium tracking-wide text-red-600 transition-colors active:bg-red-100 dark:bg-red-500/10 dark:text-red-400 dark:active:bg-red-500/20"
            >
              <LogOut size={18} strokeWidth={2.2} />
              退出登录
            </button>
          </section>
        )}
      </div>
    </div>
  );
};