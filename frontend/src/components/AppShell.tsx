"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const PRIMARY = [
  { href: "/", label: "I dag", match: (p: string) => p === "/" },
  { href: "/plan", label: "Plan", match: (p: string) => p.startsWith("/plan") },
  { href: "/progress", label: "Fremgang", match: (p: string) => p.startsWith("/progress") },
  { href: "/activities", label: "Aktiviteter", match: (p: string) => p.startsWith("/activities") },
  { href: "/insights", label: "Innsikt", match: (p: string) => p.startsWith("/insights") },
];

const SECONDARY = [
  { href: "/system", label: "System", match: (p: string) => p.startsWith("/system") || p.startsWith("/synkronisering") },
];

function NavItem({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors",
        active
          ? "bg-foreground text-background"
          : "text-muted-foreground hover:bg-surface-muted hover:text-foreground"
      )}
      aria-current={active ? "page" : undefined}
    >
      {label}
    </Link>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";

  return (
    <div className="min-h-screen bg-cockpit text-foreground">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-44 flex-col border-r border-border bg-surface/95 px-2 py-4 backdrop-blur md:flex">
        <div className="px-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Treningsanalyse
          </p>
          <p className="text-base font-semibold leading-tight">Cockpit</p>
        </div>
        <nav className="mt-5 flex flex-1 flex-col gap-0.5" aria-label="Hovednavigasjon">
          {PRIMARY.map((item) => (
            <NavItem
              key={item.href}
              href={item.href}
              label={item.label}
              active={item.match(pathname)}
            />
          ))}
        </nav>
        <nav className="flex flex-col gap-0.5 border-t border-border pt-3" aria-label="System">
          {SECONDARY.map((item) => (
            <NavItem
              key={item.href}
              href={item.href}
              label={item.label}
              active={item.match(pathname)}
            />
          ))}
        </nav>
      </aside>

      <div className="border-b border-border bg-surface/90 px-3 py-2 backdrop-blur md:hidden">
        <p className="text-sm font-semibold">Treningsanalyse</p>
      </div>

      <div className="md:pl-44">
        <main className="mx-auto w-full max-w-5xl px-3 pb-20 pt-4 md:px-4 md:pb-6 md:pt-5">
          {children}
        </main>
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 px-1 py-1 backdrop-blur md:hidden"
        aria-label="Mobilnavigasjon"
      >
        <ul className="grid grid-cols-5 gap-0.5">
          {[...PRIMARY.slice(0, 4), { href: "/insights", label: "Mer", match: (p: string) => p.startsWith("/insights") || p.startsWith("/system") }].map(
            (item) => {
              const active = item.match(pathname);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={cn(
                      "flex flex-col items-center rounded-md px-1 py-1.5 text-[10px] font-medium",
                      active ? "text-foreground" : "text-muted-foreground"
                    )}
                    aria-current={active ? "page" : undefined}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            }
          )}
        </ul>
      </nav>
    </div>
  );
}
