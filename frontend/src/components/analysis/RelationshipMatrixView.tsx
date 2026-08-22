"use client";

import type { MatrixCell } from "@/types/analysis";
import { EvidenceBadge } from "./ui";

function cellSymbol(cell: MatrixCell) {
  if (cell.status === "suppressed") return "⊘";
  if (cell.status === "insufficient" || !cell.association) return "·";
  if (cell.association === "positive") return "+";
  if (cell.association === "negative") return "−";
  return "?";
}

export function RelationshipMatrixView({
  predictors,
  outcomes,
  cells,
  disclaimer,
}: {
  predictors: string[];
  outcomes: string[];
  cells: MatrixCell[];
  disclaimer?: string;
}) {
  const lookup = new Map(cells.map((c) => [`${c.predictor}::${c.outcome}`, c]));

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold text-slate-900">Sammenhengsmatrise</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        + positiv · − negativ · ⊘ matematisk avhengig · · utilstrekkelig
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-[10px]">
          <thead>
            <tr>
              <th className="p-1 font-medium text-slate-500">Prediktor ↓ / Utfall →</th>
              {outcomes.map((o) => (
                <th key={o} className="p-1 font-medium text-slate-600">
                  {o.split(".").pop()}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {predictors.map((p) => (
              <tr key={p} className="border-t border-slate-100">
                <td className="p-1 font-medium text-slate-800">{p}</td>
                {outcomes.map((o) => {
                  const cell = lookup.get(`${p}::${o}`);
                  return (
                    <td key={o} className="p-1 text-center tabular-nums" title={cell?.warning || cell?.note || ""}>
                      <span className="text-sm font-semibold">{cell ? cellSymbol(cell) : "·"}</span>
                      {cell?.lag_days != null ? (
                        <span className="block text-[9px] text-slate-500">{cell.lag_days}d</span>
                      ) : null}
                      {cell?.evidence ? (
                        <span className="mt-0.5 inline-block">
                          <EvidenceBadge evidence={String(cell.evidence)} />
                        </span>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {disclaimer ? <p className="mt-2 text-[11px] text-slate-500">{disclaimer}</p> : null}
    </section>
  );
}
