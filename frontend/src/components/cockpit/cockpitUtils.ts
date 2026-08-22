/** Cockpit display helpers — presentation only, no coaching logic. */

const WARNING_LABELS: Record<string, string> = {
  few_recent_activities: "Få nylige aktiviteter — anbefalingen er mer konservativ.",
  missing_hrv: "HRV mangler — restitusjonssignaler er mindre sikre.",
  pb_calibration_sparse: "Kalibrering har få datapunkter — intensitetsmål er mindre presise.",
  missing_sleep: "Søvndata mangler.",
  stale_lt2: "Terskeldata er eldre — bruk puls/RPE som primær guide.",
};

const PLAN_REASON_LABELS: Record<string, string> = {
  no_quality_conflict: "Ingen planendring nødvendig etter siste vurdering.",
};

export function warningLabel(code: string): string {
  return WARNING_LABELS[code] || code.replace(/_/g, " ");
}

export function planReasonLabel(code: string): string {
  return PLAN_REASON_LABELS[code] || code.replace(/_/g, " ");
}

const REASON_LABELS_NB: Record<string, string> = {
  RECOVERY_LOW: "Restitusjon tilsier moderat belastning",
  RECOVERY_COST_HIGH: "Forventet restitusjonskostnad er høy",
  QUALITY_SESSION_DUE: "Kvalitetsøkt er due etter god spacing",
  QUALITY_SESSION_NOT_DUE: "Kvalitetsøkt er ikke due ennå",
  LOAD_PROGRESSING: "Belastningen progreserer innenfor normal ramme",
  LOAD_RAPID_INCREASE: "Rask belastningsøkning — mer forsiktighet",
  GOAL_SPECIFICITY: "Tiltaket støtter nåværende treningsmål",
  HARD_SESSION_SPACING: "For kort tid siden forrige harde økt",
  FATIGUE_EXTREME: "Høy utmattelse — restitusjon prioriteres",
  READINESS_REST: "Readiness tilsier hvile",
  ABSTAIN_LOW_EVIDENCE: "For svak evidens til entydig anbefaling",
  DEFAULT_AEROBIC: "Standard aerob vedlikehold",
  EASY_VOLUME_PRIORITY: "Rolig volum prioriteres",
};

const WORKOUT_LABELS: Record<string, string> = {
  rest: "Hvile",
  recovery_run: "Restitusjonsløp",
  easy_run: "Rolig løp",
  long_run: "Langtur",
  steady: "Steady aerob",
  threshold: "Kontrollert terskel",
  vo2_intervals: "VO₂-intervaller",
  tempo: "Tempo",
  race_pace: "Konkurransetempo",
  anaerobic: "Anaerob",
  race: "Konkurranse",
};

const TREND_LABELS: Record<string, string> = {
  improving: "Forbedres",
  stable: "Stabil",
  declining: "Synker",
  uncertain: "Usikker",
};

export function reasonTextNb(reason: { code?: string; doc?: string }): string {
  if (reason.code && REASON_LABELS_NB[reason.code]) {
    return REASON_LABELS_NB[reason.code];
  }
  if (reason.doc) return reason.doc;
  if (reason.code) return reason.code.replace(/_/g, " ").toLowerCase();
  return "Støttende signal";
}

export function workoutTypeLabel(type?: string | null): string {
  if (!type) return "Økt";
  return WORKOUT_LABELS[type] || type.replace(/_/g, " ");
}

export function trendLabel(trend?: string | null): string {
  if (!trend) return "—";
  return TREND_LABELS[trend.toLowerCase()] || trend;
}

export function formatPaceRange(pace?: number | number[] | null): string | null {
  if (pace == null) return null;
  const toStr = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return `${m}:${String(s).padStart(2, "0")}/km`;
  };
  if (Array.isArray(pace)) {
    if (pace.length >= 2) return `${toStr(pace[0])}–${toStr(pace[1])}`;
    if (pace.length === 1) return toStr(pace[0]);
    return null;
  }
  return toStr(pace);
}

export function formatHrRange(hr?: number | number[] | null): string | null {
  if (hr == null) return null;
  if (Array.isArray(hr)) {
    if (hr.length >= 2) return `${Math.round(hr[0])}–${Math.round(hr[1])} slag/min`;
    if (hr.length === 1) return `${Math.round(hr[0])} slag/min`;
    return null;
  }
  return `${Math.round(hr)} slag/min`;
}

export function formatRpeRange(rpe?: number | number[] | null): string | null {
  if (rpe == null) return null;
  if (Array.isArray(rpe)) {
    if (rpe.length >= 2) return `RPE ${rpe[0]}–${rpe[1]}`;
    if (rpe.length === 1) return `RPE ${rpe[0]}`;
    return null;
  }
  return `RPE ${rpe}`;
}

export function evidenceBand(strength?: number | null): "strong" | "supported" | "emerging" | "insufficient" {
  if (strength == null) return "insufficient";
  if (strength >= 0.75) return "strong";
  if (strength >= 0.55) return "supported";
  if (strength >= 0.35) return "emerging";
  return "insufficient";
}

export function evidenceLabel(strength?: number | null): string {
  const labels = {
    strong: "Sterk",
    supported: "Støttet",
    emerging: "Fremvoksende",
    insufficient: "Utilstrekkelig",
  };
  return labels[evidenceBand(strength)];
}

export function formatNorwegianDate(iso?: string): string {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("nb-NO", {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(new Date(`${iso}T12:00:00`));
  } catch {
    return iso;
  }
}

export function mainSetSummary(prescription?: {
  main_set?: {
    repetitions?: number;
    work_duration_min?: number;
    recovery_duration_min?: number;
    recovery_type?: string;
  };
} | null): string | null {
  const main = prescription?.main_set;
  if (!main) return null;
  const reps = main.repetitions;
  const work = main.work_duration_min;
  const rec = main.recovery_duration_min;
  if (reps && work && rec) {
    return `${reps} × ${work} min\n${rec} min rolig jogg`;
  }
  if (reps && work) return `${reps} × ${work} min`;
  if (work) return `${work} min`;
  return null;
}
