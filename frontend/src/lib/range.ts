import { toIsoDate } from "@/lib/format";

export interface DateRange {
  date_from: string;
  date_to: string;
}

const DAY_MS = 86_400_000;

/** The last `days` days ending today (UTC, both ends inclusive), as report endpoints expect. */
export function rangeEndingToday(days: number, now: number): DateRange {
  const today = new Date(now);
  return {
    date_from: toIsoDate(new Date(today.getTime() - (days - 1) * DAY_MS)),
    date_to: toIsoDate(today),
  };
}

/** Day span of a range, inclusive. */
export function rangeLength(range: DateRange): number {
  const from = Date.parse(`${range.date_from}T00:00:00Z`);
  const to = Date.parse(`${range.date_to}T00:00:00Z`);
  return Math.round((to - from) / DAY_MS) + 1;
}
