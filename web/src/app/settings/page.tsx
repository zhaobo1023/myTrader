'use client';

import { useState, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import AppShell from '@/components/layout/AppShell';
import { useAuthStore } from '@/lib/store';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { userApi } from '@/lib/api-client';

export default function SettingsPage() {
  useRequireAuth();
  const { user, fetchUser } = useAuthStore();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [profileMsg, setProfileMsg] = useState('');
  const [pwdMsg, setPwdMsg] = useState('');

  useEffect(() => {
    if (user) {
      setDisplayName(user.display_name || '');
      setEmail(user.email || '');
    }
  }, [user]);

  const profileMut = useMutation({
    mutationFn: () => userApi.updateProfile({
      display_name: displayName || undefined,
      email: email || undefined,
    }),
    onSuccess: () => { setProfileMsg('已保存'); fetchUser(); setTimeout(() => setProfileMsg(''), 2000); },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } } };
      setProfileMsg(e.response?.data?.detail || '保存失败');
    },
  });

  const pwdMut = useMutation({
    mutationFn: () => userApi.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setPwdMsg('密码已修改');
      setCurrentPassword('');
      setNewPassword('');
      setTimeout(() => setPwdMsg(''), 2000);
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } } };
      setPwdMsg(e.response?.data?.detail || '修改失败');
    },
  });

  const sectionStyle: React.CSSProperties = {
    background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '20px', marginBottom: '16px',
  };
  const labelStyle: React.CSSProperties = { display: 'block', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' };
  const inputStyle: React.CSSProperties = { width: '100%', padding: '6px 10px', fontSize: '13px', border: '1px solid var(--border-subtle)', borderRadius: '6px', background: 'var(--bg-panel)' };
  const btnStyle: React.CSSProperties = { padding: '6px 16px', fontSize: '13px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer' };

  if (!user) return <AppShell><div style={{ color: 'var(--text-muted)', padding: '20px' }}>加载中...</div></AppShell>;

  return (
    <AppShell>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '20px' }}>设置</h1>

        {/* Profile */}
        <div style={sectionStyle}>
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '16px' }}>个人信息</h2>
          <div style={{ marginBottom: '12px' }}>
            <label style={labelStyle}>用户名</label>
            <input value={user.username} disabled style={{ ...inputStyle, background: 'var(--bg-canvas)', color: 'var(--text-muted)' }} />
          </div>
          <div style={{ marginBottom: '12px' }}>
            <label style={labelStyle}>昵称</label>
            <input value={displayName} onChange={e => setDisplayName(e.target.value)} style={inputStyle} placeholder="设置显示名称" />
          </div>
          <div style={{ marginBottom: '12px' }}>
            <label style={labelStyle}>邮箱 <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(选填，用于接收日报)</span></label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} style={inputStyle} placeholder="your@email.com" />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button onClick={() => profileMut.mutate()} style={btnStyle}>保存</button>
            {profileMsg && <span style={{ fontSize: '12px', color: profileMsg === '已保存' ? 'var(--green)' : 'var(--red)' }}>{profileMsg}</span>}
          </div>
        </div>

        {/* Change Password */}
        <div style={sectionStyle}>
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '16px' }}>修改密码</h2>
          <div style={{ marginBottom: '12px' }}>
            <label style={labelStyle}>当前密码</label>
            <input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ marginBottom: '12px' }}>
            <label style={labelStyle}>新密码</label>
            <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} style={inputStyle} placeholder="至少8位，需包含字母和数字" />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => pwdMut.mutate()}
              disabled={!currentPassword || newPassword.length < 8}
              style={{ ...btnStyle, opacity: (!currentPassword || newPassword.length < 8) ? 0.5 : 1 }}
            >
              修改密码
            </button>
            {pwdMsg && <span style={{ fontSize: '12px', color: pwdMsg === '密码已修改' ? 'var(--green)' : 'var(--red)' }}>{pwdMsg}</span>}
          </div>
        </div>

        {/* Account info */}
        <div style={sectionStyle}>
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '12px' }}>账户信息</h2>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            <div style={{ marginBottom: '6px' }}>等级: <span style={{ color: 'var(--text-primary)' }}>{user.tier}</span></div>
            <div style={{ marginBottom: '6px' }}>角色: <span style={{ color: 'var(--text-primary)' }}>{user.role}</span></div>
            <div>注册时间: <span style={{ color: 'var(--text-primary)' }}>{user.created_at.slice(0, 10)}</span></div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
