"use client";

import { useMemo, useState } from "react";
import type { AnalyticsMetric } from "@/types/analysis";
import { cn } from "@/lib/utils";

const GROUP_ORDER = [
  "Training",
  "Load",
  "Recovery",
  "Fitness",
  "Performance",
  "Advanced",
  "Other",
];

export function MetricPicker({
  metrics,
  selected,
  onToggle,
  max = 4,
}: {
  metrics: AnalyticsMetric[];
  selected: string[];
  onToggle: (key: string) => void;
  max?: number;
}) {
  const [q, setQ] = useState("");
  const [group, setGroup] = useState<string>("All");

  const groups = useMemo(() => {
    const set = new Set(metrics.map((m) => m.group || "Other"));
    return ["All", ...GROUP_ORDER.filter((g) => set.has(g)), ...Array.from(set).filter((g) => !GROUP_ORDER.includes(g))];
  }, [metrics]);

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return metrics.filter((m) => {
      if (!m.supports_trend && !m.selectable_y) return false;
      if (m.key.startsWith("stimulus.")) return false; // stimuli for relationships
      if (group !== "All" && (m.group || "Other") !== group) return false;
      if (!query) return true;
      return (
        m.key.toLowerCase().includes(query) ||
        (m.label || "").toLowerCase().includes(query) ||
        (m.explanation || "").toLowerCase().includes(query)
      );
    });
  }, [metrics, q, group]);

  const selectedMeta = metrics.filter((m) => selected.includes(m.key));

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Metrikker</h3>
        <p className="text-[11px] text-slate-500">
          {selected.length}/{max} valgt
        </p>
      </div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Søk metrikker…"
        className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-xs"
        aria-label="Søk metrikker"
      />
      <div className="flex flex-wrap gap-1">
        {groups.map((g) => (
          <button
            key={g}
            type="button"
            onClick={() => setGroup(g)}
            className={cn(
              "rounded-md px-2 py-0.5 text-[10px] font-medium",
              group === g ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700"
            )}
          >
            {g}
          </button>
        ))}
      </div>
      <ul className="max-h-40 space-y-1 overflow-y-auto">
        {filtered.map((m) => {
          const on = selected.includes(m.key);
          return (
            <li key={m.key}>
              <button
                type="button"
                onClick={() => {
                  if (!on && selected.length >= max) return;
                  onToggle(m.key);
                }}
                className={cn(
                  "flex w-full flex-col rounded-md px-2 py-1.5 text-left text-xs",
                  on ? "bg-slate-900 text-white" : "hover:bg-slate-50 text-slate-800"
                )}
              >
                <span className="font-medium">{m.label || m.key}</span>
                <span className={cn("text-[10px]", on ? "text-slate-300" : "text-slate-500")}>
                  {m.key}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {selectedMeta[0]?.explanation ? (
        <p className="border-t border-slate-100 pt-2 text-[11px] text-slate-600">
          <span className="font-medium">{selectedMeta[0].label}: </span>
          {selectedMeta[0].explanation}
        </p>
      ) : null}
    </div>
  );
}
