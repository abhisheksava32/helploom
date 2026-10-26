/**
 * Styles for the widget's shadow root. The shadow boundary keeps the host page's
 * CSS out and these rules in; ":host { all: initial }" resets inherited properties
 * such as font size and line height that would otherwise leak through.
 */
export const STYLES = `
:host {
  all: initial;
  --hl-brand: #4f46e5;
  --hl-on-brand: #ffffff;
  --hl-bg: #ffffff;
  --hl-surface: #f7f8fb;
  --hl-text: #111827;
  --hl-muted: #5b6474;
  --hl-border: rgba(17, 24, 39, 0.1);
  --hl-danger: #b91c1c;
  --hl-danger-soft: #fdecec;
  --hl-chip: rgba(79, 70, 229, 0.12);
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 2147483000;
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: var(--hl-text);
}
:host([data-position="left"]) { right: auto; left: 20px; }
:host([data-theme="dark"]) {
  --hl-bg: #121826; --hl-surface: #0b0f19; --hl-text: #e6e9f0; --hl-muted: #9aa3b5;
  --hl-border: rgba(255, 255, 255, 0.12); --hl-danger: #f87171; --hl-danger-soft: #311a1d;
}
@media (prefers-color-scheme: dark) {
  :host([data-theme="auto"]) {
    --hl-bg: #121826; --hl-surface: #0b0f19; --hl-text: #e6e9f0; --hl-muted: #9aa3b5;
    --hl-border: rgba(255, 255, 255, 0.12); --hl-danger: #f87171; --hl-danger-soft: #311a1d;
  }
}
*, *::before, *::after { box-sizing: border-box; }
button, textarea, input { font: inherit; color: inherit; }
button { cursor: pointer; }
:focus-visible { outline: 2px solid var(--hl-brand); outline-offset: 2px; }
[hidden] { display: none !important; }
.launcher {
  position: relative; display: grid; place-items: center; width: 56px; height: 56px; border: 0;
  border-radius: 50%; background: var(--hl-brand); color: var(--hl-on-brand);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25); transition: transform 160ms ease;
}
.launcher:hover { transform: translateY(-2px); }
.badge {
  position: absolute; top: 2px; right: 2px; width: 12px; height: 12px; border-radius: 50%;
  background: #ef4444; border: 2px solid var(--hl-bg);
}
.panel {
  position: absolute; bottom: 72px; right: 0; display: flex; flex-direction: column;
  width: 380px; height: min(620px, calc(100vh - 110px)); overflow: hidden;
  border: 1px solid var(--hl-border); border-radius: 16px; background: var(--hl-bg);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.28); animation: hl-in 160ms ease-out;
}
:host([data-position="left"]) .panel { right: auto; left: 0; }
@keyframes hl-in { from { opacity: 0; transform: translateY(8px) scale(0.98); } }
@media (prefers-reduced-motion: reduce) { .panel, .launcher { animation: none; transition: none; } }
@media (max-width: 480px) {
  .panel { position: fixed; inset: 0; width: 100%; height: 100%; border-radius: 0; bottom: 0; }
  /* The full screen panel has its own close button; the bubble would cover the send button. */
  :host([data-open]) .launcher { display: none; }
}
.header {
  display: flex; align-items: center; gap: 12px; padding: 14px 16px;
  background: var(--hl-brand); color: var(--hl-on-brand);
}
.header-text { flex: 1; min-width: 0; }
.title { margin: 0; font-size: 15px; font-weight: 600; }
.subtitle { margin: 0; font-size: 12px; opacity: 0.85; }
.icon-button {
  display: grid; place-items: center; width: 32px; height: 32px; border: 0; border-radius: 8px;
  background: transparent; color: inherit;
}
.icon-button:hover { background: rgba(255, 255, 255, 0.16); }
.notice { margin: 0; padding: 8px 16px; font-size: 12px; background: var(--hl-surface); color: var(--hl-muted); border-bottom: 1px solid var(--hl-border); }
.notice.error { background: var(--hl-danger-soft); color: var(--hl-danger); }
.messages {
  flex: 1; margin: 0; padding: 16px; overflow-y: auto; list-style: none; background: var(--hl-surface);
  display: flex; flex-direction: column; gap: 12px;
}
.message { display: flex; flex-direction: column; max-width: 88%; }
.message.user { align-self: flex-end; align-items: flex-end; }
.bubble { padding: 9px 13px; border-radius: 14px; white-space: pre-wrap; overflow-wrap: anywhere; }
.assistant .bubble { background: var(--hl-bg); border: 1px solid var(--hl-border); border-top-left-radius: 4px; }
.user .bubble { background: var(--hl-brand); color: var(--hl-on-brand); border-bottom-right-radius: 4px; }
.bubble.failed { border-color: var(--hl-danger); }
.error-text { margin: 6px 0 0; font-size: 12px; color: var(--hl-danger); }
.cite {
  display: inline-grid; place-items: center; min-width: 16px; height: 16px; margin: 0 2px; padding: 0 4px;
  border: 0; border-radius: 4px; background: var(--hl-chip); font-size: 10px; font-weight: 700;
  vertical-align: 2px; color: var(--hl-text);
}
.cite[aria-expanded="true"] { background: var(--hl-brand); color: var(--hl-on-brand); }
.sources { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.source {
  max-width: 100%; padding: 3px 8px; border: 1px solid var(--hl-border); border-radius: 999px;
  background: var(--hl-bg); font-size: 12px; color: var(--hl-muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.source[aria-expanded="true"] { border-color: var(--hl-brand); color: var(--hl-text); }
.snippet {
  margin-top: 8px; padding: 10px 12px; border-left: 3px solid var(--hl-brand); border-radius: 6px;
  background: var(--hl-bg); font-size: 13px; color: var(--hl-text);
}
.snippet-title { margin: 0 0 4px; font-size: 12px; font-weight: 600; }
.snippet-text { margin: 0; color: var(--hl-muted); }
.actions { display: flex; align-items: center; gap: 4px; margin-top: 6px; }
.action {
  display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; border: 1px solid transparent;
  border-radius: 8px; background: transparent; font-size: 12px; color: var(--hl-muted);
}
.action:hover { background: var(--hl-bg); border-color: var(--hl-border); color: var(--hl-text); }
.action[aria-pressed="true"] { color: var(--hl-brand); background: var(--hl-chip); }
.action.primary { border-color: var(--hl-border); background: var(--hl-bg); color: var(--hl-text); }
.dots { display: inline-flex; gap: 4px; padding: 4px 0; }
.dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--hl-muted); animation: hl-blink 1.2s infinite; }
.dots span:nth-child(2) { animation-delay: 0.15s; }
.dots span:nth-child(3) { animation-delay: 0.3s; }
@keyframes hl-blink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }
.composer { display: flex; align-items: flex-end; gap: 8px; padding: 10px 12px; border-top: 1px solid var(--hl-border); background: var(--hl-bg); }
.composer textarea {
  flex: 1; min-height: 38px; max-height: 120px; padding: 8px 10px; resize: none; border: 1px solid var(--hl-border);
  border-radius: 10px; background: var(--hl-bg); outline: none; field-sizing: content;
}
.composer textarea:focus { border-color: var(--hl-brand); }
.send {
  display: grid; place-items: center; width: 38px; height: 38px; flex-shrink: 0; border: 0; border-radius: 10px;
  background: var(--hl-brand); color: var(--hl-on-brand);
}
.send:disabled { opacity: 0.45; cursor: not-allowed; }
.footer {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 14px 10px;
  background: var(--hl-bg); font-size: 11px; color: var(--hl-muted);
}
.link { padding: 0; border: 0; background: none; color: var(--hl-muted); text-decoration: underline; font-size: 12px; }
.link:hover { color: var(--hl-text); }
.link:disabled { opacity: 0.5; cursor: not-allowed; text-decoration: none; }
.handoff { flex: 1; overflow-y: auto; padding: 16px; background: var(--hl-surface); }
.handoff h3 { margin: 0 0 4px; font-size: 15px; }
.handoff p { margin: 0 0 12px; color: var(--hl-muted); font-size: 13px; }
.field { display: block; margin-bottom: 12px; font-size: 13px; font-weight: 500; }
.field input, .field textarea {
  display: block; width: 100%; margin-top: 4px; padding: 8px 10px; border: 1px solid var(--hl-border);
  border-radius: 8px; background: var(--hl-bg); font-weight: 400;
}
.field textarea { min-height: 80px; resize: vertical; }
.row { display: flex; gap: 8px; justify-content: flex-end; }
.button {
  padding: 8px 14px; border: 1px solid var(--hl-border); border-radius: 8px; background: var(--hl-bg); font-weight: 500;
}
.button.primary { border-color: transparent; background: var(--hl-brand); color: var(--hl-on-brand); }
.button:disabled { opacity: 0.6; cursor: not-allowed; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); border: 0; }
`;
