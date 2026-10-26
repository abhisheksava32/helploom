"use client";

import { LogOut, Mail, RotateCw, Trash2, UserPlus, Users } from "lucide-react";
import { useState } from "react";

import { UserAvatar } from "@/components/app-shell/user-menu";
import { UpgradeNotice } from "@/components/upgrade-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { CopyButton, Meter } from "@/components/ui/controls";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, FormError, Input, Select } from "@/components/ui/field";
import { PageHeader, TableScroll, tableClasses } from "@/components/ui/page-header";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { billingApi, organizationApi } from "@/lib/api/endpoints";
import { errorMessage, planLimitOf } from "@/lib/api/errors";
import type { Invitation, Member, Role } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { ROLE_LABELS, usePermissions } from "@/lib/auth/roles";
import { cn } from "@/lib/cn";
import { formatDate, formatRelative } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { invalidate, useMutation, useQuery } from "@/lib/query";

const ROLE_HELP: Record<Role, string> = {
  owner: "Everything, including billing and member roles.",
  admin: "Documents, widget, settings and invitations.",
  agent: "Conversations, tickets, reports and the playground.",
};

function InviteCard() {
  const { isOwner } = usePermissions();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("agent");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const invite = useMutation(() => organizationApi.invite({ email: email.trim(), role }));
  const limit = planLimitOf(invite.error);
  const fieldErrors = invite.error?.fieldErrors() ?? {};

  return (
    <Card>
      <CardHeader title="Invite a teammate" description="They get an email with a link that is valid for 7 days." />
      <CardBody className="space-y-4">
        <form
          className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px_auto] sm:items-end"
          onSubmit={async (event) => {
            event.preventDefault();
            const created = await invite.mutate();
            if (created) {
              setEmail("");
              setInviteUrl(created.invite_url);
              toast.success("Invitation sent", created.email);
              invalidate("invitations", "subscription");
            }
          }}
        >
          <Field label="Email" error={fieldErrors.email?.[0]}>
            {(props) => (
              <Input
                {...props}
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="teammate@company.com"
              />
            )}
          </Field>
          <Field label="Role" error={fieldErrors.role?.[0]}>
            {(props) => (
              <Select {...props} value={role} onChange={(event) => setRole(event.target.value as Role)}>
                <option value="agent">Agent</option>
                <option value="admin">Admin</option>
                {isOwner && <option value="owner">Owner</option>}
              </Select>
            )}
          </Field>
          <Button type="submit" loading={invite.pending} disabled={!email.trim()} icon={<UserPlus className="size-4" aria-hidden />}>
            Send invite
          </Button>
        </form>
        <p className="text-xs text-muted-foreground">{ROLE_LABELS[role]}: {ROLE_HELP[role]}</p>
        {limit ? (
          <UpgradeNotice limit={limit} />
        ) : (
          invite.error && Object.keys(fieldErrors).length === 0 && <FormError message={invite.error.message} />
        )}
        {inviteUrl && (
          <div className="rounded-lg border border-border bg-surface-muted/50 p-3">
            <p className="text-sm font-medium">Invitation link</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Shown because the server runs in debug mode with the console email backend.
            </p>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded bg-surface px-2 py-1.5 font-mono text-xs">{inviteUrl}</code>
              <CopyButton value={inviteUrl} size="sm" label="Copy link" />
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function MembersCard() {
  const { user, reload } = useAuth();
  const { isAdmin, isOwner } = usePermissions();
  const toast = useToast();
  const now = useNow();
  const members = useQuery("members:all", (signal) => organizationApi.members({ page_size: 100 }, { signal }), {
    tags: ["members"],
  });
  const [removing, setRemoving] = useState<Member | null>(null);
  const changeRole = useMutation((id: string, role: Role) => organizationApi.updateMember(id, role), {
    onError: (error) => toast.error("Could not change the role", errorMessage(error)),
  });
  const remove = useMutation(async (id: string) => {
    await organizationApi.removeMember(id);
    return true;
  }, { onError: (error) => toast.error("Could not remove the member", errorMessage(error)) });

  const isSelf = (member: Member) => member.user.id === user?.id;

  return (
    <Card>
      <CardHeader title="Members" description="Everyone with access to this workspace." />
      {members.isLoading ? (
        <SkeletonRows rows={3} />
      ) : members.error && !members.data ? (
        <ErrorState message={members.error.message} onRetry={members.refetch} />
      ) : members.data && members.data.results.length > 0 ? (
        <TableScroll>
          <table className={cn(tableClasses.table, "min-w-[520px]")}>
            <thead className={tableClasses.head}>
              <tr>
                <th scope="col" className={tableClasses.th}>
                  Member
                </th>
                <th scope="col" className={tableClasses.th}>
                  Role
                </th>
                <th scope="col" className={tableClasses.th}>
                  Joined
                </th>
                <th scope="col" className={cn(tableClasses.th, "text-right")}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {members.data.results.map((member) => {
                const canRemove = isSelf(member) || (isAdmin && (member.role !== "owner" || isOwner));
                return (
                  <tr key={member.id} className={tableClasses.row}>
                    <td className={tableClasses.td}>
                      <div className="flex items-center gap-3">
                        <UserAvatar name={member.user.full_name} email={member.user.email} />
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {member.user.full_name || member.user.email}
                            {isSelf(member) && <span className="ml-1.5 text-xs font-normal text-muted-foreground">(you)</span>}
                          </p>
                          <p className="truncate text-xs text-muted-foreground">{member.user.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className={tableClasses.td}>
                      {isOwner ? (
                        <Select
                          aria-label={`Role for ${member.user.email}`}
                          value={member.role}
                          disabled={changeRole.pending}
                          onChange={async (event) => {
                            const updated = await changeRole.mutate(member.id, event.target.value as Role);
                            if (updated) {
                              members.setData((list) =>
                                list ? { ...list, results: list.results.map((item) => (item.id === updated.id ? updated : item)) } : list,
                              );
                              if (isSelf(member)) await reload();
                              toast.success("Role updated");
                            }
                          }}
                          className="h-8 w-auto text-xs"
                        >
                          <option value="owner">Owner</option>
                          <option value="admin">Admin</option>
                          <option value="agent">Agent</option>
                        </Select>
                      ) : (
                        <Badge tone={member.role === "owner" ? "primary" : "neutral"}>{ROLE_LABELS[member.role]}</Badge>
                      )}
                    </td>
                    <td className={cn(tableClasses.td, "text-muted-foreground")}>{formatRelative(member.created_at, now)}</td>
                    <td className={cn(tableClasses.td, "text-right")}>
                      {canRemove && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setRemoving(member)}
                          icon={isSelf(member) ? <LogOut className="size-4" aria-hidden /> : <Trash2 className="size-4" aria-hidden />}
                        >
                          {isSelf(member) ? "Leave" : "Remove"}
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableScroll>
      ) : (
        <EmptyState icon={Users} title="No members" />
      )}
      <ConfirmDialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title={removing && isSelf(removing) ? "Leave this workspace?" : `Remove ${removing?.user.email ?? "member"}?`}
        description={
          removing && isSelf(removing)
            ? "You lose access straight away. An admin can invite you again."
            : "They lose access straight away. Their past tickets and conversations stay."
        }
        confirmLabel={removing && isSelf(removing) ? "Leave workspace" : "Remove member"}
        pending={remove.pending}
        onConfirm={async () => {
          if (!removing) return;
          const leaving = isSelf(removing);
          const ok = await remove.mutate(removing.id);
          setRemoving(null);
          if (!ok) return;
          if (leaving) {
            await reload();
          } else {
            invalidate("members", "subscription");
            toast.success("Member removed");
          }
        }}
      />
    </Card>
  );
}

function InvitationsCard() {
  const toast = useToast();
  const now = useNow();
  const invitations = useQuery(
    "invitations:pending",
    (signal) => organizationApi.invitations({ status: "pending", page_size: 100 }, { signal }),
    { tags: ["invitations"] },
  );
  const [revoking, setRevoking] = useState<Invitation | null>(null);
  const resend = useMutation((id: string) => organizationApi.resendInvitation(id), {
    onError: (error) => toast.error("Could not resend", errorMessage(error)),
  });
  const revoke = useMutation(async (id: string) => {
    await organizationApi.revokeInvitation(id);
    return true;
  }, { onError: (error) => toast.error("Could not revoke", errorMessage(error)) });

  return (
    <Card>
      <CardHeader title="Pending invitations" description="Pending invitations count as seats until they are accepted or revoked." />
      {invitations.isLoading ? (
        <SkeletonRows rows={2} />
      ) : invitations.error && !invitations.data ? (
        <ErrorState message={invitations.error.message} onRetry={invitations.refetch} className="py-8" />
      ) : invitations.data && invitations.data.results.length > 0 ? (
        <ul className="divide-y divide-border">
          {invitations.data.results.map((invitation) => (
            <li key={invitation.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
              <span className="grid size-8 place-items-center rounded-full bg-surface-muted text-muted-foreground">
                <Mail className="size-4" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{invitation.email}</p>
                <p className="text-xs text-muted-foreground">
                  {ROLE_LABELS[invitation.role]} &middot; sent {formatRelative(invitation.created_at, now)} &middot; expires{" "}
                  {formatDate(invitation.expires_at)}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                loading={resend.pending}
                icon={<RotateCw className="size-4" aria-hidden />}
                onClick={async () => {
                  const updated = await resend.mutate(invitation.id);
                  if (updated) {
                    toast.success("Invitation sent again", updated.invite_url ?? updated.email);
                    invalidate("invitations");
                  }
                }}
              >
                Resend
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setRevoking(invitation)} icon={<Trash2 className="size-4" aria-hidden />}>
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No pending invitations" className="py-8" />
      )}
      <ConfirmDialog
        open={revoking !== null}
        onClose={() => setRevoking(null)}
        title={`Revoke the invitation for ${revoking?.email ?? ""}?`}
        description="The link stops working and the seat is freed."
        confirmLabel="Revoke invitation"
        pending={revoke.pending}
        onConfirm={async () => {
          if (!revoking) return;
          const ok = await revoke.mutate(revoking.id);
          setRevoking(null);
          if (ok) {
            invalidate("invitations", "subscription");
            toast.success("Invitation revoked");
          }
        }}
      />
    </Card>
  );
}

export function TeamView() {
  const { isAdmin } = usePermissions();
  const subscription = useQuery("subscription", (signal) => billingApi.subscription({ signal }), { tags: ["subscription"] });
  const seats = subscription.data?.usage.seats;

  return (
    <>
      <PageHeader title="Team" description="Invite teammates and decide what each of them can change." />
      <div className="space-y-6">
        {seats && (
          <Card>
            <CardBody>
              <Meter label={`Seats on the ${subscription.data?.plan.name ?? ""} plan`} used={seats.used} limit={seats.limit} />
            </CardBody>
          </Card>
        )}
        {isAdmin && <InviteCard />}
        <MembersCard />
        {isAdmin && <InvitationsCard />}
      </div>
    </>
  );
}
