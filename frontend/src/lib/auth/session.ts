/**
 * In-memory session for the browser: the access token, the active organisation and a
 * single flight refresh. Kept outside React so the API client and websocket hooks
 * always read the latest values without re-rendering anything.
 *
 * Browser only: import it from client components and hooks, never from server code.
 */

import { ApiError, createApiClient } from "@/lib/api/client";

let accessToken: string | null = null;
let organizationId: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getOrganizationId(): string | null {
  return organizationId;
}

export function setOrganizationId(id: string | null): void {
  organizationId = id;
}

/**
 * Seconds until the JWT's exp claim, or 0 when it cannot be read. Only used to
 * decide when to refresh early; the server still verifies the signature.
 */
export function secondsUntilExpiry(token: string, now = Date.now()): number {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = (JSON.parse(json) as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp - now / 1000 : 0;
  } catch {
    return 0;
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * The refresh token rotates on every use and the old one is blacklisted, so two tabs
 * refreshing at the same moment would race: the loser sends a token that was just
 * revoked and gets logged out. A Web Lock makes refreshes take turns across tabs; the
 * second one then sends the cookie the first one just received.
 */
async function acrossTabs<T>(task: () => Promise<T>): Promise<T> {
  if (typeof navigator === "undefined" || !navigator.locks) return task();
  return (await navigator.locks.request("helploom.auth-refresh", task)) as T;
}

/**
 * Exchanges the refresh cookie for a new access token; concurrent callers share one
 * request. Resolves to null only when the server says the session is over (401 or
 * 403). A throttled refresh is retried once after Retry-After; other failures
 * (network, 5xx) reject, because the session may well still be valid and logging
 * the user out over a blip would be wrong.
 */
export function refreshAccessToken(): Promise<string | null> {
  refreshInFlight ??= (async () => {
    for (let attempt = 0; ; attempt += 1) {
      try {
        const result = await acrossTabs(() =>
          api.post<{ access: string }>("/auth/refresh/", undefined, { auth: false, cookie: true }),
        );
        accessToken = result.access;
        return result.access;
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          accessToken = null;
          return null;
        }
        if (error instanceof ApiError && error.code === "throttled" && attempt === 0) {
          const retryAfter = Number(error.details.retry_after);
          await sleep(Math.min(Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : 5, 20) * 1000);
          continue;
        }
        throw error;
      }
    }
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/**
 * A token that stays valid for at least the next 30 seconds. Websocket auth frames
 * use it, so a socket never authenticates with a token about to expire.
 */
export async function getFreshAccessToken(): Promise<string | null> {
  if (accessToken && secondsUntilExpiry(accessToken) > 30) return accessToken;
  return refreshAccessToken();
}

export const api = createApiClient({
  getAccessToken,
  getOrganizationId,
  refreshAccessToken,
});
