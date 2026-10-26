"use client";

/**
 * An interactive preview of the widget on the landing page. It replays scripted
 * answers for a fictional store, streamed word by word with citations, so the page
 * shows the product without needing a running backend. The real widget is loaded
 * separately when NEXT_PUBLIC_DEMO_SITE_KEY is set.
 */

import { FileText, LifeBuoy, MessageCircle, Send, X } from "lucide-react";
import { Fragment, useEffect, useState } from "react";

import type { Citation } from "@/lib/api/types";
import { splitCitations } from "@/lib/citations";
import { cn } from "@/lib/cn";
import { useMediaQuery } from "@/lib/hooks";

interface Script {
  question: string;
  answer: string;
  citations: Citation[];
  notFound?: boolean;
}

const cite = (marker: number, document_title: string, location: string, snippet: string): Citation => ({
  marker,
  document_id: null,
  chunk_id: null,
  document_title,
  location,
  snippet,
  score: null,
});

const SCRIPTS: Script[] = [
  {
    question: "How long do refunds take?",
    answer:
      "Refunds go back to your original payment method within 5 business days of your return reaching our warehouse [1]. You get an email the moment it is issued [1].",
    citations: [
      cite(1, "Returns and refunds", "Refunds > Timing", "Once your return arrives and passes inspection, we issue the refund to the original payment method within 5 business days and send a confirmation email."),
    ],
  },
  {
    question: "Do you ship to Canada?",
    answer:
      "Yes. Standard shipping to Canada takes 5 to 8 business days and is free on orders over $75 [1]. Duties and taxes are collected at checkout, so there is nothing to pay on delivery [2].",
    citations: [
      cite(1, "Shipping guide", "International > Canada", "Canadian orders ship with tracked standard delivery in 5 to 8 business days. Orders over $75 ship free."),
      cite(2, "Help center FAQ", "Customs and duties", "We collect duties and import taxes at checkout for Canada, the UK and the EU, so couriers never ask for payment on delivery."),
    ],
  },
  {
    question: "Can I change my order after paying?",
    answer:
      "You can edit or cancel an order for 60 minutes after placing it, from the order page [1]. After that it is already being packed, but you can return it once it arrives [2].",
    citations: [
      cite(1, "Orders and payments", "Changing an order", "Orders can be edited or cancelled from the order status page for 60 minutes after checkout."),
      cite(2, "Returns and refunds", "Return window", "Unworn items can be returned within 30 days of delivery for a full refund."),
    ],
  },
  {
    question: "What is your CEO's phone number?",
    answer: "I could not find that in our documentation. Would you like to talk to a person on our team?",
    citations: [],
    notFound: true,
  },
];

export function HeroDemo() {
  const [active, setActive] = useState(0);
  const [words, setWords] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const script = SCRIPTS[active];
  const tokens = script.answer.split(/(\s+)/);
  const total = tokens.length;
  const shown = reducedMotion ? total : words;
  const done = shown >= total;

  // Two tokens (a word and its space) every 45 ms reads like a fast model; the
  // interval stops itself through the effect once the answer is complete.
  useEffect(() => {
    if (reducedMotion || done) return;
    const timer = window.setInterval(() => setWords((count) => Math.min(total, count + 2)), 45);
    return () => window.clearInterval(timer);
  }, [active, total, done, reducedMotion]);

  const ask = (index: number) => {
    setActive(index);
    setWords(0);
    setExpanded(null);
  };

  const visible = tokens.slice(0, shown).join("");
  const byMarker = new Map(script.citations.map((citation) => [citation.marker, citation]));
  const open = expanded === null ? undefined : byMarker.get(expanded);

  return (
    <div className="relative">
      <div aria-hidden className="absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-primary/15 via-transparent to-chart-3/15 blur-2xl" />
      <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-popover">
        <div className="flex items-center justify-between bg-primary px-4 py-3 text-primary-foreground">
          <div>
            <p className="text-sm font-semibold">Northwind help</p>
            <p className="text-xs opacity-80">Answers from the store&apos;s own policies</p>
          </div>
          <X className="size-4 opacity-70" aria-hidden />
        </div>
        <div className="space-y-3 bg-background p-4" aria-live="polite">
          <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 text-sm text-primary-foreground">
            {script.question}
          </p>
          <div className="max-w-[92%] rounded-2xl rounded-tl-md border border-border bg-surface px-3.5 py-2.5 text-sm leading-relaxed">
            {shown === 0 ? (
              <span className="inline-flex gap-1 py-1" aria-label="Thinking">
                {[0, 1, 2].map((dot) => (
                  <span key={dot} className="hl-dot size-1.5 rounded-full bg-muted-foreground" />
                ))}
              </span>
            ) : (
              <p className="whitespace-pre-wrap">
                {splitCitations(visible).map((part, index) =>
                  part.kind === "text" ? (
                    <Fragment key={index}>{part.text}</Fragment>
                  ) : (
                    <button
                      key={index}
                      type="button"
                      onClick={() => setExpanded((current) => (current === part.marker ? null : part.marker))}
                      aria-expanded={expanded === part.marker}
                      aria-label={`Source ${part.marker}`}
                      className={cn(
                        "mx-0.5 inline-grid h-4 min-w-4 place-items-center rounded px-1 align-[0.15em] text-[10px] font-semibold",
                        expanded === part.marker ? "bg-primary text-primary-foreground" : "bg-accent text-accent-foreground",
                      )}
                    >
                      {part.marker}
                    </button>
                  ),
                )}
                {!done && <span aria-hidden className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-primary/70 align-[-0.15em]" />}
              </p>
            )}
            {done && script.citations.length > 0 && (
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {script.citations.map((citation) => (
                  <button
                    key={citation.marker}
                    type="button"
                    onClick={() => setExpanded((current) => (current === citation.marker ? null : citation.marker))}
                    aria-expanded={expanded === citation.marker}
                    className={cn(
                      "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs",
                      expanded === citation.marker
                        ? "border-primary/40 bg-accent text-accent-foreground"
                        : "border-border text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <FileText className="size-3" aria-hidden />
                    {citation.document_title}
                  </button>
                ))}
              </div>
            )}
            {done && open && (
              <blockquote className="hl-pop mt-2.5 rounded-md border-l-2 border-primary bg-surface-muted/70 px-3 py-2 text-xs leading-relaxed">
                <span className="block font-medium">
                  {open.document_title}, {open.location}
                </span>
                <span className="text-muted-foreground">{open.snippet}</span>
              </blockquote>
            )}
            {done && script.notFound && (
              <span className="mt-2.5 inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs font-medium">
                <LifeBuoy className="size-3.5" aria-hidden />
                Talk to a human
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 border-t border-border px-3 py-2.5">
          <span className="flex-1 text-sm text-muted-foreground">Ask a question</span>
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Send className="size-3.5" aria-hidden />
          </span>
        </div>
      </div>
      <div className="mt-4">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <MessageCircle className="size-3.5" aria-hidden />
          Try a question
        </p>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Sample questions">
          {SCRIPTS.map((item, index) => (
            <button
              key={item.question}
              type="button"
              onClick={() => ask(index)}
              aria-pressed={index === active}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                index === active
                  ? "border-primary/40 bg-accent text-accent-foreground"
                  : "border-border bg-surface text-muted-foreground hover:text-foreground",
              )}
            >
              {item.question}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
