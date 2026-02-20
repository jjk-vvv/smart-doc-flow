import React, { useState, useEffect, useRef } from 'react';
import {
    X,
    Phone,
    ArrowRight,
    LayoutGrid,
    FileSearch,
    Database,
    GitGraph,
    CheckSquare,
    MessageSquare,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import LogoImage from '../image.png';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

// WeChat JS SDK type declaration
declare global {
    interface Window {
        WxLogin: new (config: {
            self_redirect?: boolean;
            id: string;
            appid: string;
            scope: string;
            redirect_uri: string;
            state?: string;
            style?: string;
            href?: string;
            onReady?: (isReady: boolean) => void;
        }) => void;
    }
}

interface AuthModalProps {
    show: boolean;
    onClose: () => void;
    onLoginSuccess: (user: { name: string; email: string }) => void;
    isDark: boolean;
}

// Platform features for the brand panel
const features = [
    { icon: LayoutGrid, label: '智能指挥控制台' },
    { icon: FileSearch, label: '深度文档解析' },
    { icon: Database, label: '多源数据融合' },
    { icon: GitGraph, label: '全域知识图谱' },
];

// Custom CSS to inject into the WxLogin iframe to hide the default border/text
// and match our styling. This is loaded via the `href` parameter of WxLogin.
const WX_CUSTOM_CSS_URL = '';

export const AuthModal: React.FC<AuthModalProps> = ({ show, onClose, onLoginSuccess, isDark }) => {
    const [loginMode, setLoginMode] = useState<'wechat' | 'phone'>('wechat');
    const [phoneNumber, setPhoneNumber] = useState('');
    const [verifyCode, setVerifyCode] = useState('');
    const [countdown, setCountdown] = useState(0);
    const [agreed, setAgreed] = useState(false);
    const [error, setError] = useState('');
    const [wxStatus, setWxStatus] = useState<'loading' | 'ready' | 'error'>('loading');
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // WeChat config from environment variables (set in .env.local)
    const wxAppId = (import.meta as any).env?.VITE_WX_APPID || '';
    const wxRedirectUri = encodeURIComponent(
        (import.meta as any).env?.VITE_WX_REDIRECT_URI || window.location.origin + '/api/wechat/callback'
    );

    // Initialize WeChat QR when switching to wechat mode
    useEffect(() => {
        if (!show || loginMode !== 'wechat') return;

        // Generate random state for CSRF protection
        const wxState = Math.random().toString(36).substring(2, 15);

        const initWxLogin = () => {
            const container = document.getElementById('wx_login_container');
            if (!container) return;

            // Clear any previous iframe
            container.innerHTML = '';

            if (!wxAppId) {
                // No AppID configured — show configuration hint
                setWxStatus('error');
                return;
            }

            if (typeof window.WxLogin !== 'function') {
                console.warn('WxLogin SDK not loaded');
                setWxStatus('error');
                return;
            }

            try {
                setWxStatus('loading');
                new window.WxLogin({
                    self_redirect: false,
                    id: 'wx_login_container',
                    appid: wxAppId,
                    scope: 'snsapi_login',
                    redirect_uri: wxRedirectUri,
                    state: wxState,
                    style: '',
                    href: WX_CUSTOM_CSS_URL,
                    onReady: (isReady: boolean) => {
                        setWxStatus(isReady ? 'ready' : 'error');
                    },
                });
            } catch (e) {
                console.warn('WeChat QR init failed:', e);
                setWxStatus('error');
            }
        };

        // Small delay to ensure DOM container is mounted
        const timer = setTimeout(initWxLogin, 300);
        return () => clearTimeout(timer);
    }, [show, loginMode, wxAppId]);

    // Countdown timer for verification code
    useEffect(() => {
        if (countdown > 0) {
            timerRef.current = setInterval(() => {
                setCountdown(prev => {
                    if (prev <= 1) {
                        if (timerRef.current) clearInterval(timerRef.current);
                        return 0;
                    }
                    return prev - 1;
                });
            }, 1000);
        }
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [countdown]);

    // Reset state on close
    useEffect(() => {
        if (!show) {
            setError('');
            setPhoneNumber('');
            setVerifyCode('');
            setCountdown(0);
            setLoginMode('wechat');
            setWxStatus('loading');
        }
    }, [show]);

    const handleSendCode = async () => {
        if (!phoneNumber || phoneNumber.length < 11) {
            setError('请输入正确的手机号');
            return;
        }
        setError('');
        try {
            const res = await fetch('/api/send-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: phoneNumber }),
            });
            if (res.ok) {
                setCountdown(60);
            } else {
                setError('发送验证码失败，请稍后重试');
            }
        } catch {
            // For demo, start countdown anyway
            setCountdown(60);
        }
    };

    const handlePhoneLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!agreed) {
            setError('请先阅读并同意服务条款');
            return;
        }
        if (!phoneNumber || !verifyCode) {
            setError('请填写手机号和验证码');
            return;
        }
        setError('');
        try {
            const res = await fetch('/api/login/phone', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: phoneNumber, code: verifyCode }),
            });
            if (res.ok) {
                const data = await res.json();
                onLoginSuccess(data.user);
                onClose();
            } else {
                setError('验证码错误或已过期');
            }
        } catch {
            setError('网络错误，请稍后重试');
        }
    };

    if (!show) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
            <div className="w-full max-w-[720px] bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200/50 dark:border-slate-700/50 overflow-hidden relative animate-in zoom-in-95 duration-300 flex">

                {/* ===== Left Brand Panel ===== */}
                <div className="w-[220px] shrink-0 bg-gradient-to-b from-blue-600 via-blue-700 to-indigo-800 dark:from-blue-800 dark:via-indigo-900 dark:to-slate-950 p-6 flex flex-col text-white relative overflow-hidden">
                    {/* Decorative diagonal stripe */}
                    <div className="absolute top-0 right-0 w-20 h-full bg-white/5 -skew-x-12 translate-x-6" />
                    <div className="absolute top-0 right-6 w-10 h-full bg-white/5 -skew-x-12 translate-x-4" />

                    {/* Logo & Title */}
                    <div className="relative z-10 mb-8">
                        <div className="w-12 h-12 rounded-xl bg-white/15 backdrop-blur-sm border border-white/20 flex items-center justify-center mb-3 shadow-lg">
                            <img src={LogoImage} alt="Logo" className="w-8 h-8 object-contain" />
                        </div>
                        <h2 className="font-['Microsoft_YaHei'] font-bold text-lg leading-tight tracking-wide">
                            智能文档流转平台
                        </h2>
                        <p className="text-[11px] text-white/60 mt-1 font-medium">Intelligent Document Fusion</p>
                    </div>

                    {/* Feature list */}
                    <div className="relative z-10 flex-1 flex flex-col gap-3">
                        {features.map((ft, i) => {
                            return (
                                <div key={i} className="flex items-center gap-2.5 group">
                                    <div className="w-5 h-5 rounded flex items-center justify-center bg-white/10 group-hover:bg-white/20 transition-colors">
                                        <CheckSquare size={12} className="text-white/80" />
                                    </div>
                                    <span className="text-[13px] font-medium text-white/90 group-hover:text-white transition-colors whitespace-nowrap">
                                        {ft.label}
                                    </span>
                                </div>
                            );
                        })}
                    </div>

                    {/* Bottom decorative */}
                    <div className="relative z-10 mt-6 pt-4 border-t border-white/10">
                        <p className="text-[10px] text-white/40 leading-relaxed">
                            AI 驱动 · 企业级平台
                        </p>
                    </div>
                </div>

                {/* ===== Right Content Panel ===== */}
                <div className="flex-1 flex flex-col relative">
                    {/* Close button */}
                    <button
                        onClick={onClose}
                        className="absolute top-3 right-3 z-20 p-1.5 rounded-full text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    >
                        <X size={18} />
                    </button>

                    {/* Mode switch button */}
                    <div className="px-6 pt-5 pb-0 flex justify-end pr-12">
                        <button
                            onClick={() => {
                                setLoginMode(loginMode === 'wechat' ? 'phone' : 'wechat');
                                setError('');
                            }}
                            className="text-xs px-3 py-1.5 rounded-lg border border-primary/30 text-primary hover:bg-primary/5 dark:hover:bg-primary/10 transition-all font-bold flex items-center gap-1.5"
                        >
                            {loginMode === 'wechat' ? (
                                <>
                                    <Phone size={13} />
                                    切换为手机号登录
                                </>
                            ) : (
                                <>
                                    <MessageSquare size={13} />
                                    切换为微信登录
                                </>
                            )}
                        </button>
                    </div>

                    {/* Content Area */}
                    <div className="flex-1 px-8 pb-4 flex flex-col items-center justify-center">
                        {/* ---- WeChat QR Login ---- */}
                        {loginMode === 'wechat' && (
                            <div className="flex flex-col items-center gap-3 animate-in fade-in duration-300 w-full">
                                <h3 className="text-xl font-bold font-['Microsoft_YaHei'] text-foreground">微信扫码登录</h3>

                                {/*
                                  WeChat WxLogin SDK renders an iframe into this div.
                                  The iframe default size is ~300x400px. We constrain it
                                  and let the iframe scale inside.
                                  Per docs: https://developers.weixin.qq.com/doc/oplatform/Website_App/WeChat_Login/Wechat_Login.html
                                */}
                                <div
                                    id="wx_login_container"
                                    className="w-[300px] h-[300px] flex items-center justify-center overflow-hidden rounded-lg"
                                    style={{
                                        /* Ensure the iframe fills the container */
                                        position: 'relative',
                                    }}
                                />

                                {/* Show config hint when no AppID */}
                                {wxStatus === 'error' && !wxAppId && (
                                    <div className="text-center px-4 py-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/50 rounded-xl max-w-[300px]">
                                        <p className="text-xs text-amber-700 dark:text-amber-400 font-medium leading-relaxed">
                                            请在 <code className="bg-amber-100 dark:bg-amber-900/40 px-1 py-0.5 rounded text-[10px]">.env.local</code> 中配置微信 AppID：
                                        </p>
                                        <pre className="mt-2 text-[10px] text-left bg-slate-100 dark:bg-slate-800 p-2 rounded-lg font-mono text-slate-600 dark:text-slate-400 leading-relaxed">
                                            {`VITE_WX_APPID=你的AppID
VITE_WX_REDIRECT_URI=回调地址`}
                                        </pre>
                                    </div>
                                )}

                                {/* Loading indicator */}
                                {wxStatus === 'loading' && wxAppId && (
                                    <p className="text-xs text-muted-foreground animate-pulse">正在加载二维码...</p>
                                )}
                            </div>
                        )}

                        {/* ---- Phone Login ---- */}
                        {loginMode === 'phone' && (
                            <form onSubmit={handlePhoneLogin} className="flex flex-col items-center gap-5 animate-in fade-in duration-300 w-full max-w-[320px]">
                                <h3 className="text-xl font-bold font-['Microsoft_YaHei'] text-foreground">手机号码登录</h3>

                                {/* Phone number */}
                                <div className="w-full">
                                    <input
                                        type="tel"
                                        value={phoneNumber}
                                        onChange={e => setPhoneNumber(e.target.value.replace(/\D/g, '').slice(0, 11))}
                                        className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all font-medium text-foreground placeholder:text-muted-foreground/50"
                                        placeholder="请输入手机号"
                                    />
                                </div>

                                {/* Verification code + send button */}
                                <div className="w-full flex gap-2.5">
                                    <input
                                        type="text"
                                        value={verifyCode}
                                        onChange={e => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                                        className="flex-1 px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all font-medium text-foreground placeholder:text-muted-foreground/50"
                                        placeholder="请输入验证码"
                                    />
                                    <button
                                        type="button"
                                        onClick={handleSendCode}
                                        disabled={countdown > 0}
                                        className={cn(
                                            "shrink-0 px-4 py-3 rounded-xl text-sm font-bold transition-all whitespace-nowrap",
                                            countdown > 0
                                                ? "bg-slate-100 dark:bg-slate-800 text-muted-foreground cursor-not-allowed"
                                                : "bg-primary/10 text-primary hover:bg-primary/20 border border-primary/30"
                                        )}
                                    >
                                        {countdown > 0 ? `${countdown}s` : '获取验证码'}
                                    </button>
                                </div>

                                {error && (
                                    <div className="w-full text-xs text-red-500 font-bold text-center bg-red-50 dark:bg-red-900/20 p-2 rounded-lg border border-red-200 dark:border-red-800 animate-in fade-in slide-in-from-top-1">
                                        {error}
                                    </div>
                                )}

                                {/* Login button */}
                                <button
                                    type="submit"
                                    className="w-full py-3.5 rounded-xl bg-gradient-to-r from-primary to-blue-600 dark:from-primary dark:to-blue-500 hover:from-blue-600 hover:to-blue-700 dark:hover:from-blue-500 dark:hover:to-blue-600 text-white font-bold shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:-translate-y-0.5 active:translate-y-0 transition-all duration-300 flex items-center justify-center gap-2 group"
                                >
                                    <span>登录</span>
                                    <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                                </button>
                            </form>
                        )}
                    </div>

                    {/* Bottom: Terms agreement */}
                    <div className="px-8 pb-5 flex items-center justify-center gap-2">
                        <button
                            type="button"
                            onClick={() => setAgreed(!agreed)}
                            className={cn(
                                "w-4 h-4 rounded border-2 flex items-center justify-center transition-all shrink-0",
                                agreed
                                    ? "bg-primary border-primary text-white"
                                    : "border-slate-300 dark:border-slate-600 hover:border-primary/50"
                            )}
                        >
                            {agreed && (
                                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                                    <path d="M2 5L4 7L8 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                            )}
                        </button>
                        <p className="text-[11px] text-muted-foreground">
                            登录即视为同意
                            <a href="#" className="text-primary hover:underline font-medium">服务与条款</a>
                            、
                            <a href="#" className="text-primary hover:underline font-medium">隐私政策</a>
                            。
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};
