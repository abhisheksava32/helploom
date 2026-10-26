/**
 * Public runtime configuration. NEXT_PUBLIC_ values are inlined at build time, so they
 * must be referenced literally (process.env.NEXT_PUBLIC_X), never through a variable.
 */

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

export const config = {
  apiUrl: trimTrailingSlash(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"),
  wsUrl: trimTrailingSlash(process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000"),
  appUrl: trimTrailingSlash(process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"),
  /** Optional: a public site key whose live widget the landing page loads. */
  demoSiteKey: process.env.NEXT_PUBLIC_DEMO_SITE_KEY?.trim() || null,
} as const;

/** REST base: every endpoint in docs/API.md is relative to this. */
export const apiBase = `${config.apiUrl}/api/v1`;
