import type { Metadata } from "next";

import { PlaygroundView } from "./playground-view";

export const metadata: Metadata = { title: "Playground" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function PlaygroundPage() {
  return <PlaygroundView />;
}
