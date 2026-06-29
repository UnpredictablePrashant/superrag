"use client";

import { MetricCard } from "@/components/metric-card";
import { StatusBadge } from "@/components/status-badge";
import { api, listDocuments, listKnowledgeBases, listPipelineRuns } from "@/lib/api";
import { shortDate } from "@/lib/format";
import type { DocumentRecord, PipelineRun } from "@rag-console/shared-types";
import { Panel } from "@rag-console/ui";
import { useQuery } from "@tanstack/react-query";
import { Activity, BookOpenText, Bot, Database, FileText, Layers3, MessageSquare, Plug } from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const documents = useQuery({ queryKey: ["documents"], queryFn: () => listDocuments() });
  const pipelines = useQuery({ queryKey: ["pipeline-runs"], queryFn: listPipelineRuns, refetchInterval: 5000 });
  const chats = useQuery({ queryKey: ["chat-sessions"], queryFn: () => api<Array<{ id: string; title: string }>>("/chat-sessions") });
  const docs = documents.data ?? [];
  const runs = pipelines.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Dashboard</h2>
        <p className="mt-1 text-sm text-zinc-500">Operational snapshot across documents, ingestion, and chat.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Documents" value={docs.length} detail="Uploaded originals" icon={FileText} />
        <MetricCard label="Knowledge bases" value={kbs.data?.length ?? 0} detail="Tenant scoped" icon={Database} />
        <MetricCard
          label="Indexed"
          value={docs.filter((doc) => doc.processing_status.includes("COMPLETED")).length}
          detail="Ready for retrieval"
          icon={Layers3}
        />
        <MetricCard label="Recent chats" value={chats.data?.length ?? 0} detail="Saved sessions" icon={MessageSquare} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-semibold text-zinc-950">Recent pipeline runs</h3>
            <Link href="/pipeline" className="text-sm font-medium text-emerald-700 hover:text-emerald-800">
              View all
            </Link>
          </div>
          <div className="space-y-3">
            {runs.slice(0, 5).map((run) => (
              <PipelineRow key={run.id} run={run} />
            ))}
            {!runs.length ? <p className="text-sm text-zinc-500">No pipeline runs yet.</p> : null}
          </div>
        </Panel>
        <Panel className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <Activity className="h-5 w-5 text-emerald-700" aria-hidden />
            <h3 className="font-semibold text-zinc-950">Recent activity</h3>
          </div>
          <div className="space-y-3">
            {docs.slice(0, 6).map((doc) => (
              <DocumentActivity key={doc.id} doc={doc} />
            ))}
            {!docs.length ? <p className="text-sm text-zinc-500">Upload documents to begin indexing.</p> : null}
          </div>
        </Panel>
      </div>
      <Panel className="p-5">
        <div className="mb-4 flex items-center gap-2">
          <BookOpenText className="h-5 w-5 text-sky-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Docs</h3>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <Link href="/help#telegram" className="rounded-md border border-zinc-200 p-4 hover:bg-zinc-50">
            <div className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-sky-700" aria-hidden />
              <p className="font-medium text-zinc-950">Telegram setup</p>
            </div>
            <p className="mt-2 text-sm text-zinc-500">Connect a Telegram bot, register the webhook, and allow users.</p>
          </Link>
          <Link href="/help#mcp" className="rounded-md border border-zinc-200 p-4 hover:bg-zinc-50">
            <div className="flex items-center gap-2">
              <Plug className="h-4 w-4 text-emerald-700" aria-hidden />
              <p className="font-medium text-zinc-950">MCP connectors</p>
            </div>
            <p className="mt-2 text-sm text-zinc-500">Use Cursor-style MCP JSON with stdio or connect Streamable HTTP servers.</p>
          </Link>
        </div>
      </Panel>
    </div>
  );
}

function PipelineRow({ run }: { run: PipelineRun }) {
  return (
    <Link href={`/pipeline/${run.id}`} className="block rounded-md border border-zinc-200 p-3 hover:bg-zinc-50">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-zinc-950">{run.current_stage.replaceAll("_", " ")}</p>
          <p className="text-xs text-zinc-500">
            {run.processed_count}/{run.total_count} documents, {run.progress_percentage}% complete
          </p>
        </div>
        <StatusBadge status={run.current_stage} />
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-100">
        <div className="h-full bg-emerald-600" style={{ width: `${run.progress_percentage}%` }} />
      </div>
    </Link>
  );
}

function DocumentActivity({ doc }: { doc: DocumentRecord }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-zinc-100 pb-3 last:border-0 last:pb-0">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-zinc-950">{doc.name}</p>
        <p className="text-xs text-zinc-500">{shortDate(doc.updated_at)}</p>
      </div>
      <StatusBadge status={doc.processing_status} />
    </div>
  );
}
