import type {
  ActivityFeedbackPayload,
  CoachingEvidencePayload,
  FeedbackPromptPayload,
} from "@/types/coachingEvidence";

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    cache: "no-store",
    headers: { Accept: "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const coachingEvidenceApi = {
  evidence: (windowDays: number) =>
    getJson<CoachingEvidencePayload>(
      `/api/dashboard/coaching-evidence?window_days=${windowDays}`,
    ),
  feedback: (activityId: string) =>
    getJson<ActivityFeedbackPayload>(`/api/activities/${encodeURIComponent(activityId)}/feedback`),
  saveFeedback: (activityId: string, body: Record<string, unknown>) =>
    getJson<ActivityFeedbackPayload>(`/api/activities/${encodeURIComponent(activityId)}/feedback`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  prompt: (activityId: string) =>
    getJson<FeedbackPromptPayload>(
      `/api/activities/${encodeURIComponent(activityId)}/feedback-prompt`,
    ),
};
