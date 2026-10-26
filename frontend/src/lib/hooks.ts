"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

/** The value after it has stopped changing for `delayMs`, for search boxes. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

// One shared clock for relative times ("3 min ago"). Reading Date.now() during render
// would make components impure; this store ticks every 30 seconds instead.
let now = Date.now();
const clockListeners = new Set<() => void>();
let clockTimer: number | undefined;

function subscribeClock(listener: () => void): () => void {
  clockListeners.add(listener);
  if (clockTimer === undefined) {
    now = Date.now();
    clockTimer = window.setInterval(() => {
      now = Date.now();
      clockListeners.forEach((notify) => notify());
    }, 30_000);
  }
  return () => {
    clockListeners.delete(listener);
    if (clockListeners.size === 0 && clockTimer !== undefined) {
      window.clearInterval(clockTimer);
      clockTimer = undefined;
    }
  };
}

export function useNow(): number {
  return useSyncExternalStore(
    subscribeClock,
    () => now,
    () => now,
  );
}

/** Subscribes to a CSS media query; false during prerendering. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (listener) => {
      const media = window.matchMedia(query);
      media.addEventListener("change", listener);
      return () => media.removeEventListener("change", listener);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
