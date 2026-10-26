"use client";

/**
 * Session state for the dashboard.
 *
 * The access token lives only in memory (lib/auth/session.ts, so the API client
 * always reads the latest one). The refresh token is an httpOnly cookie the browser sends to
 * /auth/refresh/, which restores the session after a reload. The active
 * organisation id is remembered per browser as a convenience.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, type ApiClient } from "@/lib/api/client";
import type { AuthResponse, MeResponse, Organization, User } from "@/lib/api/types";
import {
  api,
  getFreshAccessToken,
  getOrganizationId,
  refreshAccessToken,
  setAccessToken,
  setOrganizationId as setSessionOrganization,
} from "@/lib/auth/session";

const ACTIVE_ORG_KEY = "helploom.activeOrganization";
/** Set while this browser has a session, so public pages can skip the refresh probe. */
const SESSION_HINT_KEY = "helploom.signedIn";

/** "unavailable": the server could not be reached to restore the session (it may still be valid). */
export type AuthStatus = "loading" | "authenticated" | "anonymous" | "unavailable";
/** Why the session could not be restored: rate limited, or no usable answer from the server. */
export type UnavailableReason = "throttled" | "unreachable";

export interface SignupInput {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}

export interface AuthContextValue {
  status: AuthStatus;
  /** Set while status is "unavailable". */
  unavailableReason: UnavailableReason | null;
  user: User | null;
  organizations: Organization[];
  organization: Organization | null;
  api: ApiClient;
  login: (email: string, password: string) => Promise<void>;
  signup: (input: SignupInput) => Promise<void>;
  /** Signed in: pass no body. New account: pass full_name and password. */
  acceptInvitation: (token: string, body?: { full_name: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
  switchOrganization: (organizationId: string) => void;
  /** Reload the user and organisations, for example after renaming the workspace. */
  reload: () => Promise<void>;
  /** Try to restore the session again after "unavailable". */
  retry: () => void;
  /** For websocket auth frames: the current token, refreshed when it is missing. */
  getAccessToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredOrganization(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_ORG_KEY);
  } catch {
    return null;
  }
}

function storeOrganization(organizationId: string | null): void {
  try {
    if (organizationId) window.localStorage.setItem(ACTIVE_ORG_KEY, organizationId);
    else window.localStorage.removeItem(ACTIVE_ORG_KEY);
  } catch {
    // Blocked storage only means the choice is not remembered.
  }
}

function readSessionHint(): boolean {
  try {
    return window.localStorage.getItem(SESSION_HINT_KEY) === "1";
  } catch {
    // Unknown when storage is blocked, so always ask the server.
    return true;
  }
}

function storeSessionHint(signedIn: boolean): void {
  try {
    if (signedIn) window.localStorage.setItem(SESSION_HINT_KEY, "1");
    else window.localStorage.removeItem(SESSION_HINT_KEY);
  } catch {
    // Without storage every page simply asks the server.
  }
}

function pickOrganization(organizations: Organization[], preferredId: string | null): Organization | null {
  return organizations.find((org) => org.id === preferredId) ?? organizations[0] ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [unavailableReason, setUnavailableReason] = useState<UnavailableReason | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState<string | null>(null);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    storeSessionHint(false);
    setUser(null);
    setOrganizations([]);
    setStatus("anonymous");
  }, []);

  const applySession = useCallback((nextUser: User, nextOrganizations: Organization[]) => {
    const active = pickOrganization(nextOrganizations, getOrganizationId() ?? readStoredOrganization());
    setSessionOrganization(active?.id ?? null);
    storeOrganization(active?.id ?? null);
    storeSessionHint(true);
    setUser(nextUser);
    setOrganizations(nextOrganizations);
    setOrganizationId(active?.id ?? null);
    setStatus("authenticated");
  }, []);

  const applyAuthResponse = useCallback(
    (response: AuthResponse) => {
      setAccessToken(response.access);
      applySession(response.user, response.organizations);
    },
    [applySession],
  );

  const reload = useCallback(async () => {
    const me = await api.get<MeResponse>("/auth/me/");
    applySession(me.user, me.organizations);
  }, [applySession]);

  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      // A browser that never signed in has no refresh cookie. Public pages skip the
      // probe for it, which saves a request (and an expected 401) per page view and
      // spares the per IP auth throttle. Dashboard routes always ask, so a session
      // survives cleared storage.
      if (!readSessionHint() && !window.location.pathname.startsWith("/app")) {
        clearSession();
        return;
      }
      try {
        const token = await refreshAccessToken();
        if (cancelled) return;
        if (!token) {
          clearSession();
          return;
        }
        const me = await api.get<MeResponse>("/auth/me/");
        if (!cancelled) applySession(me.user, me.organizations);
      } catch (error) {
        if (cancelled) return;
        // A 401 here means the fresh token was refused: the session is over. Anything
        // else (offline, throttled, server down) keeps the cookie for a retry.
        if (error instanceof ApiError && error.status === 401) {
          clearSession();
          return;
        }
        setUnavailableReason(error instanceof ApiError && error.code === "throttled" ? "throttled" : "unreachable");
        setStatus("unavailable");
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, [applySession, clearSession, attempt]);

  const retry = useCallback(() => {
    setUnavailableReason(null);
    setStatus("loading");
    setAttempt((value) => value + 1);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const body = { email, password };
      applyAuthResponse(await api.post<AuthResponse>("/auth/login/", body, { auth: false, cookie: true }));
    },
    [applyAuthResponse],
  );

  const signup = useCallback(
    async (input: SignupInput) => {
      applyAuthResponse(await api.post<AuthResponse>("/auth/signup/", input, { auth: false, cookie: true }));
    },
    [applyAuthResponse],
  );

  const acceptInvitation = useCallback(
    async (token: string, body?: { full_name: string; password: string }) => {
      const path = `/invitations/${encodeURIComponent(token)}/accept/`;
      applyAuthResponse(
        await api.post<AuthResponse>(path, body ?? {}, { auth: body === undefined, cookie: true }),
      );
    },
    [applyAuthResponse],
  );

  const logout = useCallback(async () => {
    try {
      await api.post<void>("/auth/logout/", undefined, { auth: false, cookie: true });
    } catch (error) {
      // Logging out locally must work even when the server is unreachable.
      if (!(error instanceof ApiError)) throw error;
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const switchOrganization = useCallback((id: string) => {
    setSessionOrganization(id);
    storeOrganization(id);
    setOrganizationId(id);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      unavailableReason,
      user,
      organizations,
      organization: organizations.find((org) => org.id === organizationId) ?? null,
      api,
      login,
      signup,
      acceptInvitation,
      logout,
      switchOrganization,
      reload,
      retry,
      getAccessToken: getFreshAccessToken,
    }),
    [
      status,
      unavailableReason,
      user,
      organizations,
      organizationId,
      login,
      signup,
      acceptInvitation,
      logout,
      switchOrganization,
      reload,
      retry,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>.");
  return value;
}
