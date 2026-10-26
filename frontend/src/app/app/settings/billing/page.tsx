import type { Metadata } from "next";
import { Suspense } from "react";

import { BillingView } from "./billing-view";
import { LoadingBlock } from "@/components/ui/states";

export const metadata: Metadata = { title: "Billing" };
// Rendered in the browser after sign in; see the instant note in app/app/layout.tsx.
export const instant = false;

export default function BillingPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <BillingView />
    </Suspense>
  );
}
