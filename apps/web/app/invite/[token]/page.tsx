"use client";

import { Button, Panel } from "@rag-console/ui";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function InvitePage() {
  const params = useParams<{ token: string }>();
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f6f7f4] px-6">
      <Panel className="w-full max-w-md p-6 text-center">
        <MailCheck className="mx-auto h-10 w-10 text-emerald-700" aria-hidden />
        <h1 className="mt-4 text-xl font-semibold text-zinc-950">Accept your invitation</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Sign in with the invited email address. The invitation token will be attached to your verified session.
        </p>
        <Link href={`/login?invite=${params.token}`}>
          <Button className="mt-6 w-full">Continue with email OTP</Button>
        </Link>
      </Panel>
    </main>
  );
}
