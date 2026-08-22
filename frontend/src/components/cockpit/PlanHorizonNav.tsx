"use client";

import { cn } from "@/lib/utils";

export type PlanHorizon = "today" | "week" | "mesocycle";

const HORIZONS: { id: PlanHorizon; label: string }[] = [
  { id: "today", label: "I dag" },
  { id: "week", label: "7 dager" },
  { id: "mesocycle", label: "4–6 uker" },
];

export function PlanHorizonNav({
  value,
  onChange,
}: {
  value: PlanHorizon;
  onChange: (horizon: PlanHorizon) => void;
}) {
  return (
    <nav className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
      {HORIZONS.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onChange(item.id)}
          className={cn(
            "flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors",
            value === item.id
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-600 hover:text-slate-900",
          )}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
