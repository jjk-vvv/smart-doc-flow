import React, { useState, useEffect, useRef } from 'react';
import { X, Mail, Lock, User, Phone, ArrowRight, CheckCircle2 } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface AuthModalProps {
    show: boolean;
    onClose: () => void;
    onLoginSuccess: (user: { name: string; email: string }) => void;
    isDark: boolean;
}

export const AuthModal: React.FC<AuthModalProps> = ({ show, onClose, onLoginSuccess, isDark }) => {
    const [authView, setAuthView] = useState<'login' | 'register' | 'forgot'>('login');

    // Form States
    const [loginForm, setLoginForm] = useState({ account: '', password: '' });
    const [registerForm, setRegisterForm] = useState({ name: '', email: '', phone: '', password: '', confirmPassword: '', code: '' });
    const [forgotForm, setForgotForm] = useState({ contact: '', code: '', newPassword: '', confirmPassword: '' });
    const [verificationSent, setVerificationSent] = useState(false);
    const [countdown, setCountdown] = useState(0);
    const [maskedContact, setMaskedContact] = useState('');
    const [registerError, setRegisterError] = useState('');
    const [loginError, setLoginError] = useState('');
    const [forgotError, setForgotError] = useState('');
    const [forgotSuccess, setForgotSuccess] = useState('');
    const [isNewUser, setIsNewUser] = useState(false);
    const [isSendingCode, setIsSendingCode] = useState(false);
    const [isResetting, setIsResetting] = useState(false);
    const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Countdown timer effect
    useEffect(() => {
        if (countdown > 0) {
            countdownRef.current = setInterval(() => {
                setCountdown(prev => {
                    if (prev <= 1) {
                        if (countdownRef.current) clearInterval(countdownRef.current);
                        return 0;
                    }
                    return prev - 1;
                });
            }, 1000);
        }
        return () => {
            if (countdownRef.current) clearInterval(countdownRef.current);
        };
    }, [countdown]);

    useEffect(() => {
        if (show) {
            setAuthView('login');
            setLoginForm({ account: '', password: '' });
            setRegisterForm({ name: '', email: '', phone: '', password: '', confirmPassword: '', code: '' });
            setForgotForm({ contact: '', code: '', newPassword: '', confirmPassword: '' });
            setRegisterError('');
            setLoginError('');
            setForgotError('');
            setForgotSuccess('');
            setVerificationSent(false);
            setCountdown(0);
            setMaskedContact('');
            setIsNewUser(false);
            setIsSendingCode(false);
            setIsResetting(false);
        }
    }, [show]);

    if (!show) return null;

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoginError('');
        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(loginForm),
            });
            const data = await res.json();
            if (res.ok) {
                onLoginSuccess(data.user);
                onClose();
            } else {
                setLoginError(data.error || 'Login failed');
            }
        } catch (err) {
            setLoginError('Network error');
        }
    };

    const handleRegister = async (e: React.FormEvent) => {
        e.preventDefault();
        setRegisterError('');
        if (registerForm.password !== registerForm.confirmPassword) {
            setRegisterError('两次密码输入不一致');
            return;
        }
        if (!registerForm.code || !/^\d{6}$/.test(registerForm.code)) {
            setRegisterError('请输入正确的6位验证码');
            return;
        }
        if (!/^1[3-9]\d{9}$/.test(registerForm.phone)) {
            setRegisterError('请输入正确的手机号码');
            return;
        }
        try {
            const res = await fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: registerForm.name,
                    email: registerForm.email,
                    phone: registerForm.phone,
                    password: registerForm.password,
                    code: registerForm.code
                }),
            });
            const data = await res.json();
            if (res.ok) {
                onLoginSuccess(data.user);
                onClose();
            } else {
                setRegisterError(data.error || '注册失败');
            }
        } catch (err) {
            setRegisterError('网络错误，请检查网络连接');
        }
    };

    const handleSendRegisterCode = async () => {
        setRegisterError('');

        if (!registerForm.email.trim() || !registerForm.email.includes('@')) {
            setRegisterError('请输入有效的邮箱地址获取验证码');
            return;
        }

        setIsSendingCode(true);
        try {
            const res = await fetch('/api/register/send-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ contact: registerForm.email.trim() }),
            });
            const data = await res.json();
            if (res.ok) {
                setCountdown(60);
                if (data.devCode) {
                    alert(`【本地开发测试】\n未配置真实邮件服务，模拟发送成功！\n您的验证码是: ${data.devCode}`);
                }
            } else {
                setRegisterError(data.error || '验证码发送失败');
            }
        } catch {
            setRegisterError('网络错误，请检查网络连接');
        } finally {
            setIsSendingCode(false);
        }
    };

    const handleSendCode = async () => {
        setForgotError('');
        setForgotSuccess('');

        if (!forgotForm.contact.trim()) {
            setForgotError('请输入注册时使用的手机号或邮箱');
            return;
        }

        setIsSendingCode(true);
        try {
            const res = await fetch('/api/forgot/send-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ contact: forgotForm.contact.trim() }),
            });
            const data = await res.json();
            if (res.ok) {
                setVerificationSent(true);
                setCountdown(60);
                setMaskedContact(data.maskedContact || forgotForm.contact);
                setForgotSuccess(`验证码已发送至 ${data.maskedContact || forgotForm.contact}，请查收`);
                if (data.devCode) {
                    alert(`【本地开发测试】\n未配置真实短信/邮件服务，模拟发送成功！\n您的验证码是: ${data.devCode}`);
                }
            } else {
                setForgotError(data.error || '发送失败，请稍后重试');
            }
        } catch {
            setForgotError('网络错误，请检查网络连接');
        } finally {
            setIsSendingCode(false);
        }
    };

    const handleResetPassword = async (e: React.FormEvent) => {
        e.preventDefault();
        setForgotError('');
        setForgotSuccess('');

        if (!forgotForm.code.trim()) {
            setForgotError('请输入验证码');
            return;
        }
        if (!forgotForm.newPassword) {
            setForgotError('请设置新密码');
            return;
        }
        if (forgotForm.newPassword.length < 6) {
            setForgotError('密码长度至少6位');
            return;
        }
        if (forgotForm.newPassword !== forgotForm.confirmPassword) {
            setForgotError('两次输入的密码不一致');
            return;
        }

        setIsResetting(true);
        try {
            const res = await fetch('/api/forgot/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    contact: forgotForm.contact.trim(),
                    code: forgotForm.code.trim(),
                    newPassword: forgotForm.newPassword,
                }),
            });
            const data = await res.json();
            if (res.ok) {
                setForgotSuccess(data.message || '密码重置成功！');
                setForgotError('');
                // Auto-redirect to login after 2 seconds
                setTimeout(() => {
                    setAuthView('login');
                    setForgotForm({ contact: '', code: '', newPassword: '', confirmPassword: '' });
                    setVerificationSent(false);
                    setCountdown(0);
                    setForgotSuccess('');
                }, 2000);
            } else {
                setForgotError(data.error || '重置失败，请重试');
            }
        } catch {
            setForgotError('网络错误，请检查网络连接');
        } finally {
            setIsResetting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-300">
            <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-300 border border-slate-200 dark:border-slate-800 relative">

                {/* Close Button */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors z-10"
                >
                    <X size={20} className="text-slate-500" />
                </button>

                <div className="p-8">
                    <div className="text-center mb-8">
                        <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                            {authView === 'login' && '欢迎回来'}
                            {authView === 'register' && '创建账号'}
                            {authView === 'forgot' && '重置密码'}
                        </h2>
                        <p className="text-slate-500 text-sm">
                            {authView === 'login' && '登录您的账户以继续使用'}
                            {authView === 'register' && '填写以下信息完成注册'}
                            {authView === 'forgot' && '验证身份以设置新密码'}
                        </p>
                    </div>

                    {/* New User Success Message */}
                    {isNewUser && (
                        <div className="mb-6 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl flex items-center gap-3 text-green-700 dark:text-green-400 animate-in slide-in-from-top-2">
                            <CheckCircle2 size={20} />
                            <div className="text-sm font-medium">注册成功！正在跳转登录...</div>
                        </div>
                    )}

                    {authView === 'login' && (
                        <form onSubmit={handleLogin} className="space-y-4">
                            {loginError && (
                                <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-100 dark:border-red-800">
                                    {loginError}
                                </div>
                            )}
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">账号</label>
                                <div className="relative">
                                    <User className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                    <input
                                        type="text"
                                        placeholder="邮箱 / 手机号"
                                        value={loginForm.account}
                                        onChange={e => setLoginForm({ ...loginForm, account: e.target.value })}
                                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                    />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <div className="flex justify-between items-center">
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">密码</label>
                                    <button
                                        type="button"
                                        onClick={() => setAuthView('forgot')}
                                        className="text-xs text-primary hover:underline"
                                    >
                                        忘记密码?
                                    </button>
                                </div>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                    <input
                                        type="password"
                                        placeholder="请输入密码"
                                        value={loginForm.password}
                                        onChange={e => setLoginForm({ ...loginForm, password: e.target.value })}
                                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                    />
                                </div>
                            </div>
                            <button
                                type="submit"
                                className="w-full py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl font-bold shadow-lg shadow-blue-500/20 transition-all active:scale-[0.98] flex items-center justify-center gap-2"
                            >
                                <span>立即登录</span>
                                <ArrowRight size={18} />
                            </button>
                            <div className="text-center text-sm text-slate-500 mt-4">
                                还没有账号?{' '}
                                <button
                                    type="button"
                                    onClick={() => setAuthView('register')}
                                    className="text-primary font-bold hover:underline"
                                >
                                    立即注册
                                </button>
                            </div>
                        </form>
                    )}

                    {authView === 'register' && (
                        <form onSubmit={handleRegister} className="space-y-4">
                            {registerError && (
                                <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-100 dark:border-red-800">
                                    {registerError}
                                </div>
                            )}
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">用户名</label>
                                    <div className="relative">
                                        <User className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                                        <input
                                            type="text"
                                            placeholder="您的昵称"
                                            value={registerForm.name}
                                            onChange={e => setRegisterForm({ ...registerForm, name: e.target.value })}
                                            className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all text-sm"
                                            required
                                        />
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">手机号</label>
                                    <div className="relative">
                                        <Phone className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                                        <input
                                            type="tel"
                                            placeholder="您的手机号码"
                                            value={registerForm.phone}
                                            onChange={e => setRegisterForm({ ...registerForm, phone: e.target.value })}
                                            className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all text-sm"
                                        />
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">QQ邮箱</label>
                                <div className="relative">
                                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                    <input
                                        type="email"
                                        placeholder="您的邮箱"
                                        value={registerForm.email}
                                        onChange={e => setRegisterForm({ ...registerForm, email: e.target.value })}
                                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">邮箱验证码</label>
                                <div className="relative">
                                    <input
                                        type="text"
                                        placeholder="6位邮箱验证码"
                                        value={registerForm.code}
                                        onChange={e => setRegisterForm({ ...registerForm, code: e.target.value.replace(/\D/g, '').slice(0, 6) })}
                                        className="w-full pl-4 pr-[7.5rem] py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all text-sm tracking-widest"
                                        required
                                        maxLength={6}
                                    />
                                    <div className="absolute right-1.5 top-1.5 bottom-1.5">
                                        <button
                                            type="button"
                                            onClick={handleSendRegisterCode}
                                            disabled={countdown > 0 || isSendingCode}
                                            className={cn(
                                                "h-full px-4 rounded-lg text-xs font-medium whitespace-nowrap transition-all flex items-center justify-center min-w-[90px]",
                                                countdown > 0 || isSendingCode
                                                    ? "bg-slate-100 dark:bg-slate-800 text-muted-foreground cursor-not-allowed"
                                                    : "bg-primary/10 text-primary hover:bg-primary/20"
                                            )}
                                        >
                                            {isSendingCode ? '发送中' : countdown > 0 ? `${countdown}s 后重发` : '获取验证码'}
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">密码</label>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                    <input
                                        type="password"
                                        placeholder="设置登录密码"
                                        value={registerForm.password}
                                        onChange={e => setRegisterForm({ ...registerForm, password: e.target.value })}
                                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                    />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">确认密码</label>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                    <input
                                        type="password"
                                        placeholder="再次输入密码"
                                        value={registerForm.confirmPassword}
                                        onChange={e => setRegisterForm({ ...registerForm, confirmPassword: e.target.value })}
                                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                    />
                                </div>
                            </div>
                            <button
                                type="submit"
                                className="w-full py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl font-bold shadow-lg shadow-blue-500/20 transition-all active:scale-[0.98]"
                            >
                                创建账号
                            </button>
                            <div className="text-center text-sm text-slate-500 mt-4">
                                已有账号?{' '}
                                <button
                                    type="button"
                                    onClick={() => setAuthView('login')}
                                    className="text-primary font-bold hover:underline"
                                >
                                    直接登录
                                </button>
                            </div>
                        </form>
                    )}

                    {authView === 'forgot' && (
                        <form onSubmit={handleResetPassword} className="space-y-4">
                            {/* Error message */}
                            {forgotError && (
                                <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-100 dark:border-red-800 animate-in fade-in slide-in-from-top-1">
                                    {forgotError}
                                </div>
                            )}
                            {/* Success message */}
                            {forgotSuccess && (
                                <div className="p-3 bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 text-sm rounded-lg border border-green-100 dark:border-green-800 flex items-center gap-2 animate-in fade-in slide-in-from-top-1">
                                    <CheckCircle2 size={16} />
                                    {forgotSuccess}
                                </div>
                            )}

                            {/* Contact input */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">联系方式</label>
                                <div className="relative">
                                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                    <input
                                        type="text"
                                        placeholder="注册邮箱 / 手机号"
                                        value={forgotForm.contact}
                                        onChange={e => setForgotForm({ ...forgotForm, contact: e.target.value })}
                                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                        disabled={isResetting}
                                    />
                                </div>
                            </div>

                            {/* Verification code + send button */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">验证码</label>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        placeholder="输入6位验证码"
                                        value={forgotForm.code}
                                        onChange={e => setForgotForm({ ...forgotForm, code: e.target.value.replace(/\D/g, '').slice(0, 6) })}
                                        className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                        disabled={isResetting}
                                        maxLength={6}
                                    />
                                    <button
                                        type="button"
                                        onClick={handleSendCode}
                                        disabled={countdown > 0 || isSendingCode || isResetting}
                                        className={cn(
                                            "shrink-0 px-4 py-2.5 rounded-xl text-sm font-medium whitespace-nowrap transition-all",
                                            countdown > 0 || isSendingCode
                                                ? "bg-slate-100 dark:bg-slate-800 text-muted-foreground cursor-not-allowed"
                                                : "bg-primary/10 text-primary hover:bg-primary/20 border border-primary/30"
                                        )}
                                    >
                                        {isSendingCode ? '发送中...' : countdown > 0 ? `${countdown}s 后重发` : '获取验证码'}
                                    </button>
                                </div>
                            </div>

                            {/* New password */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">新密码</label>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                    <input
                                        type="password"
                                        placeholder="设置新密码（至少6位）"
                                        value={forgotForm.newPassword}
                                        onChange={e => setForgotForm({ ...forgotForm, newPassword: e.target.value })}
                                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                        disabled={isResetting}
                                        minLength={6}
                                    />
                                </div>
                            </div>

                            {/* Confirm new password */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">确认新密码</label>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                    <input
                                        type="password"
                                        placeholder="再次输入新密码"
                                        value={forgotForm.confirmPassword}
                                        onChange={e => setForgotForm({ ...forgotForm, confirmPassword: e.target.value })}
                                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                        required
                                        disabled={isResetting}
                                    />
                                </div>
                            </div>

                            {/* Submit button */}
                            <button
                                type="submit"
                                disabled={isResetting}
                                className="w-full py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl font-bold shadow-lg shadow-blue-500/20 transition-all active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
                            >
                                {isResetting ? '重置中...' : '重置密码'}
                            </button>

                            <div className="text-center text-sm text-slate-500 mt-4">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setAuthView('login');
                                        setForgotError('');
                                        setForgotSuccess('');
                                    }}
                                    className="text-slate-500 hover:text-foreground transition-colors"
                                >
                                    返回登录
                                </button>
                            </div>
                        </form>
                    )}

                </div>
            </div>
        </div>
    );
};
