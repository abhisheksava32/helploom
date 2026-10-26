"use client";

import { CircleAlert, MailCheck } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Field, FormError, Input } from "@/components/ui/field";
import { LoadingBlock } from "@/components/ui/states";
import { accountApi } from "@/lib/api/endpoints";
import { errorMessage, fieldErrorsOf } from "@/lib/api/errors";
import type { InvitationPreview } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { ROLE_LABELS } from "@/lib/auth/roles";
import { formatDate } from "@/lib/format";
import { useQuery } from "@/lib/query";

function Notice({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div role="alert" className="rounded-lg border border-border bg-surface p-5">
      <div className="flex items-start gap-3">
        <CircleAlert className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden />
        <div className="space-y-2 text-sm">
          <p className="font-medium">{title}</p>
          <div className="text-muted-foreground">{children}</div>
        </div>
      </div>
    </div>
  );
}

const STATUS_COPY: Record<Exclude<InvitationPreview["status"], "pending">, string> = {
  accepted: "This invitation has already been accepted. Log in to open the workspace.",
  revoked: "This invitation was withdrawn. Ask your teammate to send a new one.",
  expired: "This invitation has expired. Ask your teammate to resend it.",
};

export function InvitationAccept() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { status, user, acceptInvitation, switchOrganization, logout } = useAuth();
  const invitation = useQuery(`invitation:${token}`, (signal) => accountApi.invitation(token, { signal }));
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  if (invitation.isLoading || status === "loading") return <LoadingBlock label="Checking your invitation" />;
  if (invitation.error) {
    return (
      <Notice title="This invitation link is not valid">
        {invitation.error.code === "not_found"
          ? "The link may be incomplete. Copy it again from the email, or ask for a new invitation."
          : errorMessage(invitation.error)}
      </Notice>
    );
  }
  const preview = invitation.data;
  if (!preview) return null;

  const accept = async (body?: { full_name: string; password: string }) => {
    setPending(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await acceptInvitation(token, body);
      switchOrganization(preview.organization.id);
      router.replace("/app");
    } catch (error) {
      setFieldErrors(fieldErrorsOf(error));
      setFormError(errorMessage(error));
      setPending(false);
    }
  };

  const onCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (password.length < 10) {
      setFieldErrors({ password: "Use at least 10 characters." });
      return;
    }
    void accept({ full_name: fullName.trim(), password });
  };

  const summary = (
    <div className="mb-6 rounded-lg border border-border bg-surface p-5">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
          <MailCheck className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 space-y-1 text-sm">
          <p>
            <span className="font-medium">{preview.invited_by_name || "A teammate"}</span> invited{" "}
            <span className="font-medium">{preview.email}</span> to{" "}
            <span className="font-medium">{preview.organization.name}</span>.
          </p>
          <p className="flex flex-wrap items-center gap-2 text-muted-foreground">
            <Badge tone="primary">{ROLE_LABELS[preview.role]}</Badge>
            <span>Expires {formatDate(preview.expires_at)}</span>
          </p>
        </div>
      </div>
    </div>
  );

  if (preview.status !== "pending") {
    return (
      <>
        {summary}
        <Notice title={`Invitation ${preview.status}`}>
          <p>{STATUS_COPY[preview.status]}</p>
          {preview.status === "accepted" && (
            <ButtonLink href="/login" variant="outline" size="sm" className="mt-3">
              Log in
            </ButtonLink>
          )}
        </Notice>
      </>
    );
  }

  if (status === "authenticated" && user) {
    const sameEmail = user.email.toLowerCase() === preview.email.toLowerCase();
    return (
      <>
        {summary}
        <FormError message={formError} />
        {sameEmail ? (
          <Button size="lg" className="mt-4 w-full" loading={pending} onClick={() => void accept()}>
            Join {preview.organization.name}
          </Button>
        ) : (
          <Notice title="Signed in with a different email">
            <p>
              You are signed in as {user.email}, but this invitation is for {preview.email}. Log out and open
              the link again with the invited account.
            </p>
            <Button variant="outline" size="sm" className="mt-3" onClick={() => void logout()}>
              Log out
            </Button>
          </Notice>
        )}
      </>
    );
  }

  if (preview.account_exists) {
    return (
      <>
        {summary}
        <p className="mb-4 text-sm text-muted-foreground">
          {preview.email} already has a Helploom account. Log in with it to accept the invitation.
        </p>
        <ButtonLink
          href={`/login?next=${encodeURIComponent(`/invite/${token}`)}`}
          size="lg"
          className="w-full"
        >
          Log in to accept
        </ButtonLink>
      </>
    );
  }

  return (
    <>
      {summary}
      <form onSubmit={onCreate} className="space-y-5" noValidate>
        <FormError message={formError} />
        <Field label="Email">
          {(props) => <Input {...props} value={preview.email} readOnly disabled />}
        </Field>
        <Field label="Your name" error={fieldErrors.full_name} optional>
          {(props) => (
            <Input {...props} autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
          )}
        </Field>
        <Field label="Choose a password" error={fieldErrors.password} hint="At least 10 characters.">
          {(props) => (
            <Input
              {...props}
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          )}
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={pending}>
          Create account and join
        </Button>
      </form>
    </>
  );
}
