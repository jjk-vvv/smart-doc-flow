import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Laptop,
  LogOut,
  RefreshCw,
  Shield,
  Trash2,
  X,
} from 'lucide-react';

import {
  listAuthSessions,
  logoutAuth,
  revokeAuthSession,
  revokeOtherAuthSessions,
  type AuthSessionItem,
  type AuthUser,
} from '../shared/api/auth';

interface AccountSecurityModalProps {
  show: boolean;
  user: NonNullable<AuthUser> | null;
  onClose: () => void;
  onLoggedOut: () => void;
}

const UI_TEXT = {
  title: '账户安全',
  subtitle: '管理当前账号的登录设备与会话状态。',
  currentSession: '当前设备',
  sessionList: '登录设备',
  noSessions: '暂时没有可展示的会话记录。',
  refresh: '刷新',
  refreshing: '刷新中...',
  revokeOthers: '下线其他设备',
  revokingOthers: '处理中...',
  revokeSession: '下线设备',
  revokingSession: '下线中...',
  signOutCurrent: '退出当前登录',
  signingOutCurrent: '退出中...',
  unsupportedMode: '当前运行在文件存储兼容模式，暂不支持持久化会话管理。',
  footerHint: '敏感操作完成后，建议重新确认当前账号登录状态。',
  unknownDevice: '未知设备',
  unknownIp: '未知 IP',
  createdAt: '登录时间',
  lastSeenAt: '最近活动',
  expiresAt: '过期时间',
  statusActive: '活跃',
  statusRevoked: '已撤销',
  statusExpired: '已过期',
} as const;

const formatDateTime = (value?: string | null): string => {
  const raw = String(value || '').trim();
  if (!raw) return '-';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

const getErrorMessage = (err: unknown, fallback: string) =>
  err instanceof Error && err.message.trim() ? err.message.trim() : fallback;

const statusLabel = (status: string): string => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'revoked') return UI_TEXT.statusRevoked;
  if (normalized === 'expired') return UI_TEXT.statusExpired;
  return UI_TEXT.statusActive;
};

const statusClasses = (status: string): string => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'revoked') {
    return 'bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400';
  }
  if (normalized === 'expired') {
    return 'bg-slate-100 text-slate-600 dark:bg-white/5 dark:text-slate-400';
  }
  return 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400';
};

export const AccountSecurityModal: React.FC<AccountSecurityModalProps> = ({
  show,
  user,
  onClose,
  onLoggedOut,
}) => {
  const [sessions, setSessions] = useState<AuthSessionItem[]>([]);
  const [supportsPersistentSessions, setSupportsPersistentSessions] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRevokingOthers, setIsRevokingOthers] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [revokingSessionId, setRevokingSessionId] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const loadSessions = async (mode: 'initial' | 'refresh' = 'initial') => {
    if (!show || !user) {
      return;
    }
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    setError('');
    try {
      const payload = await listAuthSessions();
      setSessions(Array.isArray(payload.sessions) ? payload.sessions : []);
      setSupportsPersistentSessions(Boolean(payload.supportsPersistentSessions));
    } catch (err) {
      const message = getErrorMessage(err, '加载会话列表失败，请稍后重试。');
      setError(message);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (!show || !user) {
      setSessions([]);
      setError('');
      setNotice('');
      setSupportsPersistentSessions(true);
      setIsLoading(false);
      setIsRefreshing(false);
      setIsRevokingOthers(false);
      setIsSigningOut(false);
      setRevokingSessionId('');
      return;
    }
    void loadSessions('initial');
  }, [show, user]);

  if (!show || !user) {
    return null;
  }

  const hasRevocableOtherSessions = sessions.some(
    (session) => !session.current && String(session.status || '').trim().toLowerCase() === 'active',
  );

  const handleRefresh = async () => {
    setNotice('');
    await loadSessions('refresh');
  };

  const handleRevokeOthers = async () => {
    setError('');
    setNotice('');
    setIsRevokingOthers(true);
    try {
      const payload = await revokeOtherAuthSessions();
      setNotice(payload.message || '其他设备已下线。');
      await loadSessions('refresh');
    } catch (err) {
      const message = getErrorMessage(err, '下线其他设备失败，请稍后重试。');
      setError(message);
    } finally {
      setIsRevokingOthers(false);
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    const normalizedSessionId = String(sessionId || '').trim();
    if (!normalizedSessionId) return;
    setError('');
    setNotice('');
    setRevokingSessionId(normalizedSessionId);
    try {
      const payload = await revokeAuthSession(normalizedSessionId);
      setNotice(payload.message || '设备会话已下线。');
      await loadSessions('refresh');
    } catch (err) {
      const message = getErrorMessage(err, '下线设备失败，请稍后重试。');
      setError(message);
    } finally {
      setRevokingSessionId('');
    }
  };

  const handleSignOutCurrent = async () => {
    setError('');
    setNotice('');
    setIsSigningOut(true);
    try {
      await logoutAuth();
      onClose();
      onLoggedOut();
    } catch (err) {
      const message = getErrorMessage(err, '退出当前登录失败，请稍后重试。');
      setError(message);
    } finally {
      setIsSigningOut(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-slate-900/40 px-4 backdrop-blur-sm transition-all">
      <div
        data-testid="account-security-modal"
        className="relative flex max-h-[88vh] w-full max-w-[840px] flex-col overflow-hidden rounded-2xl border border-slate-200/60 bg-white shadow-2xl dark:border-white/10 dark:bg-[#0A0A0B] dark:shadow-[0_0_60px_-15px_rgba(0,0,0,0.7)]"
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-5 top-5 z-10 rounded-full p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-white/10 dark:hover:text-slate-200"
        >
          <X size={18} />
        </button>

        <div className="border-b border-slate-200/60 bg-white px-7 py-6 dark:border-white/10 dark:bg-[#0A0A0B]">
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-100 bg-slate-50/50 text-slate-700 shadow-sm dark:border-white/5 dark:bg-white/[0.02] dark:text-slate-300">
              <Shield size={20} className="opacity-80" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">{UI_TEXT.title}</div>
              <div className="mt-1 text-[13px] text-slate-500 dark:text-slate-400">{UI_TEXT.subtitle}</div>
              <div className="mt-4 flex flex-wrap items-center gap-3 text-[13px] text-slate-500 dark:text-slate-400">
                <div className="flex items-center gap-2">
                  <div className="flex h-5 w-5 items-center justify-center overflow-hidden rounded-full bg-slate-200 text-[10px] font-bold text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                    {(user.name || user.email || 'U')[0].toUpperCase()}
                  </div>
                  <span className="font-medium text-slate-700 dark:text-slate-300">{user.name || '当前用户'}</span>
                </div>
                <span className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600"></span>
                <span>{user.email || '未设置邮箱'}</span>
                {user.tenantId ? (
                  <>
                    <span className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600"></span>
                    <span className="font-mono text-[12px]">Tenant: {user.tenantId}</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-1 flex-col overflow-hidden px-7 py-6">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{UI_TEXT.sessionList}</div>
              <div className="mt-1 text-[13px] text-slate-500 dark:text-slate-400">
                {supportsPersistentSessions
                  ? '你可以主动管理其他设备上的登录会话。'
                  : UI_TEXT.unsupportedMode}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleRefresh}
                disabled={isRefreshing || isLoading}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200/60 bg-white px-3 text-[13px] font-medium text-slate-600 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-300 dark:hover:bg-white/[0.06] dark:hover:text-white"
              >
                <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
                {isRefreshing ? UI_TEXT.refreshing : UI_TEXT.refresh}
              </button>
              <button
                type="button"
                onClick={handleRevokeOthers}
                disabled={!supportsPersistentSessions || !hasRevocableOtherSessions || isRevokingOthers}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-900 px-3 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-slate-800 hover:shadow active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200 dark:disabled:bg-white/10 dark:disabled:text-white/30"
              >
                <Shield size={14} />
                {isRevokingOthers ? UI_TEXT.revokingOthers : UI_TEXT.revokeOthers}
              </button>
              <button
                type="button"
                onClick={handleSignOutCurrent}
                disabled={isSigningOut}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-red-200/60 bg-white px-3 text-[13px] font-medium text-red-600 shadow-sm transition-all hover:bg-red-50 hover:text-red-700 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-500/20 dark:bg-transparent dark:text-red-400 dark:hover:bg-red-500/10 dark:hover:text-red-300"
              >
                <LogOut size={14} />
                {isSigningOut ? UI_TEXT.signingOutCurrent : UI_TEXT.signOutCurrent}
              </button>
            </div>
          </div>

          {error ? (
            <div className="mb-5 flex items-start gap-2.5 rounded-lg bg-red-50 px-4 py-3 text-[13px] text-red-600 dark:bg-red-500/10 dark:text-red-400">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}

          {notice ? (
            <div className="mb-5 flex items-start gap-2.5 rounded-lg bg-emerald-50 px-4 py-3 text-[13px] text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400">
              <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
              <span>{notice}</span>
            </div>
          ) : null}

          <div className="min-h-0 flex-1 overflow-y-auto pr-2 custom-scrollbar">
            {isLoading ? (
              <div className="flex h-56 items-center justify-center text-[13px] text-slate-500 dark:text-slate-400">
                {UI_TEXT.refreshing}
              </div>
            ) : sessions.length === 0 ? (
              <div className="flex h-56 items-center justify-center rounded-xl border border-dashed border-slate-200/60 bg-slate-50/50 text-[13px] text-slate-500 dark:border-white/5 dark:bg-white/[0.01] dark:text-slate-400">
                {UI_TEXT.noSessions}
              </div>
            ) : (
              <div className="space-y-3">
                {sessions.map((session) => {
                  const normalizedStatus = String(session.status || '').trim().toLowerCase();
                  const canRevoke = supportsPersistentSessions && !session.current && normalizedStatus === 'active';
                  const busy = revokingSessionId === session.sessionId;
                  return (
                    <div
                      key={session.sessionId}
                      data-testid={`account-session-row-${session.sessionId}`}
                      className="group relative flex flex-col gap-4 rounded-xl border border-slate-200/60 bg-white p-5 shadow-sm transition-all hover:border-slate-300 hover:shadow-md dark:border-white/5 dark:bg-white/[0.02] dark:hover:border-white/10 dark:hover:bg-white/[0.04] sm:flex-row sm:items-start sm:justify-between"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-3">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-50 text-slate-500 ring-1 ring-slate-200/60 dark:bg-white/[0.02] dark:text-slate-400 dark:ring-white/10">
                            <Laptop size={16} />
                          </div>
                          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                            <span className="truncate text-[14px] font-semibold text-slate-900 dark:text-slate-100" title={session.userAgent || UI_TEXT.unknownDevice}>
                              {session.userAgent || UI_TEXT.unknownDevice}
                            </span>
                            {session.current && (
                              <span className="shrink-0 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-600 dark:bg-blue-500/10 dark:text-blue-400">
                                {UI_TEXT.currentSession}
                              </span>
                            )}
                            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${statusClasses(session.status)}`}>
                              {statusLabel(session.status)}
                            </span>
                          </div>
                        </div>

                        <div className="mt-5 grid grid-cols-2 gap-y-4 gap-x-6 sm:grid-cols-4">
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">IP Address</span>
                            <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{session.ipAddress || UI_TEXT.unknownIp}</span>
                          </div>
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">{UI_TEXT.createdAt}</span>
                            <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{formatDateTime(session.createdAt)}</span>
                          </div>
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">{UI_TEXT.lastSeenAt}</span>
                            <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{formatDateTime(session.lastSeenAt)}</span>
                          </div>
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">{UI_TEXT.expiresAt}</span>
                            <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{formatDateTime(session.expiresAt)}</span>
                          </div>
                        </div>
                      </div>

                      <div className="absolute right-5 top-5 sm:static sm:mt-1">
                        {canRevoke && (
                          <button
                            type="button"
                            onClick={() => handleRevokeSession(session.sessionId)}
                            disabled={busy}
                            className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-red-600 opacity-100 transition-colors hover:bg-red-50 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 sm:opacity-0 sm:group-hover:opacity-100 dark:text-red-400 dark:hover:bg-red-500/10"
                          >
                            <Trash2 size={14} />
                            {busy ? UI_TEXT.revokingSession : UI_TEXT.revokeSession}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="mt-6 border-t border-slate-100 pt-4 text-center text-[12px] text-slate-400 dark:border-white/5 dark:text-slate-500">{UI_TEXT.footerHint}</div>
        </div>
      </div>
    </div>
  );
};
