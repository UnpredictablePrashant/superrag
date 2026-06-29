"use client";

import { ErrorBox } from "@/components/error-box";
import { StatusBadge } from "@/components/status-badge";
import { api, ProviderConnection } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { Button, Input, Label, Panel, Select } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, KeyRound, RotateCw, Save, ShieldCheck, SlidersHorizontal } from "lucide-react";
import * as React from "react";

const tabs = [
  "Organization",
  "AI Providers",
  "Model Profiles",
  "Cleanup Profiles",
  "Chunking Profiles",
  "Embedding Profiles",
  "Notifications",
  "Security",
  "Audit Logs",
];

export default function SettingsPage() {
  const [tab, setTab] = React.useState("AI Providers");
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Settings</h2>
        <p className="mt-1 text-sm text-zinc-500">Manage tenant configuration, AI providers, security, and audit history.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item}
            className={`rounded-md px-3 py-2 text-sm font-medium ${
              tab === item ? "bg-emerald-600 text-white" : "bg-white text-zinc-700 hover:bg-zinc-100"
            }`}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </div>
      {tab === "Organization" ? <OrganizationSettings /> : null}
      {tab === "AI Providers" ? <ProviderSettings /> : null}
      {tab.includes("Profiles") ? <ProfileSettings tab={tab} /> : null}
      {tab === "Notifications" ? <Notifications /> : null}
      {tab === "Security" ? <SecuritySettings /> : null}
      {tab === "Audit Logs" ? <AuditLogs /> : null}
    </div>
  );
}

function OrganizationSettings() {
  const queryClient = useQueryClient();
  const org = useQuery({ queryKey: ["organization"], queryFn: () => api<{ id: string; name: string; settings: Record<string, unknown> }>("/organizations/current") });
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    if (org.data?.name) setName(org.data.name);
  }, [org.data?.name]);
  async function save() {
    try {
      await api("/organizations/current", { method: "PATCH", body: JSON.stringify({ name }) });
      queryClient.invalidateQueries({ queryKey: ["organization"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save organization.");
    }
  }
  return (
    <Panel className="p-5">
      <ErrorBox message={error} />
      <div className="mt-4 max-w-lg space-y-2">
        <Label htmlFor="org-name">Organization name</Label>
        <Input id="org-name" value={name} onChange={(event) => setName(event.target.value)} />
      </div>
      <Button className="mt-4" onClick={save}>
        <Save className="h-4 w-4" aria-hidden />
        Save
      </Button>
    </Panel>
  );
}

function ProviderSettings() {
  const queryClient = useQueryClient();
  const [provider, setProvider] = React.useState("OpenAI");
  const [name, setName] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [error, setError] = React.useState("");
  const connections = useQuery({
    queryKey: ["provider-connections"],
    queryFn: () => api<ProviderConnection[]>("/provider-connections"),
  });
  const capabilities = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api<Array<Record<string, unknown>>>("/provider-connections/capabilities"),
  });
  const create = useMutation({
    mutationFn: () =>
      api("/provider-connections", {
        method: "POST",
        body: JSON.stringify({ provider, name: name || `${provider} connection`, api_key: apiKey }),
      }),
    onSuccess: () => {
      setName("");
      setApiKey("");
      queryClient.invalidateQueries({ queryKey: ["provider-connections"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save provider."),
  });

  async function test(id: string) {
    setError("");
    try {
      await api(`/provider-connections/${id}/test`, { method: "POST" });
      queryClient.invalidateQueries({ queryKey: ["provider-connections"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Provider test failed.");
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-emerald-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Provider credentials</h3>
        </div>
        <ErrorBox message={error} />
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="space-y-2">
            <Label>Provider</Label>
            <Select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {["OpenAI", "Anthropic", "Google Gemini", "xAI Grok", "Local"].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>API key</Label>
            <Input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} />
          </div>
        </div>
        <Button className="mt-4" onClick={() => create.mutate()}>
          <Save className="h-4 w-4" aria-hidden />
          Save connection
        </Button>
        <div className="mt-5 divide-y divide-zinc-100">
          {(connections.data ?? []).map((connection) => (
            <div key={connection.id} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="font-medium text-zinc-950">{connection.name}</p>
                <p className="text-sm text-zinc-500">
                  {connection.provider} {connection.masked_api_key ? `- ${connection.masked_api_key}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={connection.status} />
                <Button variant="secondary" onClick={() => test(connection.id)}>
                  <RotateCw className="h-4 w-4" aria-hidden />
                  Test
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Panel>
      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-5 w-5 text-sky-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Capability registry</h3>
        </div>
        <div className="mt-4 max-h-[540px] space-y-2 overflow-auto">
          {(capabilities.data ?? []).map((capability, index) => (
            <div key={`${capability.provider}-${capability.model}-${index}`} className="rounded-md bg-zinc-50 p-3 text-sm">
              <p className="font-medium text-zinc-950">
                {String(capability.provider)} / {String(capability.model)}
              </p>
              <p className="mt-1 text-zinc-500">
                chat {String(capability.supports_chat)} | streaming {String(capability.supports_streaming)} | embeddings{" "}
                {String(capability.supports_embeddings)}
              </p>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function ProfileSettings({ tab }: { tab: string }) {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => api<Record<string, Array<Record<string, unknown>>>>("/profiles") });
  const key =
    tab === "Cleanup Profiles" ? "cleanup_profiles" : tab === "Chunking Profiles" ? "chunking_profiles" : "embedding_profiles";
  return (
    <Panel className="p-5">
      <h3 className="font-semibold text-zinc-950">{tab}</h3>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(profiles.data?.[key] ?? []).map((profile) => (
          <div key={String(profile.id)} className="rounded-md border border-zinc-200 p-4">
            <p className="font-medium text-zinc-950">{String(profile.name)}</p>
            <pre className="mt-2 overflow-auto rounded bg-zinc-50 p-2 text-xs text-zinc-600">{JSON.stringify(profile, null, 2)}</pre>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Notifications() {
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: () => api<Array<Record<string, unknown>>>("/notifications") });
  return (
    <Panel className="p-5">
      <h3 className="flex items-center gap-2 font-semibold text-zinc-950">
        <Bell className="h-5 w-5 text-amber-700" aria-hidden />
        Notifications
      </h3>
      <div className="mt-4 divide-y divide-zinc-100">
        {(notifications.data ?? []).map((notification) => (
          <div key={String(notification.id)} className="py-3">
            <p className="font-medium text-zinc-950">{String(notification.title)}</p>
            <p className="text-sm text-zinc-500">{String(notification.body)}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function SecuritySettings() {
  return (
    <Panel className="p-5">
      <h3 className="flex items-center gap-2 font-semibold text-zinc-950">
        <ShieldCheck className="h-5 w-5 text-emerald-700" aria-hidden />
        Security posture
      </h3>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {[
          "HTTP-only JWT session cookies",
          "Tenant-scoped API dependencies",
          "Encrypted provider API keys",
          "Presigned S3 uploads",
          "Prompt injection aware grounding",
          "Audit logs for sensitive actions",
        ].map((item) => (
          <div key={item} className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-700">
            {item}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function AuditLogs() {
  const logs = useQuery({ queryKey: ["audit-logs"], queryFn: () => api<Array<Record<string, unknown>>>("/audit-logs") });
  return (
    <Panel className="overflow-hidden">
      <div className="border-b border-zinc-200 px-4 py-3">
        <h3 className="font-semibold text-zinc-950">Audit Logs</h3>
      </div>
      <div className="divide-y divide-zinc-100">
        {(logs.data ?? []).map((log) => (
          <div key={String(log.id)} className="grid gap-2 px-4 py-3 lg:grid-cols-[180px_1fr_180px]">
            <span className="text-sm text-zinc-500">{shortDate(String(log.created_at))}</span>
            <span className="font-medium text-zinc-950">{String(log.action)}</span>
            <span className="text-sm text-zinc-500">{String(log.resource_type)}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
