"use client";

import { getMe } from "@/lib/api";
import { Button, cn } from "@rag-console/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  BookOpen,
  ClipboardList,
  DatabaseZap,
  Files,
  LogOut,
  MessageSquare,
  Settings,
  Sparkles,
  UserCircle,
  Users,
} from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

const nav = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/directory", label: "Directory", icon: Files },
  { href: "/profile", label: "Profile", icon: UserCircle },
  { href: "/data", label: "Data Hub", icon: DatabaseZap, adminOnly: true },
  { href: "/activity", label: "Activity", icon: ClipboardList, adminOnly: true },
  { href: "/team", label: "Team", icon: Users, adminOnly: true },
  { href: "/help", label: "Docs", icon: BookOpen, adminOnly: true },
  { href: "/settings", label: "Admin Settings", icon: Settings, adminOnly: true },
];

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: getMe, retry: false });
  const canUseAdminNav = me.data?.role === "Owner" || me.data?.role === "Admin";
  const visibleNav = nav.filter((item) => !item.adminOnly || canUseAdminNav);
  const isChatRoute = pathname.startsWith("/chat");

  React.useEffect(() => {
    if (me.isError) router.replace("/login");
    if (me.data?.needs_onboarding) router.replace("/onboarding");
  }, [me.data?.needs_onboarding, me.isError, router]);

  async function logout() {
    await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api"}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    queryClient.clear();
    router.replace("/login");
  }

  if (me.isLoading) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-zinc-500">Loading console</div>;
  }

  return (
    <div className="min-h-[100dvh] bg-[#f8f2ef]">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-72 border-r border-[#e8d9d2] bg-white lg:block">
        <div className="flex h-full flex-col">
          <div className="flex h-20 flex-col items-start justify-center border-b border-[#e8d9d2] px-5">
            <Image
              src="/brand/unitus-logo.png"
              alt="Unitus Capital"
              width={1124}
              height={181}
              className="h-7 w-auto max-w-[175px] object-contain"
            />
            <div className="mt-1">
              <p className="text-sm font-semibold text-[#083d59]">Knowledge Console</p>
              <p className="text-xs text-zinc-500">{me.data?.organization?.name ?? "No organization"}</p>
            </div>
          </div>
          <nav className="flex-1 space-y-1 px-3 py-4">
            {visibleNav.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition",
                    active ? "bg-[#f8d8ca] text-[#083d59]" : "text-zinc-600 hover:bg-[#f8f2ef] hover:text-[#083d59]",
                  )}
                >
                  <item.icon className="h-4 w-4" aria-hidden />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="border-t border-zinc-200 p-4">
            <div className="mb-4 rounded-md bg-amber-50 p-3 text-sm text-amber-900">
              <div className="flex items-center gap-2 font-medium">
                <Sparkles className="h-4 w-4" aria-hidden />
                {me.data?.role ?? "Member"}
              </div>
              <p className="mt-1 text-xs text-amber-800">{me.data?.user?.email}</p>
            </div>
            <Button variant="ghost" className="w-full justify-start" onClick={logout}>
              <LogOut className="h-4 w-4" aria-hidden />
              Sign out
            </Button>
          </div>
        </div>
      </aside>
      <div className="lg:pl-72">
        <header
          className={cn(
            "sticky top-0 z-10 flex min-h-14 items-center justify-between gap-3 border-b border-[#e8d9d2] bg-white/95 px-3 py-2 backdrop-blur lg:min-h-16 lg:px-8",
            isChatRoute && "hidden lg:flex",
          )}
        >
          <div className="min-w-0">
            <p className="hidden text-sm font-medium text-zinc-500 sm:block">Connected company knowledge</p>
            <h1 className="truncate text-base font-semibold text-[#083d59] lg:text-lg">
              {me.data?.organization?.name ?? "Unitus Capital"}
            </h1>
          </div>
          <div className="flex flex-none items-center gap-2">
            <Button variant="secondary" size="icon" title="Notifications">
              <Bell className="h-4 w-4" aria-hidden />
            </Button>
            <Link className="hidden sm:block" href="/chat">
              <Button>
                <MessageSquare className="h-4 w-4" aria-hidden />
                Chat
              </Button>
            </Link>
          </div>
        </header>
        <main
          className={cn(
            "px-3 py-4 pb-[calc(5rem+env(safe-area-inset-bottom))] lg:px-8 lg:py-6 lg:pb-6",
            isChatRoute && "h-[100dvh] overflow-hidden p-0 lg:h-auto lg:overflow-visible lg:px-8 lg:py-6",
          )}
        >
          {children}
        </main>
      </div>
      {!isChatRoute ? (
        <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-[#e8d9d2] bg-white/95 px-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_24px_rgba(8,61,89,0.08)] backdrop-blur lg:hidden">
          <div className="flex gap-1 overflow-x-auto">
            {visibleNav.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex min-w-16 flex-1 flex-col items-center justify-center gap-1 rounded-md px-2 py-2 text-[11px] font-medium transition",
                    active ? "bg-[#f8d8ca] text-[#083d59]" : "text-zinc-600 hover:bg-[#f8f2ef] hover:text-[#083d59]",
                  )}
                >
                  <item.icon className="h-4 w-4" aria-hidden />
                  <span className="max-w-16 truncate">{item.label}</span>
                </Link>
              );
            })}
          </div>
        </nav>
      ) : null}
    </div>
  );
}
