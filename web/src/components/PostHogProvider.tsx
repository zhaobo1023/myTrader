'use client';

import posthog from 'posthog-js';
import { PostHogProvider as PHProvider, usePostHog } from 'posthog-js/react';
import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, Suspense } from 'react';
import { POSTHOG_KEY, POSTHOG_HOST, POSTHOG_ENABLED } from '@/lib/posthog';

// ---------------------------------------------------------------------------
// Init (runs once on the client)
// ---------------------------------------------------------------------------

if (typeof window !== 'undefined' && POSTHOG_ENABLED) {
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    // Capture page views manually so we control when they fire (after router navigation)
    capture_pageview: false,
    // Capture performance metrics (web vitals)
    capture_performance: true,
    // Store the distinct_id in localStorage, not a cookie
    persistence: 'localStorage',
    // Respect user's Do Not Track header
    respect_dnt: true,
    // Disable session recording by default — enable in PostHog UI if needed
    disable_session_recording: false,
  });
}

// ---------------------------------------------------------------------------
// Page view tracker — fires on every route change
// ---------------------------------------------------------------------------

function PageViewTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const ph = usePostHog();

  useEffect(() => {
    if (!POSTHOG_ENABLED || !ph) return;

    const url = pathname + (searchParams.toString() ? `?${searchParams.toString()}` : '');
    ph.capture('$pageview', { $current_url: url });
  }, [pathname, searchParams, ph]);

  return null;
}

// ---------------------------------------------------------------------------
// Provider wrapper
// ---------------------------------------------------------------------------

export default function PostHogProvider({ children }: { children: React.ReactNode }) {
  if (!POSTHOG_ENABLED) {
    return <>{children}</>;
  }

  return (
    <PHProvider client={posthog}>
      {/* Suspense required because useSearchParams() needs it in App Router */}
      <Suspense fallback={null}>
        <PageViewTracker />
      </Suspense>
      {children}
    </PHProvider>
  );
}
