"use client";

import { useEffect } from "react";

import { config } from "@/lib/config";

/**
 * Loads public/widget.js exactly the way a customer's snippet does (a script tag
 * with data attributes), and removes it again on unmount, so the test page and the
 * landing page exercise the real embed path.
 */
export function useEmbeddedWidget(siteKey: string | null, options: { theme?: "light" | "dark" | "auto" } = {}) {
  const theme = options.theme ?? "light";
  useEffect(() => {
    if (!siteKey) return;
    const script = document.createElement("script");
    script.src = "/widget.js";
    script.defer = true;
    script.dataset.siteKey = siteKey;
    script.dataset.apiUrl = config.apiUrl;
    script.dataset.wsUrl = config.wsUrl;
    script.dataset.theme = theme;
    document.body.appendChild(script);
    return () => {
      window.Helploom?.destroy();
      script.remove();
    };
  }, [siteKey, theme]);
}
