import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatNumber } from "@/lib/format";

export function Pagination({
  page,
  pageSize,
  count,
  onPageChange,
  label = "results",
}: {
  page: number;
  pageSize: number;
  count: number;
  onPageChange: (page: number) => void;
  label?: string;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (count === 0) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(count, page * pageSize);
  return (
    <nav
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3 text-sm text-muted-foreground"
    >
      <p>
        <span className="font-medium text-foreground">
          {formatNumber(first)} to {formatNumber(last)}
        </span>{" "}
        of {formatNumber(count)} {label}
      </p>
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
          icon={<ChevronLeft className="size-4" aria-hidden />}
        >
          <span className="hidden sm:inline">Previous</span>
        </Button>
        <span className="px-2 tabular-nums" aria-current="page">
          {page} / {pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          aria-label="Next page"
        >
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="size-4" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
