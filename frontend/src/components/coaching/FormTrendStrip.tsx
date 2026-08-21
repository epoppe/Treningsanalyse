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
  return (
    <section aria-label="Formtrend" className="rounded-2xl border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold text-foreground">Formtrend</h2>
      <ul className="mt-3 flex flex-wrap gap-4">
        {items.map((item) => {
          const d = state?.[item.key];
          return (
            <li key={item.key} className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{item.label}</span>{" "}
              <span aria-hidden>{arrow(d?.trend)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
