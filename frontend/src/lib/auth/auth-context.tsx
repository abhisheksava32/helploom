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
  getAccessToken,
  getOrganizationId,
  refreshAccessToken,
  setAccessToken,
  setOrganizationId as setSessionOrganization,
} from "@/lib/auth/session";

const ACTIVE_ORG_KEY = "helploom.activeOrganization";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface SignupInput {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}

export interface AuthContextValue {
  status: AuthStatus;
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

function pickOrganization(organizations: Organization[], preferredId: string | null): Organization | null {
  return organizations.find((org) => org.id === preferredId) ?? organizations[0] ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState<string | null>(null);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setOrganizations([]);
    setStatus("anonymous");
  }, []);

  const applySession = useCallback((nextUser: User, nextOrganizations: Organization[]) => {
    const active = pickOrganization(nextOrganizations, getOrganizationId() ?? readStoredOrganization());
    setSessionOrganization(active?.id ?? null);
    storeOrganization(active?.id ?? null);
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

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      const token = await refreshAccessToken();
      if (cancelled) return;
      if (!token) {
        clearSession();
        return;
      }
      try {
        const me = await api.get<MeResponse>("/auth/me/");
        if (!cancelled) applySession(me.user, me.organizations);
      } catch {
        if (!cancelled) clearSession();
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, [applySession, clearSession]);

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

  const getFreshAccessToken = useCallback(
    async () => getAccessToken() ?? (await refreshAccessToken()),
    [],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
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
      getAccessToken: getFreshAccessToken,
    }),
    [
      status,
      user,
      organizations,
      organizationId,
      login,
      signup,
      acceptInvitation,
      logout,
      switchOrganization,
      reload,
      getFreshAccessToken,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>.");
  return value;
}
