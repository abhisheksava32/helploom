"use client";

import { useSyncExternalStore } from "react";

import {
  applyThemePreference,
  readThemePreference,
  type ThemePreference,
} from "@/lib/theme";

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const onSystemChange = () => {
    if (readThemePreference() === "system") applyThemePreference("system");
  };
  media.addEventListener("change", onSystemChange);
  return () => {
    listeners.delete(listener);
    media.removeEventListener("change", onSystemChange);
  };
}

function setPreference(preference: ThemePreference): void {
  applyThemePreference(preference);
  listeners.forEach((listener) => listener());
}

export function ThemeToggle() {
  const preference = useSyncExternalStore<ThemePreference>(
    subscribe,
    readThemePreference,
    () => "system",
  );

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="inline-flex rounded-md border border-border bg-surface p-0.5 text-sm"
    >
      {OPTIONS.map((option) => {
        const selected = preference === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => setPreference(option.value)}
            className={`rounded-sm px-2.5 py-1 transition-colors ${
              selected
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
