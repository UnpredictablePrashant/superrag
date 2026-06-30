"use client";

import { EmptyState } from "@/components/empty-state";
import { ErrorBox } from "@/components/error-box";
import { StatusBadge } from "@/components/status-badge";
import { api, Category, ConnectorConnection, listConnectors, listDocuments, listKnowledgeBases, uploadDocument } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { Confidentiality, DocumentRecord, KnowledgeBase, PipelineRun } from "@rag-console/shared-types";
import { Badge, Button, Input, Label, Panel, Select } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Cloud, FileText, FolderPlus, Globe, HardDrive, Mail, Play, Plug, UploadCloud } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

const steps = [
  "Select documents",
  "Organize metadata",
  "Cleanup strategy",
  "Chunking strategy",
  "Embedding configuration",
  "Review and start",
];

export default function IngestionPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = React.useState(0);
  const [files, setFiles] = React.useState<File[]>([]);
  const [uploadedDocs, setUploadedDocs] = React.useState<DocumentRecord[]>([]);
  const [selectedExistingDocs, setSelectedExistingDocs] = React.useState<string[]>([]);
  const [selectedConnectorIds, setSelectedConnectorIds] = React.useState<string[]>([]);
  const [knowledgeBaseId, setKnowledgeBaseId] = React.useState("");
  const [categoryId, setCategoryId] = React.useState("");
  const [newCategory, setNewCategory] = React.useState("");
  const [tags, setTags] = React.useState("default");
  const [businessUnit, setBusinessUnit] = React.useState("");
  const [confidentiality, setConfidentiality] = React.useState<Confidentiality>("Internal");
  const [cleanupProfileId, setCleanupProfileId] = React.useState("");
  const [chunkingProfileId, setChunkingProfileId] = React.useState("");
  const [embeddingProfileId, setEmbeddingProfileId] = React.useState("");
  const [uploading, setUploading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");

  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: listConnectors });
  const docs = useQuery({ queryKey: ["documents", knowledgeBaseId], queryFn: () => listDocuments(knowledgeBaseId || undefined) });
  const categories = useQuery({
    queryKey: ["categories", knowledgeBaseId],
    enabled: Boolean(knowledgeBaseId),
    queryFn: () => api<Category[]>(`/knowledge-bases/${knowledgeBaseId}/categories`),
  });
  const profiles = useQuery({
    queryKey: ["profiles"],
    queryFn: () =>
      api<{
        cleanup_profiles: Array<{ id: string; name: string; strategy: string }>;
        chunking_profiles: Array<{ id: string; name: string; strategy: string }>;
        embedding_profiles: Array<{ id: string; name: string; model_name: string }>;
      }>("/profiles"),
  });

  React.useEffect(() => {
    if (!knowledgeBaseId && kbs.data?.[0]) setKnowledgeBaseId(kbs.data[0].id);
  }, [kbs.data, knowledgeBaseId]);
  React.useEffect(() => {
    if (!cleanupProfileId && profiles.data?.cleanup_profiles[1]) setCleanupProfileId(profiles.data.cleanup_profiles[1].id);
    if (!chunkingProfileId && profiles.data?.chunking_profiles[0]) setChunkingProfileId(profiles.data.chunking_profiles[0].id);
    if (!embeddingProfileId && profiles.data?.embedding_profiles[0]) setEmbeddingProfileId(profiles.data.embedding_profiles[0].id);
  }, [profiles.data, cleanupProfileId, chunkingProfileId, embeddingProfileId]);

  const createCategory = useMutation({
    mutationFn: () =>
      api<Category>(`/knowledge-bases/${knowledgeBaseId}/categories`, {
        method: "POST",
        body: JSON.stringify({ name: newCategory }),
      }),
    onSuccess: (category) => {
      setCategoryId(category.id);
      setNewCategory("");
      queryClient.invalidateQueries({ queryKey: ["categories", knowledgeBaseId] });
    },
  });

  async function uploadFiles() {
    if (!files.length) return;
    setError("");
    setUploading(true);
    try {
      const uploaded: DocumentRecord[] = [];
      for (const file of files) {
        const document = await uploadDocument(file, {
          knowledge_base_id: knowledgeBaseId,
          category_id: categoryId || undefined,
          tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
          business_unit: businessUnit || undefined,
          confidentiality,
        });
        uploaded.push(document);
      }
      setUploadedDocs(uploaded);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setStep(5);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function startPipeline() {
    setError("");
    setNotice("");
    try {
      const documentIds = [...uploadedDocs.map((doc) => doc.id), ...selectedExistingDocs];
      let run: PipelineRun | null = null;
      if (documentIds.length) {
        run = await api<PipelineRun>("/pipeline-runs", {
          method: "POST",
          body: JSON.stringify({
            knowledge_base_id: knowledgeBaseId,
            document_ids: documentIds,
            cleanup_profile_id: cleanupProfileId || undefined,
            chunking_profile_id: chunkingProfileId || undefined,
            embedding_profile_id: embeddingProfileId || undefined,
            retrieval_index_config: { max_chunks: 8, rrf_constant: 60 },
          }),
        });
      }
      for (const connectorId of selectedConnectorIds) {
        await api(`/connectors/${connectorId}/sync`, {
          method: "POST",
          body: JSON.stringify({
            knowledge_base_id: knowledgeBaseId,
            cleanup_profile_id: cleanupProfileId || undefined,
            chunking_profile_id: chunkingProfileId || undefined,
            embedding_profile_id: embeddingProfileId || undefined,
            share_with_organization: false,
          }),
        });
      }
      if (run) {
        router.push(`/pipeline/${run.id}`);
      } else {
        setNotice("Connector sync queued.");
        queryClient.invalidateQueries({ queryKey: ["documents"] });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start pipeline.");
    }
  }

  const existingDocs = docs.data ?? [];
  const allSelected = uploadedDocs.length + selectedExistingDocs.length + selectedConnectorIds.length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Ingestion Wizard</h2>
        <p className="mt-1 text-sm text-zinc-500">Upload, validate, clean, chunk, embed, and index documents.</p>
      </div>
      <ErrorBox message={error || (createCategory.error instanceof Error ? createCategory.error.message : "")} />
      {notice ? <div className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div> : null}
      <div className="grid gap-4 xl:grid-cols-[280px_1fr]">
        <Panel className="p-4">
          <ol className="space-y-2">
            {steps.map((label, index) => (
              <li key={label}>
                <button
                  className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm ${
                    index === step ? "bg-emerald-50 text-emerald-800" : "text-zinc-600 hover:bg-zinc-100"
                  }`}
                  onClick={() => setStep(index)}
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded bg-white text-xs font-semibold shadow-sm">
                    {index < step ? <Check className="h-3 w-3" /> : index + 1}
                  </span>
                  {label}
                </button>
              </li>
            ))}
          </ol>
        </Panel>
        <Panel className="min-h-[520px] p-5">
          {step === 0 ? (
            <SelectDocuments
              files={files}
              setFiles={setFiles}
              existingDocs={existingDocs}
              selectedExistingDocs={selectedExistingDocs}
              setSelectedExistingDocs={setSelectedExistingDocs}
              connectors={connectors.data ?? []}
              selectedConnectorIds={selectedConnectorIds}
              setSelectedConnectorIds={setSelectedConnectorIds}
            />
          ) : null}
          {step === 1 ? (
            <OrganizeStep
              kbs={kbs.data ?? []}
              knowledgeBaseId={knowledgeBaseId}
              setKnowledgeBaseId={setKnowledgeBaseId}
              categories={categories.data ?? []}
              categoryId={categoryId}
              setCategoryId={setCategoryId}
              newCategory={newCategory}
              setNewCategory={setNewCategory}
              createCategory={() => createCategory.mutate()}
              tags={tags}
              setTags={setTags}
              businessUnit={businessUnit}
              setBusinessUnit={setBusinessUnit}
              confidentiality={confidentiality}
              setConfidentiality={setConfidentiality}
            />
          ) : null}
          {step === 2 ? (
            <ProfileStep
              title="Cleanup strategy"
              options={profiles.data?.cleanup_profiles ?? []}
              value={cleanupProfileId}
              onChange={setCleanupProfileId}
            />
          ) : null}
          {step === 3 ? (
            <ProfileStep
              title="Chunking strategy"
              options={profiles.data?.chunking_profiles ?? []}
              value={chunkingProfileId}
              onChange={setChunkingProfileId}
            />
          ) : null}
          {step === 4 ? (
            <ProfileStep
              title="Embedding configuration"
              options={(profiles.data?.embedding_profiles ?? []).map((profile) => ({
                ...profile,
                strategy: profile.model_name,
              }))}
              value={embeddingProfileId}
              onChange={setEmbeddingProfileId}
            />
          ) : null}
          {step === 5 ? (
            <ReviewStep
              documents={[...uploadedDocs, ...existingDocs.filter((doc) => selectedExistingDocs.includes(doc.id))]}
              connectors={(connectors.data ?? []).filter((connection) => selectedConnectorIds.includes(connection.id))}
              cleanup={profiles.data?.cleanup_profiles.find((profile) => profile.id === cleanupProfileId)?.name}
              chunking={profiles.data?.chunking_profiles.find((profile) => profile.id === chunkingProfileId)?.name}
              embedding={profiles.data?.embedding_profiles.find((profile) => profile.id === embeddingProfileId)?.name}
            />
          ) : null}
          <div className="mt-6 flex justify-between border-t border-zinc-100 pt-4">
            <Button variant="secondary" disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}>
              Back
            </Button>
            {step < 5 ? (
              <Button onClick={() => setStep((value) => Math.min(5, value + 1))}>
                Next
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Button>
            ) : (
              <div className="flex gap-2">
                {files.length && !uploadedDocs.length ? (
                  <Button disabled={!knowledgeBaseId || uploading} onClick={uploadFiles}>
                    <UploadCloud className="h-4 w-4" aria-hidden />
                    {uploading ? "Uploading" : "Upload files"}
                  </Button>
                ) : null}
                <Button disabled={!allSelected} onClick={startPipeline}>
                  <Play className="h-4 w-4" aria-hidden />
                  Start ingestion
                </Button>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function SelectDocuments({
  files,
  setFiles,
  existingDocs,
  selectedExistingDocs,
  setSelectedExistingDocs,
  connectors,
  selectedConnectorIds,
  setSelectedConnectorIds,
}: {
  files: File[];
  setFiles: (files: File[]) => void;
  existingDocs: DocumentRecord[];
  selectedExistingDocs: string[];
  setSelectedExistingDocs: (ids: string[]) => void;
  connectors: ConnectorConnection[];
  selectedConnectorIds: string[];
  setSelectedConnectorIds: (ids: string[]) => void;
}) {
  const [source, setSource] = React.useState("files");
  const connectorSources = connectors.filter((connection) => connection.kind === source);
  const sourceOptions = [
    { id: "files", label: "Local files", icon: UploadCloud, enabled: true },
    { id: "existing", label: "Uploaded", icon: FileText, enabled: true },
    { id: "web", label: "Web", icon: Globe, enabled: true },
    { id: "mcp", label: "MCP", icon: Plug, enabled: true },
    { id: "google-drive", label: "Google Drive", icon: Cloud, enabled: false },
    { id: "gmail", label: "Gmail", icon: Mail, enabled: false },
    { id: "one-drive", label: "OneDrive", icon: HardDrive, enabled: false },
  ];
  function toggle(id: string) {
    setSelectedExistingDocs(
      selectedExistingDocs.includes(id) ? selectedExistingDocs.filter((value) => value !== id) : [...selectedExistingDocs, id],
    );
  }
  function toggleConnector(id: string) {
    setSelectedConnectorIds(
      selectedConnectorIds.includes(id) ? selectedConnectorIds.filter((value) => value !== id) : [...selectedConnectorIds, id],
    );
  }
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-zinc-950">Select documents</h3>
        <p className="mt-1 text-sm text-zinc-500">Choose local files or re-run ingestion for uploaded documents.</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {sourceOptions.map((option) => {
          const Icon = option.icon;
          return (
            <button
              key={option.id}
              disabled={!option.enabled}
              className={`rounded-md border p-3 text-left transition ${
                source === option.id
                  ? "border-emerald-300 bg-emerald-50"
                  : "border-zinc-200 bg-white hover:border-zinc-300"
              } ${option.enabled ? "" : "cursor-not-allowed opacity-60"}`}
              onClick={() => setSource(option.id)}
            >
              <Icon className="h-5 w-5 text-zinc-500" aria-hidden />
              <span className="mt-2 block text-sm font-medium text-zinc-950">{option.label}</span>
              {!option.enabled ? <Badge className="mt-2">Connector</Badge> : null}
            </button>
          );
        })}
      </div>
      {source === "files" ? (
        <>
          <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-zinc-50 text-center hover:bg-white">
            <UploadCloud className="h-9 w-9 text-zinc-400" aria-hidden />
            <span className="mt-3 text-sm font-medium text-zinc-950">Select files</span>
            <span className="mt-1 text-xs text-zinc-500">PDF, DOCX, PPTX, XLSX, CSV, TXT, Markdown, HTML, JSON, XML</span>
            <input
              className="sr-only"
              type="file"
              multiple
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            />
          </label>
          {files.length ? (
            <div className="grid gap-2">
              {files.map((file) => (
                <div key={`${file.name}-${file.size}`} className="flex items-center justify-between rounded-md border border-zinc-200 px-3 py-2">
                  <span className="text-sm font-medium text-zinc-800">{file.name}</span>
                  <Badge>{formatBytes(file.size)}</Badge>
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
      {source === "existing" ? (
        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-zinc-950">Existing uploaded documents</h4>
            {existingDocs.length ? (
              <Button
                variant="secondary"
                onClick={() =>
                  setSelectedExistingDocs(
                    selectedExistingDocs.length === existingDocs.length ? [] : existingDocs.map((doc) => doc.id),
                  )
                }
              >
                <Check className="h-4 w-4" aria-hidden />
                {selectedExistingDocs.length === existingDocs.length ? "Clear" : "Select all"}
              </Button>
            ) : null}
          </div>
          {existingDocs.length ? (
          <div className="grid gap-2">
            {existingDocs.map((doc) => (
              <label key={doc.id} className="flex items-center justify-between rounded-md border border-zinc-200 px-3 py-2">
                <span className="flex items-center gap-2 text-sm text-zinc-800">
                  <input type="checkbox" checked={selectedExistingDocs.includes(doc.id)} onChange={() => toggle(doc.id)} />
                  <FileText className="h-4 w-4 text-zinc-400" aria-hidden />
                  {doc.name}
                </span>
                <StatusBadge status={doc.processing_status} />
              </label>
            ))}
          </div>
        ) : (
          <EmptyState icon={FileText} title="No uploaded documents" body="Upload files in this wizard to create the first document set." />
        )}
        </div>
      ) : null}
      {source === "web" || source === "mcp" ? (
        <div>
          {connectorSources.length ? (
            <div className="grid gap-2">
              {connectorSources.map((connection) => (
                <label key={connection.id} className="flex items-center justify-between rounded-md border border-zinc-200 px-3 py-2">
                  <span className="flex items-center gap-2 text-sm text-zinc-800">
                    <input type="checkbox" checked={selectedConnectorIds.includes(connection.id)} onChange={() => toggleConnector(connection.id)} />
                    {source === "web" ? <Globe className="h-4 w-4 text-zinc-400" aria-hidden /> : <Plug className="h-4 w-4 text-zinc-400" aria-hidden />}
                    {connection.name}
                  </span>
                  <StatusBadge status={connection.status} />
                </label>
              ))}
            </div>
          ) : (
            <EmptyState icon={source === "web" ? Globe : Plug} title="No connector configured" body="Add a connector in Settings before selecting this source." />
          )}
        </div>
      ) : null}
    </div>
  );
}

function OrganizeStep(props: {
  kbs: KnowledgeBase[];
  knowledgeBaseId: string;
  setKnowledgeBaseId: (value: string) => void;
  categories: Category[];
  categoryId: string;
  setCategoryId: (value: string) => void;
  newCategory: string;
  setNewCategory: (value: string) => void;
  createCategory: () => void;
  tags: string;
  setTags: (value: string) => void;
  businessUnit: string;
  setBusinessUnit: (value: string) => void;
  confidentiality: Confidentiality;
  setConfidentiality: (value: Confidentiality) => void;
}) {
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-zinc-950">Organize metadata</h3>
        <p className="mt-1 text-sm text-zinc-500">Metadata follows documents into chunks and retrieval filters.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label>Knowledge base</Label>
          <Select value={props.knowledgeBaseId} onChange={(event) => props.setKnowledgeBaseId(event.target.value)}>
            {props.kbs.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Category</Label>
          <Select value={props.categoryId} onChange={(event) => props.setCategoryId(event.target.value)}>
            <option value="">Uncategorized</option>
            {props.categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.path}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label>Create category</Label>
          <div className="flex gap-2">
            <Input value={props.newCategory} onChange={(event) => props.setNewCategory(event.target.value)} />
            <Button size="icon" disabled={!props.newCategory || !props.knowledgeBaseId} onClick={props.createCategory}>
              <FolderPlus className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        </div>
        <div className="space-y-2">
          <Label>Tags</Label>
          <Input value={props.tags} onChange={(event) => props.setTags(event.target.value)} />
        </div>
        <div className="space-y-2">
          <Label>Business unit</Label>
          <Input value={props.businessUnit} onChange={(event) => props.setBusinessUnit(event.target.value)} />
        </div>
        <div className="space-y-2">
          <Label>Confidentiality</Label>
          <Select value={props.confidentiality} onChange={(event) => props.setConfidentiality(event.target.value as Confidentiality)}>
            {["Public", "Internal", "Confidential", "Restricted"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </Select>
        </div>
      </div>
    </div>
  );
}

function ProfileStep({
  title,
  options,
  value,
  onChange,
}: {
  title: string;
  options: Array<{ id: string; name: string; strategy: string }>;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-zinc-950">{title}</h3>
        <p className="mt-1 text-sm text-zinc-500">Select the profile that should be recorded on this pipeline run.</p>
      </div>
      <div className="grid gap-3">
        {options.map((option) => (
          <label
            key={option.id}
            className={`flex cursor-pointer items-center justify-between rounded-lg border p-4 ${
              value === option.id ? "border-emerald-300 bg-emerald-50" : "border-zinc-200 bg-white"
            }`}
          >
            <span>
              <span className="block font-medium text-zinc-950">{option.name}</span>
              <span className="text-sm text-zinc-500">{option.strategy}</span>
            </span>
            <input type="radio" checked={value === option.id} onChange={() => onChange(option.id)} />
          </label>
        ))}
      </div>
    </div>
  );
}

function ReviewStep({
  documents,
  connectors,
  cleanup,
  chunking,
  embedding,
}: {
  documents: DocumentRecord[];
  connectors: ConnectorConnection[];
  cleanup?: string;
  chunking?: string;
  embedding?: string;
}) {
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-zinc-950">Review and start</h3>
        <p className="mt-1 text-sm text-zinc-500">The worker will process documents asynchronously and stream progress.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Panel className="p-4">
          <p className="text-sm text-zinc-500">Cleanup</p>
          <p className="mt-1 font-semibold text-zinc-950">{cleanup ?? "Default"}</p>
        </Panel>
        <Panel className="p-4">
          <p className="text-sm text-zinc-500">Chunking</p>
          <p className="mt-1 font-semibold text-zinc-950">{chunking ?? "Default"}</p>
        </Panel>
        <Panel className="p-4">
          <p className="text-sm text-zinc-500">Embedding</p>
          <p className="mt-1 font-semibold text-zinc-950">{embedding ?? "Default"}</p>
        </Panel>
      </div>
      <div className="rounded-lg border border-zinc-200">
        {documents.map((doc) => (
          <div key={doc.id} className="flex items-center justify-between border-b border-zinc-100 px-4 py-3 last:border-0">
            <span className="text-sm font-medium text-zinc-900">{doc.name}</span>
            <StatusBadge status={doc.processing_status} />
          </div>
        ))}
        {connectors.map((connection) => (
          <div key={connection.id} className="flex items-center justify-between border-b border-zinc-100 px-4 py-3 last:border-0">
            <span className="text-sm font-medium text-zinc-900">{connection.name}</span>
            <Badge>{connection.kind}</Badge>
          </div>
        ))}
      </div>
    </div>
  );
}
