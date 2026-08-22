"use client";

import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAppDispatch } from "@/store/hooks";
import { useSyncListener } from "@/hooks/useSyncListener";
import { todayKeys } from "@/hooks/useTodayDashboard";
import {
  comparableSessionsKeys,
  historicalSupportKeys,
  whatChangedKeys,
} from "@/hooks/useDashboard";
import { planKeys } from "@/hooks/usePlan";
import { todayApi } from "@/dashboard/todayApi";
import { refreshActivitiesAfterSync } from "@/utils/syncRefresh";
import type { SyncJobStatusResponse } from "@/types/syncJob";
import { useCockpitSync } from "@/components/cockpit/CockpitSyncProvider";

export function SyncRefreshBridge() {
  const queryClient = useQueryClient();
  const dispatch = useAppDispatch();
  const { pushToast, setPostSyncSummary, setLastWhatChanged } = useCockpitSync();

  const handleSyncComplete = useCallback(
    async (status?: SyncJobStatusResponse) => {
      if (status) {
        refreshActivitiesAfterSync(dispatch, status);
      }

      try {
        const delta = await todayApi.whatChanged(true);
        setLastWhatChanged(delta);
        if (delta.recommendation_changed) {
          pushToast({
            title: "Ny treningsanbefaling etter oppdatering",
            description: delta.summary,
            tone: "warning",
          });
        } else {
          pushToast({
            title: "Data oppdatert — anbefalingen er uendret",
            description: delta.summary,
            tone: "info",
          });
        }
        queryClient.setQueryData(whatChangedKeys.latest(false), delta);

        const result = status?.result as Record<string, unknown> | undefined;
        const syncedIds = (result?.synced_activity_ids as string[] | undefined) ?? [];
        if (syncedIds.length > 0) {
          const summary = await todayApi.postSyncSummary(syncedIds[0]);
          setPostSyncSummary(summary);
        } else {
          setPostSyncSummary(null);
        }
      } catch {
        pushToast({
          title: "Data oppdatert",
          description: "Kunne ikke hente endringsoppsummering.",
          tone: "info",
        });
      }

      queryClient.invalidateQueries({ queryKey: todayKeys.all });
      queryClient.invalidateQueries({ queryKey: whatChangedKeys.all });
      queryClient.invalidateQueries({ queryKey: ["analysis"] });
      queryClient.invalidateQueries({ queryKey: planKeys.all });
      queryClient.invalidateQueries({ queryKey: ["activities"] });
      queryClient.invalidateQueries({ queryKey: ["recommendation-history"] });
      queryClient.invalidateQueries({ queryKey: historicalSupportKeys.all });
      queryClient.invalidateQueries({ queryKey: comparableSessionsKeys.all });
    },
    [dispatch, pushToast, queryClient, setLastWhatChanged, setPostSyncSummary],
  );

  useSyncListener(handleSyncComplete);
  return null;
}
