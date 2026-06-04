import type { AppDispatch } from '../store';
import { fetchActivities, fetchActivityCount, fetchNewActivities, mergeSyncedActivities } from '../store/slices/activitiesSlice';
import type { SyncJobStatusResponse } from '../types/syncJob';

/** Lett oppdatering etter synk: kun berørte aktiviteter når mulig. */
export function refreshActivitiesAfterSync(dispatch: AppDispatch, status: SyncJobStatusResponse) {
  const result = status.result as Record<string, unknown> | undefined;
  const syncedIds = (result?.synced_activity_ids as string[] | undefined) ?? [];
  const period = result?.period as { start?: string } | undefined;
  const periodStart = period?.start?.split(' ')[0];

  if (syncedIds.length > 0) {
    dispatch(mergeSyncedActivities({ activityIds: syncedIds, forceRefresh: true }));
    dispatch(fetchActivityCount());
    return;
  }

  if (periodStart) {
    dispatch(fetchNewActivities({ since: periodStart, forceRefresh: true }));
    dispatch(fetchActivityCount());
    return;
  }

  dispatch(fetchActivities({ forceRefresh: true, limit: 100 }));
  dispatch(fetchActivityCount());
}
