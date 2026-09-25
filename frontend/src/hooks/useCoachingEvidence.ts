"use client";

import { useQuery } from "@tanstack/react-query";
import { coachingEvidenceApi } from "@/dashboard/coachingEvidenceApi";
import { COCKPIT_QUERY_DEFAULTS } from "@/lib/cockpitQueryDefaults";

export function useCoachingEvidence(windowDays: number) {
  return useQuery({
    queryKey: ["coaching-evidence", windowDays],
    queryFn: () => coachingEvidenceApi.evidence(windowDays),
    ...COCKPIT_QUERY_DEFAULTS,
  });
}
