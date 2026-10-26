"use client";

import { ExternalLink, FileText, X } from "lucide-react";
import Link from "next/link";
import { Fragment, useId, useState } from "react";

import type { Citation } from "@/lib/api/types";
import { splitCitations } from "@/lib/citations";
import { cn } from "@/lib/cn";

function CitationMarker({
  marker,
  citation,
  selected,
  onToggle,
  controls,
}: {
  marker: number;
  citation: Citation | undefined;
  selected: boolean;
  onToggle: (marker: number) => void;
  controls: string;
}) {
  if (!citation) {
    // Citations arrive after the text streams; until then the marker is a plain label.
    return (
      <span className="mx-0.5 inline-grid h-4 min-w-4 place-items-center rounded bg-surface-muted px-1 align-[0.15em] text-[10px] font-semibold text-muted-foreground">
        {marker}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onToggle(marker)}
      aria-expanded={selected}
      aria-controls={controls}
      aria-label={`Source ${marker}: ${citation.document_title}`}
      title={`${citation.document_title}${citation.location ? `, ${citation.location}` : ""}`}
      className={cn(
        "mx-0.5 inline-grid h-4 min-w-4 place-items-center rounded px-1 align-[0.15em] text-[10px] font-semibold transition-colors",
        selected ? "bg-primary text-primary-foreground" : "bg-accent text-accent-foreground hover:bg-primary/20",
      )}
    >
      {marker}
    </button>
  );
}

/**
 * Answer text with interactive citation markers and the list of sources under it.
 * Text is rendered as React text nodes (never HTML), so a document cannot inject
 * markup into the dashboard.
 */
export function AnswerBody({
  content,
  citations,
  streaming = false,
  className,
}: {
  content: string;
  citations: Citation[];
  streaming?: boolean;
  className?: string;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const panelId = useId();
  const byMarker = new Map(citations.map((citation) => [citation.marker, citation]));
  const parts = splitCitations(content);
  const toggle = (marker: number) => setSelected((current) => (current === marker ? null : marker));
  const active = selected === null ? undefined : byMarker.get(selected);
  const sorted = [...citations].sort((a, b) => a.marker - b.marker);

  return (
    <div className={className}>
      <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
        {parts.map((part, index) =>
          part.kind === "text" ? (
            <Fragment key={index}>{part.text}</Fragment>
          ) : (
            <CitationMarker
              key={index}
              marker={part.marker}
              citation={byMarker.get(part.marker)}
              selected={selected === part.marker}
              onToggle={toggle}
              controls={panelId}
            />
          ),
        )}
        {streaming && (
          <span aria-hidden className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-primary/70 align-[-0.2em]" />
        )}
      </p>

      {sorted.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {sorted.map((citation) => (
            <button
              key={citation.marker}
              type="button"
              onClick={() => toggle(citation.marker)}
              aria-expanded={selected === citation.marker}
              aria-controls={panelId}
              className={cn(
                "inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors",
                selected === citation.marker
                  ? "border-primary/40 bg-accent text-accent-foreground"
                  : "border-border bg-surface text-muted-foreground hover:border-primary/30 hover:text-foreground",
              )}
            >
              <span className="font-semibold">{citation.marker}</span>
              <FileText className="size-3 shrink-0" aria-hidden />
              <span className="truncate">{citation.document_title}</span>
              {citation.location && <span className="hidden truncate text-muted-foreground sm:inline">{citation.location}</span>}
            </button>
          ))}
        </div>
      )}

      <div id={panelId} aria-live="polite">
        {active && <SourceCard citation={active} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}

export function SourceCard({ citation, onClose }: { citation: Citation; onClose?: () => void }) {
  return (
    <div className="hl-pop mt-3 rounded-lg border border-border bg-surface-muted/60 p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">
            <span className="mr-1.5 text-primary">[{citation.marker}]</span>
            {citation.document_title}
          </p>
          <p className="text-xs text-muted-foreground">
            {citation.location || "Passage"}
            {citation.score !== null && <> &middot; similarity {citation.score.toFixed(2)}</>}
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close source"
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </button>
        )}
      </div>
      <blockquote className="mt-2 border-l-2 border-primary/40 pl-3 text-sm leading-relaxed text-foreground/90">
        {citation.snippet}
      </blockquote>
      {citation.document_id ? (
        <Link
          href={`/app/documents?preview=${citation.document_id}`}
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          Open document <ExternalLink className="size-3" aria-hidden />
        </Link>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">This document has since been deleted.</p>
      )}
    </div>
  );
}

/** Animated dots shown while the first token is on its way. */
export function TypingDots({ label = "Assistant is thinking" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-1 py-1">
      <span className="sr-only">{label}</span>
      {[0, 1, 2].map((dot) => (
        <span key={dot} aria-hidden className="hl-dot size-1.5 rounded-full bg-muted-foreground" />
      ))}
    </span>
  );
}
