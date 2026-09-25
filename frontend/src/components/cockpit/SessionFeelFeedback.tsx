"use client";

import { useEffect, useState } from "react";
import { coachingEvidenceApi } from "@/dashboard/coachingEvidenceApi";
import type { ActivityFeedbackPayload, FeedbackPromptPayload } from "@/types/coachingEvidence";

export function SessionFeelFeedback({ activityId }: { activityId: string }) {
  const [payload, setPayload] = useState<ActivityFeedbackPayload | null>(null);
  const [prompt, setPrompt] = useState<FeedbackPromptPayload | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [rpe, setRpe] = useState("");
  const [legs, setLegs] = useState("");
  const [pain, setPain] = useState("");
  const [motivation, setMotivation] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([
      coachingEvidenceApi.feedback(activityId),
      coachingEvidenceApi.prompt(activityId),
    ])
      .then(([feedback, nextPrompt]) => {
        if (cancelled) return;
        setPayload(feedback);
        setPrompt(nextPrompt);
        setRpe(feedback.feedback?.rpe?.toString() || "");
        setLegs(feedback.feedback?.legs || "");
        setPain(feedback.feedback?.pain?.toString() || "");
        setMotivation(feedback.feedback?.motivation?.toString() || "");
        setNotes(feedback.feedback?.notes || "");
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Kunne ikke lese feedback");
      });
    return () => {
      cancelled = true;
    };
  }, [activityId]);

  const save = async (sessionFeel: string) => {
    if (!payload) return;
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = {
      session_feel: sessionFeel,
      legs: legs || null,
      notes: notes || null,
      rpe: rpe === "" ? null : Number(rpe),
      pain: pain === "" ? null : Number(pain),
      motivation: motivation === "" ? null : Number(motivation),
    };
    try {
      const saved = await coachingEvidenceApi.saveFeedback(activityId, body);
      setPayload(saved);
      setPrompt((current) =>
        current ? { ...current, should_prompt: false, already_has_feedback: true } : current,
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Kunne ikke lagre");
    } finally {
      setSaving(false);
    }
  };

  const selected = payload?.feedback?.session_feel;

  return (
    <div className="space-y-3">
      <p>Hvordan føltes økten?</p>
      {prompt?.should_prompt && !dismissed && !prompt.already_has_feedback ? (
        <div className="flex items-start justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700">
          <p>Denne økten har høy informasjonsverdi. Feedback er valgfritt.</p>
          <button type="button" className="underline" onClick={() => setDismissed(true)}>
            Ignorer
          </button>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {(payload?.quick_feel || []).map((option) => (
          <button
            key={option.value}
            type="button"
            disabled={saving || !payload}
            aria-pressed={selected === option.value}
            onClick={() => save(option.value)}
            className={
              selected === option.value
                ? "rounded-md bg-slate-900 px-3 py-2 text-sm text-white"
                : "rounded-md bg-white px-3 py-2 text-sm text-slate-800 ring-1 ring-slate-200"
            }
          >
            {option.label}
          </button>
        ))}
      </div>
      <button type="button" className="text-xs font-medium underline" onClick={() => setExpanded((open) => !open)}>
        {expanded ? "Skjul mer" : "Mer"}
      </button>
      {expanded && payload ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-600">
            RPE ({payload.rpe.min}–{payload.rpe.max})
            <input
              className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1 text-sm"
              inputMode="numeric"
              value={rpe}
              onChange={(event) => setRpe(event.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600">
            Smerte ({payload.pain.min}–{payload.pain.max})
            <input
              className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1 text-sm"
              inputMode="numeric"
              value={pain}
              onChange={(event) => setPain(event.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600">
            Bein
            <select
              className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1 text-sm"
              value={legs}
              onChange={(event) => setLegs(event.target.value)}
            >
              <option value="">Ikke oppgitt</option>
              {payload.legs.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-600">
            Motivasjon ({payload.motivation.min}–{payload.motivation.max})
            <input
              className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1 text-sm"
              inputMode="numeric"
              value={motivation}
              onChange={(event) => setMotivation(event.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600 sm:col-span-2">
            Notat, valgfritt
            <textarea
              className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1 text-sm"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </label>
        </div>
      ) : null}
      {error ? <p className="text-xs text-red-700">{error}</p> : null}
    </div>
  );
}
