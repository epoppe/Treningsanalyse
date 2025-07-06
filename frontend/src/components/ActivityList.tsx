'use client';

import styled from 'styled-components';
import { Activity } from '../store/slices/activitiesSlice';
import { useRouter } from 'next/navigation';
import { analysisApi } from '@/utils/api';
import { useEffect, useState } from 'react';
import { HrvData } from '@/types/hrv';

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

const ActivityStat = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem;
  background-color: #f8f9fa;
  border-radius: 4px;
  min-height: 60px;
  justify-content: center;
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
  const [hrvData, setHrvData] = useState<HrvData[]>([]);
  const [isLoadingHrv, setIsLoadingHrv] = useState(false);

  useEffect(() => {
    const fetchHrvData = async () => {
      if (activities.length === 0) return;
      
      setIsLoadingHrv(true);
      try {
        // Hent HRV-data for perioden som dekker alle aktiviteter
        const dates = activities.map(a => new Date(a.startTimeLocal));
        const minDate = new Date(Math.min(...dates.map(d => d.getTime())));
        const maxDate = new Date(Math.max(...dates.map(d => d.getTime())));
        
        const startDate = minDate.toISOString().split('T')[0];
        const endDate = maxDate.toISOString().split('T')[0];
        
        const result = await analysisApi.getHrv(startDate, endDate);
        
        // Sørg for at result er et array - HRV API returnerer { hrv_data: [] }
        if (result && result.hrv_data && Array.isArray(result.hrv_data)) {
          console.log('HRV data hentet:', result.hrv_data.length, 'datapunkter');
          setHrvData(result.hrv_data);
        } else if (Array.isArray(result)) {
          // Fallback for hvis API returnerer direkte array
          setHrvData(result);
        } else {
          console.log('HRV API returnerte ikke forventet struktur:', result);
          setHrvData([]);
        }
      } catch (error) {
        console.error('Kunne ikke hente HRV-data:', error);
        setHrvData([]);
      } finally {
        setIsLoadingHrv(false);
      }
    };

    fetchHrvData();
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

  const getHrvForDate = (activityDate: string) => {
    if (!Array.isArray(hrvData) || hrvData.length === 0) {
      return null;
    }
    
    const date = new Date(activityDate).toISOString().split('T')[0];
    const hrv = hrvData.find(h => h.date === date);
    
    // Debug logging for første aktivitet
    if (hrvData.length > 0 && !hrv) {
      console.log('Søker HRV for dato:', date);
      console.log('Tilgjengelige HRV-datoer:', hrvData.slice(0, 5).map(h => h.date));
    }
    
    return hrv ? hrv.last_night_avg : null;
  };

  const formatHrv = (hrv?: number) => {
    if (!hrv) return 'N/A';
    return `${Math.round(hrv)}`;
  };

  return (
    <ActivityContainer>
      {activities.map((activity) => (
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
                key: 'hrv',
                label: 'HRV',
                value: isLoadingHrv ? 'Laster...' : formatHrv(getHrvForDate(activity.startTimeLocal))
              }
            ].map(stat => (
              <ActivityStat key={stat.key}>
                <StatLabel>{stat.label}</StatLabel>
                <StatValue>{stat.value}</StatValue>
              </ActivityStat>
            ))}
          </ActivityDetails>
        </ActivityCard>
      ))}
    </ActivityContainer>
  );
};

export default ActivityList; 