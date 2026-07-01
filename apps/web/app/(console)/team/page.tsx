"use client";

import { ErrorBox } from "@/components/error-box";
import { api, getMe } from "@/lib/api";
import type { Role } from "@rag-console/shared-types";
import { Button, Input, Label, Panel, Select } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, Send, Shield, UserRoundMinus } from "lucide-react";
import * as React from "react";

interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name?: string | null;
  phone_number?: string | null;
  telegram_username?: string | null;
  role: Role;
  status: string;
  created_at: string;
}

const roles: Role[] = ["Owner", "Admin", "Editor", "Member", "Viewer"];
const roleRank: Record<Role, number> = {
  Viewer: 10,
  Member: 20,
  Editor: 30,
  Admin: 40,
  Owner: 50,
};

export default function TeamPage() {
  const queryClient = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<Role>("Member");
  const [telegramUsername, setTelegramUsername] = React.useState("");
  const [telegramPhoneNumber, setTelegramPhoneNumber] = React.useState("");
  const [telegramCanIngest, setTelegramCanIngest] = React.useState(true);
  const [telegramCanAsk, setTelegramCanAsk] = React.useState(true);
  const [error, setError] = React.useState("");
  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const members = useQuery({ queryKey: ["members"], queryFn: () => api<Member[]>("/organizations/members") });
  const currentRole = me.data?.role as Role | undefined;
  const canManageTeam = currentRole === "Owner" || currentRole === "Admin";
  const manageableRoles = roles.filter((item) => currentRole && roleRank[currentRole] > roleRank[item]);
  const invite = useMutation({
    mutationFn: () =>
      api<{ invite_url: string }>("/organizations/invitations", {
        method: "POST",
        body: JSON.stringify({
          email,
          role,
          telegram_username: telegramUsername || undefined,
          telegram_phone_number: telegramPhoneNumber || undefined,
          telegram_can_ingest: telegramCanIngest,
          telegram_can_query: telegramCanAsk,
        }),
      }),
    onError: (err) => setError(err instanceof Error ? err.message : "Could not send invitation."),
    onSuccess: () => {
      setEmail("");
      setTelegramUsername("");
      setTelegramPhoneNumber("");
      setTelegramCanIngest(true);
      setTelegramCanAsk(true);
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
      {canManageTeam ? (
        <Panel className="p-5">
          <div className="grid gap-3 lg:grid-cols-[1fr_200px_auto]">
            <div className="space-y-2">
              <Label htmlFor="invite-email">Invite email</Label>
              <Input id="invite-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="invite-role">Role</Label>
              <Select id="invite-role" value={role} onChange={(event) => setRole(event.target.value as Role)}>
                {manageableRoles.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </Select>
            </div>
            <div className="flex items-end">
              <Button disabled={!email || invite.isPending || !manageableRoles.includes(role)} onClick={() => invite.mutate()}>
                <Send className="h-4 w-4" aria-hidden />
                Invite
              </Button>
            </div>
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_1fr_140px_120px] lg:items-end">
            <div className="space-y-2">
              <Label htmlFor="invite-telegram-username">Telegram username</Label>
              <Input
                id="invite-telegram-username"
                value={telegramUsername}
                onChange={(event) => setTelegramUsername(event.target.value)}
                placeholder="@username"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="invite-telegram-phone">Phone</Label>
              <Input
                id="invite-telegram-phone"
                value={telegramPhoneNumber}
                onChange={(event) => setTelegramPhoneNumber(event.target.value)}
                placeholder="+91..."
              />
            </div>
            <label className="flex h-10 items-center gap-2 text-sm text-zinc-700">
              <input type="checkbox" checked={telegramCanIngest} onChange={(event) => setTelegramCanIngest(event.target.checked)} />
              Can ingest
            </label>
            <label className="flex h-10 items-center gap-2 text-sm text-zinc-700">
              <input type="checkbox" checked={telegramCanAsk} onChange={(event) => setTelegramCanAsk(event.target.checked)} />
              Can ask
            </label>
          </div>
        </Panel>
      ) : (
        <Panel className="p-5">
          <p className="text-sm text-zinc-600">Only admins can invite users or change team roles.</p>
        </Panel>
      )}
      <Panel className="overflow-hidden">
        <div className="border-b border-zinc-200 px-4 py-3">
          <h3 className="font-semibold text-zinc-950">Members</h3>
        </div>
        <div className="divide-y divide-zinc-100">
          {(members.data ?? []).map((member) => (
            <MemberRow
              key={member.id}
              member={member}
              canManageTeam={canManageTeam}
              currentRole={currentRole}
              manageableRoles={manageableRoles}
              onUpdate={updateMember}
            />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function MemberRow({
  member,
  canManageTeam,
  currentRole,
  manageableRoles,
  onUpdate,
}: {
  member: Member;
  canManageTeam: boolean;
  currentRole: Role | undefined;
  manageableRoles: Role[];
  onUpdate: (memberId: string, patch: Record<string, unknown>) => Promise<void>;
}) {
  const canEdit = canManageTeam && canManageMember(currentRole, member.role);
  const [email, setEmail] = React.useState(member.email);
  const [fullName, setFullName] = React.useState(member.full_name ?? "");
  const [phoneNumber, setPhoneNumber] = React.useState(member.phone_number ?? "");
  const [telegramUsername, setTelegramUsername] = React.useState(member.telegram_username ?? "");

  React.useEffect(() => {
    setEmail(member.email);
    setFullName(member.full_name ?? "");
    setPhoneNumber(member.phone_number ?? "");
    setTelegramUsername(member.telegram_username ?? "");
  }, [member.email, member.full_name, member.phone_number, member.telegram_username]);

  return (
    <div className="space-y-3 px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium text-zinc-950">{member.full_name || member.email}</p>
          <p className="text-xs text-zinc-500">{member.status}</p>
        </div>
        <span className="inline-flex items-center gap-2 text-sm text-zinc-600">
          <Shield className="h-4 w-4" aria-hidden />
          {member.role}
        </span>
      </div>
      <div className="grid gap-3 xl:grid-cols-[1fr_1fr_160px_180px_150px_auto] xl:items-end">
        <div className="space-y-2">
          <Label htmlFor={`member-email-${member.id}`}>Email</Label>
          <Input id={`member-email-${member.id}`} type="email" value={email} disabled={!canEdit} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`member-name-${member.id}`}>Name</Label>
          <Input id={`member-name-${member.id}`} value={fullName} disabled={!canEdit} onChange={(event) => setFullName(event.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`member-phone-${member.id}`}>Phone</Label>
          <Input id={`member-phone-${member.id}`} value={phoneNumber} disabled={!canEdit} onChange={(event) => setPhoneNumber(event.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`member-telegram-${member.id}`}>Telegram username</Label>
          <Input
            id={`member-telegram-${member.id}`}
            value={telegramUsername}
            disabled={!canEdit}
            onChange={(event) => setTelegramUsername(event.target.value)}
            placeholder="@username"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`member-role-${member.id}`}>Role</Label>
          <Select
            id={`member-role-${member.id}`}
            value={member.role}
            disabled={!canEdit}
            onChange={(event) => onUpdate(member.id, { role: event.target.value })}
          >
            {[member.role, ...manageableRoles.filter((item) => item !== member.role)].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </Select>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={!canEdit || !email}
            onClick={() =>
              onUpdate(member.id, {
                email,
                full_name: fullName || null,
                phone_number: phoneNumber || null,
                telegram_username: telegramUsername || null,
              })
            }
          >
            <Save className="h-4 w-4" aria-hidden />
            Save
          </Button>
          <Button variant="secondary" disabled={!canEdit} onClick={() => onUpdate(member.id, { status: "removed" })}>
            <UserRoundMinus className="h-4 w-4" aria-hidden />
            Remove
          </Button>
        </div>
      </div>
    </div>
  );
}

function canManageMember(actorRole: Role | undefined, memberRole: Role) {
  return Boolean(actorRole && roleRank[actorRole] > roleRank[memberRole]);
}
