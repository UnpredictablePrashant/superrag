"use client";

import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { listPipelineRuns } from "@/lib/api";
import { formatDuration, shortDate } from "@/lib/format";
import type { PipelineRun } from "@rag-console/shared-types";
import { Panel } from "@rag-console/ui";
import { useQuery } from "@tanstack/react-query";
import { FileStack } from "lucide-react";
import Link from "next/link";

export default function PipelinePage() {
  const runs = useQuery({ queryKey: ["pipeline-runs"], queryFn: listPipelineRuns, refetchInterval: 5000 });
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Pipeline Runs</h2>
        <p className="mt-1 text-sm text-zinc-500">Track asynchronous ingestion, retries, review pauses, and ETA ranges.</p>
      </div>
      {runs.data?.length ? (
        <Panel className="overflow-hidden">
          <div className="divide-y divide-zinc-100">
            {runs.data.map((run) => (
              <PipelineRow key={run.id} run={run} />
            ))}
          </div>
        </Panel>
      ) : (
        <EmptyState icon={FileStack} title="No pipeline runs" body="Start ingestion from uploaded documents to create the first run." />
      )}
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
            ETA {formatDuration(run.estimated_completion_seconds)} with {run.estimated_completion_confidence} confidence
          </p>
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
