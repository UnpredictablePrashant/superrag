"use client";

import { ErrorBox } from "@/components/error-box";
import { StatusBadge } from "@/components/status-badge";
import { API_URL, api, getPipelineRun } from "@/lib/api";
import { formatDuration, shortDate } from "@/lib/format";
import type { PipelineRun } from "@rag-console/shared-types";
import { Button, Panel } from "@rag-console/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, RefreshCw, RotateCw } from "lucide-react";
import { useParams } from "next/navigation";
import * as React from "react";

export default function PipelineDetailPage() {
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [liveRun, setLiveRun] = React.useState<PipelineRun | null>(null);
  const [error, setError] = React.useState("");
  const runQuery = useQuery({ queryKey: ["pipeline-run", params.id], queryFn: () => getPipelineRun(params.id) });
  const run = liveRun ?? runQuery.data;

  React.useEffect(() => {
    const source = new EventSource(`${API_URL}/pipeline-runs/${params.id}/events`, { withCredentials: true });
    source.addEventListener("pipeline", (event) => {
      setLiveRun(JSON.parse((event as MessageEvent).data));
    });
    source.onerror = () => source.close();
    return () => source.close();
  }, [params.id]);

  async function cancel() {
    setError("");
    try {
      await api(`/pipeline-runs/${params.id}/cancel`, { method: "POST" });
      queryClient.invalidateQueries({ queryKey: ["pipeline-run", params.id] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel pipeline.");
    }
  }

  async function retry() {
    setError("");
    try {
      await api(`/pipeline-runs/${params.id}/retry`, { method: "POST" });
      queryClient.invalidateQueries({ queryKey: ["pipeline-run", params.id] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not retry pipeline.");
    }
  }

  if (!run) {
    return <div className="text-sm text-zinc-500">Loading pipeline run</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
        <div>
          <div className="flex items-center gap-2">
            <StatusBadge status={run.current_stage} />
            <span className="text-sm text-zinc-500">{shortDate(run.created_at)}</span>
          </div>
          <h2 className="mt-2 text-2xl font-semibold text-zinc-950">Pipeline Details</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Current item: {run.current_item ?? "Waiting for worker"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={retry}>
            <RefreshCw className="h-4 w-4" aria-hidden />
            Retry
          </Button>
          <Button variant="danger" onClick={cancel}>
            <Ban className="h-4 w-4" aria-hidden />
            Cancel
          </Button>
        </div>
      </div>
      <ErrorBox message={error} />
      <Panel className="p-5">
        <div className="grid gap-4 md:grid-cols-4">
          <Stat label="Stage" value={run.current_stage.replaceAll("_", " ")} />
          <Stat label="Documents" value={`${run.processed_count}/${run.total_count}`} />
          <Stat label="ETA" value={formatDuration(run.estimated_completion_seconds)} />
          <Stat label="Confidence" value={run.estimated_completion_confidence} />
        </div>
        <div className="mt-5">
          <div className="mb-2 flex justify-between text-sm text-zinc-500">
            <span>Overall progress</span>
            <span>{run.progress_percentage}%</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-zinc-100">
            <div className="h-full bg-emerald-600" style={{ width: `${run.progress_percentage}%` }} />
          </div>
        </div>
      </Panel>
      <Panel className="overflow-hidden">
        <div className="border-b border-zinc-200 px-4 py-3">
          <h3 className="font-semibold text-zinc-950">Document status</h3>
        </div>
        <div className="divide-y divide-zinc-100">
          {run.documents.map((doc) => (
            <div key={String(doc.document_id)} className="flex flex-col gap-2 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="font-medium text-zinc-950">{String(doc.name)}</p>
                {doc.error ? <p className="text-sm text-rose-700">{String(doc.error)}</p> : null}
              </div>
              <div className="flex min-w-64 items-center gap-3">
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-100">
                  <div className="h-full bg-sky-600" style={{ width: `${Number(doc.progress_percentage ?? 0)}%` }} />
                </div>
                <StatusBadge status={String(doc.status)} />
              </div>
            </div>
          ))}
        </div>
      </Panel>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel className="p-4">
          <h3 className="font-semibold text-zinc-950">Warnings and errors</h3>
          <pre className="mt-3 max-h-72 overflow-auto rounded-md bg-zinc-950 p-3 text-xs text-zinc-100">
            {JSON.stringify({ warnings: run.warnings, errors: run.errors }, null, 2)}
          </pre>
        </Panel>
        <Panel className="p-4">
          <h3 className="flex items-center gap-2 font-semibold text-zinc-950">
            <RotateCw className="h-4 w-4 text-emerald-700" aria-hidden />
            Worker logs
          </h3>
          <pre className="mt-3 max-h-72 overflow-auto rounded-md bg-zinc-950 p-3 text-xs text-zinc-100">
            {JSON.stringify(run.worker_logs.slice(-20), null, 2)}
          </pre>
        </Panel>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-zinc-50 p-3">
      <p className="text-xs font-medium uppercase text-zinc-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-zinc-950">{value}</p>
    </div>
  );
}
