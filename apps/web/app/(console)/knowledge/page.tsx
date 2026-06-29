"use client";

import { EmptyState } from "@/components/empty-state";
import { ErrorBox } from "@/components/error-box";
import { StatusBadge } from "@/components/status-badge";
import { api, Category, listDocuments, listKnowledgeBases } from "@/lib/api";
import { formatBytes, shortDate } from "@/lib/format";
import type { DocumentRecord, KnowledgeBase } from "@rag-console/shared-types";
import { Badge, Button, Input, Label, Panel, Select } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, FolderTree, Plus, Search, Shield, UploadCloud } from "lucide-react";
import Link from "next/link";
import * as React from "react";

export default function KnowledgePage() {
  const queryClient = useQueryClient();
  const [selectedKbId, setSelectedKbId] = React.useState<string>("");
  const [search, setSearch] = React.useState("");
  const [newKbName, setNewKbName] = React.useState("");
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const documents = useQuery({
    queryKey: ["documents", selectedKbId],
    queryFn: () => listDocuments(selectedKbId || undefined),
  });
  const categories = useQuery({
    queryKey: ["categories", selectedKbId],
    enabled: Boolean(selectedKbId),
    queryFn: () => api<Category[]>(`/knowledge-bases/${selectedKbId}/categories`),
  });
  const createKb = useMutation({
    mutationFn: () =>
      api<KnowledgeBase>("/knowledge-bases", {
        method: "POST",
        body: JSON.stringify({ name: newKbName, description: "Created from Knowledge Explorer" }),
      }),
    onSuccess: (kb) => {
      setNewKbName("");
      setSelectedKbId(kb.id);
      queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
    },
  });
  const docs = (documents.data ?? []).filter((doc) => doc.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
        <div>
          <h2 className="text-2xl font-semibold text-zinc-950">Knowledge Explorer</h2>
          <p className="mt-1 text-sm text-zinc-500">Organize documents by base, category, metadata, and access level.</p>
        </div>
        <Link href="/ingestion">
          <Button>
            <UploadCloud className="h-4 w-4" aria-hidden />
            Upload
          </Button>
        </Link>
      </div>
      <ErrorBox message={createKb.error instanceof Error ? createKb.error.message : ""} />
      <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
        <aside className="space-y-4">
          <Panel className="p-4">
            <h3 className="font-semibold text-zinc-950">Knowledge bases</h3>
            <div className="mt-4 space-y-2">
              {(kbs.data ?? []).map((kb) => (
                <button
                  key={kb.id}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm transition ${
                    selectedKbId === kb.id ? "bg-emerald-50 text-emerald-800" : "hover:bg-zinc-100"
                  }`}
                  onClick={() => setSelectedKbId(kb.id)}
                >
                  <span className="block font-medium">{kb.name}</span>
                  <span className="text-xs text-zinc-500">{kb.confidentiality}</span>
                </button>
              ))}
            </div>
            <div className="mt-4 space-y-2 border-t border-zinc-100 pt-4">
              <Label htmlFor="new-kb">New knowledge base</Label>
              <div className="flex gap-2">
                <Input id="new-kb" value={newKbName} onChange={(event) => setNewKbName(event.target.value)} />
                <Button size="icon" disabled={!newKbName || createKb.isPending} onClick={() => createKb.mutate()}>
                  <Plus className="h-4 w-4" aria-hidden />
                </Button>
              </div>
            </div>
          </Panel>
          <Panel className="p-4">
            <div className="flex items-center gap-2">
              <FolderTree className="h-4 w-4 text-sky-700" aria-hidden />
              <h3 className="font-semibold text-zinc-950">Categories</h3>
            </div>
            <div className="mt-4 space-y-2">
              {(categories.data ?? []).map((category) => (
                <div key={category.id} className="rounded-md bg-zinc-50 px-3 py-2 text-sm text-zinc-700">
                  {category.path}
                </div>
              ))}
              {selectedKbId && !categories.data?.length ? (
                <p className="text-sm text-zinc-500">No categories yet.</p>
              ) : null}
            </div>
          </Panel>
        </aside>
        <section className="space-y-4">
          <Panel className="p-4">
            <div className="grid gap-3 lg:grid-cols-[1fr_220px_180px]">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-zinc-400" aria-hidden />
                <Input className="pl-9" placeholder="Search documents" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
              <Select value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
                <option value="">All knowledge bases</option>
                {(kbs.data ?? []).map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </Select>
              <Select defaultValue="">
                <option value="">All classifications</option>
                <option>Public</option>
                <option>Internal</option>
                <option>Confidential</option>
                <option>Restricted</option>
              </Select>
            </div>
          </Panel>
          {docs.length ? <DocumentTable docs={docs} /> : <EmptyState icon={Database} title="No documents found" body="Upload documents or adjust filters to populate this workspace." />}
        </section>
      </div>
    </div>
  );
}

function DocumentTable({ docs }: { docs: DocumentRecord[] }) {
  return (
    <Panel className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-zinc-200 text-sm">
          <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
            <tr>
              <th className="px-4 py-3">Document</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Security</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Updated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 bg-white">
            {docs.map((doc) => (
              <tr key={doc.id}>
                <td className="px-4 py-3">
                  <p className="font-medium text-zinc-950">{doc.name}</p>
                  <p className="text-xs text-zinc-500">{doc.file_type.toUpperCase()}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {doc.tags.map((tag) => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.processing_status} />
                </td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1 text-zinc-700">
                    <Shield className="h-4 w-4" aria-hidden />
                    {doc.confidentiality}
                  </span>
                </td>
                <td className="px-4 py-3 text-zinc-600">{formatBytes(doc.file_size)}</td>
                <td className="px-4 py-3 text-zinc-600">{shortDate(doc.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
