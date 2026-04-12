import React from 'react';
import { motion } from 'framer-motion';
import {
  BookOpen,
  ChevronRight,
  LogIn,
  LogOut,
  Moon,
  Shield,
  Sun,
  User,
  type LucideIcon,
} from 'lucide-react';

import { cn } from '../lib/utils';
import type { AuthUser } from '../shared/api/auth';

export type MobileDrawerItem = {
  id: string;
  label: string;
  desc: string;
  icon: LucideIcon;
};

type MobilePersonalDrawerProps = {
  user: AuthUser;
  avatarText?: string;
  isDark: boolean;
  activeTab: string;
  items: MobileDrawerItem[];
  onClose: () => void;
  onNavigate: (target: string) => void;
  onToggleTheme: () => void;
  onOpenAccountSecurity: () => void;
  onResetOnboarding: () => void;
  onLogin: () => void;
  onLogout: () => void;
};

type DrawerActionRowProps = {
  icon: LucideIcon;
  label: string;
  rightContent?: React.ReactNode;
  onClick: () => void;
  showChevron?: boolean;
  className?: string;
  iconClassName?: string;
  labelClassName?: string;
};

const DrawerActionRow: React.FC<DrawerActionRowProps> = ({
  icon: Icon,
  label,
  rightContent,
  onClick,
  showChevron = true,
  className,
  iconClassName,
  labelClassName,
}) => {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'group relative flex w-full items-center gap-3.5 bg-white px-4 py-[14px] text-left transition-colors active:bg-slate-50 dark:bg-slate-900 dark:active:bg-slate-800',
        className
      )}
    >
      <Icon size={20} strokeWidth={1.75} className={cn("shrink-0 text-slate-600 dark:text-slate-400", iconClassName)} />
      <span className={cn("flex-1 text-[15px] text-slate-800 dark:text-slate-200", labelClassName)}>{label}</span>
      {rightContent}
      {showChevron && (
        <ChevronRight size={16} className="ml-0.5 text-slate-300 dark:text-slate-600" />
      )}
    </button>
  );
};

export const MobilePersonalDrawer: React.FC<MobilePersonalDrawerProps> = ({
  user,
  avatarText,
  isDark,
  activeTab,
  items,
  onClose,
  onNavigate,
  onToggleTheme,
  onOpenAccountSecurity,
  onResetOnboarding,
  onLogin,
  onLogout,
}) => {
  const accountLabel = user?.name || '未登录用户';

  return (
    <>
      <motion.button
        type="button"
        aria-label="关闭个人菜单"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[60] bg-slate-950/40 backdrop-blur-[4px]"
      />
      <motion.aside
        initial={{ x: '-100%' }}
        animate={{ x: 0 }}
        exit={{ x: '-100%' }}
        transition={{ type: 'spring', stiffness: 320, damping: 32, mass: 0.9 }}
        className="fixed inset-y-0 left-0 z-[70] flex w-[85vw] max-w-[360px] flex-col overflow-hidden bg-[#F2F5F8] shadow-[24px_0_56px_rgba(15,23,42,0.2)] dark:bg-slate-950 dark:shadow-[20px_0_64px_rgba(0,0,0,0.6)]"
      >
        {/* Simple Header */}
        <div className="flex shrink-0 items-center justify-between px-5 pb-2 pt-[max(2.5rem,env(safe-area-inset-top))]">
          <h2 className="text-[20px] font-bold text-slate-900 dark:text-white">设置</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-[14px] text-slate-500 transition-colors hover:text-slate-700 dark:text-slate-400"
          >
            关闭
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-2 pb-8">
          {/* Account & Security Card */}
          <div className="mb-6 overflow-hidden rounded-2xl shadow-sm">
            <DrawerActionRow
              icon={User}
              label="账号与安全"
              onClick={user ? onOpenAccountSecurity : onLogin}
              rightContent={
                user ? (
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-cyan-100 text-[12px] font-bold text-cyan-600 dark:bg-cyan-900/50 dark:text-cyan-400">
                    {avatarText || accountLabel.slice(0, 1).toUpperCase()}
                  </div>
                ) : (
                  <span className="text-[13px] text-slate-400">未登录</span>
                )
              }
            />
          </div>

          {/* Features Section */}
          <section className="mb-6">
            <h3 className="mb-2 ml-1 text-[13px] text-slate-500 dark:text-slate-400">功能</h3>
            <div className="overflow-hidden rounded-2xl shadow-sm divide-y divide-slate-100 dark:divide-slate-800/50">
              {items.map((item) => (
                <DrawerActionRow
                  key={item.id}
                  icon={item.icon}
                  label={item.label}
                  onClick={() => onNavigate(item.id)}
                />
              ))}
              <DrawerActionRow
                icon={isDark ? Sun : Moon}
                label="模式选择"
                onClick={onToggleTheme}
                rightContent={
                  <span className="text-[13px] text-slate-400 dark:text-slate-500">
                    {isDark ? '深色模式' : '普通模式'}
                  </span>
                }
              />
              <DrawerActionRow
                icon={BookOpen}
                label="重新查看引导"
                onClick={onResetOnboarding}
              />
            </div>
          </section>

          {/* System/Bottom Section */}
          <section className="mt-8">
            <div className="overflow-hidden rounded-2xl shadow-sm">
              {user ? (
                <DrawerActionRow
                  icon={LogOut}
                  label="退出当前账号"
                  onClick={onLogout}
                />
              ) : (
                <DrawerActionRow
                  icon={LogIn}
                  label="登录 / 注册"
                  onClick={onLogin}
                  iconClassName="text-cyan-600 dark:text-cyan-400"
                  labelClassName="text-cyan-600 font-bold dark:text-cyan-400"
                  showChevron={false}
                />
              )}
            </div>
          </section>
        </div>
      </motion.aside>
    </>
  );
};
