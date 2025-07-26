import { useEffect, useRef } from 'react';
import { useAppSelector } from '../store/hooks';

export const useSyncListener = (onSyncComplete: () => void) => {
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
    // 1. Vi har nye aktiviteter OG
    // 2. Status har endret fra loading til idle (synkronisering fullført)
    if (hasNewActivities && wasLoading && isNowIdle) {
      console.log('[useSyncListener] Synkronisering fullført, oppdaterer statistikk...');
      onSyncComplete();
    }

    // Oppdater referanser
    previousActivityCount.current = currentActivityCount;
    previousStatus.current = status;
  }, [activities.length, status, onSyncComplete]);
}; 