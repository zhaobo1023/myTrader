'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/lib/store';
import { useEffect, useState } from 'react';

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
  children?: NavChild[];   // sub-menu items
}

const NAV_ITEMS: NavItem[] = [
  {
    href: '/sentiment',
    label: '大盘',
    labelEn: 'Market',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
      </svg>
    ),
  },
  {
    href: '/industry',
    label: '行业',
    labelEn: 'Industry',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="6" height="14"/><rect x="9" y="3" width="6" height="18"/><rect x="16" y="10" width="6" height="11"/>
      </svg>
    ),
  },
  {
    href: '/stock',
    label: '个股',
    labelEn: 'Stock',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
  },
  {
    href: '/strategy',
    label: '策略',
    labelEn: 'Strategy',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/>
      </svg>
    ),
  },
  {
    href: '/portfolio-mgmt',
    label: '组合管理',
    labelEn: 'Portfolio',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      </svg>
    ),
  },
];

// ----------------------------------------------------------------
// Chevron icon
// ----------------------------------------------------------------
function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'rotate(0deg)', flexShrink: 0 }}
    >
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  );
}

// ----------------------------------------------------------------
// Sidebar
// ----------------------------------------------------------------
function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  const [mounted, setMounted] = useState(false);

  // Track which parent menus are expanded
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    // Auto-expand if current path is under /strategy
    return { '/strategy': true };
  });

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setMounted(true); }, []);

  function toggleExpand(href: string) {
    setExpanded((prev) => ({ ...prev, [href]: !prev[href] }));
  }

  function isParentActive(item: NavItem): boolean {
    if (pathname === item.href) return true;
    if (item.children?.some((c) => pathname === c.href || pathname.startsWith(c.href + '/'))) return true;
    return pathname.startsWith(item.href + '/');
  }

  return (
    <aside
      style={{
        width: '200px',
        minHeight: '100vh',
        background: 'var(--bg-panel)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
      }}
    >
      {/* Logo */}
      <div style={{ padding: '20px 16px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <span style={{ fontSize: '15px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
          myTrader
        </span>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '8px', overflowY: 'auto' }}>
        {NAV_ITEMS.map((item) => {
          const parentActive = isParentActive(item);
          const hasChildren = item.children && item.children.length > 0;
          const isOpen = expanded[item.href] ?? false;

          return (
            <div key={item.href}>
              {/* Parent row */}
              <div
                style={{
                  display: 'flex', alignItems: 'center',
                  borderRadius: '6px', marginBottom: '1px',
                  background: parentActive && !hasChildren ? 'var(--bg-nav-active)' : 'transparent',
                  transition: 'background 0.12s',
                }}
                onMouseEnter={(e) => {
                  if (!parentActive || hasChildren)
                    (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-nav-hover)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.background =
                    parentActive && !hasChildren ? 'var(--bg-nav-active)' : 'transparent';
                }}
              >
                <Link
                  href={hasChildren ? '#' : item.href}
                  onClick={hasChildren ? (e) => { e.preventDefault(); toggleExpand(item.href); } : undefined}
                  style={{
                    flex: 1, display: 'flex', alignItems: 'center', gap: '9px',
                    padding: '7px 10px',
                    fontSize: '13px',
                    fontWeight: parentActive ? 510 : 400,
                    color: parentActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
                    textDecoration: 'none',
                  }}
                >
                  <span style={{ color: parentActive ? 'var(--accent)' : 'var(--text-tertiary)', flexShrink: 0 }}>
                    {item.icon}
                  </span>
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {hasChildren && (
                    <span style={{ color: 'var(--text-muted)' }}>
                      <Chevron open={isOpen} />
                    </span>
                  )}
                </Link>
              </div>

              {/* Children */}
              {hasChildren && isOpen && (
                <div style={{ marginBottom: '4px' }}>
                  {item.children!.map((child) => {
                    const childActive = pathname === child.href || pathname.startsWith(child.href + '/');
                    return (
                      <Link
                        key={child.href}
                        href={child.href}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '8px',
                          padding: '6px 10px 6px 34px',
                          borderRadius: '6px', marginBottom: '1px',
                          fontSize: '12px',
                          fontWeight: childActive ? 510 : 400,
                          color: childActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
                          background: childActive ? 'var(--bg-nav-active)' : 'transparent',
                          textDecoration: 'none',
                          transition: 'all 0.12s',
                        }}
                        onMouseEnter={(e) => {
                          if (!childActive) {
                            (e.currentTarget as HTMLAnchorElement).style.background = 'var(--bg-nav-hover)';
                            (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-secondary)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!childActive) {
                            (e.currentTarget as HTMLAnchorElement).style.background = 'transparent';
                            (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-tertiary)';
                          }
                        }}
                      >
                        <span style={{
                          width: '4px', height: '4px', borderRadius: '50%', flexShrink: 0,
                          background: childActive ? 'var(--accent)' : 'var(--text-muted)',
                        }} />
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

      {/* User section */}
      {mounted && (
        <div style={{ padding: '12px', borderTop: '1px solid var(--border-subtle)' }}>
          {user ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {user.email}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>{user.tier}</div>
              </div>
              <button
                onClick={logout}
                style={{ fontSize: '11px', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '3px 6px', borderRadius: '4px', flexShrink: 0 }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)'; }}
              >
                退出
              </button>
            </div>
          ) : (
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>dev mode</span>
          )}
        </div>
      )}
    </aside>
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
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-canvas)' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {topBar && (
          <header
            style={{
              height: '48px',
              borderBottom: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              padding: '0 24px',
              flexShrink: 0,
              background: 'var(--bg-panel)',
            }}
          >
            {topBar}
          </header>
        )}
        <main style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
