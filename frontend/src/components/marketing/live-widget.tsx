"use client";

import { config } from "@/lib/config";
import { useEmbeddedWidget } from "@/lib/widget-embed";

/** Loads the real widget on the landing page when a demo workspace's site key is configured. */
export function LiveWidget() {
  useEmbeddedWidget(config.demoSiteKey);
  return null;
}

export const liveWidgetEnabled = config.demoSiteKey !== null;
