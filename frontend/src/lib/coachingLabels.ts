/** Norwegian presentation labels for backend reason codes — codes remain canonical. */

export const REASON_LABELS_NO: Record<string, string> = {
  RECOVERY_LOW: "Restitusjonen er svakere enn normalt",
  RECOVERY_COST_HIGH: "Forventet restitusjonskostnad er høy",
  QUALITY_SESSION_DUE: "Tid for kvalitetsøkt",
  QUALITY_SESSION_NOT_DUE: "Kvalitetsøkt er ikke planlagt nå",
  LOAD_PROGRESSING: "Belastningen utvikler seg som planlagt",
  LOAD_RAPID_INCREASE: "Belastningen har økt raskt",
  GOAL_SPECIFICITY: "Tilpasset mål og kapasitet",
  PAIN_GUARDRAIL: "Smerte begrenser intensitet",
  DATA_STALE: "Noen nøkkeldata er gamle",
  DATA_MISSING: "Noen data mangler",
  HARD_SESSION_SPACING: "For kort tid siden siste harde økt",
  HARD_DENSITY_GUARDRAIL: "For mange harde økter siste uke",
  UNAVAILABLE_DAY: "Dagen er markert utilgjengelig",
  FATIGUE_EXTREME: "Høy tretthet — restitusjon anbefales",
  READINESS_REST: "Readiness tilsier hvile",
  ABSTAIN_LOW_EVIDENCE: "For lite evidens for sikker anbefaling",
  RANKER_OVERRIDE: "Rangering justerte anbefalingen",
  EASY_VOLUME_PRIORITY: "Prioritet på lett aerob volum",
  RACE_RECOVERY: "Restitusjon etter konkurranse",
  DEFAULT_AEROBIC: "Vedlikehold — aerob basis",
};

export function reasonLabel(code: string): string {
  return REASON_LABELS_NO[code] || code.replace(/_/g, " ").toLowerCase();
}

export const WORKOUT_LABELS_NO: Record<string, string> = {
  easy_run: "Lett løp",
  recovery_run: "Restitusjonsløp",
  long_run: "Langtur",
  threshold: "Terskel",
  vo2_intervals: "VO₂-intervaller",
  race_pace: "Konkurransefart",
  race: "Konkurranse",
  rest: "Hvile",
  strength: "Styrke",
  cycling: "Sykling",
};

export function workoutLabel(type?: string | null): string {
  if (!type) return "Ukjent økt";
  return WORKOUT_LABELS_NO[type] || type;
}

export function formatPace(secPerKm?: number | null): string {
  if (secPerKm == null || !Number.isFinite(secPerKm) || secPerKm <= 0) return "—";
  const m = Math.floor(secPerKm / 60);
  const s = Math.round(secPerKm % 60);
  return `${m}:${s.toString().padStart(2, "0")}/km`;
}

export function formatHrRange(hr?: number[] | null): string {
  if (!hr || hr.length === 0) return "—";
  if (hr.length === 1) return `${Math.round(hr[0])} bpm`;
  return `${Math.round(hr[0])}–${Math.round(hr[hr.length - 1])} bpm`;
}

export function formatDuration(min?: number | number[] | null): string {
  if (min == null) return "—";
  if (Array.isArray(min)) {
    if (min.length === 0) return "—";
    if (min.length === 1) return `~${Math.round(min[0])} min`;
    return `${Math.round(min[0])}–${Math.round(min[min.length - 1])} min`;
  }
  return `~${Math.round(min)} min`;
}

export function oneSentenceSummary(args: {
  workoutType?: string | null;
  decisionStatus?: string | null;
  recoveryTrend?: string | null;
}): string {
  const w = workoutLabel(args.workoutType);
  if (args.decisionStatus === "abstain" || args.decisionStatus === "insufficient_data") {
    return "For lite sikre data til en bestemt anbefaling i dag — hold det trygt.";
  }
  if (args.workoutType === "rest" || args.workoutType === "recovery_run") {
    return `Restitusjon anbefales. Plan: ${w.toLowerCase()}.`;
  }
  return `Klar for trening. Anbefaling: ${w.toLowerCase()}.`;
}
