import type { Metadata } from "next";

import { TicketsView } from "./tickets-view";

export const metadata: Metadata = { title: "Tickets" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function TicketsPage() {
  return <TicketsView />;
}
