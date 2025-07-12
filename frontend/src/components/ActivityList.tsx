'use client';

import styled from 'styled-components';
import { Activity } from '../types';
import { useRouter } from 'next/navigation';
import { api, errorHandler } from '../utils/api';
import { useEffect, useState } from 'react';
import { HrvData } from '../types/hrv';


const ActivityContainer = styled.div`
  padding: 1rem;
`;

const ActivityCardWrapper = styled.div`
  width: 100%;
  margin-bottom: 1rem;
`;

const ActivityDetails = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
  gap: 0.5rem;
  color: #666;
  font-size: 0.9rem;
`;

const ActivityStat = styled.div<{ $statKey?: string; $value?: number | null }>`
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem;
  border-radius: 4px;
  min-height: 60px;
  justify-content: center;
  background-color: ${({ $statKey, $value }) => {
    if ($value === null || $value === undefined) return '#f8f9fa'; // default gray

    if ($statKey === 'decoupling' || $statKey === 'negative_split') {
      return $value > 0 ? '#fee2e2' : '#dcfce7'; // red-100 for positive, green-100 for negative
    }

    if ($statKey === 'hrv') {
      if ($value < 35) return '#fee2e2'; // red-100
      if ($value <= 37) return '#fef9c3'; // yellow-100
      return '#dcfce7'; // green-100
    }
    
    return '#f8f9fa'; // default gray
  }};
`;

const StatLabel = styled.span`
  font-size: 0.75rem;
  color: #666;
  margin-bottom: 0.25rem;
  font-weight: 500;
  text-align: center;
`;

const StatValue = styled.span`
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
  text-align: center;
`;

const ActivityCard = styled.div`
  background: white;
  border-radius: 8px;
  padding: 0.75rem;
  margin-bottom: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: box-shadow 0.2s;
  
  &:hover {
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
  }
`;

const ActivityTitle = styled.h3`
  margin: 0 0 0.5rem 0;
  color: #2c3e50;
  font-size: 1.1rem;
`;

interface ActivityListProps {
  activities: Activity[];
}

const ActivityList: React.FC<ActivityListProps> = ({ activities }) => {
  const router = useRouter();
  const [hrvData, setHrvData] = useState<{[activityId: string]: number | null}>({});
  const [isLoadingHrv, setIsLoadingHrv] = useState(false);

  useEffect(() => {
    const fetchHrvDataForActivities = async () => {
      if (activities.length === 0) {
        setHrvData({});
        return;
      }
      setIsLoadingHrv(true);

      const hrvResults: {[activityId: string]: number | null} = {};
      
      const promises = activities.map(async (activity) => {
        const activityDate = new Date(activity.startTimeLocal);
        if (activityDate.getFullYear() < 2023) {
          hrvResults[activity.activityId] = null;
          return;
        }
        try {
          const data = await api.getHrvByActivity(activity.activityId);
          // Backend returnerer et objekt med last_night_avg property, ikke hrv
          console.log(`[HRV] Data for activity ${activity.activityId}:`, data);
          hrvResults[activity.activityId] = data?.last_night_avg ?? null;
        } catch (error: any) {
          // 404-feil er forventet for datoer uten HRV-data
          if (error?.response?.status === 404) {
            hrvResults[activity.activityId] = null;
          } else {
            // Log bare uventede feil
            console.error(`Uventet feil ved henting av HRV for aktivitet ${activity.activityId}:`, error);
            hrvResults[activity.activityId] = null;
          }
        }
      });

      await Promise.all(promises);

      setHrvData(hrvResults);
      setIsLoadingHrv(false);
    };

    fetchHrvDataForActivities();
  }, [activities]);


  const handleActivityClick = (activityId: number) => {
    router.push(`/activities/${activityId}`);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('nb-NO', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    });
  };

  const calculateRunningEconomy = (averageSpeed?: number, averageHR?: number, activityType?: any) => {
    // Sjekk om det er en løpeaktivitet
    const isRunningActivity = activityType?.typeKey?.toLowerCase().includes('running') && 
                             !activityType?.typeKey?.toLowerCase().includes('treadmill');
    
    if (!isRunningActivity) {
      return null; // Ikke en løpeaktivitet
    }
    
    if (!averageSpeed || !averageHR || averageSpeed <= 0 || averageHR <= 0) return null;
    const speedInKmh = averageSpeed * 3.6; // Konverter fra m/s til km/t
    return (speedInKmh / averageHR) * 100;
  };

  const formatRunningEconomy = (economy?: number, activityType?: any) => {
    // Sjekk om det er en løpeaktivitet
    const isRunningActivity = activityType?.typeKey?.toLowerCase().includes('running') && 
                             !activityType?.typeKey?.toLowerCase().includes('treadmill');
    
    if (!isRunningActivity) {
      return 'N/A'; // Ikke en løpeaktivitet
    }
    
    if (!economy) return 'N/A';
    return `${economy.toFixed(2)}`;
  };

  const formatVO2Max = (vo2Max?: number, activityType?: any) => {
    // Sjekk om det er en løpeaktivitet
    const isRunningActivity = activityType?.typeKey?.toLowerCase().includes('running') && 
                             !activityType?.typeKey?.toLowerCase().includes('treadmill');
    
    if (!isRunningActivity) {
      return 'N/A'; // Ikke en løpeaktivitet
    }
    
    if (!vo2Max || vo2Max <= 0) return 'N/A';
    return Math.round(vo2Max).toString();
  };

  const formatHrv = (hrv?: number) => {
    if (!hrv) return 'N/A';
    return `${Math.round(hrv)}`;
  };

  const calculatePace = (distance?: number, duration?: number) => {
    if (!distance || !duration || distance <= 0 || duration <= 0) return null;
    
    const distanceKm = distance / 1000; // Konverter fra meter til km
    const durationMin = duration / 60; // Konverter fra sekunder til minutter
    
    return durationMin / distanceKm; // min/km
  };

  const formatPace = (pace?: number) => {
    if (!pace) return 'N/A';
    
    const minutes = Math.floor(pace);
    const seconds = Math.round((pace - minutes) * 60);
    
    return `${minutes}:${seconds.toString().padStart(2, '0')} min/km`;
  };

  const formatNegativeSplit = (negativeSplitPercent?: number) => {
    if (negativeSplitPercent === undefined || negativeSplitPercent === null) return 'N/A';
    
    const sign = negativeSplitPercent >= 0 ? '+' : '';
    return `${sign}${negativeSplitPercent.toFixed(1)}%`;
  };

  const formatDecoupling = (decouplingPercent?: number) => {
    if (decouplingPercent === undefined || decouplingPercent === null) return 'N/A';
    
    const sign = decouplingPercent >= 0 ? '+' : '';
    return `${sign}${decouplingPercent.toFixed(1)}%`;
  };

  if (activities.length === 0) {
    return (
      <ActivityContainer>
        <div style={{ textAlign: 'center', padding: '2rem', color: '#666' }}>
          <h3>Ingen aktiviteter å vise</h3>
          <p>Velg aktivitetstyper fra filteret ovenfor for å se aktiviteter.</p>
        </div>
      </ActivityContainer>
    );
  }

  return (
    <ActivityContainer>
      {activities.map((activity) => {
        const hrvValue = hrvData[activity.activityId];

        return (
          <ActivityCard 
            key={activity.activityId} 
            className="hover:shadow-lg transition-shadow cursor-pointer"
            onClick={() => handleActivityClick(parseInt(activity.activityId, 10))}
          >
            <ActivityTitle>{activity.activityName}</ActivityTitle>
            <ActivityDetails>
              {[
                {
                  key: 'date',
                  label: 'Dato',
                  value: formatDate(activity.startTimeLocal)
                },
                {
                  key: 'distance',
                  label: 'Distanse',
                  value: `${((activity.distance || 0) / 1000).toFixed(2)} km`
                },
                {
                  key: 'duration',
                  label: 'Varighet',
                  value: `${Math.round((activity.duration || 0) / 60)} min`
                },
                {
                  key: 'pace',
                  label: 'Pace',
                  value: formatPace(calculatePace(activity.distance, activity.duration))
                },
                ...(activity.averageHR > 0 ? [{
                  key: 'average_hr',
                  label: 'Snitt puls',
                  value: `${Math.round(activity.averageHR)} bpm`
                }] : []),
                {
                  key: 'vo2_max',
                  label: 'VO2 Max',
                  value: formatVO2Max(activity.vO2MaxValue, activity.activityType)
                },
                {
                  key: 'running_economy',
                  label: 'Løpsøkonomi',
                  value: formatRunningEconomy(calculateRunningEconomy(activity.averageSpeed, activity.averageHR, activity.activityType), activity.activityType)
                },
                {
                  key: 'negative_split',
                  label: 'Negativ Split',
                  value: formatNegativeSplit(activity.negativeSplitPercent),
                  rawValue: activity.negativeSplitPercent
                },
                {
                  key: 'decoupling',
                  label: 'Decoupling',
                  value: formatDecoupling(activity.decouplingPercent),
                  rawValue: activity.decouplingPercent
                },
                {
                  key: 'hrv',
                  label: 'HRV',
                  value: isLoadingHrv ? 'Laster...' : formatHrv(hrvValue),
                  rawValue: hrvValue
                }
              ].map(stat => (
                <ActivityStat 
                  key={stat.key} 
                  $statKey={stat.key}
                  $value={stat.rawValue as number | undefined}
                >
                  <StatLabel>{stat.label}</StatLabel>
                  <StatValue>{stat.value}</StatValue>
                </ActivityStat>
              ))}
            </ActivityDetails>
          </ActivityCard>
        );
      })}
    </ActivityContainer>
  );
};

export default ActivityList; 