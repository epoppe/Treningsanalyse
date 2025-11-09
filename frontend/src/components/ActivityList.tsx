'use client';

import { memo, useEffect, useState } from 'react';
import { Activity } from '../types';
import { activitiesApi } from '../utils/api';
import ActivityCard from './ActivityCard';

interface ActivityListProps {
  activities: Activity[];
}

const ActivityList: React.FC<ActivityListProps> = ({ activities }) => {
  const [hrvData, setHrvData] = useState<{[activityId: string]: number | null}>({});
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
          const hrvResults: {[activityId: string]: number | null} = {};
          activities.forEach(activity => {
            hrvResults[activity.activityId] = null;
          });
          setHrvData(hrvResults);
          setIsLoadingHrv(false);
          return;
        }

        // Initialize result object with null for all
        const hrvResults: {[activityId: string]: number | null} = {};
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
                hrvResults[activityId] = hrvData.last_night_avg;
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
        const hrvResults: {[activityId: string]: number | null} = {};
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

  return (
    <div className="space-y-3" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {activities.map((activity) => {
        const hrvValue = hrvData[activity.activityId];

        return (
          <ActivityCard 
            key={activity.activityId}
            activity={activity}
            hrvValue={hrvValue}
            isLoadingHrv={isLoadingHrv}
          />
        );
      })}
    </div>
  );
};

// Wrap component with React.memo for performance optimization
export default memo(ActivityList); 