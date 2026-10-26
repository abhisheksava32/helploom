import type { Metadata } from "next";

import { ReportsView } from "./reports-view";

export const metadata: Metadata = { title: "Reports" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function ReportsPage() {
  return <ReportsView />;
}
