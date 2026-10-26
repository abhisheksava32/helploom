"use client";

/**
 * A small data fetching hook for the dashboard.
 *
 * Why not a library: the dashboard needs four things (abortable fetches keyed by
 * their inputs, keep the previous data while refetching, local updates from
 * websocket events, and tag based invalidation) and this file does exactly that in
 * plain React. Loading state is derived from "which key has settled" instead of
 * being set inside the effect, so a render never shows a stale flag.
 */

import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";

export type QueryTag =
  | "documents"
  | "collections"
  | "tags"
  | "conversations"
  | "tickets"
  | "subscription"
  | "organization"
  | "members"
  | "invitations"
  | "widget"
  | "providers"
  | "reports";

const listeners = new Map<QueryTag, Set<() => void>>();

/** Asks every mounted query with one of these tags to refetch in the background. */
export function invalidate(...tags: QueryTag[]): void {
  const called = new Set<() => void>();
  for (const tag of tags) {
    for (const listener of listeners.get(tag) ?? []) {
      if (called.has(listener)) continue;
      called.add(listener);
      listener();
    }
  }
}

export function invalidateAll(): void {
  invalidate(...(listeners.keys() as Iterable<QueryTag>));
}

function subscribe(tags: readonly QueryTag[], listener: () => void): () => void {
  for (const tag of tags) {
    let set = listeners.get(tag);
    if (!set) {
      set = new Set();
      listeners.set(tag, set);
    }
    set.add(listener);
  }
  return () => {
    for (const tag of tags) listeners.get(tag)?.delete(listener);
  };
}

export interface QueryOptions {
  tags?: readonly QueryTag[];
  /** Keep showing the last data while a new key loads (lists with filters). Default true. */
  keepPrevious?: boolean;
}

export interface QueryResult<T> {
  data: T | undefined;
  error: ApiError | null;
  /** No data yet for this key and no error: show a skeleton. */
  isLoading: boolean;
  /** A request for the current key is in flight (including background refetches). */
  isFetching: boolean;
  refetch: () => void;
  /** Local update, for example from a websocket event or a mutation response. */
  setData: (update: (current: T | undefined) => T | undefined) => void;
}

interface State<T> {
  data: T | undefined;
  dataKey: string | null;
  error: ApiError | null;
  errorKey: string | null;
  settled: string | null;
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, "client_error", "Something went wrong. Please try again.");
}

/**
 * @param key  A string that changes whenever the request changes, or null to skip.
 * @param fetcher  Runs with an AbortSignal; it is read when the key or version changes.
 */
export function useQuery<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: QueryOptions = {},
): QueryResult<T> {
  const { keepPrevious = true } = options;
  const tagKey = (options.tags ?? []).join(",");
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<State<T>>({
    data: undefined,
    dataKey: null,
    error: null,
    errorKey: null,
    settled: null,
  });

  const requestId = key === null ? null : `${key}#${version}`;
  const run = useEffectEvent((signal: AbortSignal) => fetcher(signal));

  useEffect(() => {
    if (key === null || requestId === null) return;
    const controller = new AbortController();
    run(controller.signal).then(
      (data) => {
        if (controller.signal.aborted) return;
        setState({ data, dataKey: key, error: null, errorKey: null, settled: requestId });
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState((previous) => ({ ...previous, error: toApiError(error), errorKey: key, settled: requestId }));
      },
    );
    return () => controller.abort();
  }, [key, requestId]);

  useEffect(() => {
    if (!tagKey) return;
    return subscribe(tagKey.split(",") as QueryTag[], () => setVersion((value) => value + 1));
  }, [tagKey]);

  const refetch = useCallback(() => setVersion((value) => value + 1), []);
  const setData = useCallback(
    (update: (current: T | undefined) => T | undefined) =>
      setState((previous) => ({ ...previous, data: update(previous.data) })),
    [],
  );

  const ownData = state.dataKey === key;
  const data = ownData || keepPrevious ? state.data : undefined;
  const error = state.errorKey === key ? state.error : null;
  return {
    data: key === null ? undefined : data,
    error,
    isLoading: key !== null && data === undefined && error === null,
    isFetching: requestId !== null && state.settled !== requestId,
    refetch,
    setData,
  };
}

export interface MutationOptions {
  /** Called with the error when the action fails, for example to show a toast. */
  onError?: (error: ApiError) => void;
}

/**
 * Runs a mutation and tracks its pending state and error for a form or button.
 * mutate never throws: it resolves to the result, or to undefined after a failure
 * (the error is in `error` and passed to onError).
 */
export function useMutation<A extends unknown[], R>(
  action: (...args: A) => Promise<R>,
  options: MutationOptions = {},
) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  // Event handlers call mutate, so the latest callbacks are kept in a ref (updated
  // after each commit) rather than in an Effect Event, which only effects may call.
  const latest = useRef({ action, options });
  useEffect(() => {
    latest.current = { action, options };
  });

  const mutate = useCallback(async (...args: A): Promise<R | undefined> => {
    setPending(true);
    setError(null);
    try {
      return await latest.current.action(...args);
    } catch (caught) {
      const apiError = toApiError(caught);
      setError(apiError);
      latest.current.options.onError?.(apiError);
      return undefined;
    } finally {
      setPending(false);
    }
  }, []);

  const reset = useCallback(() => setError(null), []);
  return { mutate, pending, error, reset };
}
