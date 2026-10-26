import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "primary" | "success" | "warning" | "danger";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-surface-muted text-muted-foreground ring-border",
  primary: "bg-accent text-accent-foreground ring-primary/20",
  success: "bg-success-soft text-success ring-success/20",
  warning: "bg-warning-soft text-warning ring-warning/25",
  danger: "bg-danger-soft text-danger ring-danger/20",
};

const dots: Record<BadgeTone, string> = {
  neutral: "bg-muted-foreground",
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

export function Badge({
  tone = "neutral",
  dot = false,
  pulse = false,
  className,
  children,
  title,
}: {
  tone?: BadgeTone;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {dot && (
        <span aria-hidden className="relative flex size-1.5">
          {pulse && <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", dots[tone])} />}
          <span className={cn("relative inline-flex size-1.5 rounded-full", dots[tone])} />
        </span>
      )}
      {children}
    </span>
  );
}
