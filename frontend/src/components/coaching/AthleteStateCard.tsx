"use client";

import type { AthleteStateSummary } from "@/types/coaching";
import { StatusBadge } from "./ui-states";

function trendIcon(trend?: string | null): { icon: string; label: string } {
  const t = (trend || "").toLowerCase();
  if (t.includes("up") || t.includes("improv") || t === "↑") return { icon: "↑", label: "forbedring" };
  if (t.includes("down") || t.includes("declin") || t === "↓") return { icon: "↓", label: "nedgang" };
  if (t.includes("uncertain") || t === "?") return { icon: "?", label: "usikker" };
  return { icon: "→", label: "stabil" };
}

function dimStatus(name: string, value: unknown): "positive" | "neutral" | "warning" | "muted" {
  if (value == null) return "muted";
  if (name === "recovery" && typeof value === "number" && value < 40) return "warning";
  if (name === "fatigue" && typeof value === "number" && value > 70) return "warning";
  return "neutral";
}

const LABELS: Record<string, string> = {
  fitness: "Form",
  recovery: "Restitusjon",
  fatigue: "Tretthet",
  durability: "Holdbarhet",
};

export function AthleteStateCard({ state }: { state?: AthleteStateSummary | null }) {
  const dims = ["fitness", "recovery", "fatigue"].map((key) => {
    const d = state?.[key];
    const trend = trendIcon(d?.trend);
    return {
      key,
      label: LABELS[key] || key,
      value: d?.value,
      trend,
      status: dimStatus(key, d?.value),
    };
  });

  const recovery = state?.recovery?.value;
  const headline =
    recovery == null
      ? "Status ufullstendig"
      : typeof recovery === "number" && recovery < 45
        ? "Restitusjon anbefales"
        : "Klar for vanlig trening";

  return (
    <section
      aria-labelledby="athlete-state-heading"
      className="rounded-2xl border border-border bg-surface-elevated p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">I dag</p>
          <h2 id="athlete-state-heading" className="mt-1 text-xl font-semibold text-foreground">
            {headline}
          </h2>
        </div>
        <StatusBadge status="info" label="Athlete state" />
      </div>
      <ul className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {dims.map((d) => (
          <li key={d.key} className="rounded-xl bg-surface-muted/80 px-3 py-3">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>{d.label}</span>
              <span aria-label={d.trend.label} title={d.trend.label}>
                {d.trend.icon}
              </span>
            </div>
            <p className="mt-1 text-base font-medium text-foreground">
              {d.value == null
                ? "Mangler"
                : typeof d.value === "number"
                  ? Math.round(d.value)
                  : String(d.value)}
            </p>
            <StatusBadge
              status={d.value == null ? "muted" : d.status}
              label={d.value == null ? "missing" : d.trend.label}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
