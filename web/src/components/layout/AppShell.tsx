'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/lib/store';
import { useEffect, useState, useCallback } from 'react';
import { useTrack } from '@/hooks/useTrack';
import { NAV_PERMISSIONS, hasPermission } from '@/lib/permissions';
import FloatingAssistant from '@/components/agent/FloatingAssistant';

// ----------------------------------------------------------------
// Nav structure
// ----------------------------------------------------------------

interface NavChild {
  href: string;
  label: string;
}

interface NavItem {
  href: string;
  label: string;
  labelEn: string;
  icon: React.ReactNode;
  children?: NavChild[];
}

function NavIcon({ name, size = 16 }: { name: string; size?: number }) {
  const s = {
    width: size, height: size, stroke: 'currentColor', fill: 'none' as const,
    strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
  };
  switch (name) {
    case 'pulse':
      return <svg viewBox="0 0 24 24" {...s}><path d="M3 12h3l3-8 4 16 3-8h5"/></svg>;
    case 'search':
      return <svg viewBox="0 0 24 24" {...s}><circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/></svg>;
    case 'filter':
      return <svg viewBox="0 0 24 24" {...s}><path d="M3 5h18M6 12h12M10 19h4"/></svg>;
    case 'briefcase':
      return <svg viewBox="0 0 24 24" {...s}><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/></svg>;
    case 'chat':
      return <svg viewBox="0 0 24 24" {...s}><path d="M21 12c0 4-4 7-9 7-1.5 0-2.9-.2-4.1-.7L3 20l1.2-4.2C3.4 14.6 3 13.3 3 12c0-4 4-7 9-7s9 3 9 7Z"/></svg>;
    case 'data':
      return <svg viewBox="0 0 24 24" {...s}><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v4c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 10v4c0 1.7 3.6 3 8 3s8-1.3 8-3v-4"/></svg>;
    case 'sparkle':
      return <svg viewBox="0 0 24 24" {...s}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/></svg>;
    case 'bell':
      return <svg viewBox="0 0 24 24" {...s}><path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8M10 21a2 2 0 0 0 4 0"/></svg>;
    case 'theme':
      return <svg viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18Z" fill="currentColor" stroke="none"/></svg>;
    case 'mail':
      return <svg viewBox="0 0 24 24" {...s}><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>;
    case 'settings':
      return <svg viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>;
    case 'chevron-right':
      return <svg viewBox="0 0 24 24" {...s}><polyline points="9 18 15 12 9 6"/></svg>;
    case 'menu':
      return <svg viewBox="0 0 24 24" {...s}><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>;
    case 'x':
      return <svg viewBox="0 0 24 24" {...s}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>;
    case 'collapse':
      return <svg viewBox="0 0 24 24" {...s}><polyline points="15 18 9 12 15 6"/></svg>;
    case 'expand':
      return <svg viewBox="0 0 24 24" {...s}><polyline points="9 18 15 12 9 6"/></svg>;
    default:
      return <svg viewBox="0 0 24 24" {...s}><circle cx="12" cy="12" r="4"/></svg>;
  }
}

const NAV_ITEMS: NavItem[] = [
  {
    href: '/sentiment',
    label: '指标看板',
    labelEn: 'Dashboard',
    icon: <NavIcon name="pulse" />,
  },
  {
    href: '/stock',
    label: 'AI 投研',
    labelEn: 'Research',
    icon: <NavIcon name="search" />,
  },
  {
    href: '/strategy',
    label: 'AI 选股',
    labelEn: 'Screener',
    icon: <NavIcon name="filter" />,
  },
  {
    href: '/portfolio',
    label: '仓位管理',
    labelEn: 'Portfolio',
    icon: <NavIcon name="briefcase" />,
  },
  {
    href: '/data-health',
    label: '数据完备度',
    labelEn: 'Data Health',
    icon: <NavIcon name="data" />,
  },
  {
    href: '/rag',
    label: '投资问答',
    labelEn: 'Q & A',
    icon: <NavIcon name="chat" />,
  },
];

// ----------------------------------------------------------------
// Logo
// ----------------------------------------------------------------
function Logo({ collapsed }: { collapsed: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0,
        background: 'linear-gradient(135deg, var(--brand), oklch(0.68 0.16 50))',
        display: 'grid', placeItems: 'center', color: 'var(--brand-ink)',
        fontWeight: 800, fontSize: 13, letterSpacing: '-0.04em',
        boxShadow: '0 0 0 1px var(--brand-glow), 0 0 18px -6px var(--brand-glow)',
      }}>mT</div>
      {!collapsed && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, letterSpacing: '-0.01em', color: 'var(--ink)' }}>myTrader</div>
          <div style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 9, color: 'var(--ink-2)', letterSpacing: '0.08em', marginTop: 1 }}>QUANT · AI</div>
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------
// Theme toggle
// ----------------------------------------------------------------
function useTheme() {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  useEffect(() => {
    try {
      const saved = localStorage.getItem('mt-theme') as 'dark' | 'light' | null;
      const current = document.documentElement.getAttribute('data-theme') as 'dark' | 'light';
      setTheme(saved || current || 'dark');
    } catch {
      setTheme('dark');
    }
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('mt-theme', next);
      return next;
    });
  }, []);

  return { theme, toggle };
}

// ----------------------------------------------------------------
// LiveClock
// ----------------------------------------------------------------
function LiveClock() {
  const [t, setT] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setT(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const hh = String(t.getHours()).padStart(2, '0');
  const mm = String(t.getMinutes()).padStart(2, '0');
  const ss = String(t.getSeconds()).padStart(2, '0');
  return (
    <span style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 12, color: 'var(--ink-1)', fontVariantNumeric: 'tabular-nums' }}>
      {hh}:{mm}<span style={{ color: 'var(--ink-3)' }}>:{ss}</span>
    </span>
  );
}

// ----------------------------------------------------------------
// Market index tickers (static placeholder — real data from API later)
// ----------------------------------------------------------------
function IndexTicker({ name, code, value, chg, chgPct, up }: {
  name: string; code: string; value: string; chg: string; chgPct: string; up: boolean;
}) {
  const color = up ? 'var(--up)' : 'var(--down)';
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, paddingRight: 16, borderRight: '1px solid var(--line)' }}>
      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
        <span style={{ fontSize: 11, color: 'var(--ink-2)' }}>{name}</span>
        <span style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 9, color: 'var(--ink-3)', letterSpacing: '0.06em', marginTop: 2 }}>{code}</span>
      </div>
      <span style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 13, fontWeight: 600, color, letterSpacing: '-0.01em', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
      <span style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 11, color, fontVariantNumeric: 'tabular-nums' }}>{up ? '+' : ''}{chg} {chgPct}</span>
    </div>
  );
}

// ----------------------------------------------------------------
// SideNav content
// ----------------------------------------------------------------
function SideNavContent({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  const [mounted, setMounted] = useState(false);
  const { track } = useTrack();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ '/strategy': true });

  useEffect(() => { setMounted(true); }, []);

  function toggleExpand(href: string) {
    setExpanded((prev) => ({ ...prev, [href]: !prev[href] }));
  }

  function isParentActive(item: NavItem): boolean {
    if (pathname === item.href) return true;
    if (item.children?.some((c) => pathname === c.href || pathname.startsWith(c.href + '/'))) return true;
    if (pathname.startsWith(item.href + '/')) return true;
    if (item.href === '/portfolio' && (pathname.startsWith('/positions') || pathname.startsWith('/sim-pool') || pathname.startsWith('/candidate-pool'))) return true;
    if (item.href === '/strategy' && pathname.startsWith('/theme-pool')) return true;
    return false;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Logo */}
      <div style={{ padding: collapsed ? '18px 12px 16px' : '18px 16px 16px', borderBottom: '1px solid var(--line)', flexShrink: 0 }}>
        <Logo collapsed={collapsed} />
      </div>

      {/* Nav items */}
      <nav style={{ flex: 1, padding: '10px 8px', overflowY: 'auto' }}>
        {!collapsed && (
          <div className="label" style={{ padding: '6px 10px 4px', display: 'block' }}>导航</div>
        )}
        {NAV_ITEMS.filter((item) => {
          const permission = NAV_PERMISSIONS[item.href];
          if (!permission) return true;
          return hasPermission(user?.tier ?? null, user?.role ?? null, permission);
        }).map((item) => {
          const active = isParentActive(item);
          const hasChildren = !!(item.children && item.children.length > 0);
          const isOpen = expanded[item.href] ?? false;

          return (
            <div key={item.href}>
              <div style={{ position: 'relative' }}>
                {/* Active indicator bar */}
                {active && !hasChildren && (
                  <span style={{
                    position: 'absolute', left: -8, top: 6, bottom: 6,
                    width: 3, background: 'var(--brand)', borderRadius: '0 3px 3px 0',
                  }} />
                )}
                <Link
                  href={hasChildren ? '#' : item.href}
                  onClick={hasChildren ? (e) => { e.preventDefault(); toggleExpand(item.href); } : () => {
                    track('nav_click', { nav_label: item.labelEn, nav_href: item.href });
                    onNavigate?.();
                  }}
                  title={collapsed ? item.label : undefined}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '9px 10px', borderRadius: 8, marginBottom: 2,
                    background: active && !hasChildren ? 'var(--brand-soft)' : 'transparent',
                    color: active ? 'var(--brand)' : 'var(--ink-1)',
                    border: `1px solid ${active && !hasChildren ? 'var(--brand-glow)' : 'transparent'}`,
                    textDecoration: 'none', fontSize: 13, fontWeight: active ? 600 : 500,
                    transition: 'all .15s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      const el = e.currentTarget as HTMLAnchorElement;
                      el.style.background = 'var(--bg-2)';
                      el.style.color = 'var(--ink)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      const el = e.currentTarget as HTMLAnchorElement;
                      el.style.background = 'transparent';
                      el.style.color = 'var(--ink-1)';
                    }
                  }}
                >
                  <span style={{ flexShrink: 0, display: 'flex' }}>{item.icon}</span>
                  {!collapsed && (
                    <>
                      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1, flex: 1, minWidth: 0 }}>
                        <span>{item.label}</span>
                        <span style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 9, color: active ? 'var(--brand)' : 'var(--ink-3)', letterSpacing: '0.08em', marginTop: 2, opacity: 0.8 }}>{item.labelEn}</span>
                      </div>
                      {hasChildren && (
                        <span style={{ flexShrink: 0, transition: 'transform .15s', transform: isOpen ? 'rotate(90deg)' : 'none', display: 'flex' }}>
                          <NavIcon name="chevron-right" size={12} />
                        </span>
                      )}
                    </>
                  )}
                </Link>
              </div>

              {hasChildren && isOpen && !collapsed && (
                <div style={{ marginBottom: 4 }}>
                  {item.children!.map((child) => {
                    const childActive = pathname === child.href || pathname.startsWith(child.href + '/');
                    return (
                      <Link
                        key={child.href}
                        href={child.href}
                        onClick={() => {
                          track('nav_click', { nav_label: child.label, nav_href: child.href });
                          onNavigate?.();
                        }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          padding: '6px 10px 6px 34px', borderRadius: 6, marginBottom: 1,
                          fontSize: 12, fontWeight: childActive ? 510 : 400,
                          color: childActive ? 'var(--ink)' : 'var(--ink-2)',
                          background: childActive ? 'var(--bg-2)' : 'transparent',
                          textDecoration: 'none', transition: 'all .12s',
                        }}
                        onMouseEnter={(e) => {
                          if (!childActive) {
                            (e.currentTarget as HTMLAnchorElement).style.background = 'var(--bg-2)';
                            (e.currentTarget as HTMLAnchorElement).style.color = 'var(--ink-1)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!childActive) {
                            (e.currentTarget as HTMLAnchorElement).style.background = 'transparent';
                            (e.currentTarget as HTMLAnchorElement).style.color = 'var(--ink-2)';
                          }
                        }}
                      >
                        <span style={{ width: 4, height: 4, borderRadius: '50%', flexShrink: 0, background: childActive ? 'var(--brand)' : 'var(--ink-3)' }} />
                        {child.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* User footer */}
      {mounted && (
        <div style={{ padding: '10px 12px', borderTop: '1px solid var(--line)', flexShrink: 0 }}>
          {user ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 26, height: 26, borderRadius: 999, background: 'var(--bg-3)', display: 'grid', placeItems: 'center', color: 'var(--ink-1)', fontSize: 11, fontWeight: 700, border: '1px solid var(--line-strong)', flexShrink: 0 }}>
                {(user.display_name || user.username || 'U').charAt(0).toUpperCase()}
              </div>
              {!collapsed && (
                <>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {user.display_name || user.username}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 1, fontFamily: 'var(--font-geist-mono)' }}>{user.tier}</div>
                  </div>
                  <button
                    onClick={() => { track('logout_click'); logout(); }}
                    style={{ fontSize: 11, color: 'var(--ink-3)', background: 'none', border: 'none', cursor: 'pointer', padding: '3px 6px', borderRadius: 4, flexShrink: 0 }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--ink-1)'; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--ink-3)'; }}
                  >
                    退出
                  </button>
                </>
              )}
            </div>
          ) : (
            !collapsed && <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>开发模式</span>
          )}
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------
// Desktop Sidebar (collapsible)
// ----------------------------------------------------------------
function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <aside style={{
      width: collapsed ? 64 : 220,
      minHeight: '100vh',
      background: 'var(--bg-1)',
      borderRight: '1px solid var(--line)',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      transition: 'width .2s ease',
      position: 'relative',
      overflow: 'hidden',
    }}>
      <SideNavContent collapsed={collapsed} />
      {/* Collapse toggle button */}
      <button
        onClick={onToggle}
        title={collapsed ? '展开侧边栏' : '收起侧边栏'}
        style={{
          position: 'absolute', bottom: 60, right: collapsed ? 8 : 8,
          width: 22, height: 22, borderRadius: '50%',
          background: 'var(--bg-3)', border: '1px solid var(--line-strong)',
          color: 'var(--ink-2)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'all .15s',
          padding: 0,
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--ink)'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--ink-2)'; }}
      >
        <NavIcon name={collapsed ? 'expand' : 'collapse'} size={12} />
      </button>
    </aside>
  );
}

// ----------------------------------------------------------------
// TopBar (desktop)
// ----------------------------------------------------------------
function TopBar({
  theme,
  onToggleTheme,
  topBarSlot,
}: {
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  topBarSlot?: React.ReactNode;
}) {
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href;

  const iconBtn = (href: string): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 30, height: 30, borderRadius: 6,
    color: isActive(href) ? 'var(--brand)' : 'var(--ink-2)',
    background: isActive(href) ? 'var(--brand-soft)' : 'transparent',
    border: 'none', cursor: 'pointer', transition: 'all .12s',
    flexShrink: 0, textDecoration: 'none',
  });

  return (
    <header style={{
      height: 52, borderBottom: '1px solid var(--line)',
      padding: '0 20px', display: 'flex', alignItems: 'center', gap: 16,
      background: 'var(--bg-1)', position: 'sticky', top: 0, zIndex: 5,
      flexShrink: 0,
    }}>
      {/* Page title slot */}
      {topBarSlot && (
        <div style={{ flexShrink: 0 }}>{topBarSlot}</div>
      )}

      {/* Market tickers */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flex: 1, overflow: 'hidden', minWidth: 0 }}>
        <IndexTicker name="上证" code="000001.SH" value="3,287" chg="+24" chgPct="+0.74%" up />
        <IndexTicker name="深证" code="399001.SZ" value="10,412" chg="+78" chgPct="+0.76%" up />
        <IndexTicker name="创业板" code="399006.SZ" value="2,184" chg="-8" chgPct="-0.39%" up={false} />
        <IndexTicker name="北证50" code="899050.BJ" value="1,024" chg="+12" chgPct="+1.19%" up />
      </div>

      {/* Right controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, marginLeft: 'auto' }}>
        <LiveClock />

        <button
          onClick={onToggleTheme}
          title={theme === 'dark' ? '切换浅色' : '切换深色'}
          className="btn ghost sm"
          style={{ padding: '4px 8px', gap: 4 }}
        >
          <NavIcon name="theme" size={13} />
          <span style={{ fontSize: 11 }}>{theme === 'dark' ? 'Dark' : 'Light'}</span>
        </button>

        <Link href="/inbox" style={{ ...iconBtn('/inbox') }} title="信箱"
          onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--ink)'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = isActive('/inbox') ? 'var(--brand)' : 'var(--ink-2)'; }}
        >
          <NavIcon name="mail" size={15} />
        </Link>

        <Link href="/settings" style={{ ...iconBtn('/settings') }} title="设置"
          onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--ink)'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = isActive('/settings') ? 'var(--brand)' : 'var(--ink-2)'; }}
        >
          <NavIcon name="settings" size={15} />
        </Link>
      </div>
    </header>
  );
}

// ----------------------------------------------------------------
// Mobile Nav (drawer)
// ----------------------------------------------------------------
function MobileNav({ topBar }: { topBar?: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  return (
    <>
      <style>{`
        .mt-mobile-bar {
          display: none;
        }
        @media (max-width: 767px) {
          .mt-mobile-bar {
            display: flex; align-items: center; gap: 8px;
            padding: 0 12px; height: 48px;
            background: var(--bg-1); border-bottom: 1px solid var(--line);
            flex-shrink: 0; position: sticky; top: 0; z-index: 40;
          }
        }
        .mt-drawer-overlay {
          position: fixed; inset: 0; background: rgba(0,0,0,0.45);
          z-index: 50; animation: fadeIn .15s ease;
        }
        .mt-drawer {
          position: fixed; top: 0; left: 0; bottom: 0; width: 240px;
          background: var(--bg-1); border-right: 1px solid var(--line);
          z-index: 51; animation: slideIn .2s ease; overflow-y: auto;
          display: flex; flex-direction: column;
        }
      `}</style>

      <div className="mt-mobile-bar">
        <button
          onClick={() => setOpen((v) => !v)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink)', padding: 4, display: 'flex', alignItems: 'center', flexShrink: 0 }}
        >
          <NavIcon name={open ? 'x' : 'menu'} size={20} />
        </button>
        {topBar ? (
          <div style={{ flex: 1, minWidth: 0 }}>{topBar}</div>
        ) : (
          <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.01em' }}>myTrader</span>
        )}
        <Link href="/inbox" style={{ color: 'var(--ink-2)', display: 'flex' }} title="信箱">
          <NavIcon name="mail" size={18} />
        </Link>
      </div>

      {open && (
        <>
          <div className="mt-drawer-overlay" onClick={close} />
          <div className="mt-drawer">
            <SideNavContent collapsed={false} onNavigate={close} />
          </div>
        </>
      )}
    </>
  );
}

// ----------------------------------------------------------------
// AppShell
// ----------------------------------------------------------------
export default function AppShell({
  children,
  topBar,
}: {
  children: React.ReactNode;
  topBar?: React.ReactNode;
}) {
  const { user, fetchUser } = useAuthStore();
  const [authReady, setAuthReady] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { theme, toggle: toggleTheme } = useTheme();

  useEffect(() => {
    // Restore collapse state
    const saved = localStorage.getItem('mt-sidebar-collapsed');
    if (saved === 'true') setSidebarCollapsed(true);
  }, []);

  function handleToggleSidebar() {
    setSidebarCollapsed((v) => {
      const next = !v;
      localStorage.setItem('mt-sidebar-collapsed', String(next));
      return next;
    });
  }

  useEffect(() => {
    fetchUser().finally(() => setAuthReady(true));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <style>{`
        .mt-shell {
          display: flex;
          min-height: 100vh;
          background: var(--bg);
        }
        .mt-main {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-width: 0;
        }
        .mt-content {
          flex: 1;
          overflow-y: auto;
          padding: 24px;
        }
        .mt-desktop-sidebar {
          display: flex;
        }
        .mt-desktop-topbar {
          display: flex;
        }
        @media (max-width: 767px) {
          .mt-desktop-sidebar { display: none; }
          .mt-desktop-topbar  { display: none; }
          .mt-content { padding: 16px; }
        }
      `}</style>
      <div className="mt-shell">
        <div className="mt-desktop-sidebar">
          <Sidebar collapsed={sidebarCollapsed} onToggle={handleToggleSidebar} />
        </div>
        <div className="mt-main">
          <MobileNav topBar={topBar} />
          <div className="mt-desktop-topbar" style={{ flexDirection: 'column' }}>
            <TopBar theme={theme} onToggleTheme={toggleTheme} topBarSlot={topBar} />
          </div>
          <main className="mt-content">
            {children}
          </main>
        </div>
        {authReady && user && <FloatingAssistant />}
      </div>
    </>
  );
}
