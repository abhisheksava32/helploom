"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

import { cn } from "@/lib/cn";
import { applyThemePreference, readThemePreference, type ThemePreference } from "@/lib/theme";

const OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const satisfies readonly { value: ThemePreference; label: string; icon: typeof Sun }[];

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

/** Light, dark or follow the OS. compact shows icons only (labels stay for screen readers). */
export function ThemeToggle({ compact = false, className }: { compact?: boolean; className?: string }) {
  const preference = useSyncExternalStore<ThemePreference>(subscribe, readThemePreference, () => "system");

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={cn("inline-flex rounded-md border border-border bg-surface p-0.5 text-sm", className)}
    >
      {OPTIONS.map((option) => {
        const selected = preference === option.value;
        const Icon = option.icon;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={compact ? option.label : undefined}
            title={compact ? option.label : undefined}
            onClick={() => setPreference(option.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-sm transition-colors",
              compact ? "p-1.5" : "px-2.5 py-1",
              selected ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            {!compact && option.label}
          </button>
        );
      })}
    </div>
  );
}
