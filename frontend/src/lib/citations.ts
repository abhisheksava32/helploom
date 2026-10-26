/**
 * Splits answer text into plain text and citation markers ("[1]", "[1][3]",
 * "[1, 2]"), the format every provider emits (docs/DESIGN.md, section 9).
 *
 * Pure and dependency free: the dashboard and the widget bundle both use it, and
 * both render the parts as text nodes, never as HTML.
 */

export type AnswerPart = { kind: "text"; text: string } | { kind: "cite"; marker: number };

const MARKER_GROUP = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;

export function splitCitations(text: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER_GROUP)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: "text", text: text.slice(last, start) });
    for (const value of match[1].split(",")) {
      parts.push({ kind: "cite", marker: Number.parseInt(value.trim(), 10) });
    }
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}

/** Markers in the order they first appear, for listing sources under an answer. */
export function citedMarkers(text: string): number[] {
  const seen: number[] = [];
  for (const part of splitCitations(text)) {
    if (part.kind === "cite" && !seen.includes(part.marker)) seen.push(part.marker);
  }
  return seen;
}
