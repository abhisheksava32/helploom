"use client";

import { ArrowLeft, Globe, MessageSquareQuote, Sparkles, ThumbsDown, ThumbsUp, UserRound } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { AnswerBody } from "@/components/chat/answer";
import { AnswerTypeBadge, ChannelBadge, ConversationStatusBadge, ProviderBadge } from "@/components/status";
import { TicketCard, useMembers } from "@/components/tickets/ticket-card";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { conversationsApi } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/errors";
import type { ConversationDetail, ConversationStatus, Message, Rating } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDateTime, formatDuration, formatMoney, formatNumber, pluralize } from "@/lib/format";
import { invalidate, useMutation, useQuery } from "@/lib/query";
import { useDashboardEvents } from "@/lib/ws/dashboard";

function AssistantMessage({ message, onRate }: { message: Message; onRate: (rating: Rating | null) => void }) {
  const tokens = message.usage.input_tokens + message.usage.output_tokens;
  return (
    <div className="flex gap-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
        <Sparkles className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-border bg-surface px-4 py-3">
        <AnswerBody content={message.content} citations={message.citations} />
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <ProviderBadge provider={message.provider} model={message.model} />
          <AnswerTypeBadge type={message.answer_type} />
          {message.status === "truncated" && <Badge tone="warning">Truncated</Badge>}
          {message.status === "failed" && <Badge tone="danger">Failed</Badge>}
          <span>
            {formatDuration(message.first_token_ms)} first token &middot; {formatDuration(message.latency_ms)} total
          </span>
          {tokens > 0 && (
            <span
              title={`${message.usage.input_tokens} in, ${message.usage.output_tokens} out, ${message.usage.cache_read_input_tokens} read from cache`}
            >
              {formatNumber(tokens)} tokens
            </span>
          )}
          {Number.parseFloat(message.cost_usd) > 0 && <span>{formatMoney(message.cost_usd, { precise: true })}</span>}
          <span className="ml-auto">{formatDateTime(message.created_at)}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Rate helpful"
            aria-pressed={message.rating === 1}
            onClick={() => onRate(message.rating === 1 ? null : 1)}
            className={cn(message.rating === 1 && "bg-success-soft text-success")}
          >
            <ThumbsUp className="size-4" aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Rate not helpful"
            aria-pressed={message.rating === -1}
            onClick={() => onRate(message.rating === -1 ? null : -1)}
            className={cn(message.rating === -1 && "bg-danger-soft text-danger")}
          >
            <ThumbsDown className="size-4" aria-hidden />
          </Button>
          {message.feedback_comment && (
            <p className="ml-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <MessageSquareQuote className="size-3.5" aria-hidden />
              &ldquo;{message.feedback_comment}&rdquo;
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm">{children}</dd>
    </div>
  );
}

export function ConversationDetailView() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const members = useMembers();
  const conversation = useQuery(`conversation:${id}`, (signal) => conversationsApi.get(id, { signal }), {
    keepPrevious: false,
  });
  const updateStatus = useMutation((status: ConversationStatus) => conversationsApi.update(id, { status }), {
    onError: (error) => toast.error("Could not change the status", errorMessage(error)),
  });

  useDashboardEvents((event) => {
    if (
      (event.type === "conversation.updated" && event.conversation.id === id) ||
      ((event.type === "ticket.created" || event.type === "ticket.updated") && event.ticket.conversation_id === id)
    ) {
      conversation.refetch();
    }
  });

  const patchMessage = (updated: Message) =>
    conversation.setData((current) =>
      current
        ? { ...current, messages: current.messages.map((message) => (message.id === updated.id ? updated : message)) }
        : current,
    );

  const rate = async (message: Message, rating: Rating | null) => {
    try {
      patchMessage(await conversationsApi.feedback(message.id, { rating }));
      invalidate("conversations");
    } catch (error) {
      toast.error("Could not save the rating", errorMessage(error));
    }
  };

  if (conversation.isLoading) return <LoadingBlock label="Loading conversation" />;
  if (conversation.error || !conversation.data) {
    return (
      <Card>
        <ErrorState
          title={conversation.error?.code === "not_found" ? "Conversation not found" : "Could not load the conversation"}
          message={
            conversation.error?.code === "not_found"
              ? "It may have been deleted, or it belongs to another workspace."
              : (conversation.error?.message ?? "")
          }
          onRetry={conversation.error?.code === "not_found" ? undefined : conversation.refetch}
        />
      </Card>
    );
  }

  const data: ConversationDetail = conversation.data;

  return (
    <>
      <div className="mb-6 space-y-3">
        <ButtonLink href="/app/conversations" variant="ghost" size="sm" className="-ml-3" icon={<ArrowLeft className="size-4" aria-hidden />}>
          Conversations
        </ButtonLink>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{data.title || "Untitled conversation"}</h1>
            <div className="flex flex-wrap items-center gap-3">
              <ConversationStatusBadge status={data.status} />
              <ChannelBadge channel={data.channel} />
              <span className="text-sm text-muted-foreground">{formatDateTime(data.created_at)}</span>
            </div>
          </div>
          <Select
            aria-label="Conversation status"
            value={data.status}
            disabled={updateStatus.pending}
            onChange={async (event) => {
              const updated = await updateStatus.mutate(event.target.value as ConversationStatus);
              if (updated) {
                conversation.setData((current) => (current ? { ...current, ...updated } : current));
                invalidate("conversations");
              }
            }}
            className="w-auto"
          >
            <option value="open">Open</option>
            <option value="handed_off">Handed off</option>
            <option value="closed">Closed</option>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card>
          <CardHeader title="Transcript" description={`${pluralize(data.messages.length, "message")}, oldest first.`} />
          <CardBody>
            {data.messages.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">No messages yet.</p>
            ) : (
              <ol className="space-y-5">
                {data.messages.map((message) => (
                  <li key={message.id}>
                    {message.role === "user" ? (
                      <div className="flex justify-end">
                        <div className="max-w-[85%] space-y-1 text-right">
                          <p className="whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-left text-sm text-primary-foreground">
                            {message.content}
                          </p>
                          <p className="text-xs text-muted-foreground">{formatDateTime(message.created_at)}</p>
                        </div>
                      </div>
                    ) : (
                      <AssistantMessage message={message} onRate={(rating) => void rate(message, rating)} />
                    )}
                  </li>
                ))}
              </ol>
            )}
          </CardBody>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Details" />
            <CardBody>
              <dl className="space-y-3">
                {data.channel === "widget" ? (
                  <>
                    <Detail label="Website">
                      <span className="inline-flex items-center gap-1.5">
                        <Globe className="size-3.5 text-muted-foreground" aria-hidden />
                        {data.origin || "-"}
                      </span>
                    </Detail>
                    {data.page_url && (
                      <Detail label="Page">
                        <a href={data.page_url} target="_blank" rel="noreferrer noopener" className="text-primary hover:underline">
                          {data.page_url.replace(/^https?:\/\//, "")}
                        </a>
                      </Detail>
                    )}
                    <Detail label="Visitor">
                      <span className="font-mono text-xs">{data.visitor_id || "-"}</span>
                    </Detail>
                  </>
                ) : (
                  <Detail label="Started by">
                    <span className="inline-flex items-center gap-1.5">
                      <UserRound className="size-3.5 text-muted-foreground" aria-hidden />
                      {data.started_by?.full_name || data.started_by?.email || "-"}
                    </span>
                  </Detail>
                )}
                <Detail label="Answered by">
                  <span className="flex flex-wrap gap-1.5">
                    {data.providers.length > 0
                      ? data.providers.map((provider) => <ProviderBadge key={provider} provider={provider} />)
                      : "-"}
                  </span>
                </Detail>
                <Detail label="Feedback">
                  {data.thumbs_up} helpful, {data.thumbs_down} not helpful
                </Detail>
                <Detail label="Last activity">{formatDateTime(data.last_message_at)}</Detail>
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Handoff tickets"
              description={data.tickets.length === 0 ? "Nobody asked for a person in this conversation." : undefined}
            />
            {data.tickets.length > 0 && (
              <CardBody className="space-y-3">
                {data.tickets.map((ticket) => (
                  <TicketCard
                    key={ticket.id}
                    ticket={ticket}
                    members={members.data?.results ?? []}
                    showConversation={false}
                    onUpdated={(updated) =>
                      conversation.setData((current) =>
                        current
                          ? { ...current, tickets: current.tickets.map((item) => (item.id === updated.id ? updated : item)) }
                          : current,
                      )
                    }
                  />
                ))}
              </CardBody>
            )}
          </Card>
          <p className="px-1 text-xs text-muted-foreground">
            Need to see what retrieval found for a question? Paste it into the{" "}
            <Link href="/app/playground" className="text-primary hover:underline">
              playground inspector
            </Link>
            .
          </p>
        </div>
      </div>
    </>
  );
}
