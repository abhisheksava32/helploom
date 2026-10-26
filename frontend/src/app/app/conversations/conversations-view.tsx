"use client";

import { LifeBuoy, MessagesSquare, Search, SlidersHorizontal, ThumbsDown, ThumbsUp } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { AnswerTypeBadge, ChannelBadge, ConversationStatusBadge, ProviderBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { PageHeader, TableScroll, tableClasses } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/states";
import { conversationsApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/cn";
import { formatRelative, pluralize } from "@/lib/format";
import { useDebouncedValue, useNow } from "@/lib/hooks";
import { useQuery } from "@/lib/query";

const PAGE_SIZE = 25;

interface Filters {
  channel: string;
  status: string;
  answer_type: string;
  rating: string;
  provider: string;
  has_ticket: string;
  date_from: string;
  date_to: string;
}

const EMPTY: Filters = {
  channel: "",
  status: "",
  answer_type: "",
  rating: "",
  provider: "",
  has_ticket: "",
  date_from: "",
  date_to: "",
};

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <Select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} className="w-auto">
      {options.map(([optionValue, optionLabel]) => (
        <option key={optionValue} value={optionValue}>
          {optionLabel}
        </option>
      ))}
    </Select>
  );
}

export function ConversationsView() {
  const params = useSearchParams();
  const now = useNow();
  const [filters, setFilters] = useState<Filters>(() => ({
    ...EMPTY,
    channel: params.get("channel") ?? "",
    answer_type: params.get("answer_type") ?? "",
    has_ticket: params.get("has_ticket") ?? "",
  }));
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [showMore, setShowMore] = useState(false);
  const debouncedSearch = useDebouncedValue(search.trim(), 300);

  const query = { ...filters, search: debouncedSearch, page, page_size: PAGE_SIZE };
  const conversations = useQuery(
    `conversations:${JSON.stringify(query)}`,
    (signal) => conversationsApi.list(query, { signal }),
    { tags: ["conversations"] },
  );

  const set = (field: keyof Filters) => (value: string) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setPage(1);
  };
  const active = Object.values(filters).some(Boolean) || Boolean(debouncedSearch);

  return (
    <>
      <PageHeader
        title="Conversations"
        description="Every question from the website widget and the playground, with the answer, its sources and how it was rated."
      />
      <Card>
        <div className="space-y-2 border-b border-border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-48 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                type="search"
                aria-label="Search messages and titles"
                placeholder="Search messages"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                className="pl-9"
              />
            </div>
            <FilterSelect
              label="Channel"
              value={filters.channel}
              onChange={set("channel")}
              options={[
                ["", "All channels"],
                ["widget", "Website"],
                ["playground", "Playground"],
              ]}
            />
            <FilterSelect
              label="Status"
              value={filters.status}
              onChange={set("status")}
              options={[
                ["", "Any status"],
                ["open", "Open"],
                ["handed_off", "Handed off"],
                ["closed", "Closed"],
              ]}
            />
            <FilterSelect
              label="Answer type"
              value={filters.answer_type}
              onChange={set("answer_type")}
              options={[
                ["", "Any answer"],
                ["answered", "Answered"],
                ["not_found", "Not found"],
                ["refused", "Refused"],
                ["error", "Error"],
              ]}
            />
            <Button
              variant="outline"
              onClick={() => setShowMore((value) => !value)}
              aria-expanded={showMore}
              icon={<SlidersHorizontal className="size-4" aria-hidden />}
            >
              More filters
            </Button>
          </div>
          {showMore && (
            <div className="flex flex-wrap items-center gap-2">
              <FilterSelect
                label="Rating"
                value={filters.rating}
                onChange={set("rating")}
                options={[
                  ["", "Any rating"],
                  ["up", "Rated helpful"],
                  ["down", "Rated not helpful"],
                ]}
              />
              <FilterSelect
                label="Provider"
                value={filters.provider}
                onChange={set("provider")}
                options={[
                  ["", "Any provider"],
                  ["ollama", "Ollama"],
                  ["claude", "Claude API"],
                  ["extractive", "Extractive"],
                ]}
              />
              <FilterSelect
                label="Tickets"
                value={filters.has_ticket}
                onChange={set("has_ticket")}
                options={[
                  ["", "With or without tickets"],
                  ["true", "Has a ticket"],
                  ["false", "No ticket"],
                ]}
              />
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                From
                <Input type="date" value={filters.date_from} onChange={(event) => set("date_from")(event.target.value)} className="w-auto" />
              </label>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                To
                <Input type="date" value={filters.date_to} onChange={(event) => set("date_to")(event.target.value)} className="w-auto" />
              </label>
            </div>
          )}
        </div>

        {conversations.isLoading ? (
          <SkeletonRows rows={6} />
        ) : conversations.error && !conversations.data ? (
          <ErrorState message={conversations.error.message} onRetry={conversations.refetch} />
        ) : conversations.data && conversations.data.results.length > 0 ? (
          <div className={cn("transition-opacity", conversations.isFetching && "opacity-70")}>
            <TableScroll>
              <table className={cn(tableClasses.table, tableClasses.wide)}>
                <thead className={tableClasses.head}>
                  <tr>
                    <th scope="col" className={tableClasses.th}>
                      Conversation
                    </th>
                    <th scope="col" className={tableClasses.th}>
                      Status
                    </th>
                    <th scope="col" className={tableClasses.th}>
                      Last answer
                    </th>
                    <th scope="col" className={tableClasses.th}>
                      Feedback
                    </th>
                    <th scope="col" className={tableClasses.th}>
                      Last activity
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {conversations.data.results.map((conversation) => (
                    <tr key={conversation.id} className={tableClasses.row}>
                      <td className={tableClasses.td}>
                        <Link
                          href={`/app/conversations/${conversation.id}`}
                          className="block max-w-md truncate font-medium hover:text-primary hover:underline"
                        >
                          {conversation.title || "Untitled conversation"}
                        </Link>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                          <ChannelBadge channel={conversation.channel} />
                          <span>{pluralize(conversation.message_count, "message")}</span>
                          {conversation.channel === "widget" && conversation.origin && (
                            <span className="max-w-48 truncate">{conversation.origin.replace(/^https?:\/\//, "")}</span>
                          )}
                          {conversation.started_by && (
                            <span>by {conversation.started_by.full_name || conversation.started_by.email}</span>
                          )}
                        </div>
                      </td>
                      <td className={tableClasses.td}>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <ConversationStatusBadge status={conversation.status} />
                          {conversation.open_tickets > 0 && (
                            <span className="inline-flex items-center gap-1 text-xs text-warning">
                              <LifeBuoy className="size-3.5" aria-hidden />
                              {conversation.open_tickets}
                              <span className="sr-only">open tickets</span>
                            </span>
                          )}
                        </div>
                      </td>
                      <td className={tableClasses.td}>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <AnswerTypeBadge type={conversation.last_answer_type} />
                          {conversation.providers.map((provider) => (
                            <ProviderBadge key={provider} provider={provider} />
                          ))}
                        </div>
                      </td>
                      <td className={cn(tableClasses.td, "whitespace-nowrap text-muted-foreground")}>
                        {conversation.thumbs_up + conversation.thumbs_down === 0 ? (
                          <span className="text-xs">None</span>
                        ) : (
                          <span className="inline-flex items-center gap-3 text-xs">
                            <span className="inline-flex items-center gap-1">
                              <ThumbsUp className="size-3.5 text-success" aria-label="Helpful" />
                              {conversation.thumbs_up}
                            </span>
                            <span className="inline-flex items-center gap-1">
                              <ThumbsDown className="size-3.5 text-danger" aria-label="Not helpful" />
                              {conversation.thumbs_down}
                            </span>
                          </span>
                        )}
                      </td>
                      <td className={cn(tableClasses.td, "whitespace-nowrap text-muted-foreground")}>
                        {formatRelative(conversation.last_message_at ?? conversation.created_at, now)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              count={conversations.data.count}
              onPageChange={setPage}
              label="conversations"
            />
          </div>
        ) : active ? (
          <EmptyState
            icon={Search}
            title="No conversations match"
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setFilters(EMPTY);
                  setSearch("");
                  setPage(1);
                }}
              >
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={MessagesSquare}
            title="No conversations yet"
            description="Ask something in the playground or install the widget. New conversations appear here live."
          />
        )}
      </Card>
    </>
  );
}
