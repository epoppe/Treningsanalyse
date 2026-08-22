"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  CalendarDays,
  ChevronDown,
  Home,
  MoreHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";

const PRIMARY_NAV = [
  { href: "/", label: "I dag", icon: Home, match: (path: string) => path === "/" },
  { href: "/plan", label: "Plan", icon: CalendarDays, match: (path: string) => path.startsWith("/plan") },
  {
    href: "/analyse",
    label: "Analyse",
    icon: BarChart3,
    match: (path: string) => path.startsWith("/analyse"),
  },
  {
    href: "/aktiviteter",
    label: "Aktiviteter",
    icon: Activity,
    match: (path: string) =>
      path.startsWith("/aktiviteter") || path.startsWith("/activities"),
  },
] as const;

const MORE_NAV = [
  { href: "/hrv", label: "HRV" },
  { href: "/sovn", label: "Søvn" },
  { href: "/body-battery", label: "Body Battery" },
  { href: "/vo2max", label: "VO₂max" },
  { href: "/training-stress", label: "Training stress" },
  { href: "/statistikk", label: "Rå statistikk" },
  { href: "/synkronisering", label: "Synkronisering" },
  { href: "/daglig-readiness", label: "Daglig readiness" },
  { href: "/analytics", label: "Løpeanalyse" },
  { href: "/ukesanalyse", label: "Løpsøkonomi" },
  { href: "/sammenhenger", label: "Sammenhenger (avansert)" },
  { href: "/training-status", label: "Treningstatus" },
] as const;

function NavLink({
  href,
  label,
  icon: Icon,
  active,
  compact = false,
}: {
  href: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  active: boolean;
  compact?: boolean;
}) {
  return (
    <Link
      href={href}
      prefetch
      className={cn(
        "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
        active
          ? "bg-slate-900 text-white"
          : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
        compact && "flex-col gap-1 px-2 py-1.5 text-[11px]",
      )}
    >
      {Icon ? <Icon className={cn("h-4 w-4", compact && "h-5 w-5")} /> : null}
      <span>{label}</span>
    </Link>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const [moreOpen, setMoreOpen] = useState(false);
  const moreActive = useMemo(
    () => MORE_NAV.some((item) => pathname === item.href || pathname.startsWith(`${item.href}/`)),
    [pathname],
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-3 py-2 md:px-4">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              Treningscockpit
            </p>
            <p className="truncate text-sm font-semibold text-slate-900">Treningsanalyse</p>
          </div>

          <nav className="hidden items-center gap-1 md:flex">
            {PRIMARY_NAV.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                label={item.label}
                icon={item.icon}
                active={item.match(pathname)}
              />
            ))}
            <div className="relative">
              <button
                type="button"
                onClick={() => setMoreOpen((open) => !open)}
                className={cn(
                  "flex items-center gap-1 rounded-lg px-3 py-2 text-sm transition-colors",
                  moreActive || moreOpen
                    ? "bg-slate-100 text-slate-900"
                    : "text-slate-600 hover:bg-slate-100",
                )}
              >
                Mer / Data
                <ChevronDown className={cn("h-4 w-4 transition", moreOpen && "rotate-180")} />
              </button>
              {moreOpen ? (
                <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
                  {MORE_NAV.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      prefetch
                      onClick={() => setMoreOpen(false)}
                      className={cn(
                        "block rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-50",
                        pathname === item.href && "bg-slate-100 font-medium text-slate-900",
                      )}
                    >
                      {item.label}
                    </Link>
                  ))}
                </div>
              ) : null}
            </div>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-3 pb-24 pt-4 md:px-4 md:pb-8">{children}</main>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 backdrop-blur md:hidden">
        <div className="mx-auto grid max-w-lg grid-cols-5">
          {PRIMARY_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              prefetch
              className={cn(
                "flex flex-col items-center gap-1 px-2 py-2 text-[10px] font-medium",
                item.match(pathname) ? "text-slate-900" : "text-slate-500",
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.label}
            </Link>
          ))}
          <Link
            href="/synkronisering"
            prefetch
            className={cn(
              "flex flex-col items-center gap-1 px-2 py-2 text-[10px] font-medium",
              moreActive ? "text-slate-900" : "text-slate-500",
            )}
          >
            <MoreHorizontal className="h-5 w-5" />
            Mer
          </Link>
        </div>
      </nav>
    </div>
  );
}
