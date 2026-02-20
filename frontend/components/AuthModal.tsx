import React, { useState, useEffect } from 'react';
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
  const [registerForm, setRegisterForm] = useState({ name: '', email: '', phone: '', password: '', confirmPassword: '' });
  const [forgotForm, setForgotForm] = useState({ contact: '', code: '', newPassword: '' });
  const [verificationSent, setVerificationSent] = useState(false);
  const [registerError, setRegisterError] = useState('');
  const [loginError, setLoginError] = useState('');
  const [isNewUser, setIsNewUser] = useState(false);

  useEffect(() => {
    if (show) {
      setAuthView('login');
      setLoginForm({ account: '', password: '' });
      setRegisterForm({ name: '', email: '', phone: '', password: '', confirmPassword: '' });
      setForgotForm({ contact: '', code: '', newPassword: '' });
      setRegisterError('');
      setLoginError('');
      setVerificationSent(false);
      setIsNewUser(false);
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
      setRegisterError('Passwords do not match');
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
          password: registerForm.password
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setIsNewUser(true);
        setTimeout(() => {
          setAuthView('login');
          setIsNewUser(false);
        }, 2000);
      } else {
        setRegisterError(data.error || 'Registration failed');
      }
    } catch (err) {
      setRegisterError('Network error');
    }
  };

  const handleSendCode = async () => {
    // Mock send code
    setVerificationSent(true);
    alert(`Verification code sent to ${forgotForm.contact}`);
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    // Mock reset
    alert('Password reset successful');
    setAuthView('login');
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
                      placeholder="手机号码"
                      value={registerForm.phone}
                      onChange={e => setRegisterForm({ ...registerForm, phone: e.target.value })}
                      className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all text-sm"
                      required
                    />
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">邮箱</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    type="email"
                    placeholder="example@email.com"
                    value={registerForm.email}
                    onChange={e => setRegisterForm({ ...registerForm, email: e.target.value })}
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                    required
                  />
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
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">验证码</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="输入验证码"
                    value={forgotForm.code}
                    onChange={e => setForgotForm({ ...forgotForm, code: e.target.value })}
                    className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                    required
                  />
                  <button
                    type="button"
                    onClick={handleSendCode}
                    disabled={verificationSent}
                    className="px-4 py-2 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors text-sm font-medium whitespace-nowrap disabled:opacity-50"
                  >
                    {verificationSent ? '已发送' : '获取验证码'}
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">新密码</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    type="password"
                    placeholder="设置新密码"
                    value={forgotForm.newPassword}
                    onChange={e => setForgotForm({ ...forgotForm, newPassword: e.target.value })}
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                    required
                  />
                </div>
              </div>
              <button
                type="submit"
                className="w-full py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl font-bold shadow-lg shadow-blue-500/20 transition-all active:scale-[0.98]"
              >
                重置密码
              </button>
              <div className="text-center text-sm text-slate-500 mt-4">
                <button
                  type="button"
                  onClick={() => setAuthView('login')}
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
