import type { Metadata } from "next";
import { Suspense } from "react";

import { ConversationsView } from "./conversations-view";
import { LoadingBlock } from "@/components/ui/states";

export const metadata: Metadata = { title: "Conversations" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function ConversationsPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <ConversationsView />
    </Suspense>
  );
}
