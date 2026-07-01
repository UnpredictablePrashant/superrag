"use client";

import { ErrorBox } from "@/components/error-box";
import { getMe, updateMe, type UserProfilePatchInput } from "@/lib/api";
import { Button, Input, Label, Panel, Textarea } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, UserCircle } from "lucide-react";
import * as React from "react";

export default function ProfilePage() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const [draft, setDraft] = React.useState<UserProfilePatchInput>({});
  const [notice, setNotice] = React.useState("");
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    const user = me.data?.user;
    if (!user) return;
    setDraft({
      full_name: user.full_name ?? "",
      job_title: user.job_title ?? "",
      department: user.department ?? "",
      phone_number: user.phone_number ?? "",
      telegram_username: user.telegram_username ?? "",
      location: user.location ?? "",
      bio: user.bio ?? "",
    });
  }, [me.data?.user]);

  const save = useMutation({
    mutationFn: () => updateMe(draft),
    onSuccess: () => {
      setNotice("Profile saved.");
      setError("");
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (err) => {
      setNotice("");
      setError(err instanceof Error ? err.message : "Could not save profile.");
    },
  });

  function update<K extends keyof UserProfilePatchInput>(key: K, value: UserProfilePatchInput[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Profile</h2>
        <p className="mt-1 text-sm text-zinc-500">Keep your workplace details current for account and collaboration context.</p>
      </div>
      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <UserCircle className="h-5 w-5 text-emerald-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Your information</h3>
        </div>
        <ErrorBox message={error} />
        {notice ? <div className="mt-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div> : null}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Email</Label>
            <Input value={me.data?.user?.email ?? ""} disabled />
          </div>
          <div className="space-y-2">
            <Label>Full name</Label>
            <Input value={draft.full_name ?? ""} onChange={(event) => update("full_name", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Job title</Label>
            <Input value={draft.job_title ?? ""} onChange={(event) => update("job_title", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Department</Label>
            <Input value={draft.department ?? ""} onChange={(event) => update("department", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Phone</Label>
            <Input value={draft.phone_number ?? ""} onChange={(event) => update("phone_number", event.target.value)} placeholder="+91..." />
          </div>
          <div className="space-y-2">
            <Label>Telegram username</Label>
            <Input value={draft.telegram_username ?? ""} onChange={(event) => update("telegram_username", event.target.value)} placeholder="@username" />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Location</Label>
            <Input value={draft.location ?? ""} onChange={(event) => update("location", event.target.value)} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Bio</Label>
            <Textarea value={draft.bio ?? ""} onChange={(event) => update("bio", event.target.value)} />
          </div>
        </div>
        <Button className="mt-5" disabled={save.isPending} onClick={() => save.mutate()}>
          <Save className="h-4 w-4" aria-hidden />
          Save profile
        </Button>
      </Panel>
    </div>
  );
}
