"use client";

import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAppDispatch } from "@/store/hooks";
import { useSyncListener } from "@/hooks/useSyncListener";
import { todayKeys } from "@/hooks/useTodayDashboard";
import { refreshActivitiesAfterSync } from "@/utils/syncRefresh";
import type { SyncJobStatusResponse } from "@/types/syncJob";

export function SyncRefreshBridge() {
  const queryClient = useQueryClient();
  const dispatch = useAppDispatch();

  const handleSyncComplete = useCallback(
    (status?: SyncJobStatusResponse) => {
      if (status) {
        refreshActivitiesAfterSync(dispatch, status);
      }
      queryClient.invalidateQueries({ queryKey: todayKeys.all });
      queryClient.invalidateQueries({ queryKey: ["analysis"] });
      queryClient.invalidateQueries({ queryKey: ["plan"] });
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
    [dispatch, queryClient],
  );

  useSyncListener(handleSyncComplete);
  return null;
}
