/**
 * PostHog client configuration.
 *
 * NEXT_PUBLIC_POSTHOG_KEY   - Project API key from PostHog UI (Settings > Project)
 * NEXT_PUBLIC_POSTHOG_HOST  - Self-hosted instance URL, defaults to cloud
 */
export const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY ?? '';
export const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? 'https://us.i.posthog.com';

/** True when PostHog is configured (key is present). */
export const POSTHOG_ENABLED = Boolean(POSTHOG_KEY);
