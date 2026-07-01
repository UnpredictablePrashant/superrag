"use client";

import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { api, getAiUsageSummary, getWorkspaceSummary, listConnectors, listDocuments, listPipelineRuns, listTelegramMessages } from "@/lib/api";
import { formatCurrency, formatDuration, formatNumber, shortDate } from "@/lib/format";
import type { DocumentRecord, PipelineRun } from "@rag-console/shared-types";
import { Badge, Panel } from "@rag-console/ui";
import { useQuery } from "@tanstack/react-query";
import { Activity, Bell, Bot, Coins, FileStack, Plug, RefreshCw } from "lucide-react";
import Link from "next/link";

export default function ActivityPage() {
  const summary = useQuery({ queryKey: ["workspace-summary"], queryFn: getWorkspaceSummary, refetchInterval: 10000 });
  const runs = useQuery({ queryKey: ["pipeline-runs"], queryFn: listPipelineRuns, refetchInterval: 5000 });
  const documents = useQuery({ queryKey: ["documents"], queryFn: () => listDocuments() });
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: listConnectors, refetchInterval: 10000 });
  const telegramMessages = useQuery({ queryKey: ["telegram-messages"], queryFn: listTelegramMessages, refetchInterval: 5000 });
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: () => api<Array<Record<string, unknown>>>("/notifications") });
  const aiUsage = useQuery({ queryKey: ["ai-usage", 30], queryFn: () => getAiUsageSummary(30), refetchInterval: 30000 });

  const reviewDocs = (documents.data ?? []).filter((doc) => ["AWAITING_REVIEW", "FAILED"].includes(doc.processing_status));
  const failedConnectors = (connectors.data ?? []).filter((connection) => connection.status === "error" || connection.last_sync_status === "failed");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Activity</h2>
        <p className="mt-1 text-sm text-zinc-500">Watch ingestion, source health, review work, and notifications.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <ActivityStat label="Review items" value={summary.data?.review_item_count ?? 0} />
        <ActivityStat label="Failed syncs" value={summary.data?.failed_sync_count ?? 0} />
        <ActivityStat label="Indexed docs" value={summary.data?.indexed_document_count ?? 0} />
        <ActivityStat label="Active sources" value={summary.data?.active_source_count ?? 0} />
        <ActivityStat label="AI spend" value={formatCurrency(aiUsage.data?.totals.cost_usd)} />
      </div>

      <Panel className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Coins className="h-5 w-5 text-emerald-700" aria-hidden />
            <h3 className="font-semibold text-zinc-950">AI assistant usage</h3>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
            <Badge>{formatNumber(aiUsage.data?.totals.total_tokens)} tokens</Badge>
            <Badge>{aiUsage.data?.totals.request_count ?? 0} request(s)</Badge>
            <Badge>{formatCurrency(aiUsage.data?.totals.cost_usd)}</Badge>
          </div>
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <UsageTable
            title="By user"
            rows={(aiUsage.data?.by_user ?? []).map((row) => ({
              key: row.user_id,
              name: row.full_name || row.email || row.user_id,
              detail: row.email && row.full_name ? row.email : `${row.request_count} request(s)`,
              tokens: row.total_tokens,
              cost: row.cost_usd,
            }))}
          />
          <UsageTable
            title="By model"
            rows={(aiUsage.data?.by_model ?? []).map((row) => ({
              key: `${row.provider}:${row.model}`,
              name: row.model,
              detail: `${row.provider} / ${row.pricing_source ?? "pricing"}`,
              tokens: row.total_tokens,
              cost: row.cost_usd,
            }))}
          />
        </div>
        {!aiUsage.data?.totals.request_count ? <p className="mt-4 text-sm text-zinc-500">No AI assistant usage recorded in the last 30 days.</p> : null}
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-zinc-200 px-4 py-3">
            <FileStack className="h-5 w-5 text-emerald-700" aria-hidden />
            <h3 className="font-semibold text-zinc-950">Pipeline runs</h3>
          </div>
          <div className="divide-y divide-zinc-100">
            {(runs.data ?? []).map((run) => (
              <PipelineRow key={run.id} run={run} />
            ))}
            {!runs.data?.length ? <EmptyState icon={FileStack} title="No pipeline runs" body="Index files or sync a source to create activity." /> : null}
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5 text-amber-700" aria-hidden />
            <h3 className="font-semibold text-zinc-950">Review attention</h3>
          </div>
          <div className="mt-4 space-y-3">
            {reviewDocs.map((doc) => (
              <ReviewDoc key={doc.id} doc={doc} />
            ))}
            {failedConnectors.map((connection) => (
              <Link key={connection.id} href="/data" className="block rounded-md border border-zinc-200 p-3 hover:bg-zinc-50">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-zinc-950">{connection.name}</span>
                  <StatusBadge status={connection.last_sync_status ?? connection.status} />
                </div>
                <p className="mt-1 text-xs text-zinc-500">{connection.kind} source needs attention.</p>
              </Link>
            ))}
            {!reviewDocs.length && !failedConnectors.length ? <p className="text-sm text-zinc-500">No review work right now.</p> : null}
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel className="p-5">
          <div className="flex items-center gap-2">
            <Plug className="h-5 w-5 text-sky-700" aria-hidden />
            <h3 className="font-semibold text-zinc-950">Source health</h3>
          </div>
          <div className="mt-4 divide-y divide-zinc-100">
            {(connectors.data ?? []).map((connection) => (
              <div key={connection.id} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="font-medium text-zinc-950">{connection.name}</p>
                  <p className="text-sm text-zinc-500">
                    {connection.kind} / {connection.indexed_item_count} indexed item(s)
                  </p>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <StatusBadge status={connection.status} />
                  {connection.live_tools_supported ? <Badge tone="blue">Live</Badge> : null}
                </div>
              </div>
            ))}
            {!connectors.data?.length ? <p className="text-sm text-zinc-500">No sources connected.</p> : null}
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-sky-700" aria-hidden />
            <h3 className="font-semibold text-zinc-950">Telegram messages</h3>
          </div>
          <div className="mt-4 divide-y divide-zinc-100">
            {(telegramMessages.data ?? []).slice(0, 8).map((message) => (
              <div key={message.id} className="py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-zinc-950">
                    {message.mode} / {message.source_type}
                  </p>
                  <StatusBadge status={message.status} />
                </div>
                {message.error ? <p className="mt-1 text-sm text-rose-700">{message.error}</p> : null}
                <p className="mt-1 text-xs text-zinc-500">{shortDate(message.created_at)}</p>
              </div>
            ))}
            {!telegramMessages.data?.length ? <p className="text-sm text-zinc-500">No Telegram messages received.</p> : null}
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-violet-700" aria-hidden />
            <h3 className="font-semibold text-zinc-950">Notifications</h3>
          </div>
          <div className="mt-4 divide-y divide-zinc-100">
            {(notifications.data ?? []).map((notification) => (
              <div key={String(notification.id)} className="py-3">
                <p className="font-medium text-zinc-950">{String(notification.title)}</p>
                <p className="text-sm text-zinc-500">{String(notification.body)}</p>
              </div>
            ))}
            {!notifications.data?.length ? <p className="text-sm text-zinc-500">No notifications yet.</p> : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function ActivityStat({ label, value }: { label: string; value: number | string }) {
  return (
    <Panel className="p-4">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
          <Activity className="h-5 w-5" aria-hidden />
        </span>
        <div>
          <p className="text-sm text-zinc-500">{label}</p>
          <p className="text-2xl font-semibold text-zinc-950">{value}</p>
        </div>
      </div>
    </Panel>
  );
}

function UsageTable({
  title,
  rows,
}: {
  title: string;
  rows: Array<{ key: string; name: string; detail: string; tokens: number; cost: number }>;
}) {
  return (
    <div className="overflow-hidden rounded-md border border-zinc-200">
      <div className="border-b border-zinc-200 bg-zinc-50 px-3 py-2 text-sm font-medium text-zinc-950">{title}</div>
      <div className="divide-y divide-zinc-100">
        {rows.slice(0, 8).map((row) => (
          <div key={row.key} className="grid grid-cols-[1fr_auto] gap-3 px-3 py-3 text-sm">
            <div className="min-w-0">
              <p className="truncate font-medium text-zinc-950">{row.name}</p>
              <p className="truncate text-xs text-zinc-500">{row.detail}</p>
            </div>
            <div className="text-right">
              <p className="font-medium text-zinc-950">{formatCurrency(row.cost)}</p>
              <p className="text-xs text-zinc-500">{formatNumber(row.tokens)} tokens</p>
            </div>
          </div>
        ))}
        {!rows.length ? <p className="px-3 py-3 text-sm text-zinc-500">No usage yet.</p> : null}
      </div>
    </div>
  );
}

function PipelineRow({ run }: { run: PipelineRun }) {
  return (
    <Link href={`/pipeline/${run.id}`} className="block p-4 hover:bg-zinc-50">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <StatusBadge status={run.current_stage} />
            <span className="text-sm text-zinc-500">{shortDate(run.created_at)}</span>
          </div>
          <p className="mt-2 font-medium text-zinc-950">
            {run.processed_count}/{run.total_count} documents processed
          </p>
          <p className="text-sm text-zinc-500">
            {run.current_item ? `${run.current_item} / ` : ""}ETA {formatDuration(run.estimated_completion_seconds)}
          </p>
          {run.errors.length || run.warnings.length ? (
            <p className="mt-1 text-xs text-zinc-500">
              {run.errors.length} error(s), {run.warnings.length} warning(s)
            </p>
          ) : null}
        </div>
        <div className="w-full max-w-sm">
          <div className="mb-1 flex justify-between text-xs text-zinc-500">
            <span>Progress</span>
            <span>{run.progress_percentage}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-zinc-100">
            <div className="h-full bg-emerald-600" style={{ width: `${run.progress_percentage}%` }} />
          </div>
        </div>
      </div>
    </Link>
  );
}

function ReviewDoc({ doc }: { doc: DocumentRecord }) {
  return (
    <Link href="/data" className="block rounded-md border border-zinc-200 p-3 hover:bg-zinc-50">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-zinc-950">{doc.name}</span>
        <StatusBadge status={doc.processing_status} />
      </div>
      <p className="mt-1 text-xs text-zinc-500">{shortDate(doc.updated_at)}</p>
    </Link>
  );
}
