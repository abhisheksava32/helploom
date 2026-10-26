"use client";

import { Check, CheckCircle2, CircleAlert, CreditCard, ExternalLink, FlaskConical } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Meter } from "@/components/ui/controls";
import { ConfirmDialog } from "@/components/ui/dialog";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { billingApi } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/errors";
import type { Plan, Subscription } from "@/lib/api/types";
import { usePermissions } from "@/lib/auth/roles";
import { cn } from "@/lib/cn";
import { formatDate, formatNumber, formatPrice } from "@/lib/format";
import { invalidate, useMutation, useQuery } from "@/lib/query";

const LIMIT_NAMES: Record<string, string> = { documents: "documents", seats: "seats", messages: "answered questions" };

function CheckoutBanner() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const status = params.get("checkout");
  if (status !== "success" && status !== "cancelled") return null;
  const success = status === "success";
  return (
    <div
      role="status"
      className={cn(
        "mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm",
        success ? "border-success/30 bg-success-soft text-success" : "border-border bg-surface-muted text-muted-foreground",
      )}
    >
      <span className="flex items-center gap-2">
        {success ? <CheckCircle2 className="size-4" aria-hidden /> : <CircleAlert className="size-4" aria-hidden />}
        {success
          ? "Payment received. Your plan updates as soon as Stripe confirms it, usually within seconds."
          : "Checkout was cancelled. Your plan has not changed."}
      </span>
      <button type="button" className="font-medium underline" onClick={() => router.replace(pathname)}>
        Dismiss
      </button>
    </div>
  );
}

function PlanCard({
  plan,
  subscription,
  onChoose,
  pending,
}: {
  plan: Plan;
  subscription: Subscription;
  onChoose: (plan: Plan) => void;
  pending: boolean;
}) {
  const { isOwner } = usePermissions();
  const current = plan.code === subscription.plan.code;
  const upgrade = plan.price_monthly_cents > subscription.plan.price_monthly_cents;
  return (
    <div
      className={cn(
        "flex flex-col rounded-xl border bg-surface p-5 shadow-card",
        current ? "border-primary ring-1 ring-primary" : "border-border",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{plan.name}</h3>
        {current && <Badge tone="primary">Current plan</Badge>}
      </div>
      <p className="mt-3">
        <span className="text-3xl font-semibold tracking-tight">{formatPrice(plan.price_monthly_cents)}</span>
        <span className="text-sm text-muted-foreground"> / month</span>
      </p>
      <ul className="mt-4 space-y-1.5 text-sm">
        <li>{formatNumber(plan.limits.messages_per_month)} answered questions a month</li>
        <li>{formatNumber(plan.limits.documents)} documents</li>
        <li>{formatNumber(plan.limits.seats)} seats</li>
      </ul>
      <ul className="mt-4 flex-1 space-y-1.5 border-t border-border pt-4 text-sm text-muted-foreground">
        {plan.features.map((feature) => (
          <li key={feature} className="flex gap-2">
            <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
            {feature}
          </li>
        ))}
      </ul>
      {!current && isOwner && (
        <Button
          variant={upgrade ? "primary" : "outline"}
          className="mt-5 w-full"
          loading={pending}
          onClick={() => onChoose(plan)}
        >
          {upgrade ? `Upgrade to ${plan.name}` : `Switch to ${plan.name}`}
        </Button>
      )}
    </div>
  );
}

export function BillingView() {
  const { isOwner } = usePermissions();
  const toast = useToast();
  const subscription = useQuery("subscription", (signal) => billingApi.subscription({ signal }), { tags: ["subscription"] });
  const plans = useQuery("plans", (signal) => billingApi.plans({ signal }));
  const [confirming, setConfirming] = useState<Plan | null>(null);
  const [choosing, setChoosing] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);

  const portal = useMutation(() => billingApi.portal(), {
    onError: (error) => toast.error("Could not open the billing portal", errorMessage(error)),
  });
  const checkout = useMutation((plan: Plan) => billingApi.checkout(plan.code), {
    onError: async (error) => {
      if (error.code === "plan_downgrade_blocked") {
        const { limit, used, allowed } = error.details as { limit?: string; used?: number; allowed?: number };
        setBlocked(
          `You use ${formatNumber(used ?? 0)} ${LIMIT_NAMES[limit ?? ""] ?? limit}, but that plan allows ${formatNumber(allowed ?? 0)}. Remove some first.`,
        );
      } else if (error.code === "use_billing_portal") {
        const session = await portal.mutate();
        if (session) window.location.assign(session.url);
      } else {
        toast.error("Could not change the plan", errorMessage(error));
      }
    },
  });

  const choose = async (plan: Plan) => {
    setBlocked(null);
    setChoosing(plan.code);
    const result = await checkout.mutate(plan);
    setChoosing(null);
    setConfirming(null);
    if (!result) return;
    if (result.mode === "stripe" && result.checkout_url) {
      window.location.assign(result.checkout_url);
      return;
    }
    subscription.setData(() => result.subscription);
    invalidate("subscription");
    toast.success(`You are on ${result.subscription.plan.name}`, "Demo billing: the change applied instantly.");
  };

  if (subscription.isLoading || plans.isLoading) return <LoadingBlock />;
  if (subscription.error || !subscription.data) {
    return (
      <Card>
        <ErrorState message={subscription.error?.message ?? "Billing is unavailable."} onRetry={subscription.refetch} />
      </Card>
    );
  }

  const data = subscription.data;
  const demo = data.billing_mode === "demo";
  const usage = data.usage;

  return (
    <>
      <PageHeader
        title="Billing"
        description="Your plan, this month's usage and upgrades."
        actions={
          !demo &&
          isOwner &&
          data.provider === "stripe" && (
            <Button
              variant="outline"
              loading={portal.pending}
              icon={<ExternalLink className="size-4" aria-hidden />}
              onClick={async () => {
                const session = await portal.mutate();
                if (session) window.location.assign(session.url);
              }}
            >
              Manage billing
            </Button>
          )
        }
      />
      <CheckoutBanner />

      {demo && (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning">
          <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <span className="font-semibold">Demo billing.</span> No payment provider is configured, so plan changes
            apply instantly and nothing is charged. Set STRIPE_SECRET_KEY on the server to use Stripe Checkout.
          </p>
        </div>
      )}

      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Current plan" />
          <CardBody className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-lg bg-accent text-accent-foreground">
                <CreditCard className="size-5" aria-hidden />
              </span>
              <div>
                <p className="text-lg font-semibold">{data.plan.name}</p>
                <p className="text-sm text-muted-foreground">{formatPrice(data.plan.price_monthly_cents)} per month</p>
              </div>
            </div>
            <dl className="space-y-1.5 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Status</dt>
                <dd>
                  <Badge tone={data.status === "active" || data.status === "trialing" ? "success" : "warning"}>
                    {data.status.replace("_", " ")}
                  </Badge>
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Billed by</dt>
                <dd>{demo ? "Demo mode" : data.provider === "stripe" ? "Stripe" : "Demo mode"}</dd>
              </div>
              {data.current_period_end && (
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{data.cancel_at_period_end ? "Ends" : "Renews"}</dt>
                  <dd>{formatDate(data.current_period_end)}</dd>
                </div>
              )}
            </dl>
          </CardBody>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Usage" description={`Since ${formatDate(`${usage.period_start}T00:00:00Z`)}. Documents and seats are live counts.`} />
          <CardBody className="grid gap-6 sm:grid-cols-3">
            <Meter label="Answered questions" used={usage.messages.used} limit={usage.messages.limit} />
            <Meter label="Documents" used={usage.documents.used} limit={usage.documents.limit} />
            <Meter label="Seats" used={usage.seats.used} limit={usage.seats.limit} />
          </CardBody>
        </Card>
      </div>

      <h2 className="mb-1 text-base font-semibold">Plans</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        {isOwner ? "Change plans at any time." : "Only the workspace owner can change the plan."}
      </p>
      {blocked && (
        <p role="alert" className="mb-4 rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
          {blocked}
        </p>
      )}
      {plans.error ? (
        <Card>
          <ErrorState message={plans.error.message} onRetry={plans.refetch} />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {(plans.data?.results ?? []).map((plan) => (
            <PlanCard
              key={plan.code}
              plan={plan}
              subscription={data}
              pending={checkout.pending && choosing === plan.code}
              onChoose={(chosen) => (demo || chosen.price_monthly_cents < data.plan.price_monthly_cents ? setConfirming(chosen) : void choose(chosen))}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        tone="primary"
        title={`Switch to ${confirming?.name ?? ""}?`}
        description={
          demo
            ? "Demo billing applies the change instantly. No payment is taken."
            : "You will be taken to Stripe to confirm the change."
        }
        confirmLabel={`Switch to ${confirming?.name ?? ""}`}
        pending={checkout.pending}
        onConfirm={() => confirming && void choose(confirming)}
      />
    </>
  );
}
