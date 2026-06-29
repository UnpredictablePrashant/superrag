"use client";

import { ErrorBox } from "@/components/error-box";
import { api } from "@/lib/api";
import type { Role } from "@rag-console/shared-types";
import { Button, Input, Label, Panel, Select } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, Shield, UserRoundMinus } from "lucide-react";
import * as React from "react";

interface Member {
  id: string;
  user_id: string;
  email: string;
  role: Role;
  status: string;
  created_at: string;
}

const roles: Role[] = ["Owner", "Admin", "Editor", "Member", "Viewer"];

export default function TeamPage() {
  const queryClient = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<Role>("Member");
  const [error, setError] = React.useState("");
  const members = useQuery({ queryKey: ["members"], queryFn: () => api<Member[]>("/organizations/members") });
  const invite = useMutation({
    mutationFn: () =>
      api<{ invite_url: string }>("/organizations/invitations", {
        method: "POST",
        body: JSON.stringify({ email, role }),
      }),
    onError: (err) => setError(err instanceof Error ? err.message : "Could not send invitation."),
    onSuccess: () => {
      setEmail("");
      setError("");
    },
  });

  async function updateMember(memberId: string, patch: Record<string, unknown>) {
    setError("");
    try {
      await api(`/organizations/members/${memberId}`, { method: "PATCH", body: JSON.stringify(patch) });
      queryClient.invalidateQueries({ queryKey: ["members"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update member.");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Team Management</h2>
        <p className="mt-1 text-sm text-zinc-500">Invite users and enforce role-based access to product workflows.</p>
      </div>
      <ErrorBox message={error} />
      <Panel className="p-5">
        <div className="grid gap-3 lg:grid-cols-[1fr_200px_auto]">
          <div className="space-y-2">
            <Label htmlFor="invite-email">Invite email</Label>
            <Input id="invite-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="invite-role">Role</Label>
            <Select id="invite-role" value={role} onChange={(event) => setRole(event.target.value as Role)}>
              {roles.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </Select>
          </div>
          <div className="flex items-end">
            <Button disabled={!email || invite.isPending} onClick={() => invite.mutate()}>
              <Send className="h-4 w-4" aria-hidden />
              Invite
            </Button>
          </div>
        </div>
      </Panel>
      <Panel className="overflow-hidden">
        <div className="border-b border-zinc-200 px-4 py-3">
          <h3 className="font-semibold text-zinc-950">Members</h3>
        </div>
        <div className="divide-y divide-zinc-100">
          {(members.data ?? []).map((member) => (
            <div key={member.id} className="grid gap-3 px-4 py-3 lg:grid-cols-[1fr_180px_140px_auto] lg:items-center">
              <div>
                <p className="font-medium text-zinc-950">{member.email}</p>
                <p className="text-xs text-zinc-500">{member.status}</p>
              </div>
              <Select value={member.role} onChange={(event) => updateMember(member.id, { role: event.target.value })}>
                {roles.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </Select>
              <span className="inline-flex items-center gap-2 text-sm text-zinc-600">
                <Shield className="h-4 w-4" aria-hidden />
                {member.role}
              </span>
              <Button variant="secondary" onClick={() => updateMember(member.id, { status: "removed" })}>
                <UserRoundMinus className="h-4 w-4" aria-hidden />
                Remove
              </Button>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
