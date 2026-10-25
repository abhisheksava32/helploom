/**
 * In-memory session for the browser: the access token, the active organisation and a
 * single flight refresh. Kept outside React so the API client and websocket hooks
 * always read the latest values without re-rendering anything.
 *
 * Browser only: import it from client components and hooks, never from server code.
 */

import { createApiClient } from "@/lib/api/client";

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

/** Exchanges the refresh cookie for a new access token; concurrent callers share one request. */
export function refreshAccessToken(): Promise<string | null> {
  refreshInFlight ??= api
    .post<{ access: string }>("/auth/refresh/", undefined, { auth: false, cookie: true })
    .then((result) => {
      accessToken = result.access;
      return result.access;
    })
    .catch(() => {
      accessToken = null;
      return null;
    })
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

export const api = createApiClient({
  getAccessToken,
  getOrganizationId,
  refreshAccessToken,
});
