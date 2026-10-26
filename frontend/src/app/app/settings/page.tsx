import type { Metadata } from "next";

import { SettingsView } from "./settings-view";

export const metadata: Metadata = { title: "Settings" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function SettingsPage() {
  return <SettingsView />;
}
