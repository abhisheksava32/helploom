"use client";

/**
 * The dashboard's live connection (ws/dashboard/). One socket per signed in tab,
 * shared through context. Events are hints (docs/API.md, section 14): pages patch
 * what they show from the payload, and every reconnect refetches everything because
 * events sent while offline are lost.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useEffectEvent,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { DashboardEvent, DashboardEventType, ErrorFrame, Role } from "@/lib/api/types";
import { getFreshAccessToken, refreshAccessToken } from "@/lib/auth/session";
import { config } from "@/lib/config";
import { invalidate, invalidateAll, type QueryTag } from "@/lib/query";
import { ManagedSocket, type SocketStatus } from "@/lib/ws/socket";

type DashboardFrame =
  | DashboardEvent
  | ErrorFrame
  | { type: "auth.ok"; user_id: string; organization_id: string; role: Role };

type Listener = (event: DashboardEvent) => void;

interface DashboardSocketValue {
  status: SocketStatus;
  subscribe: (listener: Listener) => () => void;
}

const DashboardSocketContext = createContext<DashboardSocketValue | null>(null);

/** Lists that cannot be patched from a payload alone are refetched instead. */
const INVALIDATES: Record<DashboardEventType, QueryTag[]> = {
  "document.status": [],
  "document.deleted": ["subscription", "tags"],
  "conversation.created": ["conversations", "subscription"],
  "conversation.updated": ["conversations"],
  "ticket.created": ["tickets", "conversations"],
  "ticket.updated": ["tickets", "conversations"],
  "subscription.updated": ["subscription"],
};

export function DashboardSocketProvider({
  organizationId,
  children,
}: {
  organizationId: string;
  children: ReactNode;
}) {
  const [status, setStatus] = useState<SocketStatus>("idle");
  const [listeners] = useState(() => new Set<Listener>());

  useEffect(() => {
    let authenticatedOnce = false;
    let pendingTags = new Set<QueryTag>();
    let flushTimer: number | undefined;

    // Bursts (one event per streamed answer) collapse into one refetch per list.
    const queueInvalidation = (tags: QueryTag[]) => {
      tags.forEach((tag) => pendingTags.add(tag));
      if (flushTimer !== undefined || pendingTags.size === 0) return;
      flushTimer = window.setTimeout(() => {
        const tagsToFlush = [...pendingTags];
        pendingTags = new Set();
        flushTimer = undefined;
        invalidate(...tagsToFlush);
      }, 400);
    };

    const socket = new ManagedSocket<DashboardFrame>({
      url: () => `${config.wsUrl}/ws/dashboard/`,
      readyType: "auth.ok",
      authenticate: async ({ forceRefresh }) => {
        const token = forceRefresh ? await refreshAccessToken() : await getFreshAccessToken();
        return token ? { type: "auth", token, organization_id: organizationId } : null;
      },
      onStatus: (next) => setStatus(next),
      onFrame: (frame) => {
        if (frame.type === "auth.ok") {
          if (authenticatedOnce) invalidateAll();
          authenticatedOnce = true;
          return;
        }
        if (frame.type === "error") return;
        listeners.forEach((listener) => listener(frame));
        queueInvalidation(INVALIDATES[frame.type] ?? []);
      },
    });
    socket.start();
    return () => {
      window.clearTimeout(flushTimer);
      socket.stop();
    };
  }, [organizationId, listeners]);

  const subscribe = useCallback(
    (listener: Listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    [listeners],
  );
  const value = useMemo<DashboardSocketValue>(() => ({ status, subscribe }), [status, subscribe]);

  return <DashboardSocketContext.Provider value={value}>{children}</DashboardSocketContext.Provider>;
}

export function useDashboardSocketStatus(): SocketStatus {
  return useContext(DashboardSocketContext)?.status ?? "idle";
}

/** Calls the handler for every live dashboard event while the component is mounted. */
export function useDashboardEvents(handler: (event: DashboardEvent) => void): void {
  const context = useContext(DashboardSocketContext);
  const subscribe = context?.subscribe;
  const onEvent = useEffectEvent(handler);
  useEffect(() => {
    if (!subscribe) return;
    return subscribe((event) => onEvent(event));
  }, [subscribe]);
}
