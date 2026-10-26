"use client";

import { ExternalLink, KeyRound, MessageCircle, RotateCw, Send, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { CopyButton, Segmented, Switch, TokenInput } from "@/components/ui/controls";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, FormError, Input, Textarea } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { widgetApi } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/errors";
import type { WidgetPosition, WidgetSettings } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { usePermissions } from "@/lib/auth/roles";
import { contrastText, normalizeOrigin } from "@/lib/origins";
import { useMutation, useQuery } from "@/lib/query";

const HEX = /^#[0-9a-f]{6}$/i;

interface FormState {
  is_enabled: boolean;
  title: string;
  greeting: string;
  brand_color: string;
  position: WidgetPosition;
  allowed_origins: string[];
}

function toForm(settings: WidgetSettings): FormState {
  return {
    is_enabled: settings.is_enabled,
    title: settings.title,
    greeting: settings.greeting,
    brand_color: settings.brand_color,
    position: settings.position,
    allowed_origins: settings.allowed_origins,
  };
}

/** A static rendering of the widget in its current settings, so changes are visible before saving. */
function WidgetPreview({ form, organizationName }: { form: FormState; organizationName: string }) {
  const brand = HEX.test(form.brand_color) ? form.brand_color : "#4f46e5";
  const ink = contrastText(brand);
  const right = form.position === "right";
  return (
    <div
      className="relative h-[420px] overflow-hidden rounded-lg border border-border bg-[radial-gradient(circle_at_1px_1px,var(--border)_1px,transparent_0)] [background-size:16px_16px]"
      aria-label="Widget preview"
      role="img"
    >
      <div className={`absolute bottom-20 w-[280px] overflow-hidden rounded-xl border border-black/10 bg-white text-[#111827] shadow-xl ${right ? "right-4" : "left-4"}`}>
        <div className="flex items-center justify-between px-4 py-3" style={{ backgroundColor: brand, color: ink }}>
          <div>
            <p className="text-sm font-semibold">{form.title || "Help"}</p>
            <p className="text-xs opacity-80">{organizationName}</p>
          </div>
          <X className="size-4 opacity-80" aria-hidden />
        </div>
        <div className="space-y-2 bg-[#f7f8fb] p-3">
          <p className="max-w-[85%] rounded-xl rounded-tl-sm bg-white px-3 py-2 text-xs leading-relaxed shadow-sm">
            {form.greeting || "Hi! How can we help?"}
          </p>
          <p
            className="ml-auto max-w-[80%] rounded-xl rounded-br-sm px-3 py-2 text-xs"
            style={{ backgroundColor: brand, color: ink }}
          >
            How long do refunds take?
          </p>
          <p className="max-w-[85%] rounded-xl rounded-tl-sm bg-white px-3 py-2 text-xs leading-relaxed shadow-sm">
            Refunds reach your card within 5 business days{" "}
            <span className="rounded px-1 text-[10px] font-semibold" style={{ backgroundColor: `${brand}22`, color: "#111827" }}>
              1
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2 border-t border-black/10 px-3 py-2">
          <span className="flex-1 text-xs text-[#6b7280]">Ask a question</span>
          <span className="grid size-7 place-items-center rounded-full" style={{ backgroundColor: brand, color: ink }}>
            <Send className="size-3.5" aria-hidden />
          </span>
        </div>
      </div>
      <span
        className={`absolute bottom-4 grid size-12 place-items-center rounded-full shadow-lg ${right ? "right-4" : "left-4"}`}
        style={{ backgroundColor: brand, color: ink }}
      >
        <MessageCircle className="size-5" aria-hidden />
      </span>
      {!form.is_enabled && (
        <div className="absolute inset-0 grid place-items-center bg-background/70 backdrop-blur-[1px]">
          <Badge tone="warning">Widget disabled</Badge>
        </div>
      )}
    </div>
  );
}

function WidgetForm({ settings, onSaved }: { settings: WidgetSettings; onSaved: (settings: WidgetSettings) => void }) {
  const { organization } = useAuth();
  const { isAdmin } = usePermissions();
  const toast = useToast();
  const [form, setForm] = useState<FormState>(() => toForm(settings));
  const [confirmRotate, setConfirmRotate] = useState(false);
  const save = useMutation(() => widgetApi.update(form));
  const rotate = useMutation(() => widgetApi.rotateKey(), {
    onError: (error) => toast.error("Could not rotate the key", errorMessage(error)),
  });
  const serverErrors = save.error?.fieldErrors() ?? {};
  const dirty = JSON.stringify(form) !== JSON.stringify(toForm(settings));
  const colorValid = HEX.test(form.brand_color);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => ({ ...current, [key]: value }));
  const demoHref = `/widget-demo?site_key=${encodeURIComponent(settings.site_key)}`;

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-6">
        <Card>
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              const saved = await save.mutate();
              if (saved) {
                onSaved(saved);
                setForm(toForm(saved));
                toast.success("Widget saved", "Open pages pick up the new look on their next load.");
              }
            }}
          >
            <CardHeader title="Appearance and access" description="How the widget looks and which websites may load it." />
            <CardBody className="space-y-6">
              <FormError message={save.error && Object.keys(serverErrors).length === 0 ? save.error.message : null} />
              <Switch
                id="widget-enabled"
                label="Widget enabled"
                description="When off, the script renders nothing and the socket refuses connections."
                checked={form.is_enabled}
                disabled={!isAdmin}
                onChange={(checked) => set("is_enabled", checked)}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Title" error={serverErrors.title?.[0]} hint="Shown in the panel header.">
                  {(props) => (
                    <Input {...props} value={form.title} maxLength={60} disabled={!isAdmin} onChange={(event) => set("title", event.target.value)} />
                  )}
                </Field>
                <Field
                  label="Brand colour"
                  error={serverErrors.brand_color?.[0] ?? (colorValid ? null : "Use a hex colour such as #4f46e5.")}
                >
                  {(props) => (
                    <div className="flex gap-2">
                      <input
                        type="color"
                        aria-label="Pick brand colour"
                        value={colorValid ? form.brand_color : "#4f46e5"}
                        disabled={!isAdmin}
                        onChange={(event) => set("brand_color", event.target.value)}
                        className="h-9 w-12 shrink-0 cursor-pointer rounded-md border border-input bg-surface p-1"
                      />
                      <Input
                        {...props}
                        value={form.brand_color}
                        maxLength={7}
                        disabled={!isAdmin}
                        onChange={(event) => set("brand_color", event.target.value.trim())}
                        className="font-mono"
                      />
                    </div>
                  )}
                </Field>
              </div>
              <Field label="Greeting" error={serverErrors.greeting?.[0]} hint="The first message visitors see.">
                {(props) => (
                  <Textarea
                    {...props}
                    value={form.greeting}
                    maxLength={300}
                    disabled={!isAdmin}
                    onChange={(event) => set("greeting", event.target.value)}
                  />
                )}
              </Field>
              <div className="space-y-1.5">
                <span className="text-sm font-medium">Position</span>
                <div>
                  <Segmented
                    label="Widget position"
                    size="md"
                    value={form.position}
                    onChange={(value) => isAdmin && set("position", value)}
                    options={[
                      { value: "left", label: "Bottom left" },
                      { value: "right", label: "Bottom right" },
                    ]}
                  />
                </div>
              </div>
              <Field
                label="Allowed origins"
                error={serverErrors.allowed_origins?.[0]}
                hint="Exact origins that may embed the widget, such as https://shop.example.com. Press Enter after each. While the server runs in debug mode, localhost is always allowed."
              >
                {(props) => (
                  <TokenInput
                    id={props.id}
                    ariaDescribedBy={props["aria-describedby"]}
                    ariaInvalid={props["aria-invalid"]}
                    values={form.allowed_origins}
                    onChange={(values) => set("allowed_origins", values)}
                    disabled={!isAdmin}
                    max={20}
                    placeholder="https://shop.example.com"
                    normalize={(value) => {
                      const result = normalizeOrigin(value);
                      return "origin" in result ? result.origin : value.trim();
                    }}
                    validate={(value) => {
                      const result = normalizeOrigin(value);
                      return "error" in result ? result.error : null;
                    }}
                  />
                )}
              </Field>
            </CardBody>
            {isAdmin && (
              <CardFooter>
                {dirty && (
                  <Button variant="ghost" onClick={() => setForm(toForm(settings))}>
                    Discard changes
                  </Button>
                )}
                <Button type="submit" loading={save.pending} disabled={!dirty || !colorValid || !form.title.trim() || !form.greeting.trim()}>
                  Save widget
                </Button>
              </CardFooter>
            )}
          </form>
        </Card>

        <Card>
          <CardHeader
            title="Install on your website"
            description="Paste this before the closing </body> tag on every page that should show the widget."
            actions={<CopyButton value={settings.embed_snippet} label="Copy snippet" />}
          />
          <CardBody className="space-y-4">
            <pre className="whitespace-pre-wrap break-all rounded-lg bg-[#0b0f19] p-4 font-mono text-xs leading-relaxed text-[#e6e9f0]">
              <code>{settings.embed_snippet}</code>
            </pre>
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border px-4 py-3">
              <KeyRound className="size-4 text-muted-foreground" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">Site key</p>
                <p className="truncate font-mono text-xs text-muted-foreground">{settings.site_key}</p>
              </div>
              <CopyButton value={settings.site_key} size="icon-sm" variant="ghost" label="Copy site key" />
              {isAdmin && (
                <Button variant="outline" size="sm" onClick={() => setConfirmRotate(true)} icon={<RotateCw className="size-4" aria-hidden />}>
                  Rotate
                </Button>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              The site key is public by design: it ships in your page source. The allowed origins list and per visitor
              rate limits are what protect the widget.
            </p>
          </CardBody>
        </Card>
      </div>

      <div className="space-y-4 xl:sticky xl:top-8 xl:self-start">
        <WidgetPreview form={form} organizationName={organization?.name ?? ""} />
        <ButtonLink href={demoHref} target="_blank" variant="outline" className="w-full" icon={<ExternalLink className="size-4" aria-hidden />}>
          Try the live widget on a test page
        </ButtonLink>
      </div>

      <ConfirmDialog
        open={confirmRotate}
        onClose={() => setConfirmRotate(false)}
        title="Rotate the site key?"
        description="The current key stops working immediately, including open chats. Update the snippet on your website right after."
        confirmLabel="Rotate key"
        pending={rotate.pending}
        onConfirm={async () => {
          const updated = await rotate.mutate();
          setConfirmRotate(false);
          if (updated) {
            onSaved(updated);
            toast.success("New site key issued", "Copy the updated snippet to your website.");
          }
        }}
      />
    </div>
  );
}

export function WidgetSettingsView() {
  const widget = useQuery("widget", (signal) => widgetApi.config({ signal }), { tags: ["widget"] });
  return (
    <>
      <PageHeader
        title="Website widget"
        description="A chat bubble for your site that answers from your documents and hands off to your team."
      />
      {widget.isLoading ? (
        <LoadingBlock />
      ) : widget.error || !widget.data ? (
        <Card>
          <ErrorState message={widget.error?.message ?? "No widget settings found."} onRetry={widget.refetch} />
        </Card>
      ) : (
        <WidgetForm
          key={widget.data.updated_at + widget.data.site_key}
          settings={widget.data}
          onSaved={(settings) => widget.setData(() => settings)}
        />
      )}
    </>
  );
}
