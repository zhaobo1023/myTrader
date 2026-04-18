'use client';

import { useEffect, useCallback } from 'react';
import { usePathname } from 'next/navigation';
import { useAgentStore } from '@/lib/agent-store';
import FloatingButton from './FloatingButton';
import ChatPanel from './ChatPanel';

/**
 * FloatingAssistant - global agent component embedded in AppShell.
 *
 * Renders the floating button + chat panel on all authenticated pages.
 * Listens for Cmd+/ or Ctrl+/ to toggle.
 * Updates page context on route changes.
 */
export default function FloatingAssistant() {
  const { toggle, updatePageContext } = useAgentStore();
  const pathname = usePathname();

  // Update page context on route change
  useEffect(() => {
    const page = pathname.split('/')[1] || '';
    // Extract stock_code from query params if present
    const params = new URLSearchParams(
      typeof window !== 'undefined' ? window.location.search : '',
    );
    const ctx: Record<string, unknown> = { page };
    const stockCode = params.get('code') || params.get('stock_code');
    if (stockCode) ctx.stock_code = stockCode;
    const stockName = params.get('name') || params.get('stock_name');
    if (stockName) ctx.stock_name = stockName;

    updatePageContext(ctx);
  }, [pathname, updatePageContext]);

  // Keyboard shortcut: Cmd+/ or Ctrl+/
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        toggle();
      }
    },
    [toggle],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <>
      <FloatingButton />
      <ChatPanel />
    </>
  );
}
