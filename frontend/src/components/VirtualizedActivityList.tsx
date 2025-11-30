'use client';

import { useRef, useEffect, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import styled from 'styled-components';
import { Activity } from '../types';
import ActivityCard from './ActivityCard';
import { activitiesApi } from '../utils/api';

const ActivityContainer = styled.div`
  padding: 0.5rem;
`;

const VirtualScrollContainer = styled.div`
  height: 100vh;
  overflow-auto;
`;

const VirtualList = styled.div<{ height: number }>`
  height: ${props => props.height}px;
  width: 100%;
  position: relative;
`;

const VirtualRow = styled.div<{ start: number }>`
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  transform: translateY(${props => props.start}px);
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 2rem;
  color: #666;
  
  h3 {
    margin-bottom: 0.5rem;
  }
  
  p {
    margin: 0;
  }
`;

const LoadingIndicator = styled.div`
  text-align: center;
  padding: 1rem;
  color: #666;
`;

interface VirtualizedActivityListProps {
  activities: Activity[];
}

const VirtualizedActivityList: React.FC<VirtualizedActivityListProps> = ({ activities }) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const [hrvData, setHrvData] = useState<{[activityId: string]: number | null | undefined}>({});
  const [isLoadingHrv, setIsLoadingHrv] = useState(false);

  // Setup virtualizer
  const rowVirtualizer = useVirtualizer({
    count: activities.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 250, // Estimated height of each activity card
    overscan: 5, // Render 5 extra items above and below viewport for smooth scrolling
  });

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
      <ActivityContainer>
        <EmptyState>
          <h3>Ingen aktiviteter å vise</h3>
          <p>Velg aktivitetstyper fra filteret ovenfor for å se aktiviteter.</p>
        </EmptyState>
      </ActivityContainer>
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

  const items = rowVirtualizer.getVirtualItems();

  return (
    <ActivityContainer>
      <VirtualScrollContainer ref={parentRef}>
        <VirtualList height={rowVirtualizer.getTotalSize()}>
          {items.map((virtualRow) => {
            const activity = activities[virtualRow.index];
            const hrvValue = hrvData[activity.activityId];
            const previousValidVO2Max = getPreviousValidVO2Max(virtualRow.index);
            
            return (
              <VirtualRow
                key={virtualRow.key}
                start={virtualRow.start}
                ref={rowVirtualizer.measureElement}
                data-index={virtualRow.index}
              >
                <ActivityCard
                  activity={activity}
                  hrvValue={hrvValue}
                  isLoadingHrv={isLoadingHrv}
                  previousValidVO2Max={previousValidVO2Max}
                />
              </VirtualRow>
            );
          })}
        </VirtualList>
      </VirtualScrollContainer>
      
      {isLoadingHrv && (
        <LoadingIndicator>
          Laster HRV-data...
        </LoadingIndicator>
      )}
    </ActivityContainer>
  );
};

export default VirtualizedActivityList;
