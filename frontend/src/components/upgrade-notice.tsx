import { Sparkles } from "lucide-react";

import { ButtonLink } from "@/components/ui/button";
import type { PlanLimit } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";

const LIMIT_COPY: Record<PlanLimit["limit"], string> = {
  messages: "answered questions this month",
  documents: "documents",
  seats: "seats",
};

/** Friendly upgrade prompt for a 402 plan_limit_exceeded, with the numbers from the error. */
export function UpgradeNotice({ limit, compact = false }: { limit: PlanLimit; compact?: boolean }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-primary/25 bg-accent px-4 py-3"
    >
      <div className="flex items-start gap-3">
        <Sparkles className="mt-0.5 size-4 shrink-0 text-accent-foreground" aria-hidden />
        <div className="text-sm text-accent-foreground">
          <p className="font-medium">You have reached your plan limit</p>
          {!compact && (
            <p className="mt-0.5 opacity-90">
              {formatNumber(limit.used)} of {formatNumber(limit.allowed)} {LIMIT_COPY[limit.limit]} used
              {limit.plan ? ` on the ${limit.plan.charAt(0).toUpperCase()}${limit.plan.slice(1)} plan` : ""}.
              Upgrade to keep going.
            </p>
          )}
        </div>
      </div>
      <ButtonLink href="/app/settings/billing" size="sm">
        See plans
      </ButtonLink>
    </div>
  );
}
