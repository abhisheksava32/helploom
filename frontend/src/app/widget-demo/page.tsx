import type { Metadata } from "next";
import { Suspense } from "react";

import { WidgetDemoView } from "./widget-demo-view";
import { LoadingBlock } from "@/components/ui/states";

export const metadata: Metadata = { title: "Widget test page", robots: { index: false, follow: false } };

export default function WidgetDemoPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <WidgetDemoView />
    </Suspense>
  );
}
