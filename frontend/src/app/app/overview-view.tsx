"use client";

import {
  ArrowRight,
  CheckCircle2,
  Circle,
  Code2,
  FileUp,
  LifeBuoy,
  MessagesSquare,
  Sparkles,
  UserPlus,
} from "lucide-react";
import Link from "next/link";

import { AnswerTypeBadge, ChannelBadge, ProviderBadge } from "@/components/status";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Meter } from "@/components/ui/controls";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/states";
import {
  analyticsApi,
  assistantApi,
  billingApi,
  conversationsApi,
  documentsApi,
  ticketsApi,
  widgetApi,
} from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth/auth-context";
import { usePermissions } from "@/lib/auth/roles";
import { cn } from "@/lib/cn";
import { formatCompact, formatDuration, formatPercent, formatRelative, pluralize } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { useQuery } from "@/lib/query";
import { rangeEndingToday } from "@/lib/range";
import { useDashboardEvents } from "@/lib/ws/dashboard";

function GettingStarted({
  steps,
}: {
  steps: { title: string; description: string; href: string; done: boolean; icon: typeof FileUp }[];
}) {
  const done = steps.filter((step) => step.done).length;
  if (done === steps.length) return null;
  return (
    <Card className="mb-6 overflow-hidden">
      <CardHeader
        title="Get your help desk live"
        description={`${done} of ${steps.length} steps done. Most teams finish in under ten minutes.`}
        actions={
          <div className="h-1.5 w-32 overflow-hidden rounded-full bg-accent" aria-hidden>
            <div className="h-full rounded-full bg-primary" style={{ width: `${(done / steps.length) * 100}%` }} />
          </div>
        }
      />
      <ol className="grid divide-y divide-border sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4 lg:divide-x">
        {steps.map((step) => {
          const Icon = step.icon;
          return (
            <li key={step.title}>
              <Link
                href={step.href}
                className="group flex h-full gap-3 p-4 transition-colors hover:bg-surface-muted/60 sm:p-5"
              >
                {step.done ? (
                  <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-label="Done" />
                ) : (
                  <Circle className="mt-0.5 size-5 shrink-0 text-muted-foreground/60" aria-label="To do" />
                )}
                <span className="min-w-0">
                  <span className={cn("flex items-center gap-1.5 text-sm font-medium", step.done && "text-muted-foreground line-through")}>
                    <Icon className="size-4" aria-hidden />
                    {step.title}
                  </span>
                  <span className="mt-1 block text-sm text-muted-foreground">{step.description}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export function OverviewView() {
  const { user, organization } = useAuth();
  const { isAdmin } = usePermissions();
  const now = useNow();
  const range = rangeEndingToday(7, now);
  const rangeKey = `${range.date_from}:${range.date_to}`;

  const overview = useQuery(`overview:stats:${rangeKey}`, (signal) => analyticsApi.overview(range, { signal }), {
    tags: ["conversations", "reports"],
  });
  const subscription = useQuery("subscription", (signal) => billingApi.subscription({ signal }), {
    tags: ["subscription"],
  });
  const conversations = useQuery(
    "overview:conversations",
    (signal) => conversationsApi.list({ page_size: 5 }, { signal }),
    { tags: ["conversations"] },
  );
  const tickets = useQuery(
    "overview:tickets",
    (signal) => ticketsApi.list({ status: "open", page_size: 5 }, { signal }),
    { tags: ["tickets"] },
  );
  const documents = useQuery("overview:documents", (signal) => documentsApi.list({ page_size: 1 }, { signal }), {
    tags: ["documents"],
  });
  const widget = useQuery("widget", (signal) => widgetApi.config({ signal }), { tags: ["widget"] });
  const providers = useQuery("providers", (signal) => assistantApi.providers({ signal }), { tags: ["providers"] });

  useDashboardEvents((event) => {
    if (event.type === "document.status" || event.type === "document.deleted") documents.refetch();
  });

  const stats = overview.data;
  const usage = subscription.data?.usage;
  const firstName = user?.full_name.split(" ")[0];

  const steps = [
    {
      title: "Upload documents",
      description: "Policies, FAQs and handbooks in PDF, DOCX, Markdown, TXT or HTML.",
      href: "/app/documents",
      done: (documents.data?.count ?? 0) > 0,
      icon: FileUp,
    },
    {
      title: "Ask a test question",
      description: "Try the playground and check the citations.",
      href: "/app/playground",
      done: (conversations.data?.count ?? 0) > 0,
      icon: Sparkles,
    },
    {
      title: "Add the widget",
      description: "Allow your site's origin and paste one script tag.",
      href: "/app/settings/widget",
      done: (widget.data?.allowed_origins.length ?? 0) > 0,
      icon: Code2,
    },
    {
      title: "Invite your team",
      description: "Agents can answer handoff tickets.",
      href: "/app/settings/team",
      done: (usage?.seats.used ?? 0) > 1,
      icon: UserPlus,
    },
  ];
  // Setup steps are admin work (uploads, widget, invitations), so agents never see them.
  const checklistReady = isAdmin && documents.data && conversations.data && widget.data && subscription.data;

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome back, ${firstName}` : "Overview"}
        description={`How ${organization?.name ?? "your"} help desk did over the last 7 days.`}
        actions={
          <ButtonLink href="/app/playground" icon={<Sparkles className="size-4" aria-hidden />}>
            Open playground
          </ButtonLink>
        }
      />

      {checklistReady && <GettingStarted steps={steps} />}

      {overview.error ? (
        <Card className="mb-6">
          <ErrorState message={overview.error.message} onRetry={overview.refetch} />
        </Card>
      ) : (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatTile
            label="Answer rate"
            emphasis
            loading={overview.isLoading}
            value={stats ? formatPercent(stats.answer_rate) : "-"}
            detail={stats ? `${formatCompact(stats.answered)} of ${pluralize(stats.questions, "question")}` : undefined}
          />
          <StatTile
            label="Conversations"
            loading={overview.isLoading}
            value={stats ? formatCompact(stats.conversations) : "-"}
            detail={stats ? `${pluralize(stats.questions, "question")} asked` : undefined}
          />
          <StatTile
            label="Not found"
            loading={overview.isLoading}
            value={stats ? formatPercent(stats.not_found_rate) : "-"}
            detail="Questions your documents do not cover"
          />
          <StatTile
            label="Satisfaction"
            loading={overview.isLoading}
            value={stats ? formatPercent(stats.ratings.satisfaction, 0) : "-"}
            detail={stats ? `${stats.ratings.up} up, ${stats.ratings.down} down` : undefined}
          />
          <StatTile
            label="First token"
            loading={overview.isLoading}
            value={stats ? formatDuration(stats.avg_first_token_ms) : "-"}
            detail={stats ? `Full answer ${formatDuration(stats.avg_latency_ms)}` : undefined}
            className="col-span-2 lg:col-span-1"
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2 lg:self-start">
          <CardHeader
            title="Recent conversations"
            description="Updates live as visitors ask questions."
            actions={
              <ButtonLink href="/app/conversations" variant="ghost" size="sm">
                View all <ArrowRight className="size-4" aria-hidden />
              </ButtonLink>
            }
          />
          {conversations.isLoading ? (
            <SkeletonRows rows={4} />
          ) : conversations.error ? (
            <ErrorState message={conversations.error.message} onRetry={conversations.refetch} />
          ) : conversations.data && conversations.data.results.length > 0 ? (
            <ul className="divide-y divide-border">
              {conversations.data.results.map((conversation) => (
                <li key={conversation.id}>
                  <Link
                    href={`/app/conversations/${conversation.id}`}
                    className="flex items-center gap-4 px-5 py-3 transition-colors hover:bg-surface-muted/50"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{conversation.title || "Untitled conversation"}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <ChannelBadge channel={conversation.channel} />
                        <span className="text-xs text-muted-foreground">
                          {pluralize(conversation.message_count, "message")}
                        </span>
                        {conversation.providers.map((provider) => (
                          <ProviderBadge key={provider} provider={provider} />
                        ))}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <AnswerTypeBadge type={conversation.last_answer_type} />
                      <span className="text-xs text-muted-foreground">
                        {formatRelative(conversation.last_message_at ?? conversation.created_at, now)}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={MessagesSquare}
              title="No conversations yet"
              description="Questions from the playground and your website widget appear here as they happen."
            />
          )}
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Usage this month"
              actions={
                subscription.data && (
                  <Badge tone={subscription.data.billing_mode === "demo" ? "warning" : "primary"}>
                    {subscription.data.plan.name}
                    {subscription.data.billing_mode === "demo" ? " (demo billing)" : ""}
                  </Badge>
                )
              }
            />
            <CardBody className="space-y-4">
              {subscription.isLoading ? (
                <SkeletonRows rows={3} className="p-0" />
              ) : subscription.error ? (
                <ErrorState message={subscription.error.message} onRetry={subscription.refetch} className="py-4" />
              ) : usage ? (
                <>
                  <Meter label="Answered questions" used={usage.messages.used} limit={usage.messages.limit} />
                  <Meter label="Documents" used={usage.documents.used} limit={usage.documents.limit} />
                  <Meter label="Seats" used={usage.seats.used} limit={usage.seats.limit} />
                  <ButtonLink href="/app/settings/billing" variant="outline" size="sm" className="w-full">
                    Manage plan
                  </ButtonLink>
                </>
              ) : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Open tickets"
              actions={
                <ButtonLink href="/app/tickets" variant="ghost" size="sm">
                  View all <ArrowRight className="size-4" aria-hidden />
                </ButtonLink>
              }
            />
            {tickets.isLoading ? (
              <SkeletonRows rows={2} />
            ) : tickets.error ? (
              <ErrorState message={tickets.error.message} onRetry={tickets.refetch} className="py-6" />
            ) : tickets.data && tickets.data.results.length > 0 ? (
              <ul className="divide-y divide-border">
                {tickets.data.results.map((ticket) => (
                  <li key={ticket.id}>
                    <Link
                      href={`/app/conversations/${ticket.conversation_id}`}
                      className="block px-5 py-3 transition-colors hover:bg-surface-muted/50"
                    >
                      <p className="truncate text-sm font-medium">{ticket.requester_name || ticket.requester_email}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {ticket.conversation_title} &middot; {formatRelative(ticket.created_at, now)}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={LifeBuoy} title="Inbox zero" description="No visitor is waiting for a person." className="py-8" />
            )}
          </Card>

          {providers.data && (
            <Card>
              <CardHeader title="Answer engine" />
              <CardBody className="space-y-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground">Next answer from</span>
                  <ProviderBadge provider={providers.data.active.name} model={providers.data.active.model} />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground">Embeddings</span>
                  <span className="font-mono text-xs">{providers.data.embedder.active}</span>
                </div>
                {providers.data.embedder.stale_documents > 0 && (
                  <p className="rounded-md bg-warning-soft px-3 py-2 text-xs text-warning">
                    {pluralize(providers.data.embedder.stale_documents, "document")}{" "}
                    {providers.data.embedder.stale_documents === 1 ? "was" : "were"} embedded with a different model.
                    Re-index them so search covers everything.
                  </p>
                )}
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
