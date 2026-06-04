import { useEffect, useRef } from 'react';
import { useAppSelector } from '../store/hooks';
import type { SyncJobStatusResponse } from '../types/syncJob';

export const useSyncListener = (onSyncComplete: (status?: SyncJobStatusResponse) => void) => {
  const { items: activities, status } = useAppSelector((state) => state.activities);
  const previousActivityCount = useRef<number>(0);
  const previousStatus = useRef<string>('idle');

  useEffect(() => {
    // Sjekk om aktiviteter har blitt oppdatert (antall endret)
    const currentActivityCount = activities.length;
    const hasNewActivities = currentActivityCount > previousActivityCount.current;
    const wasLoading = previousStatus.current === 'loading';
    const isNowIdle = status === 'idle';

    // Trigger callback hvis:
    // 1. Vi har nye aktiviteter OG status har endret fra loading til idle
    // ELLER
    // 2. Status har endret fra loading til idle (kan være at sync fullført men ingen nye aktiviteter)
    if ((hasNewActivities && wasLoading && isNowIdle) || (wasLoading && isNowIdle)) {
      console.log('[useSyncListener] Synkronisering fullført, oppdaterer aktiviteter...', {
        hasNewActivities,
        wasLoading,
        isNowIdle,
        currentActivityCount,
        previousActivityCount: previousActivityCount.current
      });
      onSyncComplete();
    }

    // Oppdater referanser
    previousActivityCount.current = currentActivityCount;
    previousStatus.current = status;
  }, [activities.length, status, onSyncComplete]);

  // Lytter etter custom syncCompleted event
  useEffect(() => {
    const handleSyncCompleted = (event: CustomEvent<{ status?: SyncJobStatusResponse }>) => {
      console.log('[useSyncListener] Mottok syncCompleted event:', event.detail);
      onSyncComplete(event.detail?.status);
    };

    window.addEventListener('syncCompleted', handleSyncCompleted as EventListener);

    return () => {
      window.removeEventListener('syncCompleted', handleSyncCompleted as EventListener);
    };
  }, [onSyncComplete]);
}; 