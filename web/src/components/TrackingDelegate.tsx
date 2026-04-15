'use client';

/**
 * TrackingDelegate — global click listener for declarative button tracking.
 *
 * Any element with a `data-track` attribute will automatically fire a
 * "button_click" event when clicked. Extra properties can be passed via
 * additional `data-track-*` attributes.
 *
 * Example:
 *   <button data-track="generate_report" data-track-tab="technical">
 *     Generate
 *   </button>
 *
 * This avoids wiring useTrack() into every individual button and keeps
 * component code clean.
 */

import { useEffect } from 'react';
import { usePostHog } from 'posthog-js/react';
import { usePathname } from 'next/navigation';
import { POSTHOG_ENABLED } from '@/lib/posthog';

export default function TrackingDelegate() {
  const ph = usePostHog();
  const pathname = usePathname();

  useEffect(() => {
    if (!POSTHOG_ENABLED || !ph) return;

    function handleClick(e: MouseEvent) {
      // Walk up the DOM to find the nearest element with data-track
      let el = e.target as HTMLElement | null;
      while (el && el !== document.body) {
        const eventName = el.dataset.track;
        if (eventName) {
          // Collect all data-track-* attributes as extra properties
          const extra: Record<string, string> = {};
          for (const key of Object.keys(el.dataset)) {
            if (key.startsWith('track') && key !== 'track') {
              // Convert camelCase key back to snake_case label, e.g. trackTabName -> tab_name
              const label = key
                .replace(/^track/, '')
                .replace(/([A-Z])/g, '_$1')
                .toLowerCase()
                .replace(/^_/, '');
              extra[label] = el.dataset[key]!;
            }
          }
          ph.capture('button_click', {
            button: eventName,
            page: pathname,
            ...extra,
          });
          return;
        }
        el = el.parentElement;
      }
    }

    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [ph, pathname]);

  return null;
}
