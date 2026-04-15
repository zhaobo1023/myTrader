'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/lib/store';
import { useEffect, useState, useCallback } from 'react';

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
    href: '/rag',
    label: 'RAG',
    labelEn: 'RAG',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
      </svg>
    ),
    children: [
      { href: '/rag', label: '研报生成' },
      { href: '/rag?tab=knowledge', label: '知识库' },
    ],
  },
  {
    href: '/theme-pool',
    label: '主题选股',
    labelEn: 'Themes',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    ),
  },
  {
    href: '/candidate-pool',
    label: '候选池',
    labelEn: 'Watchlist',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
      </svg>
    ),
  },
  {
    href: '/sim-pool',
    label: '模拟池',
    labelEn: 'SimPool',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><path d="M14 17h7m-3.5-3.5v7"/>
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

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    return { '/strategy': true };
  });

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
    <>
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
                    : onNavigate
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
                        onClick={onNavigate}
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
          {topBar && (
            <header className="app-topbar">
              {topBar}
            </header>
          )}
          <main className="app-content">
            {children}
          </main>
        </div>
      </div>
    </>
  );
}
