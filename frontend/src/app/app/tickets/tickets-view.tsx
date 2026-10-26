"use client";

import { LifeBuoy, Search } from "lucide-react";
import { useState } from "react";

import { TicketCard, useMembers } from "@/components/tickets/ticket-card";
import { Card } from "@/components/ui/card";
import { Segmented } from "@/components/ui/controls";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/states";
import { ticketsApi } from "@/lib/api/endpoints";
import type { Paginated, Ticket } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { useDebouncedValue } from "@/lib/hooks";
import { useQuery } from "@/lib/query";

const PAGE_SIZE = 20;

type StatusFilter = "open" | "pending" | "resolved" | "all";

const EMPTY_COPY: Record<StatusFilter, { title: string; description: string }> = {
  open: { title: "No open tickets", description: "When a visitor asks for a person, the ticket lands here." },
  pending: { title: "Nothing pending", description: "Tickets waiting on the customer show up here." },
  resolved: { title: "No resolved tickets yet", description: "Resolved tickets are kept for reference." },
  all: { title: "No tickets yet", description: "Handoff requests from the widget and the playground appear here." },
};

export function TicketsView() {
  const [status, setStatus] = useState<StatusFilter>("open");
  const [assigned, setAssigned] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebouncedValue(search.trim(), 300);

  const query = {
    status: status === "all" ? "" : status,
    assigned_to: assigned,
    search: debouncedSearch,
    page,
    page_size: PAGE_SIZE,
  };
  const members = useMembers();
  const tickets = useQuery(`tickets:${JSON.stringify(query)}`, (signal) => ticketsApi.list(query, { signal }), {
    tags: ["tickets"],
  });

  const replace = (updated: Ticket) =>
    tickets.setData((current: Paginated<Ticket> | undefined) =>
      current
        ? { ...current, results: current.results.map((ticket) => (ticket.id === updated.id ? updated : ticket)) }
        : current,
    );

  return (
    <>
      <PageHeader
        title="Tickets"
        description="Visitors who asked for a person. Reply by email, then resolve the ticket so reports stay accurate."
      />
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <Segmented
            label="Ticket status"
            size="md"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              { value: "open", label: "Open" },
              { value: "pending", label: "Pending" },
              { value: "resolved", label: "Resolved" },
              { value: "all", label: "All" },
            ]}
          />
          <Select
            aria-label="Assignee"
            value={assigned}
            onChange={(event) => {
              setAssigned(event.target.value);
              setPage(1);
            }}
            className="w-auto"
          >
            <option value="">Anyone</option>
            <option value="me">Assigned to me</option>
            <option value="none">Unassigned</option>
          </Select>
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              type="search"
              aria-label="Search tickets"
              placeholder="Search email, name or note"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              className="pl-9"
            />
          </div>
        </div>
        {tickets.isLoading ? (
          <SkeletonRows rows={4} />
        ) : tickets.error && !tickets.data ? (
          <ErrorState message={tickets.error.message} onRetry={tickets.refetch} />
        ) : tickets.data && tickets.data.results.length > 0 ? (
          <div className={cn("transition-opacity", tickets.isFetching && "opacity-70")}>
            <ul className="space-y-3 p-3 sm:p-4">
              {tickets.data.results.map((ticket) => (
                <li key={ticket.id}>
                  <TicketCard ticket={ticket} members={members.data?.results ?? []} onUpdated={replace} />
                </li>
              ))}
            </ul>
            <Pagination page={page} pageSize={PAGE_SIZE} count={tickets.data.count} onPageChange={setPage} label="tickets" />
          </div>
        ) : (
          <EmptyState
            icon={LifeBuoy}
            title={debouncedSearch || assigned ? "No tickets match" : EMPTY_COPY[status].title}
            description={debouncedSearch || assigned ? undefined : EMPTY_COPY[status].description}
          />
        )}
      </Card>
    </>
  );
}
