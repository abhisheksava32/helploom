"use client";

import { useId, type ComponentProps, type ReactNode } from "react";

import { cn } from "@/lib/cn";

export const controlClasses =
  "block rounded-md border border-input bg-surface px-3 text-sm text-foreground shadow-card " +
  "placeholder:text-muted-foreground/80 transition-colors " +
  "focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-ring/40 " +
  "disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-danger";

/**
 * Controls fill their container unless the caller sets a width class; Tailwind does
 * not resolve two conflicting width utilities in one class list, so only one is sent.
 */
function width(className: string | undefined): string {
  return className && /(^|\s)w-/.test(className) ? "" : "w-full";
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(controlClasses, width(className), "h-9", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(controlClasses, "w-full min-h-20 py-2 leading-relaxed", className)} {...props} />;
}

export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <select className={cn(controlClasses, width(className), "h-9 cursor-pointer pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium text-foreground", className)} {...props} />;
}

export interface FieldControlProps {
  id: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
}

/**
 * Label, control, hint and error wired together: the control gets an id, the hint
 * and error are linked with aria-describedby, and aria-invalid marks the error.
 */
export function Field({
  label,
  hint,
  error,
  className,
  optional,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  className?: string;
  optional?: boolean;
  children: (props: FieldControlProps) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {optional && <span className="ml-1 font-normal text-muted-foreground">(optional)</span>}
      </Label>
      {children({ id, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy })}
      {hint && !error && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs font-medium text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/** A form level error from the server, announced to screen readers. */
export function FormError({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
      {message}
    </p>
  );
}
