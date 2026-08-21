"use client";

import type { AthleteStateSummary } from "@/types/coaching";

function trendIcon(trend?: string | null): { icon: string; label: string } {
  const t = (trend || "").toLowerCase();
  if (t.includes("up") || t.includes("improv") || t === "↑") return { icon: "↑", label: "forbedring" };
  if (t.includes("down") || t.includes("declin") || t === "↓") return { icon: "↓", label: "nedgang" };
  if (t.includes("uncertain") || t === "?") return { icon: "?", label: "usikker" };
  return { icon: "→", label: "stabil" };
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
      className="rounded-xl border border-border bg-surface-elevated px-3 py-2.5"
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">I dag</p>
          <h2 id="athlete-state-heading" className="text-base font-semibold leading-tight text-foreground">
            {headline}
          </h2>
        </div>
      </div>
      <ul className="mt-2 grid grid-cols-3 gap-1.5">
        {dims.map((d) => (
          <li key={d.key} className="rounded-lg bg-surface-muted/80 px-2 py-1.5">
            <div className="flex items-center justify-between gap-1 text-[11px] text-muted-foreground">
              <span className="truncate">{d.label}</span>
              <span aria-label={d.trend.label} title={d.trend.label}>
                {d.trend.icon}
              </span>
            </div>
            <p className="text-sm font-semibold tabular-nums text-foreground">
              {d.value == null
                ? "—"
                : typeof d.value === "number"
                  ? Math.round(d.value)
                  : String(d.value)}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
