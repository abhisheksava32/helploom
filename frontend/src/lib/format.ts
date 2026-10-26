/**
 * Display formatting. Every function is pure and takes "now" explicitly where time
 * matters, so components stay deterministic and render the same on every pass.
 */

const numberFormat = new Intl.NumberFormat("en-US");
const compactFormat = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const dateFormat = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const shortDayFormat = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

/** 1,284 / 12.9K / 4.2M, for stat tiles and axis ticks. */
export function formatCompact(value: number): string {
  return value < 1000 ? numberFormat.format(value) : compactFormat.format(value);
}

/** A 0..1 ratio as a percentage; null (no data) renders as a dash. */
export function formatPercent(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "-";
  return `${(ratio * 100).toFixed(digits)}%`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

/** Money arrives as a decimal string ("0.004120") so it is never rounded by floats in transit. */
export function formatMoney(amount: string | number, options: { precise?: boolean } = {}): string {
  const value = typeof amount === "number" ? amount : Number.parseFloat(amount);
  if (!Number.isFinite(value)) return "$0.00";
  if (options.precise && value > 0 && value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

export function formatPrice(cents: number): string {
  return cents % 100 === 0 ? `$${cents / 100}` : `$${(cents / 100).toFixed(2)}`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "-";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

export function formatDate(timestamp: string | null | undefined): string {
  if (!timestamp) return "-";
  return dateFormat.format(new Date(timestamp));
}

export function formatDateTime(timestamp: string | null | undefined): string {
  if (!timestamp) return "-";
  return dateTimeFormat.format(new Date(timestamp));
}

/** "Oct 25" for a "YYYY-MM-DD" date, read as UTC like the API's report days. */
export function formatDay(date: string): string {
  return shortDayFormat.format(new Date(`${date}T00:00:00Z`));
}

export function formatRelative(timestamp: string | null | undefined, now: number): string {
  if (!timestamp) return "-";
  const seconds = Math.round((now - new Date(timestamp).getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return days === 1 ? "yesterday" : `${days} days ago`;
  return formatDate(timestamp);
}

/** "YYYY-MM-DD" for a Date, in UTC, matching the API's report day boundaries. */
export function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function initials(name: string, fallback: string): string {
  const source = name.trim() || fallback;
  const parts = source.split(/[\s@.]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : source.slice(0, 2);
  return letters.toUpperCase();
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`;
}

export const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama",
  claude: "Claude API",
  extractive: "Extractive",
};

export function providerLabel(name: string): string {
  return PROVIDER_LABELS[name] ?? name;
}
