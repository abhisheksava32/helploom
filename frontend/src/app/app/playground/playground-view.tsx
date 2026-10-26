"use client";

import {
  ArrowUp,
  CircleAlert,
  ExternalLink,
  LifeBuoy,
  RotateCcw,
  ScanSearch,
  Sparkles,
  Square,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { HandoffDialog } from "./handoff-dialog";
import { RetrievalInspector } from "./retrieval-inspector";
import { AnswerBody, TypingDots } from "@/components/chat/answer";
import { AnswerTypeBadge, ProviderBadge } from "@/components/status";
import { UpgradeNotice } from "@/components/upgrade-notice";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { useToast } from "@/components/ui/toast";
import { assistantApi, conversationsApi } from "@/lib/api/endpoints";
import { errorMessage, planLimitFrom, retryAfterSeconds } from "@/lib/api/errors";
import type { Rating } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { useChat, type Turn } from "@/lib/chat/use-chat";
import { cn } from "@/lib/cn";
import { formatDuration, formatMoney, formatNumber } from "@/lib/format";
import { invalidate, useQuery } from "@/lib/query";
import type { SocketStatus } from "@/lib/ws/socket";

const MAX_CHARS = 2000;

const SUGGESTIONS = [
  "What is your refund policy?",
  "How long does delivery take?",
  "How do I reset my password?",
  "Can I change my plan later?",
];

const SOCKET_BADGES: Record<SocketStatus, { label: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  idle: { label: "Connecting", tone: "neutral" },
  connecting: { label: "Connecting", tone: "warning" },
  open: { label: "Connected", tone: "success" },
  reconnecting: { label: "Reconnecting", tone: "warning" },
  closed: { label: "Disconnected", tone: "danger" },
};

function TurnError({ turn }: { turn: Turn }) {
  const error = turn.answer.error;
  if (!error) return null;
  const limit = planLimitFrom(error.code, error.details);
  if (limit) return <UpgradeNotice limit={limit} />;
  const wait = error.code === "throttled" ? retryAfterSeconds(error.details) : null;
  return (
    <p role="alert" className="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>
        {error.message}
        {wait ? ` Try again in ${wait} s.` : ""}
      </span>
    </p>
  );
}

function AnswerMeta({
  turn,
  onRate,
  onInspect,
  onHandoff,
}: {
  turn: Turn;
  onRate: (messageId: string, rating: Rating | null) => void;
  onInspect: (question: string) => void;
  onHandoff: () => void;
}) {
  const { answer } = turn;
  const done = answer.status === "complete" || answer.status === "truncated";
  if (!done) return null;
  const tokens = answer.usage ? answer.usage.input_tokens + answer.usage.output_tokens : 0;
  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
        <ProviderBadge provider={answer.provider} model={answer.model} />
        <AnswerTypeBadge type={answer.answerType} />
        {answer.status === "truncated" && <Badge tone="warning">Truncated</Badge>}
        <span title="Time to first token, then the full answer">
          {formatDuration(answer.firstTokenMs)} first token &middot; {formatDuration(answer.latencyMs)} total
        </span>
        {tokens > 0 && (
          <span title={answer.usage ? `${answer.usage.input_tokens} in, ${answer.usage.output_tokens} out, ${answer.usage.cache_read_input_tokens} cached` : undefined}>
            {formatNumber(tokens)} tokens
          </span>
        )}
        {Number.parseFloat(answer.costUsd) > 0 && <span>{formatMoney(answer.costUsd, { precise: true })}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {answer.messageId && (
          <>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Helpful"
              aria-pressed={answer.rating === 1}
              onClick={() => onRate(answer.messageId ?? "", answer.rating === 1 ? null : 1)}
              className={cn(answer.rating === 1 && "bg-success-soft text-success")}
            >
              <ThumbsUp className="size-4" aria-hidden />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Not helpful"
              aria-pressed={answer.rating === -1}
              onClick={() => onRate(answer.messageId ?? "", answer.rating === -1 ? null : -1)}
              className={cn(answer.rating === -1 && "bg-danger-soft text-danger")}
            >
              <ThumbsDown className="size-4" aria-hidden />
            </Button>
          </>
        )}
        <Button variant="ghost" size="sm" onClick={() => onInspect(turn.question)} icon={<ScanSearch className="size-4" aria-hidden />}>
          Inspect retrieval
        </Button>
        {answer.offerHandoff && (
          <Button variant="outline" size="sm" onClick={onHandoff} icon={<LifeBuoy className="size-4" aria-hidden />}>
            Talk to a human
          </Button>
        )}
      </div>
    </div>
  );
}

export function PlaygroundView() {
  const { user, organization } = useAuth();
  const toast = useToast();
  const chat = useChat();
  const [draft, setDraft] = useState("");
  const [inspectQuery, setInspectQuery] = useState("");
  const [handoffOpen, setHandoffOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const providers = useQuery("providers", (signal) => assistantApi.providers({ signal }), { tags: ["providers"] });

  const lastTurn = chat.turns.at(-1);
  const scrollSignature = `${chat.turns.length}:${lastTurn?.answer.content.length ?? 0}:${lastTurn?.answer.status ?? ""}`;
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    // Follow the stream only while the reader is already near the bottom.
    const nearBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 160;
    if (nearBottom || lastTurn?.answer.status === "pending") node.scrollTo({ top: node.scrollHeight });
  }, [scrollSignature, lastTurn?.answer.status]);

  const submit = (text = draft) => {
    if (!text.trim() || chat.streaming || text.length > MAX_CHARS) return;
    if (chat.send(text)) {
      setDraft("");
      setInspectQuery(text.trim());
    }
    textareaRef.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  const rate = async (messageId: string, rating: Rating | null) => {
    try {
      await conversationsApi.feedback(messageId, { rating });
      chat.markRated(messageId, rating);
      invalidate("conversations");
    } catch (error) {
      toast.error("Could not save the rating", errorMessage(error));
    }
  };

  const socketBadge = SOCKET_BADGES[chat.status];
  const active = providers.data?.active;

  return (
    <>
      <PageHeader
        title="Playground"
        description={`Ask what ${organization?.name ?? "your"} customers would ask. Answers stream from the same pipeline as the website widget.`}
        actions={
          <>
            {chat.conversationId && (
              <ButtonLink
                href={`/app/conversations/${chat.conversationId}`}
                variant="ghost"
                icon={<ExternalLink className="size-4" aria-hidden />}
              >
                Open conversation
              </ButtonLink>
            )}
            <Button
              variant="outline"
              onClick={() => {
                chat.reset();
                setInspectQuery("");
                textareaRef.current?.focus();
              }}
              disabled={chat.turns.length === 0}
              icon={<RotateCcw className="size-4" aria-hidden />}
            >
              New conversation
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card className="flex h-[calc(100dvh-14rem)] min-h-[520px] flex-col overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Next answer from</span>
              {active ? <ProviderBadge provider={active.name} model={active.model} /> : <span>...</span>}
            </div>
            <Badge tone={socketBadge.tone} dot pulse={chat.status === "connecting" || chat.status === "reconnecting"}>
              {socketBadge.label}
            </Badge>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5 sm:px-6" aria-live="polite" aria-busy={chat.streaming}>
            {chat.turns.length === 0 ? (
              <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center text-center">
                <div className="mb-4 grid size-12 place-items-center rounded-xl bg-accent text-accent-foreground">
                  <Sparkles className="size-5" aria-hidden />
                </div>
                <h2 className="text-base font-semibold">Test your help desk</h2>
                <p className="mt-1.5 text-sm text-muted-foreground">
                  Answers cite your documents. Questions they do not cover get an honest &ldquo;not found&rdquo; and a
                  handoff offer.
                </p>
                <div className="mt-6 flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => submit(suggestion)}
                      disabled={chat.status !== "open"}
                      className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:opacity-50"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <ol className="mx-auto max-w-3xl space-y-6">
                {chat.turns.map((turn) => (
                  <li key={turn.clientId} className="space-y-4">
                    <div className="flex justify-end">
                      <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                        {turn.question}
                      </p>
                    </div>
                    <div className="flex gap-3">
                      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
                        <Sparkles className="size-4" aria-hidden />
                      </span>
                      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-border bg-surface px-4 py-3">
                        {turn.answer.status === "pending" || (turn.answer.status === "streaming" && !turn.answer.content) ? (
                          <TypingDots />
                        ) : turn.answer.content ? (
                          <AnswerBody
                            content={turn.answer.content}
                            citations={turn.answer.citations}
                            streaming={turn.answer.status === "streaming"}
                          />
                        ) : null}
                        {turn.answer.error && (
                          <div className={cn(turn.answer.content && "mt-3")}>
                            <TurnError turn={turn} />
                          </div>
                        )}
                        <AnswerMeta
                          turn={turn}
                          onRate={(id, rating) => void rate(id, rating)}
                          onInspect={setInspectQuery}
                          onHandoff={() => setHandoffOpen(true)}
                        />
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {chat.notice && (
            <div className="mx-4 mb-2 flex items-center justify-between gap-2 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
              <span>{chat.notice.message}</span>
              <button type="button" className="text-xs font-medium underline" onClick={chat.dismissNotice}>
                Dismiss
              </button>
            </div>
          )}

          <form
            className="border-t border-border p-3 sm:p-4"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <div className="flex items-end gap-2 rounded-xl border border-input bg-surface p-2 shadow-card focus-within:border-ring">
              <label htmlFor="playground-question" className="sr-only">
                Your question
              </label>
              <textarea
                id="playground-question"
                ref={textareaRef}
                rows={1}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown}
                placeholder={chat.status === "open" ? "Ask a question your customers might ask" : "Connecting to the assistant..."}
                className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none [field-sizing:content] placeholder:text-muted-foreground/80"
                aria-describedby="playground-hint"
              />
              {chat.streaming ? (
                <Button variant="outline" size="icon" aria-label="Stop the answer" onClick={chat.cancel}>
                  <Square className="size-3.5 fill-current" aria-hidden />
                </Button>
              ) : (
                <Button
                  type="submit"
                  size="icon"
                  aria-label="Send question"
                  disabled={!draft.trim() || chat.status !== "open" || draft.length > MAX_CHARS}
                >
                  <ArrowUp className="size-4" aria-hidden />
                </Button>
              )}
            </div>
            <p id="playground-hint" className="mt-1.5 flex justify-between px-1 text-xs text-muted-foreground">
              <span>Enter to send, Shift and Enter for a new line.</span>
              <span className={cn("tabular-nums", draft.length > MAX_CHARS && "font-medium text-danger")}>
                {draft.length > MAX_CHARS * 0.8 ? `${draft.length} / ${MAX_CHARS}` : ""}
              </span>
            </p>
          </form>
        </Card>

        <div className="flex flex-col gap-3 xl:h-[calc(100dvh-14rem)] xl:min-h-[520px]">
          <RetrievalInspector query={inspectQuery} onQueryChange={setInspectQuery} />
          <p className="px-1 text-xs text-muted-foreground">
            Playground conversations are saved with channel &ldquo;playground&rdquo; and count toward your monthly
            answers. <Link href="/app/conversations?channel=playground" className="text-primary hover:underline">See them all</Link>.
          </p>
        </div>
      </div>

      <HandoffDialog
        open={handoffOpen}
        onClose={() => setHandoffOpen(false)}
        defaultEmail={user?.email ?? ""}
        defaultName={user?.full_name ?? ""}
        onSubmit={async (input) => {
          await chat.requestHandoff(input);
          toast.success("Ticket created", "It is waiting in Tickets for your team.");
          invalidate("tickets", "conversations");
        }}
      />
    </>
  );
}
