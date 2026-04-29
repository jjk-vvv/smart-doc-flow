import React, { useEffect, useRef, useState } from 'react';
import { X, Mail, Lock, User, Phone, ArrowRight, CheckCircle2 } from 'lucide-react';

import {
  type AuthUser,
  loginAuth,
  registerAuth,
  resetForgotPassword,
  sendForgotCode,
  sendRegisterCode,
} from '../shared/api/auth';
import { cn } from '../lib/utils';
import { useMobileOverlayRegistration } from '../shared/hooks/useMobileOverlayPresence';

interface AuthModalProps {
  show: boolean;
  onClose: () => void;
  onLoginSuccess: (user: NonNullable<AuthUser>) => void;
}

const AUTH_TEXT = {
  devCodeAlert: '【本地开发调试】\n当前未配置真实',
  devCodeServiceSuffix: '服务，已返回模拟验证码。\n验证码：',
  loginTitle: '欢迎回来',
  registerTitle: '创建账号',
  forgotTitle: '重置密码',
  loginSubtitle: '登录您的账号以继续使用平台。',
  registerSubtitle: '填写以下信息完成注册。',
  registerSuccess: '注册成功，正在登录您的账号。',
  forgotHintSent: '验证码已发送至 ',
  forgotHintSentSuffix: '，请完成验证后重置密码。',
  forgotHintInput: '验证码已发送，请输入验证码并设置新密码。',
  forgotHintDefault: '验证身份后即可重置密码。',
  accountLabel: '账号',
  accountPlaceholder: '邮箱 / 手机号',
  passwordLabel: '密码',
  passwordPlaceholder: '请输入密码',
  forgotPassword: '忘记密码？',
  loginAction: '立即登录',
  noAccount: '还没有账号？',
  registerAction: '立即注册',
  usernameLabel: '用户名',
  usernamePlaceholder: '您的名称',
  phoneLabel: '手机号',
  phonePlaceholder: '您的手机号',
  emailLabel: '联系邮箱',
  emailPlaceholder: '您的邮箱',
  emailCodeLabel: '邮箱验证码',
  emailCodePlaceholder: '6 位邮箱验证码',
  sendingCode: '发送中',
  resendSuffix: '秒后重发',
  getCode: '获取验证码',
  setPasswordPlaceholder: '设置登录密码',
  confirmPasswordLabel: '确认密码',
  confirmPasswordPlaceholder: '再次输入密码',
  createAccount: '创建账号',
  hasAccount: '已有账号？',
  directLogin: '直接登录',
  contactLabel: '联系方式',
  contactPlaceholder: '注册邮箱 / 手机号',
  codeLabel: '验证码',
  codePlaceholder: '输入 6 位验证码',
  sendingCodeEllipsis: '发送中...',
  newPasswordLabel: '新密码',
  newPasswordPlaceholder: '设置新密码（至少 6 位）',
  confirmNewPasswordLabel: '确认新密码',
  confirmNewPasswordPlaceholder: '再次输入新密码',
  resetting: '重置中...',
  resetPassword: '重置密码',
  backToLogin: '返回登录',
} as const;

const getErrorMessage = (error: unknown, fallback: string) => {
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  return fallback;
};

const showDevCodeAlert = (channel: '邮箱' | '短信', devCode?: string) => {
  if (!devCode) return;

  alert(
    AUTH_TEXT.devCodeAlert + channel + AUTH_TEXT.devCodeServiceSuffix + devCode,
  );
};

export const AuthModal: React.FC<AuthModalProps> = ({
  show,
  onClose,
  onLoginSuccess,
}) => {
  useMobileOverlayRegistration(show);

  const [authView, setAuthView] = useState<'login' | 'register' | 'forgot'>('login');

  const baseInputClasses =
    "flex h-[44px] w-full items-center rounded-[12px] border border-slate-200 bg-white px-3 text-[14px] text-slate-900 transition-all placeholder:text-slate-400/80 hover:border-slate-300 hover:bg-slate-50 focus:border-slate-400 focus:bg-white focus:outline-none focus:ring-[3px] focus:ring-slate-400/20 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-200 dark:placeholder:text-slate-500 dark:hover:border-white/20 dark:hover:bg-white/[0.04] dark:focus:border-slate-500 dark:focus:bg-white/[0.05] dark:focus:ring-slate-500/20";

  const [loginForm, setLoginForm] = useState({ account: '', password: '' });
  const [registerForm, setRegisterForm] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    confirmPassword: '',
    code: '',
  });
  const [forgotForm, setForgotForm] = useState({
    contact: '',
    code: '',
    newPassword: '',
    confirmPassword: '',
  });

  const [verificationSent, setVerificationSent] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [maskedContact, setMaskedContact] = useState('');
  const [registerError, setRegisterError] = useState('');
  const [registerSuccess, setRegisterSuccess] = useState('');
  const [loginError, setLoginError] = useState('');
  const [forgotError, setForgotError] = useState('');
  const [forgotSuccess, setForgotSuccess] = useState('');
  const [isNewUser, setIsNewUser] = useState(false);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (countdown <= 0) {
      return undefined;
    }

    countdownRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (countdownRef.current) {
            clearInterval(countdownRef.current);
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
      }
    };
  }, [countdown]);

  useEffect(() => {
    if (!show) {
      return;
    }

    setAuthView('login');
    setLoginForm({ account: '', password: '' });
    setRegisterForm({
      name: '',
      email: '',
      phone: '',
      password: '',
      confirmPassword: '',
      code: '',
    });
    setForgotForm({ contact: '', code: '', newPassword: '', confirmPassword: '' });
    setRegisterError('');
    setRegisterSuccess('');
    setLoginError('');
    setForgotError('');
    setForgotSuccess('');
    setVerificationSent(false);
    setCountdown(0);
    setMaskedContact('');
    setIsNewUser(false);
    setIsSendingCode(false);
    setIsResetting(false);
  }, [show]);

  if (!show) return null;

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError('');

    try {
      const data = await loginAuth(loginForm);
      onLoginSuccess(data.user);
      onClose();
    } catch (error) {
      setLoginError(getErrorMessage(error, '登录失败，请稍后重试。'));
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setRegisterError('');
    setRegisterSuccess('');

    if (registerForm.password !== registerForm.confirmPassword) {
      setRegisterError('两次输入的密码不一致。');
      return;
    }

    if (!registerForm.code || !/^\d{6}$/.test(registerForm.code)) {
      setRegisterError('请输入正确的 6 位验证码。');
      return;
    }

    if (!/^1[3-9]\d{9}$/.test(registerForm.phone)) {
      setRegisterError('请输入正确的手机号。');
      return;
    }

    try {
      const data = await registerAuth({
        name: registerForm.name,
        email: registerForm.email,
        phone: registerForm.phone,
        password: registerForm.password,
        code: registerForm.code,
      });
      setIsNewUser(true);
      onLoginSuccess(data.user);
      onClose();
    } catch (error) {
      setRegisterError(getErrorMessage(error, '注册失败，请稍后重试。'));
    }
  };

  const handleSendRegisterCode = async () => {
    setRegisterError('');
    setRegisterSuccess('');

    if (!registerForm.email.trim() || !registerForm.email.includes('@')) {
      setRegisterError('请输入有效的邮箱地址后再获取验证码。');
      return;
    }

    setIsSendingCode(true);
    try {
      const data = await sendRegisterCode(registerForm.email.trim());
      const nextMaskedContact = data.maskedContact || registerForm.email.trim();
      setCountdown(60);
      setRegisterSuccess(`验证码已发送至 ${nextMaskedContact}，请检查收件箱和垃圾邮件。`);
      showDevCodeAlert('邮箱', data.devCode);
    } catch (error) {
      const message = getErrorMessage(error, '验证码发送失败，请稍后重试。');
      if (message.toLowerCase().includes('already registered')) {
        setRegisterError('该邮箱已注册，请直接登录或使用忘记密码。');
      } else {
        setRegisterError(message);
      }
    } finally {
      setIsSendingCode(false);
    }
  };

  const handleSendCode = async () => {
    setForgotError('');
    setForgotSuccess('');

    if (!forgotForm.contact.trim()) {
      setForgotError('请输入注册时使用的手机号或邮箱。');
      return;
    }

    setIsSendingCode(true);
    try {
      const data = await sendForgotCode(forgotForm.contact.trim());
      const nextMaskedContact = data.maskedContact || forgotForm.contact.trim();
      setVerificationSent(true);
      setCountdown(60);
      setMaskedContact(nextMaskedContact);
      setForgotSuccess(`验证码已发送至 ${nextMaskedContact}，请查收。`);
      showDevCodeAlert('短信', data.devCode);
    } catch (error) {
      setForgotError(getErrorMessage(error, '验证码发送失败，请稍后重试。'));
    } finally {
      setIsSendingCode(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotError('');
    setForgotSuccess('');

    if (!forgotForm.code.trim()) {
      setForgotError('请输入验证码。');
      return;
    }

    if (!forgotForm.newPassword) {
      setForgotError('请设置新密码。');
      return;
    }

    if (forgotForm.newPassword.length < 6) {
      setForgotError('密码长度至少为 6 位。');
      return;
    }

    if (forgotForm.newPassword !== forgotForm.confirmPassword) {
      setForgotError('两次输入的新密码不一致。');
      return;
    }

    setIsResetting(true);
    try {
      const data = await resetForgotPassword({
        contact: forgotForm.contact.trim(),
        code: forgotForm.code.trim(),
        newPassword: forgotForm.newPassword,
      });
      setForgotSuccess(data.message || '密码已重置，请重新登录。');
      setForgotError('');
      window.setTimeout(() => {
        setAuthView('login');
        setForgotForm({ contact: '', code: '', newPassword: '', confirmPassword: '' });
        setVerificationSent(false);
        setCountdown(0);
        setMaskedContact('');
        setForgotSuccess('');
      }, 2000);
    } catch (error) {
      setForgotError(getErrorMessage(error, '密码重置失败，请稍后重试。'));
    } finally {
      setIsResetting(false);
    }
  };

  const forgotHint = maskedContact
    ? AUTH_TEXT.forgotHintSent + maskedContact + AUTH_TEXT.forgotHintSentSuffix
    : verificationSent
      ? AUTH_TEXT.forgotHintInput
      : AUTH_TEXT.forgotHintDefault;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/40 p-4 pt-[max(1rem,var(--mobile-safe-top))] pb-[max(1rem,var(--mobile-safe-bottom))] dark:bg-black/60 backdrop-blur-md animate-in fade-in duration-300">
      <div className="relative flex max-h-[calc(var(--app-visual-height,100dvh)-2rem)] w-full max-w-[420px] flex-col overflow-hidden rounded-[24px] border border-white/60 bg-white/95 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.1)] backdrop-blur-xl animate-in zoom-in-95 duration-300 dark:border-white/[0.05] dark:bg-[#0B1120]/95 dark:shadow-[0_20px_80px_-15px_rgba(0,0,0,0.6)]">
        <button
          onClick={onClose}
          className="absolute right-5 top-5 z-10 flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition-all hover:bg-slate-100 hover:text-slate-600 dark:text-slate-500 dark:hover:bg-white/10 dark:hover:text-slate-300"
        >
          <X size={18} className="currentColor" />
        </button>

        <div className="overflow-y-auto p-6 sm:p-8">
          <div className="mb-6 text-center">
            <h2 className="mb-2.5 text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              {authView === 'login' && AUTH_TEXT.loginTitle}
              {authView === 'register' && AUTH_TEXT.registerTitle}
              {authView === 'forgot' && AUTH_TEXT.forgotTitle}
            </h2>
            <p className="text-sm text-slate-500">
              {authView === 'login' && AUTH_TEXT.loginSubtitle}
              {authView === 'register' && AUTH_TEXT.registerSubtitle}
              {authView === 'forgot' && forgotHint}
            </p>
          </div>

          {isNewUser && (
            <div className="mb-6 flex items-center gap-3 rounded-[10px] border border-green-200/60 bg-green-50/50 p-4 text-green-700 animate-in slide-in-from-top-2 dark:border-green-500/20 dark:bg-green-500/10 dark:text-green-400">
              <CheckCircle2 size={20} />
              <div className="text-sm font-medium">{AUTH_TEXT.registerSuccess}</div>
            </div>
          )}

          {authView === 'login' && (
            <form onSubmit={handleLogin} className="space-y-4">
              {loginError && (
                <div className="rounded-[12px] border border-red-200/60 bg-red-50/50 p-3 text-[13px] text-red-600 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-400 flex items-center gap-2">
                  {loginError}
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.accountLabel}</label>
                <div className="relative">
                  <User className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    type="text"
                    placeholder={AUTH_TEXT.accountPlaceholder}
                    value={loginForm.account}
                    onChange={(e) => setLoginForm({ ...loginForm, account: e.target.value })}
                    className={cn(baseInputClasses, "pl-10 pr-4")}
                    required
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.passwordLabel}</label>
                  <button
                    type="button"
                    onClick={() => setAuthView('forgot')}
                    className="text-[13px] text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
                  >
                    {AUTH_TEXT.forgotPassword}
                  </button>
                </div>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    type="password"
                    placeholder={AUTH_TEXT.passwordPlaceholder}
                    value={loginForm.password}
                    onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                    className={cn(baseInputClasses, "pl-10 pr-4")}
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                className="mt-2 flex h-[44px] w-full items-center justify-center gap-2 rounded-[12px] bg-slate-900 text-[15px] font-medium text-white shadow-sm transition-all hover:bg-slate-800 active:scale-[0.98] dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
              >
                <span>{AUTH_TEXT.loginAction}</span>
                <ArrowRight size={18} />
              </button>

              <div className="mt-5 text-center text-[13px] text-slate-500 dark:text-slate-400">
                {AUTH_TEXT.noAccount}{' '}
                <button
                  type="button"
                  onClick={() => setAuthView('register')}
                  className="font-medium text-slate-900 hover:underline dark:text-white transition-colors"
                >
                  {AUTH_TEXT.registerAction}
                </button>
              </div>
            </form>
          )}

          {authView === 'register' && (
            <form onSubmit={handleRegister} className="space-y-4">
              {registerError && (
                <div className="rounded-[12px] border border-red-200/60 bg-red-50/50 p-3 text-[13px] text-red-600 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-400 flex items-center gap-2">
                  {registerError}
                </div>
              )}

              {registerSuccess && (
                <div className="rounded-[12px] border border-green-200/60 bg-green-50/50 p-3 text-[13px] text-green-700 dark:border-green-500/20 dark:bg-green-500/10 dark:text-green-400 flex items-center gap-2">
                  {registerSuccess}
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.usernameLabel}</label>
                  <div className="relative">
                    <User className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input
                      type="text"
                      placeholder={AUTH_TEXT.usernamePlaceholder}
                      value={registerForm.name}
                      onChange={(e) => setRegisterForm({ ...registerForm, name: e.target.value })}
                      className={cn(baseInputClasses, "pl-10 pr-3")}
                      required
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.phoneLabel}</label>
                  <div className="relative">
                    <Phone className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input
                      type="tel"
                      placeholder={AUTH_TEXT.phonePlaceholder}
                      value={registerForm.phone}
                      onChange={(e) => setRegisterForm({ ...registerForm, phone: e.target.value })}
                      className={cn(baseInputClasses, "pl-10 pr-3")}
                      required
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.emailLabel}</label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    type="email"
                    placeholder={AUTH_TEXT.emailPlaceholder}
                    value={registerForm.email}
                    onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
                    className={cn(baseInputClasses, "pl-10 pr-4")}
                    required
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.emailCodeLabel}</label>
                <div className="relative">
                  <input
                    type="text"
                    placeholder={AUTH_TEXT.emailCodePlaceholder}
                    value={registerForm.code}
                    onChange={(e) =>
                      setRegisterForm({
                        ...registerForm,
                        code: e.target.value.replace(/\D/g, '').slice(0, 6),
                      })
                    }
                    className={cn(baseInputClasses, "pl-4 pr-[7.5rem] tracking-widest")}
                    required
                    maxLength={6}
                  />
                  <div className="absolute bottom-1.5 right-1.5 top-1.5">
                    <button
                      type="button"
                      onClick={handleSendRegisterCode}
                      disabled={countdown > 0 || isSendingCode}
                      className={cn(
                        'flex h-full min-w-[80px] items-center justify-center whitespace-nowrap rounded-[8px] px-3 text-[13px] font-medium transition-all',
                        countdown > 0 || isSendingCode
                          ? 'cursor-not-allowed text-slate-400 dark:text-slate-500'
                          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white',
                      )}
                    >
                      {isSendingCode ? AUTH_TEXT.sendingCode : countdown > 0 ? `${countdown}${AUTH_TEXT.resendSuffix}` : AUTH_TEXT.getCode}
                    </button>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.passwordLabel}</label>
                  <div className="relative">
                    <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input
                      type="password"
                      placeholder={AUTH_TEXT.setPasswordPlaceholder}
                      value={registerForm.password}
                      onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
                      className={cn(baseInputClasses, "pl-10 pr-3")}
                      required
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.confirmPasswordLabel}</label>
                  <div className="relative">
                    <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input
                      type="password"
                      placeholder={AUTH_TEXT.confirmPasswordPlaceholder}
                      value={registerForm.confirmPassword}
                      onChange={(e) =>
                        setRegisterForm({ ...registerForm, confirmPassword: e.target.value })
                      }
                      className={cn(baseInputClasses, "pl-10 pr-3")}
                      required
                    />
                  </div>
                </div>
              </div>

              <button
                type="submit"
                className="mt-2 flex h-[44px] w-full items-center justify-center gap-2 rounded-[12px] bg-slate-900 text-[15px] font-medium text-white shadow-sm transition-all hover:bg-slate-800 active:scale-[0.98] dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
              >
                {AUTH_TEXT.createAccount}
              </button>

              <div className="mt-5 text-center text-[13px] text-slate-500 dark:text-slate-400">
                {AUTH_TEXT.hasAccount}{' '}
                <button
                  type="button"
                  onClick={() => setAuthView('login')}
                  className="font-medium text-slate-900 hover:underline dark:text-white transition-colors"
                >
                  {AUTH_TEXT.directLogin}
                </button>
              </div>
            </form>
          )}

          {authView === 'forgot' && (
            <form onSubmit={handleResetPassword} className="space-y-4">
              {forgotError && (
                <div className="animate-in slide-in-from-top-1 rounded-[12px] border border-red-200/60 bg-red-50/50 p-3 text-[13px] text-red-600 fade-in dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-400 flex items-center gap-2">
                  {forgotError}
                </div>
              )}

              {forgotSuccess && (
                <div className="flex items-center gap-2 rounded-[12px] border border-green-200/60 bg-green-50/50 p-3 text-[13px] text-green-600 animate-in fade-in slide-in-from-top-1 dark:border-green-500/20 dark:bg-green-500/10 dark:text-green-400">
                  <CheckCircle2 size={16} />
                  {forgotSuccess}
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.contactLabel}</label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    type="text"
                    placeholder={AUTH_TEXT.contactPlaceholder}
                    value={forgotForm.contact}
                    onChange={(e) => setForgotForm({ ...forgotForm, contact: e.target.value })}
                    className={cn(baseInputClasses, "pl-10 pr-4")}
                    required
                    disabled={isResetting}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.codeLabel}</label>
                <div className="relative">
                  <input
                    type="text"
                    placeholder={AUTH_TEXT.codePlaceholder}
                    value={forgotForm.code}
                    onChange={(e) =>
                      setForgotForm({
                        ...forgotForm,
                        code: e.target.value.replace(/\D/g, '').slice(0, 6),
                      })
                    }
                    className={cn(baseInputClasses, "pl-4 pr-[7.5rem] tracking-widest")}
                    required
                    disabled={isResetting}
                    maxLength={6}
                  />
                  <div className="absolute bottom-1.5 right-1.5 top-1.5">
                    <button
                      type="button"
                      onClick={handleSendCode}
                      disabled={countdown > 0 || isSendingCode || isResetting}
                      className={cn(
                        'flex h-full min-w-[80px] items-center justify-center whitespace-nowrap rounded-[8px] px-3 text-[13px] font-medium transition-all',
                        countdown > 0 || isSendingCode
                          ? 'cursor-not-allowed text-slate-400 dark:text-slate-500'
                          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white',
                      )}
                    >
                      {isSendingCode ? AUTH_TEXT.sendingCodeEllipsis : countdown > 0 ? `${countdown}${AUTH_TEXT.resendSuffix}` : AUTH_TEXT.getCode}
                    </button>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.newPasswordLabel}</label>
                  <div className="relative">
                    <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input
                      type="password"
                      placeholder={AUTH_TEXT.newPasswordPlaceholder}
                      value={forgotForm.newPassword}
                      onChange={(e) =>
                        setForgotForm({ ...forgotForm, newPassword: e.target.value })
                      }
                      className={cn(baseInputClasses, "pl-10 pr-3")}
                      required
                      disabled={isResetting}
                      minLength={6}
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[13px] font-medium text-slate-700 dark:text-slate-300">{AUTH_TEXT.confirmNewPasswordLabel}</label>
                  <div className="relative">
                    <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input
                      type="password"
                      placeholder={AUTH_TEXT.confirmNewPasswordPlaceholder}
                      value={forgotForm.confirmPassword}
                      onChange={(e) =>
                        setForgotForm({ ...forgotForm, confirmPassword: e.target.value })
                      }
                      className={cn(baseInputClasses, "pl-10 pr-3")}
                      required
                      disabled={isResetting}
                      minLength={6}
                    />
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={isResetting}
                className={cn(
                  'mt-2 flex h-[44px] w-full items-center justify-center gap-2 rounded-[12px] text-[15px] font-medium text-white shadow-sm transition-all',
                  isResetting
                    ? 'cursor-not-allowed bg-slate-300 dark:bg-slate-700'
                    : 'bg-slate-900 hover:bg-slate-800 active:scale-[0.98] dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100',
                )}
              >
                {isResetting ? AUTH_TEXT.resetting : AUTH_TEXT.resetPassword}
              </button>

              <div className="mt-5 text-center text-[13px]">
                <button
                  type="button"
                  onClick={() => {
                    setAuthView('login');
                    setForgotError('');
                    setForgotSuccess('');
                    setVerificationSent(false);
                    setMaskedContact('');
                  }}
                  disabled={isResetting}
                  className="font-medium text-slate-500 hover:text-slate-900 hover:underline dark:text-slate-400 dark:hover:text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {AUTH_TEXT.backToLogin}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
