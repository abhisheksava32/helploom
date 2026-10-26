/**
 * Only same origin paths are accepted as post login destinations, so a crafted
 * ?next=https://evil.example link cannot turn the login page into an open redirect.
 */
export function safeNextPath(next: string | null | undefined, fallback = "/app"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  return next;
}
