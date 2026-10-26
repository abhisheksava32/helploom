import type { Metadata } from "next";
import { Suspense } from "react";

import { ConversationDetailView } from "./conversation-detail";
import { LoadingBlock } from "@/components/ui/states";

export const metadata: Metadata = { title: "Conversation" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function ConversationPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <ConversationDetailView />
    </Suspense>
  );
}
