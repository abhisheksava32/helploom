import type { Metadata } from "next";
import { Suspense } from "react";

import { DocumentsView } from "./documents-view";
import { LoadingBlock } from "@/components/ui/states";

export const metadata: Metadata = { title: "Documents" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function DocumentsPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <DocumentsView />
    </Suspense>
  );
}
