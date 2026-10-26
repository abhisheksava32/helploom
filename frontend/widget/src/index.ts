/**
 * Entry point of public/widget.js. Customers embed:
 *
 *   <script src="https://app.example.com/widget.js" data-site-key="hlp_pk_..."
 *     data-api-url="https://api.example.com" data-ws-url="wss://api.example.com" defer></script>
 *
 * Optional attributes: data-theme="light|dark|auto", data-position="left|right".
 * window.Helploom exposes open(), close() and destroy() for single page apps.
 */

import { fetchPublicConfig, HelploomWidget, type WidgetOptions, type WidgetTheme } from "./widget";

// window.Helploom is declared in src/types/global.d.ts, shared with the dashboard.

function findScript(): HTMLScriptElement | null {
  const current = document.currentScript;
  if (current instanceof HTMLScriptElement && current.dataset.siteKey) return current;
  return document.querySelector<HTMLScriptElement>("script[data-site-key][src*='widget']");
}

function optionsFrom(script: HTMLScriptElement): WidgetOptions | null {
  const siteKey = script.dataset.siteKey?.trim();
  if (!siteKey) {
    console.warn("[Helploom] The widget script needs a data-site-key attribute.");
    return null;
  }
  const scriptOrigin = new URL(script.src, window.location.href).origin;
  const theme = script.dataset.theme;
  const position = script.dataset.position;
  return {
    siteKey,
    apiUrl: script.dataset.apiUrl?.trim() || scriptOrigin,
    wsUrl: script.dataset.wsUrl?.trim() || null,
    theme: theme === "dark" || theme === "auto" ? (theme as WidgetTheme) : "light",
    position: position === "left" || position === "right" ? position : null,
  };
}

async function boot(script: HTMLScriptElement): Promise<void> {
  const options = optionsFrom(script);
  if (!options) return;
  const config = await fetchPublicConfig(options);
  // A page (or a single page app) may remove the tag while the config loads, or add a
  // second copy: mount only for a tag still in the document and only once.
  if (!config || !script.isConnected || window.Helploom) return;
  const widget = new HelploomWidget(options, config);
  window.Helploom = {
    open: () => widget.open(),
    close: () => widget.close(),
    destroy: () => {
      widget.destroy();
      delete window.Helploom;
    },
  };
}

// currentScript is only set while the script first runs, so read it before awaiting.
const script = findScript();
if (script && !window.Helploom) {
  const start = () => void boot(script);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}
