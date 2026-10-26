import type { Metadata } from "next";

import { WidgetSettingsView } from "./widget-settings-view";

export const metadata: Metadata = { title: "Website widget" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function WidgetSettingsPage() {
  return <WidgetSettingsView />;
}
