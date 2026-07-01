"use client";

import { EmptyState } from "@/components/empty-state";
import { ErrorBox } from "@/components/error-box";
import {
  createRelationshipActionItem,
  deleteAllRelationships,
  discoverWebRelationships,
  getRelationshipEntity,
  getLatestRelationshipScan,
  getRelationshipSummary,
  listRelationshipActionItems,
  listRelationshipDeals,
  listRelationshipEntities,
  listRelationshipInteractions,
  RelationshipActionItem,
  RelationshipDeal,
  RelationshipEntity,
  RelationshipInteraction,
  RelationshipScanRun,
  rescanRelationships,
  updateRelationshipActionItem,
} from "@/lib/api";
import { shortDate } from "@/lib/format";
import { Badge, Button, Input, Label, Panel, Select, Textarea } from "@rag-console/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  BriefcaseBusiness,
  Building2,
  CalendarClock,
  Check,
  Globe,
  Handshake,
  ListTodo,
  MessageSquare,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

const ENTITY_TYPES = [
  { value: "", label: "All" },
  { value: "company", label: "Companies" },
  { value: "investor", label: "Investors" },
  { value: "person", label: "People" },
];

export default function RelationshipsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = React.useState("");
  const [entityType, setEntityType] = React.useState("");
  const [selectedEntityId, setSelectedEntityId] = React.useState("");
  const [webQuery, setWebQuery] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [error, setError] = React.useState("");
  const summary = useQuery({ queryKey: ["relationships-summary"], queryFn: getRelationshipSummary, refetchInterval: 15000 });
  const latestScan = useQuery({
    queryKey: ["relationship-scan-latest"],
    queryFn: getLatestRelationshipScan,
    refetchInterval: (query) => (isActiveScan(query.state.data) ? 5000 : 15000),
  });
  const entities = useQuery({
    queryKey: ["relationship-entities", search, entityType],
    queryFn: () => listRelationshipEntities({ search, entity_type: entityType }),
  });
  const entityDetail = useQuery({
    queryKey: ["relationship-entity", selectedEntityId],
    enabled: Boolean(selectedEntityId),
    queryFn: () => getRelationshipEntity(selectedEntityId),
  });
  const interactions = useQuery({ queryKey: ["relationship-interactions"], queryFn: listRelationshipInteractions });
  const deals = useQuery({ queryKey: ["relationship-deals"], queryFn: listRelationshipDeals });
  const actions = useQuery({ queryKey: ["relationship-actions"], queryFn: () => listRelationshipActionItems("open") });
  const selectedEntity = entityDetail.data;
  const activeScan = isActiveScan(latestScan.data);

  React.useEffect(() => {
    if (!selectedEntityId && entities.data?.[0]) setSelectedEntityId(entities.data[0].id);
  }, [entities.data, selectedEntityId]);

  async function rescan() {
    setNotice("");
    setError("");
    try {
      const run = await rescanRelationships();
      setNotice(isActiveScan(run) ? "Relationship scan is already running in the background." : "Relationship scan queued. OpenAI will verify candidates before adding records.");
      await queryClient.invalidateQueries({ queryKey: ["relationship-scan-latest"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rescan relationship intelligence.");
    }
  }

  async function discoverWeb() {
    setNotice("");
    setError("");
    try {
      await discoverWebRelationships(webQuery || undefined);
      setNotice("Internet discovery queued. OpenAI web search and verification will run in the background.");
      setWebQuery("");
      await queryClient.invalidateQueries({ queryKey: ["relationship-scan-latest"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start internet discovery.");
    }
  }

  async function clearAll() {
    setNotice("");
    setError("");
    if (!window.confirm("Delete all relationship intelligence records and scan history? Indexed documents and existing app data will stay untouched.")) {
      return;
    }
    try {
      const result = await deleteAllRelationships();
      const count = Object.values(result.deleted).reduce((sum, value) => sum + value, 0);
      setNotice(`Deleted ${count} relationship intelligence record(s).`);
      setSelectedEntityId("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["relationships-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["relationship-entities"] }),
        queryClient.invalidateQueries({ queryKey: ["relationship-interactions"] }),
        queryClient.invalidateQueries({ queryKey: ["relationship-deals"] }),
        queryClient.invalidateQueries({ queryKey: ["relationship-actions"] }),
        queryClient.invalidateQueries({ queryKey: ["relationship-scan-latest"] }),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete relationship intelligence records.");
    }
  }

  async function markActionDone(action: RelationshipActionItem) {
    setError("");
    try {
      await updateRelationshipActionItem(action.id, { status: "done" });
      queryClient.invalidateQueries({ queryKey: ["relationship-actions"] });
      queryClient.invalidateQueries({ queryKey: ["relationships-summary"] });
      if (selectedEntityId) queryClient.invalidateQueries({ queryKey: ["relationship-entity", selectedEntityId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update action item.");
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 xl:flex-row xl:items-end">
        <div>
          <h2 className="text-2xl font-semibold text-zinc-950">Relationship Intelligence</h2>
          <p className="mt-1 text-sm text-zinc-500">
            AI-prepared clients, investors, contacts, meetings, deals, evidence, and follow-ups from indexed knowledge.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/chat">
            <Button variant="secondary">
              <MessageSquare className="h-4 w-4" aria-hidden />
              Chat
            </Button>
          </Link>
          <Button variant="secondary" disabled={activeScan} onClick={() => void discoverWeb()}>
            <Globe className="h-4 w-4" aria-hidden />
            Find Internet Leads
          </Button>
          <Button variant="secondary" disabled={activeScan} onClick={() => void clearAll()}>
            <Trash2 className="h-4 w-4" aria-hidden />
            Delete All
          </Button>
          <Button disabled={activeScan} onClick={() => void rescan()}>
            <RefreshCw className="h-4 w-4" aria-hidden />
            {activeScan ? "Scanning" : "Rescan"}
          </Button>
        </div>
      </div>

      <ErrorBox message={error} />
      {notice ? <div className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div> : null}
      <ScanStatusPanel scan={latestScan.data} />

      <Panel className="p-4">
        <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
          <div>
            <Label>Internet discovery query</Label>
            <Input
              className="mt-2"
              value={webQuery}
              onChange={(event) => setWebQuery(event.target.value)}
              placeholder="Optional: fintech growth investors in India with public contact emails"
              disabled={activeScan}
            />
          </div>
          <div className="flex items-end">
            <Button variant="secondary" disabled={activeScan} onClick={() => void discoverWeb()}>
              <Globe className="h-4 w-4" aria-hidden />
              Discover
            </Button>
          </div>
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          Uses the backend OpenAI provider key for web search and classification. The API key is never sent to the browser.
        </p>
      </Panel>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <Metric label="Relationships" value={summary.data?.entity_count ?? 0} icon={Handshake} />
        <Metric label="Clients" value={summary.data?.client_count ?? 0} icon={Building2} />
        <Metric label="Investors" value={summary.data?.investor_count ?? 0} icon={BriefcaseBusiness} />
        <Metric label="Open Actions" value={summary.data?.open_action_count ?? 0} icon={ListTodo} tone={summary.data?.overdue_action_count ? "amber" : "neutral"} />
        <Metric label="Deals" value={summary.data?.deal_count ?? 0} icon={Sparkles} />
      </div>

      <div className="grid gap-4 2xl:grid-cols-[minmax(520px,0.95fr)_minmax(620px,1.25fr)]">
        <Panel className="overflow-hidden">
          <div className="border-b border-zinc-200 p-4">
            <div className="flex flex-col gap-3 lg:flex-row">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" aria-hidden />
                <Input className="pl-9" placeholder="Search clients, investors, people" value={search} onChange={(event) => setSearch(event.target.value)} />
              </div>
              <Select className="lg:w-44" value={entityType} onChange={(event) => setEntityType(event.target.value)}>
                {ENTITY_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <RelationshipTable entities={entities.data ?? []} selectedId={selectedEntityId} onSelect={setSelectedEntityId} />
        </Panel>

        <EntityDetailPanel
          entity={selectedEntity}
          isLoading={entityDetail.isLoading}
          onActionSaved={() => {
            queryClient.invalidateQueries({ queryKey: ["relationship-actions"] });
            queryClient.invalidateQueries({ queryKey: ["relationships-summary"] });
            if (selectedEntityId) queryClient.invalidateQueries({ queryKey: ["relationship-entity", selectedEntityId] });
          }}
          onActionDone={markActionDone}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr_0.9fr]">
        <TimelinePanel interactions={interactions.data ?? []} />
        <DealsPanel deals={deals.data ?? []} />
        <ActionsPanel actions={actions.data ?? []} onDone={markActionDone} />
      </div>
    </div>
  );
}

function RelationshipTable({
  entities,
  selectedId,
  onSelect,
}: {
  entities: RelationshipEntity[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  if (!entities.length) {
    return <EmptyState icon={Handshake} title="No relationships yet" body="Run ingestion or rescan indexed documents to prepare client and investor intelligence." />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-zinc-200 text-sm">
        <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
          <tr>
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Last touch</th>
            <th className="px-4 py-3">Next action</th>
            <th className="px-4 py-3">Evidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white">
          {entities.map((entity) => (
            <tr key={entity.id} className={selectedId === entity.id ? "bg-orange-50" : "hover:bg-zinc-50"}>
              <td className="max-w-72 px-4 py-3">
                <button className="w-full text-left" onClick={() => onSelect(entity.id)}>
                  <span className="block truncate font-medium text-zinc-950">{entity.name}</span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    {entity.role_names.slice(0, 3).map((role) => (
                      <Badge key={role}>{labelize(role)}</Badge>
                    ))}
                    {entity.open_action_count ? <Badge tone="amber">{entity.open_action_count} open</Badge> : null}
                  </span>
                </button>
              </td>
              <td className="px-4 py-3 text-zinc-700">{labelize(entity.entity_type)}</td>
              <td className="px-4 py-3 text-zinc-700">{entity.last_interaction_at ? shortDate(entity.last_interaction_at) : "No meeting"}</td>
              <td className="px-4 py-3 text-zinc-700">{entity.next_action_at ? shortDate(entity.next_action_at) : "None"}</td>
              <td className="px-4 py-3 text-zinc-700">{entity.evidence_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScanStatusPanel({ scan }: { scan?: RelationshipScanRun | null }) {
  if (!scan) {
    return (
      <Panel className="p-4">
        <div className="flex items-center gap-2 text-sm text-zinc-600">
          <Sparkles className="h-4 w-4 text-[#e3602a]" aria-hidden />
          OpenAI verification is required before new relationship records are added.
        </div>
      </Panel>
    );
  }
  const active = isActiveScan(scan);
  const progress = scan.total_count ? Math.round((scan.processed_count / Math.max(1, scan.total_count)) * 100) : 0;
  return (
    <Panel className="p-4">
      <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={active ? "amber" : scan.status === "failed" ? "red" : "green"}>{labelize(scan.status)}</Badge>
            <span className="text-sm font-medium text-zinc-950">{labelize(scan.scan_type)} scan</span>
            {active ? <span className="text-sm text-zinc-500">running in background</span> : null}
          </div>
          <p className="mt-1 text-sm text-zinc-600">
            {scan.last_scanned_document_name ? `Last scanned file: ${scan.last_scanned_document_name}` : "No file scanned yet"}
            {scan.completed_at ? ` / completed ${shortDate(scan.completed_at)}` : ""}
            {scan.error ? ` / ${scan.error}` : ""}
          </p>
        </div>
        <div className="min-w-52">
          <div className="flex justify-between text-xs text-zinc-500">
            <span>{scan.processed_count}/{scan.total_count || 0}</span>
            <span>{progress}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-100">
            <div className="h-full bg-[#e3602a]" style={{ width: `${active ? Math.max(8, progress) : progress}%` }} />
          </div>
        </div>
      </div>
    </Panel>
  );
}

function EntityDetailPanel({
  entity,
  isLoading,
  onActionSaved,
  onActionDone,
}: {
  entity?: RelationshipEntity;
  isLoading: boolean;
  onActionSaved: () => void;
  onActionDone: (action: RelationshipActionItem) => void;
}) {
  const [tab, setTab] = React.useState<"overview" | "interactions" | "deals" | "actions" | "evidence" | "chat">("overview");
  React.useEffect(() => setTab("overview"), [entity?.id]);
  if (isLoading) return <Panel className="p-5 text-sm text-zinc-500">Loading relationship</Panel>;
  if (!entity) return <Panel className="p-5"><EmptyState icon={Handshake} title="Select a relationship" body="Choose a client, investor, or contact to inspect the structured profile." /></Panel>;
  return (
    <Panel className="overflow-hidden">
      <div className="border-b border-zinc-200 p-5">
        <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-lg font-semibold text-zinc-950">{entity.name}</h3>
              <Badge tone={entity.status === "suggested" ? "amber" : "green"}>{labelize(entity.status)}</Badge>
              <Badge tone="blue">{labelize(entity.entity_type)}</Badge>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">{entity.summary ?? "No summary generated yet."}</p>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-xs text-zinc-500">
            <MiniStat label="Evidence" value={entity.evidence_count} />
            <MiniStat label="Actions" value={entity.open_action_count} />
            <MiniStat label="Confidence" value={Math.round((entity.confidence ?? 0) * 100)} suffix="%" />
          </div>
        </div>
        <div className="mt-4 flex gap-1 overflow-x-auto">
          {[
            ["overview", "Overview"],
            ["interactions", "Interactions"],
            ["deals", "Deals"],
            ["actions", "Actions"],
            ["evidence", "Evidence"],
            ["chat", "Chat"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={`rounded-md px-3 py-2 text-sm font-medium ${tab === id ? "bg-[#f8d8ca] text-[#083d59]" : "text-zinc-600 hover:bg-zinc-100"}`}
              onClick={() => setTab(id as typeof tab)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="p-5">
        {tab === "overview" ? <Overview entity={entity} /> : null}
        {tab === "interactions" ? <TimelinePanel interactions={entity.interactions ?? []} embedded /> : null}
        {tab === "deals" ? <DealsPanel deals={entity.deals ?? []} embedded /> : null}
        {tab === "actions" ? (
          <div className="space-y-4">
            <ActionComposer entity={entity} onSaved={onActionSaved} />
            <ActionList actions={entity.action_items ?? []} onDone={onActionDone} />
          </div>
        ) : null}
        {tab === "evidence" ? <EvidenceList entity={entity} /> : null}
        {tab === "chat" ? <ScopedChat entity={entity} onActionSaved={onActionSaved} /> : null}
      </div>
    </Panel>
  );
}

function Overview({ entity }: { entity: RelationshipEntity }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Info label="Relationship Roles" value={entity.role_names.map(labelize).join(", ") || "Not classified"} />
      <Info label="Last Communicated" value={entity.last_interaction_at ? shortDate(entity.last_interaction_at) : "No interaction detected"} />
      <Info label="Next Action" value={entity.next_action_at ? shortDate(entity.next_action_at) : "No open dated action"} />
      <Info label="Sector / Geography" value={[entity.sector, entity.geography].filter(Boolean).join(" / ") || "Not detected"} />
      <div className="lg:col-span-2">
        <h4 className="text-sm font-semibold text-zinc-950">Recent evidence signal</h4>
        <p className="mt-2 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm leading-6 text-zinc-700">
          {entity.evidence?.[0]?.excerpt ?? "Evidence will appear as documents and meeting notes are processed."}
        </p>
      </div>
    </div>
  );
}

function TimelinePanel({ interactions, embedded = false }: { interactions: RelationshipInteraction[]; embedded?: boolean }) {
  const body = (
    <div className="space-y-3">
      {interactions.slice(0, embedded ? 8 : 6).map((interaction) => (
        <div key={interaction.id} className="border-b border-zinc-100 pb-3 last:border-0 last:pb-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="blue">{labelize(interaction.interaction_type)}</Badge>
            <span className="text-sm font-medium text-zinc-950">{interaction.title}</span>
          </div>
          <p className="mt-1 text-xs text-zinc-500">
            {interaction.occurred_at ? shortDate(interaction.occurred_at) : shortDate(interaction.created_at)} / {labelize(interaction.source_type)}
          </p>
          <p className="mt-2 text-sm leading-6 text-zinc-600">{interaction.summary ?? "No summary yet."}</p>
        </div>
      ))}
      {!interactions.length ? <p className="text-sm text-zinc-500">No interactions detected yet.</p> : null}
    </div>
  );
  if (embedded) return body;
  return (
    <Panel className="p-5">
      <div className="mb-4 flex items-center gap-2">
        <CalendarClock className="h-5 w-5 text-sky-700" aria-hidden />
        <h3 className="font-semibold text-zinc-950">Recent Interactions</h3>
      </div>
      {body}
    </Panel>
  );
}

function DealsPanel({ deals, embedded = false }: { deals: RelationshipDeal[]; embedded?: boolean }) {
  const body = (
    <div className="space-y-3">
      {deals.slice(0, embedded ? 8 : 6).map((deal) => (
        <div key={deal.id} className="border-b border-zinc-100 pb-3 last:border-0 last:pb-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="amber">{labelize(deal.stage)}</Badge>
            <span className="text-sm font-medium text-zinc-950">{deal.name}</span>
          </div>
          <p className="mt-1 text-xs text-zinc-500">
            {labelize(deal.deal_type)}
            {deal.amount ? ` / ${deal.currency ?? ""} ${compactAmount(deal.amount)}` : ""}
          </p>
          <p className="mt-2 text-sm leading-6 text-zinc-600">{deal.summary ?? "No deal summary yet."}</p>
        </div>
      ))}
      {!deals.length ? <p className="text-sm text-zinc-500">No deal signals detected yet.</p> : null}
    </div>
  );
  if (embedded) return body;
  return (
    <Panel className="p-5">
      <div className="mb-4 flex items-center gap-2">
        <BriefcaseBusiness className="h-5 w-5 text-violet-700" aria-hidden />
        <h3 className="font-semibold text-zinc-950">Deal Signals</h3>
      </div>
      {body}
    </Panel>
  );
}

function ActionsPanel({ actions, onDone }: { actions: RelationshipActionItem[]; onDone: (action: RelationshipActionItem) => void }) {
  return (
    <Panel className="p-5">
      <div className="mb-4 flex items-center gap-2">
        <ListTodo className="h-5 w-5 text-emerald-700" aria-hidden />
        <h3 className="font-semibold text-zinc-950">Open Actions</h3>
      </div>
      <ActionList actions={actions} onDone={onDone} />
    </Panel>
  );
}

function ActionList({ actions, onDone }: { actions: RelationshipActionItem[]; onDone: (action: RelationshipActionItem) => void }) {
  return (
    <div className="space-y-3">
      {actions.map((action) => (
        <div key={action.id} className="rounded-md border border-zinc-200 p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={action.priority === "high" ? "red" : action.priority === "low" ? "green" : "amber"}>{labelize(action.priority)}</Badge>
                <span className="text-sm font-medium text-zinc-950">{action.title}</span>
              </div>
              <p className="mt-1 text-xs text-zinc-500">
                {action.entity_name ?? "No relationship"} {action.due_at ? `/ due ${shortDate(action.due_at)}` : ""}
              </p>
            </div>
            {action.status === "open" ? (
              <Button size="icon" variant="ghost" title="Mark done" onClick={() => onDone(action)}>
                <Check className="h-4 w-4" aria-hidden />
              </Button>
            ) : null}
          </div>
          {action.description ? <p className="mt-2 text-sm leading-6 text-zinc-600">{action.description}</p> : null}
        </div>
      ))}
      {!actions.length ? <p className="text-sm text-zinc-500">No open action items.</p> : null}
    </div>
  );
}

function ActionComposer({ entity, onSaved }: { entity: RelationshipEntity; onSaved: () => void }) {
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [priority, setPriority] = React.useState<"low" | "medium" | "high">("medium");
  const [due, setDue] = React.useState("");
  const [error, setError] = React.useState("");
  async function save() {
    if (!title.trim()) return;
    setError("");
    try {
      await createRelationshipActionItem({
        title,
        description: description || undefined,
        relationship_entity_id: entity.id,
        priority,
        due_at: due ? new Date(`${due}T12:00:00`).toISOString() : undefined,
      });
      setTitle("");
      setDescription("");
      setDue("");
      setPriority("medium");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create action item.");
    }
  }
  return (
    <div className="rounded-md border border-zinc-200 p-4">
      <div className="grid gap-3 md:grid-cols-[1fr_150px_150px_auto]">
        <div className="space-y-2">
          <Label>Action</Label>
          <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={`Follow up with ${entity.name}`} />
        </div>
        <div className="space-y-2">
          <Label>Priority</Label>
          <Select value={priority} onChange={(event) => setPriority(event.target.value as "low" | "medium" | "high")}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Due</Label>
          <Input type="date" value={due} onChange={(event) => setDue(event.target.value)} />
        </div>
        <div className="flex items-end">
          <Button onClick={() => void save()}>
            <ListTodo className="h-4 w-4" aria-hidden />
            Add
          </Button>
        </div>
      </div>
      <Textarea className="mt-3 min-h-20" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Optional context" />
      <ErrorBox message={error} />
    </div>
  );
}

function EvidenceList({ entity }: { entity: RelationshipEntity }) {
  const evidence = entity.evidence ?? [];
  return (
    <div className="space-y-3">
      {evidence.map((item) => (
        <div key={item.id} className="border-b border-zinc-100 pb-3 last:border-0 last:pb-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="blue">{labelize(item.source_type)}</Badge>
            <span className="text-sm font-medium text-zinc-950">{labelize(item.field_name)}</span>
            {item.confidence ? <Badge>{Math.round(item.confidence * 100)}%</Badge> : null}
          </div>
          {item.source_url ? <p className="mt-1 break-all text-xs text-sky-700">{item.source_url}</p> : null}
          <p className="mt-2 text-sm leading-6 text-zinc-600">{item.excerpt ?? "No excerpt stored."}</p>
        </div>
      ))}
      {!evidence.length ? <p className="text-sm text-zinc-500">No evidence rows yet.</p> : null}
    </div>
  );
}

function ScopedChat({ entity, onActionSaved }: { entity: RelationshipEntity; onActionSaved: () => void }) {
  const prompts = [
    `What did we last discuss with ${entity.name}?`,
    `Summarize open action items for ${entity.name}.`,
    `What changed recently for ${entity.name}?`,
  ];
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-zinc-200 p-4">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-[#e3602a]" aria-hidden />
          <h4 className="font-semibold text-zinc-950">Relationship chat prompts</h4>
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          {prompts.map((prompt) => (
            <Link
              key={prompt}
              href="/chat"
              className="rounded-md border border-zinc-200 p-3 text-sm leading-6 text-zinc-700 hover:bg-zinc-50"
            >
              {prompt}
            </Link>
          ))}
        </div>
      </div>
      <ActionComposer entity={entity} onSaved={onActionSaved} />
    </div>
  );
}

function Metric({ label, value, icon: Icon, tone = "neutral" }: { label: string; value: number; icon: typeof Handshake; tone?: "neutral" | "amber" }) {
  return (
    <Panel className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-zinc-500">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-zinc-950">{value}</p>
        </div>
        <span className={`flex h-10 w-10 items-center justify-center rounded-md ${tone === "amber" ? "bg-amber-50 text-amber-700" : "bg-sky-50 text-sky-700"}`}>
          <Icon className="h-5 w-5" aria-hidden />
        </span>
      </div>
    </Panel>
  );
}

function MiniStat({ label, value, suffix = "" }: { label: string; value: number; suffix?: string }) {
  return (
    <div className="rounded-md border border-zinc-200 px-3 py-2">
      <p className="text-base font-semibold text-zinc-950">
        {value}
        {suffix}
      </p>
      <p>{label}</p>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-200 p-3">
      <p className="text-xs font-semibold uppercase text-zinc-500">{label}</p>
      <p className="mt-1 text-sm text-zinc-800">{value}</p>
    </div>
  );
}

function labelize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function compactAmount(value: number) {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function isActiveScan(scan?: RelationshipScanRun | null) {
  return Boolean(scan && ["queued", "running"].includes(scan.status));
}
