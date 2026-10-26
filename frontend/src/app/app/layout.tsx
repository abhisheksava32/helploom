import type { Metadata } from "next";
import { Suspense } from "react";

import { AppShell, AppSplash } from "@/components/app-shell/app-shell";

export const metadata: Metadata = {
  title: "Dashboard",
  robots: { index: false, follow: false },
};

// The dashboard renders in the browser: the access token lives in memory only, so
// the server has nothing to render it with, and its static shell is the splash.
// Instant navigation validation would only report that pages are not prerendered,
// which is by design here, so these routes opt out of it.
export const instant = false;

// Suspense lets pages with dynamic params prerender the splash while the client
// resolves the URL.
export default function DashboardLayout({ children }: LayoutProps<"/app">) {
  return (
    <Suspense fallback={<AppSplash />}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
