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
        "rounded-md px-3 py-2 text-sm font-medium transition-colors",
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
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 flex-col border-r border-border bg-surface/95 px-3 py-6 backdrop-blur md:flex">
        <div className="px-3">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Treningsanalyse
          </p>
          <p className="mt-1 text-lg font-semibold">Cockpit</p>
        </div>
        <nav className="mt-8 flex flex-1 flex-col gap-1" aria-label="Hovednavigasjon">
          {PRIMARY.map((item) => (
            <NavItem
              key={item.href}
              href={item.href}
              label={item.label}
              active={item.match(pathname)}
            />
          ))}
        </nav>
        <nav className="flex flex-col gap-1 border-t border-border pt-4" aria-label="System">
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

      {/* Mobile top brand */}
      <div className="border-b border-border bg-surface/90 px-4 py-3 backdrop-blur md:hidden">
        <p className="text-sm font-semibold">Treningsanalyse</p>
      </div>

      <div className="md:pl-56">
        <main className="mx-auto w-full max-w-6xl px-4 pb-24 pt-6 md:pb-10 md:pt-8">
          {children}
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav
        className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 px-2 py-2 backdrop-blur md:hidden"
        aria-label="Mobilnavigasjon"
      >
        <ul className="grid grid-cols-5 gap-1">
          {[...PRIMARY.slice(0, 4), { href: "/insights", label: "Mer", match: (p: string) => p.startsWith("/insights") || p.startsWith("/system") }].map(
            (item) => {
              const active = item.match(pathname);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={cn(
                      "flex flex-col items-center rounded-md px-1 py-2 text-[11px] font-medium",
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
