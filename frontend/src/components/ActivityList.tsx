'use client';

import { memo, useEffect, useState } from 'react';
import { Activity } from '../types';
import { activitiesApi } from '../utils/api';
import ActivityCard from './ActivityCard';

interface ActivityListProps {
  activities: Activity[];
}

const ActivityList: React.FC<ActivityListProps> = ({ activities }) => {
  const [hrvData, setHrvData] = useState<{[activityId: string]: number | null | undefined}>({});
  const [isLoadingHrv, setIsLoadingHrv] = useState(false);

  // Fetch HRV data progressively
  useEffect(() => {
    const fetchHrvDataForActivities = async () => {
      if (activities.length === 0) {
        setHrvData({});
        return;
      }
      
      setIsLoadingHrv(true);

      try {
        // Filter activities needing HRV data (from 2023 onwards)
        const activitiesNeedingHrv = activities.filter(activity => {
          const activityDate = new Date(activity.startTimeLocal);
          return activityDate.getFullYear() >= 2023;
        });

        console.log(`[HRV] 🚀 Progressive HRV-loading: ${activitiesNeedingHrv.length} aktiviteter trenger HRV (av ${activities.length} totalt)`);

        if (activitiesNeedingHrv.length === 0) {
          const hrvResults: {[activityId: string]: number | null | undefined} = {};
          activities.forEach(activity => {
            hrvResults[activity.activityId] = null;
          });
          setHrvData(hrvResults);
          setIsLoadingHrv(false);
          return;
        }

        // Initialize result object with null for all
        const hrvResults: {[activityId: string]: number | null | undefined} = {};
        activities.forEach(activity => {
          const activityDate = new Date(activity.startTimeLocal);
          hrvResults[activity.activityId] = activityDate.getFullYear() < 2023 ? null : undefined;
        });
        setHrvData(hrvResults);

        // Split into chunks of 100 activities for progressive loading
        const CHUNK_SIZE = 100;
        const activityIds = activitiesNeedingHrv.map(activity => activity.activityId);
        
        for (let i = 0; i < activityIds.length; i += CHUNK_SIZE) {
          const chunk = activityIds.slice(i, i + CHUNK_SIZE);
          console.log(`[HRV] 📥 Henter chunk ${Math.floor(i/CHUNK_SIZE) + 1}/${Math.ceil(activityIds.length/CHUNK_SIZE)} (${chunk.length} aktiviteter)`);
          
          try {
            const hrvResponse = await activitiesApi.getHrvForMultipleActivities(chunk);
            
            // Update result object with new data
            Object.entries(hrvResponse.hrv_data).forEach(([activityId, hrvData]) => {
              if (hrvData && typeof hrvData === 'object' && 'last_night_avg' in hrvData) {
                const last = (hrvData as any).last_night_avg as number | null | undefined;
                hrvResults[activityId] = last ?? null;
              } else {
                hrvResults[activityId] = null;
              }
            });
            
            // Update state after each chunk for progressive display
            setHrvData({...hrvResults});
            
          } catch (chunkError) {
            console.warn(`[HRV] ⚠️ Feil ved henting av chunk, hopper over:`, chunkError);
            chunk.forEach(id => {
              hrvResults[id] = null;
            });
          }
          
          // Small pause between chunks to avoid overload
          if (i + CHUNK_SIZE < activityIds.length) {
            await new Promise(resolve => setTimeout(resolve, 100));
          }
        }

        console.log(`[HRV] ✅ Ferdig med henting av HRV-data for alle aktiviteter`);
        
      } catch (error) {
        console.error('[HRV] ❌ Feil ved henting av HRV-data:', error);
        const hrvResults: {[activityId: string]: number | null | undefined} = {};
        activities.forEach(activity => {
          hrvResults[activity.activityId] = null;
        });
        setHrvData(hrvResults);
      } finally {
        setIsLoadingHrv(false);
      }
    };

    fetchHrvDataForActivities();
  }, [activities]);

  if (activities.length === 0) {
    return (
      <div
        className="rounded-2xl border border-dashed border-border/70 bg-muted/40 p-10 text-center text-sm text-muted-foreground"
        style={{
          border: '1px dashed rgba(148, 163, 184, 0.6)',
          borderRadius: '16px',
          padding: '2.5rem',
          textAlign: 'center',
          color: '#64748b',
        }}
      >
        <h3 className="text-base font-semibold text-foreground" style={{ color: '#0f172a', fontSize: '1rem', fontWeight: 600 }}>
          Ingen aktiviteter å vise
        </h3>
        <p className="mt-2 max-w-md mx-auto" style={{ marginTop: '0.75rem', maxWidth: '32rem', marginLeft: 'auto', marginRight: 'auto' }}>
          Juster filtrene ovenfor for å se aktiviteter eller synkroniser nye økter.
        </p>
      </div>
    );
  }

  // Beregn forrige gyldige VO2 Max-verdi for hver aktivitet
  const getPreviousValidVO2Max = (currentIndex: number): number | undefined => {
    // Gå bakover gjennom aktivitetene for å finne forrige gyldige VO2 Max-verdi
    for (let i = currentIndex - 1; i >= 0; i--) {
      const prevActivity = activities[i];
      const typeKey = prevActivity.activityType?.typeKey?.toLowerCase() || '';
      const isRunningActivity = typeKey === 'running' || typeKey === 'treadmill_running';
      
      if (isRunningActivity && prevActivity.vO2MaxValue != null && prevActivity.vO2MaxValue > 0) {
        return prevActivity.vO2MaxValue;
      }
    }
    return undefined;
  };

  return (
    <div className="space-y-3" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {activities.map((activity, index) => {
        const hrvValue = hrvData[activity.activityId];
        const previousValidVO2Max = getPreviousValidVO2Max(index);
        
        // Debug logging for VO2 Max
        if (activity.activityType?.typeKey === 'running' && index < 5) {
          console.log(`[VO2Max Debug] Activity ${activity.activityId} (${activity.startTimeLocal}):`, {
            vO2MaxValue: activity.vO2MaxValue,
            previousValidVO2Max: previousValidVO2Max,
            activityType: activity.activityType?.typeKey
          });
        }

        return (
          <ActivityCard 
            key={activity.activityId}
            activity={activity}
            hrvValue={hrvValue}
            isLoadingHrv={isLoadingHrv}
            previousValidVO2Max={previousValidVO2Max}
          />
        );
      })}
    </div>
  );
};

// Wrap component with React.memo for performance optimization
export default memo(ActivityList); 