"use client";

import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { listDocuments, listKnowledgeBases } from "@/lib/api";
import { formatBytes, shortDate } from "@/lib/format";
import { Badge, Input, Panel, Select } from "@rag-console/ui";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText, Search } from "lucide-react";
import * as React from "react";

export default function DirectoryPage() {
  const [knowledgeBaseId, setKnowledgeBaseId] = React.useState("");
  const [search, setSearch] = React.useState("");
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const docs = useQuery({ queryKey: ["documents", knowledgeBaseId], queryFn: () => listDocuments(knowledgeBaseId || undefined) });
  const visibleDocs = (docs.data ?? []).filter((doc) => {
    const haystack = `${doc.name} ${doc.original_filename} ${doc.tags.join(" ")} ${doc.business_unit ?? ""}`.toLowerCase();
    return haystack.includes(search.toLowerCase().trim());
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Document Directory</h2>
        <p className="mt-1 text-sm text-zinc-500">Browse uploaded company knowledge without changing ingestion settings.</p>
      </div>
      <Panel className="p-4">
        <div className="grid gap-3 md:grid-cols-[260px_1fr]">
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-800">Knowledge base</label>
            <Select value={knowledgeBaseId} onChange={(event) => setKnowledgeBaseId(event.target.value)}>
              <option value="">All knowledge bases</option>
              {(kbs.data ?? []).map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-800">Search documents</label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" aria-hidden />
              <Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
          </div>
        </div>
      </Panel>
      <Panel className="overflow-hidden">
        <div className="border-b border-zinc-200 px-4 py-3">
          <h3 className="font-semibold text-zinc-950">Uploaded documents</h3>
        </div>
        {visibleDocs.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-medium uppercase text-zinc-500">
                <tr>
                  <th className="px-4 py-3">Document</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Confidentiality</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="px-4 py-3">Updated</th>
                  <th className="px-4 py-3">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 bg-white">
                {visibleDocs.map((doc) => (
                  <tr key={doc.id}>
                    <td className="max-w-md px-4 py-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <FileText className="mt-0.5 h-4 w-4 flex-none text-zinc-400" aria-hidden />
                        <div className="min-w-0">
                          <p className="truncate font-medium text-zinc-950">{doc.name}</p>
                          <p className="truncate text-xs text-zinc-500">{doc.original_filename}</p>
                          {doc.tags.length ? (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {doc.tags.slice(0, 4).map((tag) => (
                                <Badge key={tag}>{tag}</Badge>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={doc.processing_status} />
                    </td>
                    <td className="px-4 py-3 text-zinc-700">{doc.confidentiality}</td>
                    <td className="px-4 py-3 text-zinc-700">{formatBytes(doc.file_size)}</td>
                    <td className="px-4 py-3 text-zinc-700">{shortDate(doc.updated_at)}</td>
                    <td className="max-w-xs px-4 py-3">
                      {doc.source_url ? (
                        <a className="inline-flex max-w-full items-center gap-1 truncate text-sky-700 hover:underline" href={doc.source_url} target="_blank" rel="noreferrer">
                          <ExternalLink className="h-3.5 w-3.5 flex-none" aria-hidden />
                          <span className="truncate">{doc.source_url}</span>
                        </a>
                      ) : (
                        <span className="text-zinc-400">Uploaded file</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6">
            <EmptyState icon={FileText} title="No documents found" body="Uploaded documents will appear here once they are available in a knowledge base." />
          </div>
        )}
      </Panel>
    </div>
  );
}
