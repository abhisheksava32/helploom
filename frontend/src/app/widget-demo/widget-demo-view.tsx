"use client";

import { ArrowLeft, Info, Package, RotateCcw, Truck } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Logo } from "@/components/brand";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { widgetApi } from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth/auth-context";
import { useQuery } from "@/lib/query";
import { useEmbeddedWidget } from "@/lib/widget-embed";

const PRODUCTS = [
  { name: "Trailhead 28L pack", price: "$129", tone: "from-emerald-200 to-teal-300" },
  { name: "Ridgeline rain shell", price: "$189", tone: "from-sky-200 to-indigo-300" },
  { name: "Basecamp wool beanie", price: "$34", tone: "from-amber-200 to-orange-300" },
];

export function WidgetDemoView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { status } = useAuth();
  const siteKey = params.get("site_key");
  const [draft, setDraft] = useState(siteKey ?? "");
  const [loadedKey, setLoadedKey] = useState(siteKey);
  // Show the key that is loaded, also when it came from "Use my workspace key".
  if (siteKey !== loadedKey) {
    setLoadedKey(siteKey);
    setDraft(siteKey ?? "");
  }
  const own = useQuery(status === "authenticated" && !siteKey ? "widget" : null, (signal) => widgetApi.config({ signal }));

  useEmbeddedWidget(siteKey);

  const load = (key: string) => {
    const trimmed = key.trim();
    router.replace(trimmed ? `${pathname}?site_key=${encodeURIComponent(trimmed)}` : pathname);
  };
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    load(draft);
  };

  return (
    <div className="min-h-dvh bg-background">
      <div className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <Logo />
          <span className="rounded-md bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">Widget test page</span>
          <ButtonLink href="/app/settings/widget" variant="ghost" size="sm" className="ml-auto" icon={<ArrowLeft className="size-4" aria-hidden />}>
            Widget settings
          </ButtonLink>
        </div>
        <div className="mx-auto max-w-5xl px-4 pb-4 sm:px-6">
          <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-2">
            <label htmlFor="site-key" className="text-sm font-medium">
              Site key
            </label>
            <Input
              id="site-key"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="hlp_pk_..."
              className="max-w-md flex-1 font-mono"
            />
            <Button type="submit" disabled={!draft.trim() || draft.trim() === siteKey}>
              Load widget
            </Button>
            {siteKey && (
              <Button variant="ghost" onClick={() => load("")} icon={<RotateCcw className="size-4" aria-hidden />}>
                Unload
              </Button>
            )}
            {own.data && (
              <Button variant="outline" onClick={() => load(own.data?.site_key ?? "")}>
                Use my workspace key
              </Button>
            )}
          </form>
          <p className="mt-2 flex items-start gap-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            This page loads /widget.js through a script tag, exactly like a customer site. While the server runs in debug
            mode it accepts localhost origins; in production, add this page&apos;s origin to the allowed list first.
          </p>
        </div>
      </div>

      {/* A stand-in storefront so the bubble has a realistic page to sit on. */}
      <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
        <p className="text-sm font-medium text-primary">Sample storefront</p>
        <h1 className="mt-2 max-w-xl text-3xl font-semibold tracking-tight sm:text-4xl">Gear for long days outside.</h1>
        <p className="mt-3 max-w-xl text-muted-foreground">
          Ask the help bubble in the corner about shipping, returns or your order. Answers come from the documents in the
          workspace that owns the site key.
        </p>
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {PRODUCTS.map((product) => (
            <div key={product.name} className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
              <div className={`aspect-[4/3] bg-gradient-to-br ${product.tone}`} aria-hidden />
              <div className="flex items-center justify-between p-4">
                <p className="text-sm font-medium">{product.name}</p>
                <p className="text-sm text-muted-foreground">{product.price}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-10 grid gap-4 rounded-xl border border-border bg-surface p-6 sm:grid-cols-3">
          {[
            { icon: Truck, title: "Free shipping over $75" },
            { icon: RotateCcw, title: "30 day returns" },
            { icon: Package, title: "Ships in 1 to 2 days" },
          ].map(({ icon: Icon, title }) => (
            <p key={title} className="flex items-center gap-2 text-sm">
              <Icon className="size-4 text-primary" aria-hidden />
              {title}
            </p>
          ))}
        </div>
        {!siteKey && (
          <p className="mt-10 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            Enter a site key above to load the widget.
          </p>
        )}
      </main>
    </div>
  );
}
