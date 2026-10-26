import { Compass } from "lucide-react";

import { Logo } from "@/components/brand";
import { ButtonLink } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col px-4 py-6 sm:px-8">
      <Logo />
      <main className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center text-center">
        <div className="mb-5 grid size-12 place-items-center rounded-xl border border-border bg-surface text-muted-foreground">
          <Compass className="size-5" aria-hidden />
        </div>
        <p className="text-sm font-medium text-primary">404</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">This page does not exist</h1>
        <p className="mt-2 text-muted-foreground">The link may be old or mistyped.</p>
        <div className="mt-6 flex gap-2">
          <ButtonLink href="/app">Go to the dashboard</ButtonLink>
          <ButtonLink href="/" variant="outline">
            Home
          </ButtonLink>
        </div>
      </main>
    </div>
  );
}
