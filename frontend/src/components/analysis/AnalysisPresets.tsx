"use client";

import type { AnalysisPreset } from "@/types/analysis";

export function AnalysisPresets({
  presets,
  onSelect,
}: {
  presets: AnalysisPreset[];
  onSelect: (preset: AnalysisPreset) => void;
}) {
  if (!presets.length) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold text-slate-900">Analyse-presets</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Konfigurerer prediktorer/utfall — ingen ferdige konklusjoner.
      </p>
      <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
        {presets.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onSelect(p)}
              className="w-full rounded-md border border-slate-200 px-2.5 py-2 text-left text-xs font-medium text-slate-800 hover:border-slate-400"
            >
              {p.title}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
