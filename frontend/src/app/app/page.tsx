import type { Metadata } from "next";

import { OverviewView } from "./overview-view";

export const metadata: Metadata = { title: "Overview" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function OverviewPage() {
  return <OverviewView />;
}
