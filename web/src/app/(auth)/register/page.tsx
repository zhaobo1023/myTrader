'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { register } from '@/lib/auth';

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // 密码强度检查
  const hasMinLength = password.length >= 8;
  const hasLetter = /[a-zA-Z]/.test(password);
  const hasDigit = /\d/.test(password);
  const isPasswordValid = hasMinLength && hasLetter && hasDigit;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }

    if (!isPasswordValid) {
      setError('请满足所有密码要求');
      return;
    }

    if (!inviteCode.trim()) {
      setError('请输入邀请码');
      return;
    }

    setLoading(true);
    try {
      await register(username, password, inviteCode.trim(), displayName || undefined);
      router.push('/dashboard');
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-lg shadow-sm border p-8">
          <h1 className="text-2xl font-bold text-center mb-6">myTrader</h1>
          <h2 className="text-sm text-gray-500 text-center mb-8">
            创建你的账户
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="invite-code" className="block text-sm font-medium text-gray-700 mb-1">
                邀请码 <span className="text-red-500">*</span>
              </label>
              <input
                id="invite-code"
                type="text"
                required
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="输入邀请码"
              />
            </div>

            <div>
              <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
                用户名 <span className="text-red-500">*</span>
              </label>
              <input
                id="username"
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="支持中文、字母、数字、下划线"
              />
            </div>

            <div>
              <label htmlFor="display-name" className="block text-sm font-medium text-gray-700 mb-1">
                昵称 <span className="text-gray-400">(选填)</span>
              </label>
              <input
                id="display-name"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="显示名称"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                密码 <span className="text-red-500">*</span>
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={`w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-1 ${
                  password && !isPasswordValid
                    ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                    : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'
                }`}
                placeholder="请输入密码"
              />
              {/* 密码要求提示 */}
              {password && (
                <div className="mt-2 space-y-1">
                  <div className={`flex items-center text-xs ${hasMinLength ? 'text-green-600' : 'text-gray-400'}`}>
                    <span className="mr-1">{hasMinLength ? '✓' : '○'}</span>
                    至少 8 位字符
                  </div>
                  <div className={`flex items-center text-xs ${hasLetter ? 'text-green-600' : 'text-gray-400'}`}>
                    <span className="mr-1">{hasLetter ? '✓' : '○'}</span>
                    至少 1 个字母
                  </div>
                  <div className={`flex items-center text-xs ${hasDigit ? 'text-green-600' : 'text-gray-400'}`}>
                    <span className="mr-1">{hasDigit ? '✓' : '○'}</span>
                    至少 1 个数字
                  </div>
                </div>
              )}
            </div>

            <div>
              <label htmlFor="confirm" className="block text-sm font-medium text-gray-700 mb-1">
                确认密码 <span className="text-red-500">*</span>
              </label>
              <input
                id="confirm"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={`w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-1 ${
                  confirmPassword && password !== confirmPassword
                    ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                    : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'
                }`}
                placeholder="再次输入密码"
              />
            </div>

            {/* 加密存储提示 */}
            <div className="bg-blue-50 rounded-md p-3 flex items-start">
              <svg className="w-5 h-5 text-blue-600 mt-0.5 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              <p className="text-xs text-blue-700">
                密码采用 <strong>bcrypt</strong> 加密存储，我们无法查看您的原始密码
              </p>
            </div>

            {error && (
              <div className="text-sm text-red-600 bg-red-50 rounded-md p-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !isPasswordValid}
              className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed"
            >
              {loading ? '注册中...' : '注册'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500">
            已有账户？{' '}
            <a href="/login" className="text-blue-600 hover:text-blue-500">
              登录
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
