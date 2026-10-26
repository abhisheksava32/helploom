"use client";

import { Check } from "lucide-react";

import { Button, ButtonLink } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/states";
import { billingApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/cn";
import { formatNumber, formatPrice } from "@/lib/format";
import { useQuery } from "@/lib/query";

/** Pricing straight from GET /billing/plans/, so the page can never disagree with what is enforced. */
export function Pricing() {
  const plans = useQuery("plans", (signal) => billingApi.plans({ signal }));

  if (plans.isLoading) {
    return (
      <div className="grid gap-6 md:grid-cols-3" aria-busy="true" aria-label="Loading plans">
        {[0, 1, 2].map((index) => (
          <Skeleton key={index} className="h-96 rounded-2xl" />
        ))}
      </div>
    );
  }

  if (plans.error || !plans.data) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-8 text-center">
        <p className="font-medium">Pricing is unavailable right now</p>
        <p className="mt-1 text-sm text-muted-foreground">Every workspace starts on the free plan, no card needed.</p>
        <div className="mt-5 flex justify-center gap-2">
          <Button variant="outline" onClick={plans.refetch}>
            Try again
          </Button>
          <ButtonLink href="/signup">Start free</ButtonLink>
        </div>
      </div>
    );
  }

  const list = plans.data.results;
  const featured = list.length > 1 ? list[1].code : null;

  return (
    <div className="grid gap-6 md:grid-cols-3">
      {list.map((plan) => {
        const highlight = plan.code === featured;
        return (
          <div
            key={plan.code}
            className={cn(
              "relative flex flex-col rounded-2xl border bg-surface p-6 shadow-card",
              highlight ? "border-primary ring-1 ring-primary" : "border-border",
            )}
          >
            {highlight && (
              <span className="absolute -top-3 left-6 rounded-full bg-primary px-2.5 py-0.5 text-xs font-medium text-primary-foreground">
                Most popular
              </span>
            )}
            <h3 className="font-semibold">{plan.name}</h3>
            <p className="mt-4">
              <span className="text-4xl font-semibold tracking-tight">{formatPrice(plan.price_monthly_cents)}</span>
              <span className="text-sm text-muted-foreground"> / month</span>
            </p>
            <ul className="mt-6 space-y-2 text-sm">
              <li>
                <span className="font-medium">{formatNumber(plan.limits.messages_per_month)}</span> answered questions a month
              </li>
              <li>
                <span className="font-medium">{formatNumber(plan.limits.documents)}</span> documents
              </li>
              <li>
                <span className="font-medium">{formatNumber(plan.limits.seats)}</span> team seats
              </li>
            </ul>
            <ul className="mt-6 flex-1 space-y-2 border-t border-border pt-6 text-sm text-muted-foreground">
              {plan.features.map((feature) => (
                <li key={feature} className="flex gap-2">
                  <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
                  {feature}
                </li>
              ))}
            </ul>
            <ButtonLink href="/signup" variant={highlight ? "primary" : "outline"} className="mt-8 w-full">
              {plan.price_monthly_cents === 0 ? "Start free" : `Start with ${plan.name}`}
            </ButtonLink>
          </div>
        );
      })}
    </div>
  );
}
