import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/states";
import { cn } from "@/lib/cn";

export function StatTile({
  label,
  value,
  detail,
  loading = false,
  emphasis = false,
  className,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  loading?: boolean;
  emphasis?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-border bg-surface p-4 shadow-card", className)}>
      <p className="text-sm text-muted-foreground">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-20" />
      ) : (
        <p className={cn("mt-1 font-semibold tracking-tight", emphasis ? "text-3xl" : "text-2xl")}>{value}</p>
      )}
      {detail && !loading && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}
