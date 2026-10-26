import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * min-w-0 lets a card shrink inside grid and flex parents, so wide content (tables,
 * code) scrolls inside it instead of widening the page.
 */
export function Card({ className, ...props }: ComponentProps<"section">) {
  return <section className={cn("min-w-0 rounded-lg border border-border bg-surface shadow-card", className)} {...props} />;
}

export function CardHeader({
  title,
  description,
  actions,
  className,
  titleId,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
  titleId?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4", className)}>
      <div className="min-w-0 space-y-1">
        <h2 id={titleId} className="text-sm font-semibold text-foreground">
          {title}
        </h2>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("px-5 py-4", className)} {...props} />;
}

export function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-end gap-2 border-t border-border bg-surface-muted/50 px-5 py-3",
        className,
      )}
      {...props}
    />
  );
}
