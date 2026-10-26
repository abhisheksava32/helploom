import type { Metadata } from "next";

import { TeamView } from "./team-view";

export const metadata: Metadata = { title: "Team" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function TeamPage() {
  return <TeamView />;
}
