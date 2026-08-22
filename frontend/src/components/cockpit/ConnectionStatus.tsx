"use client";

export function ConnectionStatus({
  online,
  asOf,
}: {
  online: boolean;
  asOf?: string;
}) {
  if (!online) {
    return (
      <p
        role="status"
        className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-medium text-rose-800"
      >
        Treningsanalyse-serveren er ikke tilgjengelig.
      </p>
    );
  }

  const timeLabel = asOf ? asOf.slice(0, 16).replace("T", " ") : null;

  return (
    <p className="text-[11px] text-slate-500" role="status">
      Connected{timeLabel ? ` · As of ${timeLabel}` : ""}
    </p>
  );
}
