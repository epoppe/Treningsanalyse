/**
 * Readiness chat med LM Studio: henter kun relevante datamoduler basert på spørsmålet (RAG-lignende).
 */
import { NextRequest, NextResponse } from 'next/server';

export const maxDuration = 300; // 5 min – lokale LLM-er kan ta lang tid

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const LM_STUDIO_URL = process.env.LM_STUDIO_URL || 'http://localhost:1234';
const LM_STUDIO_MODEL = process.env.LM_STUDIO_MODEL || 'local-model';

const DEFAULT_DAYS = 50;
// LLM velger moduler basert på spørsmålet. Sett USE_LLM_MODULE_SELECTOR=false for raskere regelbasert valg.
const USE_LLM_MODULE_SELECTOR = process.env.USE_LLM_MODULE_SELECTOR !== 'false';

type ModuleKey = 'overview' | 'tss' | 'daily' | 'stress' | 'hrv' | 'bodyBattery' | 'sleep' | 'activities' | 'readiness';

const ALL_MODULES: ModuleKey[] = ['overview', 'tss', 'daily', 'stress', 'hrv', 'bodyBattery', 'sleep', 'activities', 'readiness'];

/** Systemprompt som får LLM til å vurdere hvilke datamoduler som trengs for spørsmålet. */
const SYSTEM_PROMPT_MODULE_SELECTOR = `Du er en datamodul-velger for en treningsassistent. Brukeren stiller et spørsmål om sine Garmin-treningsdata.

Tilgjengelige datamoduler (velg kun de som er relevante for spørsmålet):
- overview: Generell treningsoversikt (VO2max, aktivitetsfrekvens, volum, recovery-metrics)
- tss: TSS, CTL, ATL, Form (Training Stress Score, kronisk/akut belastning)
- daily: Daglige sammendrag (aktiviteter, km, minutter per dag)
- stress: Stressnivå per dag
- hrv: HRV (RMSSD) per dag – hjertevariabilitet
- bodyBattery: Body Battery per dag – kroppsenergi
- sleep: Søvndata per dag (timer, kvalitet)
- activities: Full aktivitetsliste med dato, type, navn, distanse, varighet, pace, puls, TSS
- readiness: Training readiness score (søvn+HRV+form)

Svar KUN med en JSON-liste over modulnavn du trenger, f.eks. ["activities","daily"] eller ["sleep","readiness","hrv"].
Ingen annen tekst, forklaring eller markdown. Kun JSON-array.`;

/** Regelbasert modulvalg – rask, ingen ekstra LLM-kall. */
function selectModulesByRules(message: string): Set<ModuleKey> {
  const m = message.toLowerCase();
  const modules = new Set<ModuleKey>();

  // Søvn → sleep, readiness
  if (/\b(søvn|sleep|sovn|søvne|sovne)\b/.test(m)) {
    modules.add('sleep');
    modules.add('readiness');
  }
  // HRV → hrv, readiness
  if (/\b(hrv|hjerte|heart rate|puls)\b/.test(m)) {
    modules.add('hrv');
    modules.add('readiness');
  }
  // Stress
  if (/\b(stress|slitasje)\b/.test(m)) {
    modules.add('stress');
  }
  // Body Battery
  if (/\b(body battery|kroppsbatteri|batteri)\b/.test(m)) {
    modules.add('bodyBattery');
  }
  // Aktiviteter – løp, sykle, km, distanse, økt, tren
  if (/\b(aktivitet|aktiviteter|trening|tren|løp|sykl|km|kilometer|distanse|økt|volum)\b/.test(m)) {
    modules.add('activities');
    modules.add('daily');
  }
  // Readiness, form, TSS, fatigue
  if (/\b(readiness|klar|form|formen|tsb|fatigue|utmattelse|anbefal|anbefaling)\b/.test(m)) {
    modules.add('readiness');
    modules.add('tss');
  }
  // VO2max, fitness
  if (/\b(vo2|vo2max|fitness|form)\b/.test(m)) {
    modules.add('overview');
  }
  // Generelle/spørsmål – hent bredt
  if (/\b(hvordan|hva|er jeg|begrunn|oppsummer|sammendrag)\b/.test(m)) {
    modules.add('overview');
    modules.add('readiness');
    modules.add('tss');
  }

  // Hvis ingen moduler matchet – hent standard
  if (modules.size === 0) {
    modules.add('overview');
    modules.add('readiness');
    modules.add('tss');
    modules.add('activities');
  }

  return modules;
}

/** LLM-basert modulvalg – bruker systemprompt til å vurdere spørsmålet. Ekstra LLM-kall, men mer fleksibel. */
async function selectModulesViaLLM(message: string): Promise<Set<ModuleKey>> {
  try {
    const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: LM_STUDIO_MODEL,
        messages: [
          { role: 'system', content: SYSTEM_PROMPT_MODULE_SELECTOR },
          { role: 'user', content: message },
        ],
        max_tokens: 128,
        temperature: 0,
      }),
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return selectModulesByRules(message); // Fallback til regler
    const data = await res.json();
    const raw = data?.choices?.[0]?.message?.content?.trim();
    if (!raw) return selectModulesByRules(message);
    const json = raw.replace(/^```\w*\n?|\n?```$/g, '').trim();
    const arr = JSON.parse(json) as string[];
    const valid = new Set(ALL_MODULES);
    const selected = new Set<ModuleKey>();
    for (const k of arr) {
      if (valid.has(k as ModuleKey)) selected.add(k as ModuleKey);
    }
    if (selected.size === 0) return selectModulesByRules(message);
    return selected;
  } catch {
    return selectModulesByRules(message);
  }
}

function parseDaysFromMessage(message: string): number {
  const m = message.toLowerCase();
  const weekMatch = m.match(/(\d+)\s*(uke|uker)/);
  if (weekMatch) return parseInt(weekMatch[1], 10) * 7;
  const dayMatch = m.match(/(\d+)\s*(dag|dager)/);
  if (dayMatch) return parseInt(dayMatch[1], 10);
  const monthMatch = m.match(/(\d+)\s*(måned|måneder)\b/);
  if (monthMatch) return parseInt(monthMatch[1], 10) * 30;
  return DEFAULT_DAYS;
}

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { message, date } = body;

    if (!message || typeof message !== 'string') {
      return NextResponse.json({ detail: 'Mangler message' }, { status: 400 });
    }

    const modules = USE_LLM_MODULE_SELECTOR
      ? await selectModulesViaLLM(message)
      : selectModulesByRules(message);
    const days = parseDaysFromMessage(message);
    const endDate = new Date(date || Date.now());
    const startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - days);

    const startStr = startDate.toISOString().split('T')[0];
    const endStr = endDate.toISOString().split('T')[0];

    const base = `${BACKEND_URL}/api`;

    // Hent kun valgte moduler – raskere og mindre kontekst til LLM
    const fetches: Promise<[ModuleKey, unknown]>[] = [];
    if (modules.has('overview')) fetches.push(fetchJson<any>(`${base}/analysis/training-overview?days=${days}`).then((r) => ['overview', r]));
    if (modules.has('tss')) fetches.push(fetchJson<any>(`${base}/training-stress/metrics?start_date=${startStr}&end_date=${endStr}`).then((r) => ['tss', r]));
    if (modules.has('daily')) fetches.push(fetchJson<any[]>(`${base}/analysis/daily-summaries?end_date=${endStr}&limit=${days}`).then((r) => ['daily', r]));
    if (modules.has('stress')) fetches.push(fetchJson<any[]>(`${base}/health/stress/range?start_date=${startStr}&end_date=${endStr}`).then((r) => ['stress', r]));
    if (modules.has('hrv')) fetches.push(fetchJson<any[]>(`${base}/health/hrv/range?start_date=${startStr}&end_date=${endStr}`).then((r) => ['hrv', r]));
    if (modules.has('bodyBattery')) fetches.push(fetchJson<any[]>(`${base}/health/body-battery/range?start_date=${startStr}&end_date=${endStr}`).then((r) => ['bodyBattery', r]));
    if (modules.has('sleep')) fetches.push(fetchJson<any[]>(`${base}/health/sleep/range?start_date=${startStr}&end_date=${endStr}`).then((r) => ['sleep', r]));
    if (modules.has('activities')) fetches.push(fetchJson<any>(`${base}/activities/date-range?start_date=${startStr}&end_date=${endStr}&force_refresh=false`).then((r) => ['activities', r]));
    if (modules.has('readiness')) fetches.push(fetchJson<any>(`${base}/training-readiness/weekly?end_date=${endStr}`).then((r) => ['readiness', r]));

    const results = await Promise.all(fetches);
    const data: Record<ModuleKey, unknown> = {} as Record<ModuleKey, unknown>;
    for (const [k, v] of results) data[k] = v;

    const overview = data.overview as any;
    const tssMetrics = data.tss as any;
    const dailySummaries = data.daily as any[];
    const stressRange = data.stress as any[];
    const hrvRange = data.hrv as any[];
    const bodyBatteryRange = data.bodyBattery as any[];
    const sleepRange = data.sleep as any[];
    const activitiesResp = data.activities as any;
    const readinessWeekly = data.readiness as any;

    const dataBlob: string[] = [];

    if (overview) {
      dataBlob.push(`## Treningsoversikt (${days} dager)\n${JSON.stringify(overview, null, 0)}`);
    }
    if (tssMetrics?.data?.summary) {
      dataBlob.push(`## TSS/Form\n${JSON.stringify(tssMetrics.data.summary, null, 0)}`);
    }
    if (tssMetrics?.data?.daily_data?.length) {
      const daily = tssMetrics.data.daily_data;
      const last = daily[daily.length - 1];
      dataBlob.push(`Siste dag TSS: CTL=${last?.ctl?.toFixed(1)}, ATL=${last?.atl?.toFixed(1)}, Form=${last?.form?.toFixed(1)}, TSS=${last?.tss}`);
    }
    if (dailySummaries?.length) {
      const summary = dailySummaries.map((d: any) =>
        `${d.date}: ${d.total_activities} aktiviteter, ${((d.total_distance || 0) / 1000).toFixed(1)} km, ${Math.round((d.total_duration || 0) / 60)} min`
      ).join('\n');
      dataBlob.push(`## Daglige sammendrag (alle ${dailySummaries.length} dager)\n${summary}`);
    }
    if (stressRange?.length) {
      const avg = stressRange.reduce((s: number, x: any) => s + (x.stress_level || 0), 0) / stressRange.length;
      const lines = stressRange.map((x: any) => `${x.date}: ${x.stress_level ?? '-'}`).join(', ');
      dataBlob.push(`## Stress (snitt ${avg.toFixed(1)}) – per dag: ${lines}`);
    }
    if (hrvRange?.length) {
      const vals = hrvRange.map((x: any) => x.rmssd ?? x.last_night_avg).filter((v: any) => v != null);
      const avg = vals.length ? vals.reduce((a: number, b: number) => a + b, 0) / vals.length : 0;
      const lines = hrvRange.map((x: any) => `${x.date}: ${x.rmssd ?? x.last_night_avg ?? '-'}`).join(', ');
      dataBlob.push(`## HRV (snitt RMSSD ${avg.toFixed(1)} ms) – per dag: ${lines}`);
    }
    if (bodyBatteryRange?.length) {
      const maxes = bodyBatteryRange.map((x: any) => x.max_body_battery ?? x.body_battery_max).filter(Boolean);
      const avg = maxes.length ? maxes.reduce((a: number, b: number) => a + b, 0) / maxes.length : 0;
      const lines = bodyBatteryRange.map((x: any) => `${x.date}: max ${x.max_body_battery ?? x.body_battery_max ?? '-'}`).join(', ');
      dataBlob.push(`## Body Battery (snitt max ${avg.toFixed(0)}) – per dag: ${lines}`);
    }
    if (sleepRange?.length) {
      const withDuration = sleepRange.filter((x: any) => x.total_sleep_time || x.duration);
      const avgMin = withDuration.length
        ? withDuration.reduce((s: number, x: any) => s + ((x.total_sleep_time || x.duration || 0) / 60), 0) / withDuration.length
        : 0;
      const lines = sleepRange.map((x: any) => {
        const min = (x.total_sleep_time || x.duration || 0) / 60;
        return `${x.date}: ${(min / 60).toFixed(1)}t`;
      }).join(', ');
      dataBlob.push(`## Søvn (snitt ${(avgMin / 60).toFixed(1)} timer) – per dag: ${lines}`);
    }
    const activities = Array.isArray(activitiesResp) ? activitiesResp : (activitiesResp?.activities ?? []);
    if (activities.length) {
      const typeKey = (a: any) => a.activityType?.typeKey ?? a.activity_type?.typeKey ?? 'other';
      const totalKm = activities.reduce((s, a) => s + (a.distance || 0) / 1000, 0);
      const totalMin = activities.reduce((s, a) => s + (a.duration || 0) / 60, 0);
      const byType: Record<string, number> = {};
      activities.forEach((a) => { const t = typeKey(a); byType[t] = (byType[t] || 0) + 1; });
      // Full aktivitetsliste – hver aktivitet med dato, navn, type, distanse, varighet, pace, puls, TSS
      const lines = activities.map((a: any) => {
        const dt = a.startTimeLocal ? new Date(a.startTimeLocal).toISOString().split('T')[0] : '?';
        const km = ((a.distance || 0) / 1000).toFixed(1);
        const min = Math.round((a.duration || 0) / 60);
        const pace = a.averagePace ? `${Math.floor(a.averagePace / 60)}:${String(Math.floor(a.averagePace % 60)).padStart(2, '0')}/km` : '';
        const hr = a.averageHR ?? a.average_heart_rate ?? '';
        const tss = a.trainingStressScore ?? a.training_stress_score ?? '';
        const name = (a.activityName ?? a.activity_name ?? '').slice(0, 40);
        const type = typeKey(a);
        return `${dt} | ${type} | ${name} | ${km} km, ${min} min${pace ? `, pace ${pace}` : ''}${hr ? `, HR ${hr}` : ''}${tss ? `, TSS ${tss}` : ''}`;
      });
      dataBlob.push(`## Aktiviteter (${activities.length} stk) – totalt ${totalKm.toFixed(1)} km, ${Math.round(totalMin)} min\nTyper: ${JSON.stringify(byType)}\n\nListe (dato | type | navn | distanse, varighet, pace, puls, TSS):\n${lines.join('\n')}`);
    }
    if (readinessWeekly?.data?.length) {
      const latest = readinessWeekly.data.slice(-7);
      dataBlob.push(`## Readiness (siste 7 dager)\n${latest.map((r: any) => `${r.date}: ${r.total_score}/100 (${r.readiness_status})`).join('\n')}`);
    }

    const contextText = dataBlob.length
      ? dataBlob.join('\n\n')
      : 'Ingen treningsdata tilgjengelig for perioden.';

    const systemPrompt = `Du er en treningsassistent. Brukeren har Garmin-treningsdata. Svar kort og konkret på norsk basert på dataene under. Ikke finn på tall - bruk kun det som står i dataene.`;
    const userPrompt = `Perioden: ${startStr} til ${endStr} (${days} dager)\n\n## Tilgjengelige data\n${contextText}\n\n## Brukerens spørsmål\n${message}\n\nSvar:`;

    const lmRes = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: LM_STUDIO_MODEL,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
        ],
        max_tokens: 1024,
        temperature: 0.5,
      }),
      signal: AbortSignal.timeout(300000), // 5 min – lokale LLM-er kan ta lang tid
    });

    if (!lmRes.ok) {
      const errText = await lmRes.text();
      return NextResponse.json({
        response: `LM Studio returnerte feil (${lmRes.status}). Sjekk at serveren kjører og at en modell er lastet. Feil: ${errText.slice(0, 200)}`,
      }, { status: 200 });
    }

    const lmData = await lmRes.json();
    const content = lmData?.choices?.[0]?.message?.content?.trim();
    if (!content) {
      return NextResponse.json({
        response: 'LM Studio returnerte tomt svar. Prøv igjen eller sjekk at en modell er lastet.',
      }, { status: 200 });
    }

    return NextResponse.json({ response: content });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Ukjent feil';
    return NextResponse.json(
      { response: `Beklager, det oppstod en feil: ${msg}` },
      { status: 200 }
    );
  }
}
