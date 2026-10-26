"use client";

import { CheckCircle2, CircleSlash, Search } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/field";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/states";
import { assistantApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/cn";
import { useQuery } from "@/lib/query";

function Score({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-surface-muted/70 px-2.5 py-1.5">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="font-mono text-sm tabular-nums">{value}</p>
    </div>
  );
}

/**
 * Runs retrieval only (POST /assistant/search/) for a question and shows both
 * halves of hybrid search: vector similarity and keyword rank, the fused RRF score,
 * and whether the relevance threshold would let the assistant answer.
 */
export function RetrievalInspector({ query, onQueryChange }: { query: string; onQueryChange: (query: string) => void }) {
  const [draft, setDraft] = useState(query);
  const [lastQuery, setLastQuery] = useState(query);
  // Follow questions picked from the chat while still allowing manual edits.
  if (query !== lastQuery) {
    setLastQuery(query);
    setDraft(query);
  }

  const search = useQuery(query ? `retrieval:${query}` : null, (signal) =>
    assistantApi.search({ query, top_k: 8 }, { signal }),
  );

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (draft.trim()) onQueryChange(draft.trim());
  };

  const result = search.data;
  return (
    <Card className="flex max-h-[70vh] min-h-0 flex-1 flex-col overflow-hidden xl:max-h-none">
      <CardHeader
        title="Retrieval inspector"
        description="What hybrid search finds before any model runs."
      />
      <form onSubmit={onSubmit} className="flex gap-2 border-b border-border p-3">
        <Input
          aria-label="Search query"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Type a question to inspect"
        />
        <Button type="submit" variant="outline" size="icon" aria-label="Run retrieval" disabled={!draft.trim()}>
          <Search className="size-4" aria-hidden />
        </Button>
      </form>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {!query ? (
          <EmptyState
            icon={Search}
            title="Nothing inspected yet"
            description="Ask a question, then choose Inspect retrieval under the answer."
            className="py-10"
          />
        ) : search.isLoading ? (
          <SkeletonRows rows={4} />
        ) : search.error ? (
          <ErrorState message={search.error.message} onRetry={search.refetch} className="py-8" />
        ) : result ? (
          <div className={cn("space-y-3 p-3 transition-opacity", search.isFetching && "opacity-60")}>
            <div
              className={cn(
                "flex items-start gap-2 rounded-md px-3 py-2 text-sm",
                result.would_answer ? "bg-success-soft text-success" : "bg-warning-soft text-warning",
              )}
            >
              {result.would_answer ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
              ) : (
                <CircleSlash className="mt-0.5 size-4 shrink-0" aria-hidden />
              )}
              <p>
                {result.would_answer
                  ? "Above the relevance threshold: the assistant answers from these passages."
                  : "Below the relevance threshold: the assistant says it could not find this and offers a person."}
              </p>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Score label="Top similarity" value={result.top_similarity === null ? "-" : result.top_similarity.toFixed(3)} />
              <Score label="Threshold" value={result.threshold.toFixed(3)} />
              <Score label="Keyword hits" value={String(result.keyword_hits)} />
            </div>
            <p className="text-xs text-muted-foreground">
              Embedder <span className="font-mono">{result.embedder}</span>. Ranked by reciprocal rank fusion of the
              vector and keyword lists.
            </p>
            {result.results.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">No passages matched.</p>
            ) : (
              <ol className="space-y-2">
                {result.results.map((item, index) => (
                  <li key={item.chunk_id} className="rounded-lg border border-border p-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 text-sm font-medium">
                        <span className="mr-1.5 text-muted-foreground">{index + 1}.</span>
                        {item.document_title}
                      </p>
                      <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
                        {item.score.toFixed(4)}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">{item.location || item.heading}</p>
                    <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-foreground/85">{item.snippet}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                      <span className="rounded bg-surface-muted px-1.5 py-0.5">
                        cosine {item.similarity === null ? "-" : item.similarity.toFixed(3)}
                      </span>
                      <span className="rounded bg-surface-muted px-1.5 py-0.5">
                        {item.vector_rank === null ? "no vector match" : `vector #${item.vector_rank}`}
                      </span>
                      <span className="rounded bg-surface-muted px-1.5 py-0.5">
                        {item.keyword_rank === null ? "no keyword match" : `keyword #${item.keyword_rank}`}
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        ) : null}
      </div>
    </Card>
  );
}
