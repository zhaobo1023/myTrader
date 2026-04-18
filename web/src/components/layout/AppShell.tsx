'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/lib/store';
import { useEffect, useState, useCallback, useMemo } from 'react';
import { useTrack } from '@/hooks/useTrack';
import { NAV_PERMISSIONS, hasPermission } from '@/lib/permissions';

// ----------------------------------------------------------------
// Nav structure with permission requirements
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
    label: '指标看板',
    labelEn: 'Market',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
      </svg>
    ),
  },
  {
    href: '/stock',
    label: 'AI投研',
    labelEn: 'Stock',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
  },
  {
    href: '/strategy',
    label: 'AI选股',
    labelEn: 'Strategy',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/>
      </svg>
    ),
  },
  {
    href: '/portfolio',
    label: '仓位管理',
    labelEn: 'Portfolio',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      </svg>
    ),
  },
  {
    href: '/data-health',
    label: '数据完备度',
    labelEn: 'Data Health',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        <circle cx="12" cy="12" r="1"/>
      </svg>
    ),
  },
  {
    href: '/rag',
    label: '投资问答',
    labelEn: 'Knowledge',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
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
// Topbar icon links (Inbox + Settings)
// ----------------------------------------------------------------
function TopBarIcons() {
  const pathname = usePathname();
  const iconBtnStyle = (href: string): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: '32px', height: '32px', borderRadius: '6px',
    color: pathname === href ? 'var(--accent)' : 'var(--text-tertiary)',
    background: pathname === href ? 'var(--bg-nav-active)' : 'transparent',
    transition: 'all 0.12s',
    flexShrink: 0,
  });

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <Link
        href="/inbox"
        style={{ ...iconBtnStyle('/inbox'), textDecoration: 'none' }}
        title="信箱"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
        </svg>
      </Link>
      <Link
        href="/settings"
        style={{ ...iconBtnStyle('/settings'), textDecoration: 'none' }}
        title="设置"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
      </Link>
    </div>
  );
}

// ----------------------------------------------------------------
// Hamburger icon
// ----------------------------------------------------------------
function HamburgerIcon({ open }: { open: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {open ? (
        <>
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </>
      ) : (
        <>
          <line x1="3" y1="6" x2="21" y2="6"/>
          <line x1="3" y1="12" x2="21" y2="12"/>
          <line x1="3" y1="18" x2="21" y2="18"/>
        </>
      )}
    </svg>
  );
}

// ----------------------------------------------------------------
// Sidebar Nav content (shared between desktop sidebar and mobile drawer)
// ----------------------------------------------------------------
function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  const [mounted, setMounted] = useState(false);
  const { track } = useTrack();

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    return { '/strategy': true };
  });

  useEffect(() => { setMounted(true); }, []);

  function toggleExpand(href: string) {
    setExpanded((prev) => ({ ...prev, [href]: !prev[href] }));
  }

  function handleNavClick(item: NavItem) {
    track('nav_click', { nav_label: item.labelEn, nav_href: item.href });
    onNavigate?.();
  }

  function handleChildNavClick(child: NavChild, parentLabel: string) {
    track('nav_click', { nav_label: child.label, nav_href: child.href, parent: parentLabel });
    onNavigate?.();
  }

  function isParentActive(item: NavItem): boolean {
    if (pathname === item.href) return true;
    if (item.children?.some((c) => pathname === c.href || pathname.startsWith(c.href + '/'))) return true;
    if (pathname.startsWith(item.href + '/')) return true;
    // Merged routes: /positions, /sim-pool, /candidate-pool -> /portfolio; /theme-pool -> /strategy
    if (item.href === '/portfolio' && (pathname.startsWith('/positions') || pathname.startsWith('/sim-pool') || pathname.startsWith('/candidate-pool'))) return true;
    if (item.href === '/strategy' && pathname.startsWith('/theme-pool')) return true;
    return false;
  }

  return (
    <>
      {/* Logo */}
      <div style={{ padding: '20px 16px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <span style={{ fontSize: '15px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
          myTrader
        </span>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '8px', overflowY: 'auto' }}>
        {NAV_ITEMS.filter((item) => {
          // Filter navigation items based on user permissions
          const permission = NAV_PERMISSIONS[item.href];
          if (!permission) return true;
          return hasPermission(user?.tier ?? null, user?.role ?? null, permission);
        }).map((item) => {
          const parentActive = isParentActive(item);
          const hasChildren = item.children && item.children.length > 0;
          const isOpen = expanded[item.href] ?? false;

          return (
            <div key={item.href}>
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
                  onClick={hasChildren
                    ? (e) => { e.preventDefault(); toggleExpand(item.href); }
                    : () => handleNavClick(item)
                  }
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

              {hasChildren && isOpen && (
                <div style={{ marginBottom: '4px' }}>
                  {item.children!.map((child) => {
                    const childActive = pathname === child.href || pathname.startsWith(child.href + '/');
                    return (
                      <Link
                        key={child.href}
                        href={child.href}
                        onClick={() => handleChildNavClick(child, item.labelEn)}
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
                  {user.display_name || user.username}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>{user.tier}</div>
              </div>
              <button
                onClick={() => { track('logout_click'); logout(); }}
                style={{ fontSize: '11px', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '3px 6px', borderRadius: '4px', flexShrink: 0 }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)'; }}
              >
                退出
              </button>
            </div>
          ) : (
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>开发模式</span>
          )}
        </div>
      )}
    </>
  );
}

// ----------------------------------------------------------------
// Desktop Sidebar (hidden on mobile)
// ----------------------------------------------------------------
function Sidebar() {
  return (
    <>
      <style>{`
        .app-sidebar {
          width: 200px;
          min-height: 100vh;
          background: var(--bg-panel);
          border-right: 1px solid var(--border-subtle);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
        }
        @media (max-width: 767px) {
          .app-sidebar { display: none; }
        }
      `}</style>
      <aside className="app-sidebar">
        <SidebarNav />
      </aside>
    </>
  );
}

// ----------------------------------------------------------------
// Mobile top bar + drawer
// ----------------------------------------------------------------
function MobileNav({ topBar }: { topBar?: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close drawer on route change
  useEffect(() => { setOpen(false); }, [pathname]);

  // Prevent body scroll when drawer open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  const close = useCallback(() => setOpen(false), []);

  return (
    <>
      <style>{`
        .mobile-topbar {
          display: none;
        }
        @media (max-width: 767px) {
          .mobile-topbar {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 0 12px;
            height: 48px;
            background: var(--bg-panel);
            border-bottom: 1px solid var(--border-subtle);
            flex-shrink: 0;
            position: sticky;
            top: 0;
            z-index: 40;
          }
          .mobile-topbar-logo {
            font-size: 15px;
            font-weight: 590;
            color: var(--text-primary);
            letter-spacing: -0.3px;
            flex-shrink: 0;
          }
          .mobile-topbar-slot {
            flex: 1;
            min-width: 0;
            display: flex;
            align-items: center;
          }
        }
        .mobile-drawer-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0,0,0,0.4);
          z-index: 50;
          animation: fadeIn 0.15s ease;
        }
        .mobile-drawer {
          position: fixed;
          top: 0;
          left: 0;
          bottom: 0;
          width: 240px;
          background: var(--bg-panel);
          border-right: 1px solid var(--border-subtle);
          display: flex;
          flex-direction: column;
          z-index: 51;
          animation: slideIn 0.2s ease;
          overflow-y: auto;
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes slideIn {
          from { transform: translateX(-100%); }
          to   { transform: translateX(0); }
        }
      `}</style>

      <div className="mobile-topbar">
        <button
          onClick={() => setOpen((v) => !v)}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-primary)', padding: '4px', display: 'flex', alignItems: 'center', flexShrink: 0,
          }}
          aria-label="Toggle menu"
        >
          <HamburgerIcon open={open} />
        </button>
        {topBar ? (
          <div className="mobile-topbar-slot">{topBar}</div>
        ) : (
          <span className="mobile-topbar-logo">myTrader</span>
        )}
        <TopBarIcons />
      </div>

      {open && (
        <>
          <div className="mobile-drawer-overlay" onClick={close} />
          <div className="mobile-drawer">
            <SidebarNav onNavigate={close} />
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
  return (
    <>
      <style>{`
        .app-shell {
          display: flex;
          min-height: 100vh;
          background: var(--bg-canvas);
        }
        .app-main {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-width: 0;
        }
        .app-topbar {
          height: 48px;
          border-bottom: 1px solid var(--border-subtle);
          display: flex;
          align-items: center;
          padding: 0 24px;
          flex-shrink: 0;
          background: var(--bg-panel);
        }
        .app-content {
          flex: 1;
          overflow-y: auto;
          padding: 24px;
        }
        @media (max-width: 767px) {
          .app-content {
            padding: 16px;
          }
          /* Desktop topbar hidden on mobile — topBar content is in MobileNav instead */
          .app-topbar {
            display: none;
          }
        }
      `}</style>
      <div className="app-shell">
        <Sidebar />
        <div className="app-main">
          <MobileNav topBar={topBar} />
          <header className="app-topbar">
            <div style={{ flex: 1, minWidth: 0 }}>{topBar}</div>
            <TopBarIcons />
          </header>
          <main className="app-content">
            {children}
          </main>
        </div>
      </div>
    </>
  );
}
