"use client";

import { CheckCircle2, CircleSlash, RefreshCw, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { ProviderBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Field, FormError, Input } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, SkeletonRows } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { accountApi, assistantApi, organizationApi } from "@/lib/api/endpoints";
import type { AssistantTone } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { usePermissions } from "@/lib/auth/roles";
import { cn } from "@/lib/cn";
import { pluralize, providerLabel } from "@/lib/format";
import { invalidate, useMutation, useQuery } from "@/lib/query";

const TONES: { value: AssistantTone; label: string; example: string }[] = [
  {
    value: "friendly",
    label: "Friendly",
    example: "Happy to help! You can return any item within 30 days of delivery [1].",
  },
  {
    value: "professional",
    label: "Professional",
    example: "Items may be returned within 30 days of delivery [1].",
  },
  { value: "concise", label: "Concise", example: "Returns: within 30 days of delivery [1]." },
];

function WorkspaceCard() {
  const { organization, reload } = useAuth();
  const { isAdmin } = usePermissions();
  const toast = useToast();
  const [name, setName] = useState(organization?.name ?? "");
  const [tone, setTone] = useState<AssistantTone>(organization?.assistant_tone ?? "friendly");
  const save = useMutation(() => organizationApi.update({ name: name.trim(), assistant_tone: tone }));
  const dirty = name.trim() !== organization?.name || tone !== organization?.assistant_tone;

  return (
    <Card>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (await save.mutate()) {
            await reload();
            toast.success("Workspace saved", "The assistant uses the new name and tone from the next question.");
          }
        }}
      >
        <CardHeader
          title="Workspace"
          description="The business name and tone go into the assistant's system prompt."
        />
        <CardBody className="space-y-6">
          <FormError message={save.error && !save.error.fieldErrors().name ? save.error.message : null} />
          <Field label="Business name" error={save.error?.fieldErrors().name?.[0]} className="max-w-md">
            {(props) => (
              <Input
                {...props}
                value={name}
                minLength={2}
                maxLength={150}
                disabled={!isAdmin}
                onChange={(event) => setName(event.target.value)}
              />
            )}
          </Field>
          <fieldset className="space-y-2" disabled={!isAdmin}>
            <legend className="text-sm font-medium">Assistant tone</legend>
            <div className="grid gap-3 md:grid-cols-3">
              {TONES.map((option) => (
                <label
                  key={option.value}
                  className={cn(
                    "cursor-pointer rounded-lg border p-4 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                    tone === option.value ? "border-primary bg-accent/60" : "border-border hover:bg-surface-muted/60",
                    !isAdmin && "cursor-not-allowed opacity-70",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="tone"
                      value={option.value}
                      checked={tone === option.value}
                      onChange={() => setTone(option.value)}
                      className="accent-primary"
                    />
                    <span className="text-sm font-medium">{option.label}</span>
                  </span>
                  <span className="mt-2 block text-sm italic text-muted-foreground">&ldquo;{option.example}&rdquo;</span>
                </label>
              ))}
            </div>
          </fieldset>
        </CardBody>
        {isAdmin ? (
          <CardFooter>
            <Button type="submit" loading={save.pending} disabled={!dirty || name.trim().length < 2}>
              Save workspace
            </Button>
          </CardFooter>
        ) : (
          <CardFooter className="justify-start text-sm text-muted-foreground">
            Only admins and owners can change workspace settings.
          </CardFooter>
        )}
      </form>
    </Card>
  );
}

function ProvidersCard() {
  const providers = useQuery("providers", (signal) => assistantApi.providers({ signal }), { tags: ["providers"] });
  const data = providers.data;
  return (
    <Card>
      <CardHeader
        title="Answer engine"
        description="Which model answers and how passages are embedded. Configured on the server with LLM_PROVIDER and EMBEDDER."
        actions={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Check providers again"
            onClick={() => invalidate("providers")}
            disabled={providers.isFetching}
          >
            <RefreshCw className={cn("size-4", providers.isFetching && "animate-spin")} aria-hidden />
          </Button>
        }
      />
      {providers.isLoading ? (
        <SkeletonRows rows={3} />
      ) : providers.error && !data ? (
        <ErrorState message={providers.error.message} onRetry={providers.refetch} className="py-8" />
      ) : data ? (
        <CardBody className="space-y-5">
          <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface-muted/60 px-4 py-3 text-sm">
            <span className="text-muted-foreground">Mode</span>
            <Badge tone="primary">{data.configured === "auto" ? "Automatic" : providerLabel(data.configured)}</Badge>
            <span className="text-muted-foreground">Next answer from</span>
            <ProviderBadge provider={data.active.name} model={data.active.model} />
          </div>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {data.providers.map((provider) => (
              <li key={provider.name} className="flex items-start gap-3 px-4 py-3">
                {provider.available ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="Available" />
                ) : (
                  <CircleSlash className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="Unavailable" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                    {providerLabel(provider.name)}
                    <span className="font-mono text-xs font-normal text-muted-foreground">{provider.model}</span>
                    {provider.name === data.active.name && <Badge tone="success">Active</Badge>}
                  </p>
                  <p className="text-sm text-muted-foreground">{provider.detail}</p>
                </div>
              </li>
            ))}
          </ul>
          <dl className="grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Embedder</dt>
              <dd className="font-mono text-xs">{data.embedder.active}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Dimensions</dt>
              <dd>{data.embedder.dimensions}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Embedder mode</dt>
              <dd>{data.embedder.configured === "auto" ? "Automatic" : data.embedder.configured}</dd>
            </div>
          </dl>
          {data.embedder.stale_documents > 0 && (
            <p className="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                {pluralize(data.embedder.stale_documents, "document")} {data.embedder.stale_documents === 1 ? "was" : "were"}{" "}
                embedded with another model and {data.embedder.stale_documents === 1 ? "is" : "are"} skipped by search.
                Run <code className="font-mono">uv run python manage.py reembed</code> on the server, or re-index them.
              </span>
            </p>
          )}
        </CardBody>
      ) : null}
    </Card>
  );
}

function ProfileCard() {
  const { user, reload } = useAuth();
  const toast = useToast();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const save = useMutation(() => accountApi.updateProfile({ full_name: fullName.trim() }));

  return (
    <Card id="profile" className="scroll-mt-8">
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (await save.mutate()) {
            await reload();
            toast.success("Profile saved");
          }
        }}
      >
        <CardHeader title="Your profile" description="Shown to teammates on tickets and conversations." />
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name" error={save.error?.fieldErrors().full_name?.[0]}>
            {(props) => (
              <Input {...props} autoComplete="name" value={fullName} maxLength={150} onChange={(event) => setFullName(event.target.value)} />
            )}
          </Field>
          <Field label="Email" hint="Your login. Contact support to change it.">
            {(props) => <Input {...props} value={user?.email ?? ""} readOnly disabled />}
          </Field>
        </CardBody>
        <CardFooter>
          <Button type="submit" loading={save.pending} disabled={fullName.trim() === user?.full_name}>
            Save profile
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

function PasswordCard() {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  // The endpoint answers 204, so the action returns true to tell success from failure.
  const change = useMutation(async () => {
    await accountApi.changePassword({ current_password: current, new_password: next });
    return true;
  });
  const errors = change.error?.fieldErrors() ?? {};

  return (
    <Card>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (await change.mutate()) {
            setCurrent("");
            setNext("");
            toast.success("Password changed");
          }
        }}
      >
        <CardHeader
          title="Password"
          description="At least 10 characters. Other sessions stay signed in until their access token expires."
        />
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <Field label="Current password" error={errors.current_password?.[0]}>
            {(props) => (
              <Input
                {...props}
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
              />
            )}
          </Field>
          <Field label="New password" error={errors.new_password?.[0]}>
            {(props) => (
              <Input
                {...props}
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
              />
            )}
          </Field>
          {change.error && !errors.current_password && !errors.new_password && (
            <div className="sm:col-span-2">
              <FormError message={change.error.message} />
            </div>
          )}
        </CardBody>
        <CardFooter>
          <Button type="submit" loading={change.pending} disabled={!current || next.length < 10}>
            Change password
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

export function SettingsView() {
  return (
    <>
      <PageHeader title="Settings" description="Workspace, assistant and account settings." />
      <div className="space-y-6">
        <WorkspaceCard />
        <ProvidersCard />
        <ProfileCard />
        <PasswordCard />
      </div>
    </>
  );
}
