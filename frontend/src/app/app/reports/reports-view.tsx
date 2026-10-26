"use client";

import { BarChart3, FileQuestion, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { BarList, ConversationsChart, DailyTable, OutcomesChart } from "./charts";
import { ProviderBadge } from "@/components/status";
import { StatTile } from "@/components/stat-tile";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Segmented } from "@/components/ui/controls";
import { Input, Select } from "@/components/ui/field";
import { TableScroll, tableClasses, PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "@/components/ui/states";
import { analyticsApi, type ReportRange } from "@/lib/api/endpoints";
import type { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import {
  formatCompact,
  formatDateTime,
  formatDuration,
  formatMoney,
  formatNumber,
  formatPercent,
  formatRelative,
  pluralize,
} from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { invalidate, useQuery } from "@/lib/query";
import { rangeEndingToday, rangeLength } from "@/lib/range";

type Preset = "7" | "30" | "90" | "custom";
type View = "chart" | "table";

function Panel<T>({
  title,
  description,
  query,
  empty,
  actions,
  children,
  bodyClassName,
}: {
  title: string;
  description?: string;
  query: { data: T | undefined; error: ApiError | null; isLoading: boolean; isFetching: boolean; refetch: () => void };
  empty?: (data: T) => boolean;
  actions?: ReactNode;
  children: (data: T) => ReactNode;
  bodyClassName?: string;
}) {
  return (
    <Card className="flex flex-col">
      <CardHeader title={title} description={description} actions={actions} />
      {query.isLoading ? (
        <CardBody>
          <Skeleton className="h-48 w-full" />
        </CardBody>
      ) : query.error && !query.data ? (
        <ErrorState message={query.error.message} onRetry={query.refetch} className="py-8" />
      ) : query.data !== undefined && empty?.(query.data) ? (
        <EmptyState icon={BarChart3} title="No data in this range" className="py-10" />
      ) : query.data !== undefined ? (
        // Refetches keep the previous render, dimmed, instead of flashing a skeleton.
        <CardBody className={cn("flex-1 transition-opacity", query.isFetching && "opacity-60", bodyClassName)}>
          {children(query.data)}
        </CardBody>
      ) : null}
    </Card>
  );
}

export function ReportsView() {
  const now = useNow();
  const [preset, setPreset] = useState<Preset>("30");
  const [custom, setCustom] = useState<ReportRange>(() => rangeEndingToday(30, now));
  const [channel, setChannel] = useState<"" | "widget" | "playground">("");
  const [dailyView, setDailyView] = useState<View>("chart");
  const [unansweredPage, setUnansweredPage] = useState(1);

  const base = preset === "custom" ? custom : rangeEndingToday(Number(preset), now);
  const validCustom = base.date_from <= base.date_to && rangeLength(base) <= 366;
  const range: ReportRange = { ...base, channel };
  const key = `${range.date_from}:${range.date_to}:${channel}`;
  const enabled = validCustom ? key : null;

  const overview = useQuery(enabled && `report:overview:${key}`, (signal) => analyticsApi.overview(range, { signal }), {
    tags: ["reports"],
  });
  const daily = useQuery(enabled && `report:daily:${key}`, (signal) => analyticsApi.perDay(range, { signal }), {
    tags: ["reports"],
  });
  const questions = useQuery(enabled && `report:questions:${key}`, (signal) => analyticsApi.topQuestions(range, 10, { signal }), {
    tags: ["reports"],
  });
  const documents = useQuery(enabled && `report:documents:${key}`, (signal) => analyticsApi.topDocuments(range, 8, { signal }), {
    tags: ["reports"],
  });
  const unanswered = useQuery(
    enabled && `report:unanswered:${key}:${unansweredPage}`,
    (signal) => analyticsApi.unanswered(range, unansweredPage, { signal }),
    { tags: ["reports"] },
  );
  const costs = useQuery(enabled && `report:costs:${key}`, (signal) => analyticsApi.costs(range, { signal }), {
    tags: ["reports"],
  });

  const stats = overview.data;
  const ratingsTotal = stats ? stats.ratings.up + stats.ratings.down : 0;
  const refreshing = [overview, daily, questions, documents, unanswered, costs].some((query) => query.isFetching);

  return (
    <>
      <PageHeader
        title="Reports"
        description="How well the help desk answers, what customers ask, and where the documentation has gaps."
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Segmented
          label="Date range"
          size="md"
          value={preset}
          onChange={(value) => {
            setPreset(value);
            setUnansweredPage(1);
          }}
          options={[
            { value: "7", label: "7 days" },
            { value: "30", label: "30 days" },
            { value: "90", label: "90 days" },
            { value: "custom", label: "Custom" },
          ]}
        />
        {preset === "custom" && (
          <div className="flex flex-wrap items-center gap-2">
            <Input
              type="date"
              aria-label="From date"
              value={custom.date_from}
              max={custom.date_to}
              onChange={(event) => setCustom((current) => ({ ...current, date_from: event.target.value }))}
              className="w-auto"
            />
            <span className="text-sm text-muted-foreground">to</span>
            <Input
              type="date"
              aria-label="To date"
              value={custom.date_to}
              min={custom.date_from}
              onChange={(event) => setCustom((current) => ({ ...current, date_to: event.target.value }))}
              className="w-auto"
            />
          </div>
        )}
        <Select
          aria-label="Channel"
          value={channel}
          onChange={(event) => {
            setChannel(event.target.value as typeof channel);
            setUnansweredPage(1);
          }}
          className="w-auto"
        >
          <option value="">All channels</option>
          <option value="widget">Website widget</option>
          <option value="playground">Playground</option>
        </Select>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Refresh reports"
          onClick={() => invalidate("reports")}
          disabled={refreshing}
        >
          <RefreshCw className={cn("size-4", refreshing && "animate-spin")} aria-hidden />
        </Button>
        {!validCustom && (
          <p role="alert" className="text-sm text-danger">
            Pick a start date before the end date, at most 366 days apart.
          </p>
        )}
      </div>

      {overview.error && !stats ? (
        <Card className="mb-6">
          <ErrorState message={overview.error.message} onRetry={overview.refetch} />
        </Card>
      ) : (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7">
          <StatTile
            label="Answer rate"
            emphasis
            loading={overview.isLoading}
            value={stats ? formatPercent(stats.answer_rate) : "-"}
            detail={stats ? `${formatCompact(stats.answered)} answered` : undefined}
            className="col-span-2 md:col-span-1"
          />
          <StatTile
            label="Questions"
            loading={overview.isLoading}
            value={stats ? formatCompact(stats.questions) : "-"}
            detail={stats ? `${pluralize(stats.conversations, "conversation")}` : undefined}
          />
          <StatTile
            label="Not found"
            loading={overview.isLoading}
            value={stats ? formatPercent(stats.not_found_rate) : "-"}
            detail={stats ? `${pluralize(stats.not_found, "question")}` : undefined}
          />
          <StatTile
            label="Satisfaction"
            loading={overview.isLoading}
            value={stats ? formatPercent(stats.ratings.satisfaction, 0) : "-"}
            detail={stats ? `${pluralize(ratingsTotal, "rating")}` : undefined}
          />
          <StatTile
            label="First token"
            loading={overview.isLoading}
            value={stats ? formatDuration(stats.avg_first_token_ms) : "-"}
            detail={stats ? `${formatDuration(stats.avg_latency_ms)} full answer` : undefined}
          />
          <StatTile
            label="Tickets opened"
            loading={overview.isLoading}
            value={stats ? formatCompact(stats.tickets_opened) : "-"}
            detail={stats ? `${formatNumber(stats.refused)} refused, ${pluralize(stats.errors, "error")}` : undefined}
          />
          <StatTile
            label="Model cost"
            loading={overview.isLoading}
            value={stats ? formatMoney(stats.cost_usd) : "-"}
            detail="Estimated from token usage"
          />
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel
          title="Conversations per day"
          query={daily}
          actions={
            <Segmented
              label="Show as"
              value={dailyView}
              onChange={setDailyView}
              options={[
                { value: "chart", label: "Chart" },
                { value: "table", label: "Table" },
              ]}
            />
          }
        >
          {(data) => (dailyView === "chart" ? <ConversationsChart data={data.results} /> : <DailyTable data={data.results} />)}
        </Panel>
        <Panel
          title="Answered vs not found"
          description="Per day. Not found means the documents did not cover the question."
          query={daily}
        >
          {(data) => (dailyView === "chart" ? <OutcomesChart data={data.results} /> : <DailyTable data={data.results} />)}
        </Panel>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Panel title="Ratings" description="Thumbs up and down from visitors and your team." query={overview}>
          {(data) => {
            const total = data.ratings.up + data.ratings.down;
            if (total === 0) return <p className="py-6 text-center text-sm text-muted-foreground">No ratings in this range.</p>;
            const upShare = data.ratings.up / total;
            return (
              <div className="space-y-5">
                <div>
                  <p className="text-4xl font-semibold tracking-tight">{formatPercent(data.ratings.satisfaction, 0)}</p>
                  <p className="text-sm text-muted-foreground">of rated answers were helpful</p>
                </div>
                <div className="flex h-3 gap-0.5 overflow-hidden rounded-full" aria-hidden>
                  <div className="rounded-l-full bg-chart-1" style={{ width: `${upShare * 100}%` }} />
                  <div className="rounded-r-full bg-chart-2" style={{ width: `${(1 - upShare) * 100}%` }} />
                </div>
                <dl className="grid grid-cols-3 gap-2 text-sm">
                  <div>
                    <dt className="flex items-center gap-1.5 text-muted-foreground">
                      <span aria-hidden className="size-2.5 rounded-sm bg-chart-1" /> Helpful
                    </dt>
                    <dd className="font-medium tabular-nums">{formatNumber(data.ratings.up)}</dd>
                  </div>
                  <div>
                    <dt className="flex items-center gap-1.5 text-muted-foreground">
                      <span aria-hidden className="size-2.5 rounded-sm bg-chart-2" /> Not helpful
                    </dt>
                    <dd className="font-medium tabular-nums">{formatNumber(data.ratings.down)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Average</dt>
                    <dd className="font-medium tabular-nums" title="On a scale from -1 to 1">
                      {data.ratings.average === null ? "-" : data.ratings.average.toFixed(2)}
                    </dd>
                  </div>
                </dl>
              </div>
            );
          }}
        </Panel>

        <Panel
          title="Top cited documents"
          description="Which documents answers lean on most."
          query={documents}
          empty={(data) => data.results.length === 0}
        >
          {(data) => (
            <BarList
              unit="citation"
              items={data.results.map((item, index) => ({
                key: item.document_id ?? `deleted-${index}`,
                label: item.document_id ? item.title : `${item.title} (deleted)`,
                value: item.citations,
                detail: pluralize(item.answers, "answer"),
                href: item.document_id ? `/app/documents?preview=${item.document_id}` : undefined,
              }))}
            />
          )}
        </Panel>

        <Panel title="Cost by provider" description="Estimated from recorded token usage." query={costs} empty={(data) => data.results.length === 0}>
          {(data) => (
            <div className="space-y-4">
              <p>
                <span className="text-3xl font-semibold tracking-tight">{formatMoney(data.total_cost_usd)}</span>
                <span className="ml-2 text-sm text-muted-foreground">total</span>
              </p>
              <ul className="divide-y divide-border">
                {data.results.map((row) => (
                  <li key={`${row.provider}:${row.model}`} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0 space-y-1">
                      <ProviderBadge provider={row.provider} model={row.model} />
                      <p className="text-xs text-muted-foreground">
                        {pluralize(row.messages, "answer")} &middot; {formatCompact(row.input_tokens)} in &middot;{" "}
                        {formatCompact(row.output_tokens)} out &middot; {formatCompact(row.cache_read_input_tokens)} cached
                      </p>
                    </div>
                    <span className="shrink-0 font-medium tabular-nums">{formatMoney(row.cost_usd, { precise: true })}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Top questions" description="Grouped by wording, ignoring case and punctuation." />
          {questions.isLoading ? (
            <SkeletonRows rows={5} />
          ) : questions.error && !questions.data ? (
            <ErrorState message={questions.error.message} onRetry={questions.refetch} className="py-8" />
          ) : questions.data && questions.data.results.length > 0 ? (
            <TableScroll>
              <table className={cn(tableClasses.table, "min-w-[420px]", questions.isFetching && "opacity-60")}>
                <thead className={tableClasses.head}>
                  <tr>
                    <th scope="col" className={tableClasses.th}>
                      Question
                    </th>
                    <th scope="col" className={cn(tableClasses.th, "text-right")}>
                      Asked
                    </th>
                    <th scope="col" className={cn(tableClasses.th, "w-36")}>
                      Answered
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {questions.data.results.map((item) => {
                    const share = item.count > 0 ? item.answered / item.count : 0;
                    return (
                      <tr key={item.question} className={tableClasses.row}>
                        <td className={tableClasses.td}>
                          <p className="line-clamp-2">{item.question}</p>
                          <p className="text-xs text-muted-foreground">Last asked {formatRelative(item.last_asked_at, now)}</p>
                        </td>
                        <td className={cn(tableClasses.td, "text-right font-medium tabular-nums")}>{formatNumber(item.count)}</td>
                        <td className={tableClasses.td}>
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-surface-muted" aria-hidden>
                              <div className="h-full rounded-full bg-chart-1" style={{ width: `${share * 100}%` }} />
                            </div>
                            <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">
                              {formatPercent(share, 0)}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </TableScroll>
          ) : (
            <EmptyState icon={BarChart3} title="No questions in this range" className="py-10" />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Content gaps"
            description="Questions answered with not found. Each one is a document worth writing."
          />
          {unanswered.isLoading ? (
            <SkeletonRows rows={5} />
          ) : unanswered.error && !unanswered.data ? (
            <ErrorState message={unanswered.error.message} onRetry={unanswered.refetch} className="py-8" />
          ) : unanswered.data && unanswered.data.results.length > 0 ? (
            <div className={cn(unanswered.isFetching && "opacity-60")}>
              <ul className="divide-y divide-border">
                {unanswered.data.results.map((item) => (
                  <li key={item.message_id}>
                    <Link
                      href={`/app/conversations/${item.conversation_id}`}
                      className="flex items-start justify-between gap-3 px-5 py-3 transition-colors hover:bg-surface-muted/50"
                    >
                      <div className="min-w-0">
                        <p className="line-clamp-2 text-sm">{item.question}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground" title={formatDateTime(item.asked_at)}>
                          {item.channel === "widget" ? "Website" : "Playground"} &middot; {formatRelative(item.asked_at, now)}
                          {item.has_ticket && <> &middot; handed off</>}
                        </p>
                      </div>
                      <span className="shrink-0 rounded bg-surface-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground" title="Best vector similarity">
                        {item.top_similarity === null ? "-" : item.top_similarity.toFixed(2)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              <Pagination
                page={unansweredPage}
                pageSize={10}
                count={unanswered.data.count}
                onPageChange={setUnansweredPage}
                label="questions"
              />
            </div>
          ) : (
            <EmptyState
              icon={FileQuestion}
              title="No gaps found"
              description="Every question in this range was covered by your documents."
              className="py-10"
            />
          )}
        </Card>
      </div>
    </>
  );
}
