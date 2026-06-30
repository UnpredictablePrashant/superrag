"use client";

import { ErrorBox } from "@/components/error-box";
import { api } from "@/lib/api";
import { Button, Input, Label, Panel } from "@rag-console/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Mail, RotateCw, ShieldCheck } from "lucide-react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Suspense } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const emailSchema = z.object({ email: z.string().email() });
const otpSchema = z.object({ code: z.string().length(6), organizationName: z.string().optional() });

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-sm text-zinc-500">Loading sign in</div>}>
      <LoginClient />
    </Suspense>
  );
}

function LoginClient() {
  const router = useRouter();
  const params = useSearchParams();
  const invitationToken = params.get("invite") ?? undefined;
  const [email, setEmail] = React.useState("");
  const [devCode, setDevCode] = React.useState<string | null>(null);
  const [error, setError] = React.useState("");
  const [isSending, setIsSending] = React.useState(false);
  const [isVerifying, setIsVerifying] = React.useState(false);
  const emailForm = useForm<z.infer<typeof emailSchema>>({ resolver: zodResolver(emailSchema) });
  const otpForm = useForm<z.infer<typeof otpSchema>>({ resolver: zodResolver(otpSchema) });

  async function requestOtp(values: z.infer<typeof emailSchema>) {
    setError("");
    setIsSending(true);
    try {
      const result = await api<{ dev_code?: string | null }>("/auth/request-otp", {
        method: "POST",
        body: JSON.stringify({ email: values.email }),
      });
      setEmail(values.email);
      setDevCode(result.dev_code ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send OTP.");
    } finally {
      setIsSending(false);
    }
  }

  async function verifyOtp(values: z.infer<typeof otpSchema>) {
    setError("");
    setIsVerifying(true);
    try {
      const result = await api<{ needs_onboarding: boolean }>("/auth/verify-otp", {
        method: "POST",
        body: JSON.stringify({
          email,
          code: values.code,
          organization_name: values.organizationName || undefined,
          invitation_token: invitationToken,
        }),
      });
      router.replace(result.needs_onboarding ? "/onboarding" : "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not verify OTP.");
    } finally {
      setIsVerifying(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-[#f8f2ef] lg:grid-cols-[1.1fr_0.9fr]">
      <section className="flex items-center justify-center px-6 py-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3">
            <Image
              src="/brand/unitus-logo.png"
              alt="Unitus Capital"
              width={1124}
              height={181}
              priority
              className="h-9 w-auto max-w-[190px] object-contain"
            />
            <div>
              <h1 className="text-xl font-semibold text-[#083d59]">Knowledge Console</h1>
              <p className="text-sm text-zinc-500">Secure Unitus Capital knowledge access</p>
            </div>
          </div>
          <Panel className="p-6">
            <div className="mb-5">
              <h2 className="text-lg font-semibold text-zinc-950">Sign in with email</h2>
              <p className="mt-1 text-sm text-zinc-500">A short-lived code keeps the workspace passwordless.</p>
            </div>
            <ErrorBox message={error} />
            {!email ? (
              <form className="mt-5 space-y-4" onSubmit={emailForm.handleSubmit(requestOtp)}>
                <div className="space-y-2">
                  <Label htmlFor="email">Work email</Label>
                  <Input id="email" type="email" autoComplete="email" {...emailForm.register("email")} />
                  {emailForm.formState.errors.email ? (
                    <p className="text-sm text-rose-700">{emailForm.formState.errors.email.message}</p>
                  ) : null}
                </div>
                <Button className="w-full" disabled={isSending}>
                  {isSending ? <RotateCw className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                  Send code
                </Button>
              </form>
            ) : (
              <form className="mt-5 space-y-4" onSubmit={otpForm.handleSubmit(verifyOtp)}>
                <div className="rounded-md bg-[#f8d8ca] px-3 py-2 text-sm text-[#083d59]">
                  Code sent to {email}
                  {devCode ? <span className="block font-mono">Local code: {devCode}</span> : null}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="code">Six-digit code</Label>
                  <Input id="code" inputMode="numeric" autoComplete="one-time-code" {...otpForm.register("code")} />
                </div>
                <Button className="w-full" disabled={isVerifying}>
                  {isVerifying ? <RotateCw className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                  Verify and continue
                </Button>
                <Button type="button" variant="ghost" className="w-full" onClick={() => setEmail("")}>
                  Use a different email
                </Button>
              </form>
            )}
          </Panel>
        </div>
      </section>
      <section className="hidden items-center bg-[#083d59] px-12 text-white lg:flex">
        <div className="max-w-xl">
          <ShieldCheck className="h-10 w-10 text-[#f15829]" aria-hidden />
          <h2 className="mt-6 text-4xl font-semibold">Unitus Capital knowledge, answerable with evidence.</h2>
          <p className="mt-4 text-base leading-7 text-zinc-300">
            Upload internal documents, inspect data quality, control ingestion, and retrieve only the sources each
            user is allowed to see.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-3 text-sm">
            {["Tenant isolation", "Citations", "Provider control"].map((item) => (
              <div key={item} className="rounded-md border border-white/10 bg-white/5 p-3 text-[#f8f2ef]">
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
