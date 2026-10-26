"use client";

import { CircleAlert } from "lucide-react";

import { Button, ButtonLink } from "@/components/ui/button";

/** Last line of defence for render errors: offer a retry instead of a blank page. */
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <div role="alert" className="max-w-md text-center">
        <div className="mx-auto mb-5 grid size-12 place-items-center rounded-xl bg-danger-soft text-danger">
          <CircleAlert className="size-5" aria-hidden />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Something went wrong</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The page hit an unexpected error. Try again, and if it keeps happening, reload the page.
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <Button onClick={reset}>Try again</Button>
          <ButtonLink href="/app" variant="outline">
            Dashboard
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}
