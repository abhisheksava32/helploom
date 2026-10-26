"use client";

/**
 * Report charts on recharts. Colours come from the --chart-* tokens (validated for
 * colour vision deficiency in both themes), marks stay thin, and every chart has a
 * table twin so no value is reachable only by hovering.
 */

import Link from "next/link";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { tableClasses } from "@/components/ui/page-header";
import type { DailyPoint } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatCompact, formatDay, formatNumber } from "@/lib/format";

const AXIS_TICK = { fill: "var(--muted-foreground)", fontSize: 12 };

function ChartTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-sm shadow-popover">
      <p className="mb-1 text-xs text-muted-foreground">{typeof label === "string" ? formatDay(label) : label}</p>
      <ul className="space-y-1">
        {payload.map((entry) => (
          <li key={String(entry.dataKey)} className="flex items-center gap-2">
            <span aria-hidden className="h-0.5 w-3 rounded-full" style={{ backgroundColor: entry.color }} />
            <span className="font-semibold tabular-nums">{formatNumber(Number(entry.value ?? 0))}</span>
            <span className="text-muted-foreground">{entry.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Legend">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-sm" style={{ backgroundColor: item.color }} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** Ticks on day axes: a handful of evenly spaced dates however long the range is. */
function tickInterval(points: number): number {
  return Math.max(0, Math.ceil(points / 7) - 1);
}

export function ConversationsChart({ data }: { data: DailyPoint[] }) {
  return (
    <div className="h-64 w-full" role="img" aria-label="Conversations per day, area chart. A table view is available.">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey="date"
            tickFormatter={formatDay}
            interval={tickInterval(data.length)}
            tickLine={false}
            axisLine={{ stroke: "var(--chart-axis)" }}
            tick={AXIS_TICK}
            tickMargin={8}
          />
          <YAxis
            allowDecimals={false}
            tickFormatter={formatCompact}
            tickLine={false}
            axisLine={false}
            tick={AXIS_TICK}
            width={44}
          />
          <Tooltip content={ChartTooltip} cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }} />
          <Area
            type="monotone"
            dataKey="conversations"
            name="Conversations"
            stroke="var(--chart-1)"
            strokeWidth={2}
            fill="var(--chart-1)"
            fillOpacity={0.1}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)", fill: "var(--chart-1)" }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function OutcomesChart({ data }: { data: DailyPoint[] }) {
  return (
    <div className="space-y-3">
      <Legend
        items={[
          { label: "Answered", color: "var(--chart-1)" },
          { label: "Not found", color: "var(--chart-2)" },
        ]}
      />
      <div className="h-60 w-full" role="img" aria-label="Answered and not found questions per day, stacked columns. A table view is available.">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }} barCategoryGap="30%">
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="date"
              tickFormatter={formatDay}
              interval={tickInterval(data.length)}
              tickLine={false}
              axisLine={{ stroke: "var(--chart-axis)" }}
              tick={AXIS_TICK}
              tickMargin={8}
            />
            <YAxis allowDecimals={false} tickFormatter={formatCompact} tickLine={false} axisLine={false} tick={AXIS_TICK} width={44} />
            <Tooltip content={ChartTooltip} cursor={{ fill: "var(--surface-muted)", opacity: 0.6 }} />
            {/* The surface coloured stroke is the 2px gap between stacked segments. */}
            <Bar
              dataKey="answered"
              name="Answered"
              stackId="outcome"
              fill="var(--chart-1)"
              stroke="var(--surface)"
              strokeWidth={2}
              maxBarSize={24}
              isAnimationActive={false}
            />
            <Bar
              dataKey="not_found"
              name="Not found"
              stackId="outcome"
              fill="var(--chart-2)"
              stroke="var(--surface)"
              strokeWidth={2}
              maxBarSize={24}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function DailyTable({ data }: { data: DailyPoint[] }) {
  return (
    <div className="relative max-h-64 overflow-auto rounded-md border border-border">
      <table className={tableClasses.table}>
        <caption className="sr-only">Daily activity</caption>
        <thead className={cn(tableClasses.head, "sticky top-0")}>
          <tr>
            <th scope="col" className="px-3 py-2">
              Day
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              Conversations
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              Questions
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              Answered
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              Not found
            </th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {[...data].reverse().map((point) => (
            <tr key={point.date} className="border-b border-border last:border-0">
              <th scope="row" className="px-3 py-1.5 text-left font-normal">
                {formatDay(point.date)}
              </th>
              <td className="px-3 py-1.5 text-right">{formatNumber(point.conversations)}</td>
              <td className="px-3 py-1.5 text-right">{formatNumber(point.questions)}</td>
              <td className="px-3 py-1.5 text-right">{formatNumber(point.answered)}</td>
              <td className="px-3 py-1.5 text-right">{formatNumber(point.not_found)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Horizontal bars in plain HTML: long document titles wrap instead of being clipped by an SVG axis. */
export function BarList({
  items,
  unit,
}: {
  items: { key: string; label: string; value: number; detail?: string; href?: string }[];
  /** Singular unit for the value, for example "citation". */
  unit: string;
}) {
  const max = Math.max(1, ...items.map((item) => item.value));
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.key} className="space-y-1">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            {item.href ? (
              <Link href={item.href} className="min-w-0 truncate hover:text-primary hover:underline">
                {item.label}
              </Link>
            ) : (
              <span className="min-w-0 truncate">{item.label}</span>
            )}
            <span className="shrink-0 tabular-nums text-muted-foreground">
              <span className="font-medium text-foreground">{formatNumber(item.value)}</span> {item.value === 1 ? unit : `${unit}s`}
              {item.detail && <span className="hidden sm:inline">, {item.detail}</span>}
            </span>
          </div>
          <div className="h-2 rounded-full bg-surface-muted">
            <div className="h-full rounded-full bg-chart-1" style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
