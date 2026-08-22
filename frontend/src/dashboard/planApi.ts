import type { PlanDashboardPayload } from "@/types/plan";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const planApi = {
  plan: (date?: string, mesocycleWeeks = 5) => {
    const params = new URLSearchParams();
    if (date) params.set("target_date", date);
    params.set("mesocycle_weeks", String(mesocycleWeeks));
    const q = params.toString();
    return getJson<PlanDashboardPayload>(`/api/dashboard/plan${q ? `?${q}` : ""}`);
  },
};
