import { CircleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span role="status" className="inline-flex items-center">
      <span
        aria-hidden
        className={cn("size-5 animate-spin rounded-full border-2 border-primary border-r-transparent", className)}
      />
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-surface-muted", className)} />;
}

/** Placeholder rows for tables and lists while the first page loads. */
export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3 p-5", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center gap-4">
          <Skeleton className="size-8 rounded-md" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-2/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}>
      {Icon && (
        <div className="mb-4 grid size-12 place-items-center rounded-xl border border-border bg-surface-muted text-muted-foreground">
          <Icon className="size-5" aria-hidden />
        </div>
      )}
      <h3 className="text-sm font-semibold">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Could not load this",
  message,
  onRetry,
  className,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("flex flex-col items-center px-6 py-12 text-center", className)}>
      <div className="mb-4 grid size-12 place-items-center rounded-xl bg-danger-soft text-danger">
        <CircleAlert className="size-5" aria-hidden />
      </div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-5" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Centered spinner for a whole region. */
export function LoadingBlock({ className, label }: { className?: string; label?: string }) {
  return (
    <div className={cn("grid place-items-center py-16", className)}>
      <Spinner label={label} />
    </div>
  );
}
