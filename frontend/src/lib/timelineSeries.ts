export type TimelinePoint = { date: string; value: number | null };

export type TimelineSeriesMeta = {
  unit?: string;
  temporal_semantics?: string;
  native_cadence_days?: number;
  show_gaps?: boolean;
};

export function groupSeriesByUnit(
  keys: string[],
  meta: Record<string, TimelineSeriesMeta>,
): string[][] {
  const groups: string[][] = [];
  const index = new Map<string, number>();
  keys.forEach((key) => {
    const unit = meta[key]?.unit || "ukjent";
    const existing = index.get(unit);
    if (existing == null) {
      index.set(unit, groups.length);
      groups.push([key]);
      return;
    }
    groups[existing].push(key);
  });
  return groups;
}

export function sharesRawAxis(groups: string[][]): boolean {
  return groups.length <= 1;
}

export function seriesShowsGaps(meta?: TimelineSeriesMeta): boolean {
  if (!meta) return false;
  if (typeof meta.show_gaps === "boolean") return meta.show_gaps;
  const semantics = meta.temporal_semantics;
  if (semantics === "snapshot" || semantics === "rolling_best" || semantics === "derived_state") {
    return false;
  }
  return (meta.native_cadence_days ?? 1) <= 1;
}

function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const next = new Date(year, month - 1, day + days);
  const mm = String(next.getMonth() + 1).padStart(2, "0");
  const dd = String(next.getDate()).padStart(2, "0");
  return `${next.getFullYear()}-${mm}-${dd}`;
}

export function insertGapNulls(
  points: Array<{ date: string; value: number }>,
  showGaps: boolean,
): TimelinePoint[] {
  if (!showGaps || points.length < 2) {
    return points.map((point) => ({ date: point.date, value: point.value }));
  }
  const byDate = new Map(points.map((point) => [point.date, point.value]));
  const ordered = [...points].sort((a, b) => a.date.localeCompare(b.date));
  const rows: TimelinePoint[] = [];
  let cursor = ordered[0].date;
  const end = ordered[ordered.length - 1].date;
  while (cursor <= end) {
    rows.push({
      date: cursor,
      value: byDate.has(cursor) ? (byDate.get(cursor) as number) : null,
    });
    cursor = addDays(cursor, 1);
  }
  return rows;
}
