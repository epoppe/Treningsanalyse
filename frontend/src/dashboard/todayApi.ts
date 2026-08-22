import type { TodayDashboardPayload } from "@/types/today";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const todayApi = {
  today: (date?: string, persist = false) => {
    const params = new URLSearchParams();
    if (date) params.set("target_date", date);
    if (persist) params.set("persist", "true");
    const q = params.toString();
    return getJson<TodayDashboardPayload>(`/api/dashboard/today${q ? `?${q}` : ""}`);
  },
};
