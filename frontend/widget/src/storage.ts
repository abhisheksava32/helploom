/**
 * localStorage that never throws. Storage can be blocked (private windows, strict
 * cookie settings, sandboxed iframes); the widget then works for the current page
 * and simply does not remember the visitor.
 */

export function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Not persisted; nothing else to do.
  }
}

/** 24 URL safe random characters: matches the server's visitor_id rule ([A-Za-z0-9_-]{16,64}). */
export function randomVisitorId(): string {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return `v_${btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;
}
