import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 space-y-1">
        {eyebrow && <div className="text-sm text-muted-foreground">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {description && <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/**
 * Wraps a wide table so it scrolls inside its card instead of widening the page.
 * relative keeps absolutely positioned descendants (sr-only labels) inside the
 * scroller; otherwise they escape it and widen the document on phones.
 */
export function TableScroll({ children }: { children: ReactNode }) {
  return <div className="relative overflow-x-auto">{children}</div>;
}

export const tableClasses = {
  table: "w-full border-collapse text-left text-sm",
  /** Lists with many columns keep their shape and scroll sideways on small screens. */
  wide: "min-w-[600px]",
  head: "border-b border-border bg-surface-muted/60 text-xs font-medium uppercase tracking-wide text-muted-foreground",
  th: "px-5 py-2.5 font-medium",
  row: "border-b border-border last:border-0 transition-colors hover:bg-surface-muted/40",
  td: "px-5 py-3 align-middle",
};
