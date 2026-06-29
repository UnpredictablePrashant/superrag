"use client";

import { ErrorBox } from "@/components/error-box";
import { api, getMe } from "@/lib/api";
import { Button, Input, Label, Panel, Select } from "@rag-console/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Building2, Database, KeyRound, Send, UploadCloud } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: getMe, retry: false });
  const [companyName, setCompanyName] = React.useState("");
  const [kbName, setKbName] = React.useState("Company Knowledge");
  const [inviteEmail, setInviteEmail] = React.useState("");
  const [provider, setProvider] = React.useState("Local");
  const [apiKey, setApiKey] = React.useState("");
  const [error, setError] = React.useState("");
  const [isBusy, setIsBusy] = React.useState(false);

  async function finish() {
    setError("");
    setIsBusy(true);
    try {
      if (me.data?.needs_onboarding) {
        await api("/organizations/current", {
          method: "POST",
          body: JSON.stringify({ name: companyName }),
        });
        await queryClient.invalidateQueries({ queryKey: ["me"] });
      }
      await api("/knowledge-bases", {
        method: "POST",
        body: JSON.stringify({ name: kbName, description: "Default onboarding knowledge base", tags: ["default"] }),
      });
      if (inviteEmail) {
        await api("/organizations/invitations", {
          method: "POST",
          body: JSON.stringify({ email: inviteEmail, role: "Member" }),
        });
      }
      if (provider !== "Local" || apiKey) {
        await api("/provider-connections", {
          method: "POST",
          body: JSON.stringify({ provider, name: `${provider} default`, api_key: apiKey || undefined }),
        });
      }
      router.replace("/data");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish onboarding.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f6f7f4] px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-zinc-950">Set up RAG Console</h1>
          <p className="mt-2 text-zinc-500">Create the tenant, seed a knowledge base, and prepare ingestion.</p>
        </div>
        <ErrorBox message={error} />
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Panel className="p-5">
            <div className="flex items-center gap-3">
              <Building2 className="h-5 w-5 text-emerald-700" aria-hidden />
              <h2 className="font-semibold text-zinc-950">Organization</h2>
            </div>
            <div className="mt-4 space-y-2">
              <Label htmlFor="company">Company name</Label>
              <Input id="company" value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
            </div>
          </Panel>
          <Panel className="p-5">
            <div className="flex items-center gap-3">
              <Database className="h-5 w-5 text-sky-700" aria-hidden />
              <h2 className="font-semibold text-zinc-950">Default knowledge base</h2>
            </div>
            <div className="mt-4 space-y-2">
              <Label htmlFor="kb">Knowledge base name</Label>
              <Input id="kb" value={kbName} onChange={(event) => setKbName(event.target.value)} />
            </div>
          </Panel>
          <Panel className="p-5">
            <div className="flex items-center gap-3">
              <Send className="h-5 w-5 text-amber-700" aria-hidden />
              <h2 className="font-semibold text-zinc-950">Invite a teammate</h2>
            </div>
            <div className="mt-4 space-y-2">
              <Label htmlFor="invite">Email</Label>
              <Input
                id="invite"
                type="email"
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
              />
            </div>
          </Panel>
          <Panel className="p-5">
            <div className="flex items-center gap-3">
              <KeyRound className="h-5 w-5 text-rose-700" aria-hidden />
              <h2 className="font-semibold text-zinc-950">AI provider</h2>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="provider">Provider</Label>
                <Select id="provider" value={provider} onChange={(event) => setProvider(event.target.value)}>
                  {["Local", "OpenAI", "Anthropic", "Google Gemini", "xAI Grok"].map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="key">API key</Label>
                <Input id="key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} />
              </div>
            </div>
          </Panel>
        </div>
        <div className="mt-6 flex justify-end">
          <Button disabled={!companyName || !kbName || isBusy} onClick={finish}>
            {isBusy ? <UploadCloud className="h-4 w-4 animate-pulse" /> : <ArrowRight className="h-4 w-4" />}
            Continue to Data Hub
          </Button>
        </div>
      </div>
    </main>
  );
}
