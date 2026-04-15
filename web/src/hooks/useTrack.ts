'use client';

/**
 * useTrack — thin wrapper around PostHog for manual event capture.
 *
 * Usage:
 *   const { track } = useTrack();
 *   track('button_click', { button: 'generate_report', page: '/analysis' });
 *
 * If PostHog is not configured (NEXT_PUBLIC_POSTHOG_KEY is empty) every call
 * is a no-op, so development stays clean.
 */

import { usePostHog } from 'posthog-js/react';
import { usePathname } from 'next/navigation';
import { useCallback } from 'react';
import { POSTHOG_ENABLED } from '@/lib/posthog';

export type TrackFn = (event: string, props?: Record<string, unknown>) => void;

export function useTrack(): { track: TrackFn } {
  const ph = usePostHog();
  const pathname = usePathname();

  const track = useCallback<TrackFn>(
    (event, props) => {
      if (!POSTHOG_ENABLED || !ph) return;
      ph.capture(event, { page: pathname, ...props });
    },
    [ph, pathname],
  );

  return { track };
}
