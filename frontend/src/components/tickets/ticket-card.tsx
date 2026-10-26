"use client";

import { Mail, StickyNote } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { TicketStatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { organizationApi, ticketsApi } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/errors";
import type { Member, Ticket, TicketStatus } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { invalidate, useMutation, useQuery } from "@/lib/query";

/** Members for the assignee picker. Pages load them once and pass them to every card. */
export function useMembers() {
  return useQuery("members:all", (signal) => organizationApi.members({ page_size: 100 }, { signal }), {
    tags: ["members"],
  });
}

export function TicketCard({
  ticket,
  members,
  onUpdated,
  showConversation = true,
}: {
  ticket: Ticket;
  members: Member[];
  onUpdated?: (ticket: Ticket) => void;
  showConversation?: boolean;
}) {
  const toast = useToast();
  const now = useNow();
  const { user } = useAuth();
  const [editingNote, setEditingNote] = useState(false);
  const [note, setNote] = useState(ticket.note);
  const update = useMutation(
    (body: { status?: TicketStatus; assigned_to?: string | null; note?: string }) => ticketsApi.update(ticket.id, body),
    { onError: (error) => toast.error("Could not update the ticket", errorMessage(error)) },
  );

  const apply = async (body: { status?: TicketStatus; assigned_to?: string | null; note?: string }) => {
    const updated = await update.mutate(body);
    if (updated) {
      onUpdated?.(updated);
      invalidate("tickets", "conversations");
    }
    return updated;
  };

  return (
    <article className="rounded-lg border border-border bg-surface p-4" aria-busy={update.pending}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <TicketStatusBadge status={ticket.status} />
            <h3 className="truncate text-sm font-semibold">{ticket.requester_name || ticket.requester_email}</h3>
          </div>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <a href={`mailto:${ticket.requester_email}`} className="inline-flex items-center gap-1 hover:text-foreground">
              <Mail className="size-3" aria-hidden />
              {ticket.requester_email}
            </a>
            <span title={formatDateTime(ticket.created_at)}>Opened {formatRelative(ticket.created_at, now)}</span>
            {ticket.resolved_at && <span>Resolved {formatRelative(ticket.resolved_at, now)}</span>}
          </p>
          {showConversation && (
            <Link
              href={`/app/conversations/${ticket.conversation_id}`}
              className="block truncate text-sm text-primary hover:underline"
            >
              {ticket.conversation_title || "Open conversation"}
            </Link>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            aria-label="Ticket status"
            value={ticket.status}
            disabled={update.pending}
            onChange={(event) => void apply({ status: event.target.value as TicketStatus })}
            className="h-8 w-auto text-xs"
          >
            <option value="open">Open</option>
            <option value="pending">Pending</option>
            <option value="resolved">Resolved</option>
          </Select>
          <Select
            aria-label="Assignee"
            value={ticket.assigned_to?.id ?? ""}
            disabled={update.pending}
            onChange={(event) => void apply({ assigned_to: event.target.value || null })}
            className="h-8 w-auto max-w-44 text-xs"
          >
            <option value="">Unassigned</option>
            {ticket.assigned_to && !members.some((member) => member.user.id === ticket.assigned_to?.id) && (
              <option value={ticket.assigned_to.id}>{ticket.assigned_to.full_name || ticket.assigned_to.email}</option>
            )}
            {members.map((member) => (
              <option key={member.user.id} value={member.user.id}>
                {member.user.id === user?.id ? "Me" : member.user.full_name || member.user.email}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {editingNote ? (
        <form
          className="mt-3 space-y-2"
          onSubmit={async (event) => {
            event.preventDefault();
            if (await apply({ note: note.trim() })) setEditingNote(false);
          }}
        >
          <Textarea aria-label="Ticket note" value={note} maxLength={2000} onChange={(event) => setNote(event.target.value)} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setEditingNote(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={update.pending}>
              Save note
            </Button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => {
            setNote(ticket.note);
            setEditingNote(true);
          }}
          className="mt-3 flex w-full items-start gap-2 rounded-md bg-surface-muted/60 px-3 py-2 text-left text-sm hover:bg-surface-muted"
        >
          <StickyNote className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className={ticket.note ? "whitespace-pre-wrap" : "text-muted-foreground"}>
            {ticket.note || "Add a note for the team"}
          </span>
        </button>
      )}
    </article>
  );
}
