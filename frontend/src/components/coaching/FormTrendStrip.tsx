"use client";

import type { AthleteStateSummary } from "@/types/coaching";

function arrow(trend?: string | null) {
  const t = (trend || "").toLowerCase();
  if (t.includes("up") || t.includes("improv")) return "↑";
  if (t.includes("down") || t.includes("declin")) return "↓";
  if (t.includes("uncertain")) return "?";
  return "→";
}

export function FormTrendStrip({ state }: { state?: AthleteStateSummary | null }) {
  const items = [
    { key: "fitness", label: "Form" },
    { key: "fatigue", label: "Tretthet" },
    { key: "recovery", label: "Restitusjon" },
  ];
  const hasSignal = items.some((item) => {
    const d = state?.[item.key];
    return d?.trend != null || (d?.value != null && Number(d.value) !== 0);
  });
  return (
    <section aria-label="Formtrend" className="rounded-xl border border-border bg-surface px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="text-xs font-semibold text-foreground">Formtrend</h2>
        {!hasSignal ? (
          <p className="text-[11px] text-muted-foreground">Lite historikk</p>
        ) : null}
        <ul className="flex flex-wrap gap-x-3 gap-y-0.5">
          {items.map((item) => {
            const d = state?.[item.key];
            const trendText = (d?.trend || "stabil").toString();
            return (
              <li key={item.key} className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{item.label}</span>{" "}
                <span aria-hidden>{arrow(d?.trend)}</span>
                <span className="sr-only">{trendText}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
