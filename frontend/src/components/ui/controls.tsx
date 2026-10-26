"use client";

import { Check, Copy, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { controlClasses } from "@/components/ui/field";
import { cn } from "@/lib/cn";

/** An accessible on/off switch (role="switch" with aria-checked). */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
  id,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: ReactNode;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-0.5">
        <span id={id ? `${id}-label` : undefined} className="text-sm font-medium">
          {label}
        </span>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={id ? undefined : label}
        aria-labelledby={id ? `${id}-label` : undefined}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
          checked ? "bg-primary" : "bg-input",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "inline-block size-5 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-5" : "translate-x-0.5",
          )}
        />
      </button>
    </div>
  );
}

export function CopyButton({
  value,
  label = "Copy",
  size = "sm",
  variant = "outline",
  className,
}: {
  value: string;
  label?: string;
  size?: "sm" | "md" | "icon-sm";
  variant?: "outline" | "ghost" | "secondary";
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // Clipboard access can be denied (insecure origin, permissions); fall back to a selection copy.
      const area = document.createElement("textarea");
      area.value = value;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setCopied(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), 1800);
  };

  const icon = copied ? <Check className="size-4 text-success" aria-hidden /> : <Copy className="size-4" aria-hidden />;
  return (
    <Button
      variant={variant}
      size={size}
      onClick={copy}
      className={className}
      aria-label={size === "icon-sm" ? label : undefined}
      icon={icon}
    >
      {size === "icon-sm" ? null : copied ? "Copied" : label}
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied to clipboard" : ""}
      </span>
    </Button>
  );
}

/**
 * Free form list input (tags, origins): Enter or comma adds, Backspace on an empty
 * input removes the last value. Validation is the caller's, so the same control
 * serves tags and URLs.
 */
export function TokenInput({
  id,
  values,
  onChange,
  placeholder,
  validate,
  normalize = (value) => value.trim(),
  disabled,
  max,
  ariaDescribedBy,
  ariaInvalid,
}: {
  id?: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  validate?: (value: string) => string | null;
  normalize?: (value: string) => string;
  disabled?: boolean;
  max?: number;
  ariaDescribedBy?: string;
  ariaInvalid?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const commit = (): boolean => {
    const value = normalize(draft);
    if (!value) return true;
    const problem = validate?.(value) ?? null;
    if (problem) {
      setError(problem);
      return false;
    }
    if (max !== undefined && values.length >= max) {
      setError(`At most ${max} entries.`);
      return false;
    }
    if (!values.includes(value)) onChange([...values, value]);
    setDraft("");
    setError(null);
    return true;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && !draft && values.length > 0) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          controlClasses,
          "flex min-h-9 w-full flex-wrap items-center gap-1.5 px-2 py-1.5 focus-within:border-ring",
          disabled && "opacity-60",
        )}
      >
        {values.map((value) => (
          <span
            key={value}
            className="inline-flex max-w-full items-center gap-1 rounded bg-surface-muted px-2 py-0.5 text-xs font-medium"
          >
            <span className="truncate">{value}</span>
            {!disabled && (
              <button
                type="button"
                onClick={() => onChange(values.filter((item) => item !== value))}
                className="rounded text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${value}`}
              >
                <X className="size-3" aria-hidden />
              </button>
            )}
          </span>
        ))}
        <input
          id={id}
          value={draft}
          disabled={disabled}
          onChange={(event) => {
            setDraft(event.target.value);
            setError(null);
          }}
          onKeyDown={onKeyDown}
          onBlur={() => {
            commit();
          }}
          placeholder={values.length === 0 ? placeholder : undefined}
          aria-describedby={ariaDescribedBy}
          aria-invalid={ariaInvalid || Boolean(error) || undefined}
          className="min-w-32 flex-1 bg-transparent px-1 py-0.5 text-sm outline-none placeholder:text-muted-foreground/80"
        />
      </div>
      {error && <p className="text-xs font-medium text-danger">{error}</p>}
    </div>
  );
}

/** A row of mutually exclusive options (date presets, view toggles). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  size = "sm",
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-border bg-surface p-0.5">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded px-2.5 font-medium transition-colors",
              size === "sm" ? "h-7 text-xs" : "h-8 text-sm",
              selected ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** A usage meter: the fill turns amber at 80% and red when the limit is reached. */
export function Meter({
  label,
  used,
  limit,
  unit,
}: {
  label: string;
  used: number;
  limit: number;
  unit?: string;
}) {
  const ratio = limit > 0 ? Math.min(1, used / limit) : 0;
  const tone = ratio >= 1 ? "bg-danger" : ratio >= 0.8 ? "bg-warning" : "bg-primary";
  const track = ratio >= 1 ? "bg-danger-soft" : ratio >= 0.8 ? "bg-warning-soft" : "bg-accent";
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          <span className="font-medium text-foreground">{used.toLocaleString("en-US")}</span> /{" "}
          {limit.toLocaleString("en-US")}
          {unit ? ` ${unit}` : ""}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={Math.min(used, limit)}
        aria-valuetext={`${used} of ${limit}`}
        className={cn("h-2 overflow-hidden rounded-full", track)}
      >
        <div className={cn("h-full rounded-full transition-[width]", tone)} style={{ width: `${ratio * 100}%` }} />
      </div>
    </div>
  );
}
