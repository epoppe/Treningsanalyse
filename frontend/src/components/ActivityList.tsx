'use client';

import styled from 'styled-components';
import { Activity } from '../types';
import { useRouter } from 'next/navigation';
import { analysisApi } from '../utils/api';
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
  const [negativeSplitData, setNegativeSplitData] = useState<{[activityId: string]: number}>({});
  const [isLoadingNegativeSplit, setIsLoadingNegativeSplit] = useState(false);
  const [decouplingData, setDecouplingData] = useState<{[activityId: string]: number}>({});
  const [isLoadingDecoupling, setIsLoadingDecoupling] = useState(false);

  useEffect(() => {
    const fetchHrvData = async () => {
      if (activities.length === 0) {
        console.log('Ingen aktiviteter å hente HRV for - avbryter HRV-henting');
        setHrvData([]);
        setIsLoadingHrv(false);
        return;
      }
      
      // Filtrer aktiviteter fra 2023 og nyere for HRV-data
      const recentActivities = activities.filter(activity => {
        const activityDate = new Date(activity.startTimeLocal);
        return activityDate.getFullYear() >= 2023;
      });

      if (recentActivities.length === 0) {
        console.log('Ingen aktiviteter fra 2023 eller nyere funnet for HRV-data');
        setHrvData([]);
        setIsLoadingHrv(false);
        return;
      }
      
      setIsLoadingHrv(true);
      try {
        // Hent HRV-data for perioden som dekker aktiviteter fra 2023 og nyere
        const dates = recentActivities.map(a => new Date(a.startTimeLocal));
        const minDate = new Date(Math.min(...dates.map(d => d.getTime())));
        const maxDate = new Date(Math.max(...dates.map(d => d.getTime())));
        
        // Legg til buffer på begge sider
        minDate.setDate(minDate.getDate() - 1);
        maxDate.setDate(maxDate.getDate() + 1);
        
        const startDate = minDate.toISOString().split('T')[0];
        const endDate = maxDate.toISOString().split('T')[0];
        
        const response = await fetch(`http://localhost:8000/api/analysis/hrv?start_date=${startDate}&end_date=${endDate}`);
        const result = await response.json();
        
        if (result && result.hrv_data && Array.isArray(result.hrv_data)) {
          console.log('HRV data hentet:', result.hrv_data.length, 'datapunkter');
          setHrvData(result.hrv_data);
        } else {
          console.log('Ingen HRV data funnet for perioden');
        }
      } catch (error) {
        console.error('Feil ved henting av HRV data:', error);
      } finally {
        setIsLoadingHrv(false);
      }
    };

    fetchHrvData();
  }, [activities]);

  useEffect(() => {
    const fetchNegativeSplitData = async () => {
      if (activities.length === 0) {
        console.log('Ingen aktiviteter å hente negative split for - avbryter negative split-henting');
        setNegativeSplitData({});
        setIsLoadingNegativeSplit(false);
        return;
      }
      
      setIsLoadingNegativeSplit(true);
      const negativeSplitResults: {[activityId: string]: number} = {};
      
      try {
        // Hent negativ split-data for løpeaktiviteter fra 2018 og nyere som er minst 2km
        const runningActivities = activities.filter(activity => {
          const isRunning = activity.activityType?.typeKey?.toLowerCase().includes('running') || 
                           activity.activityType?.typeKey?.toLowerCase().includes('løp');
          const hasMinDistance = (activity.distance || 0) >= 2000; // Minst 2km
          const activityDate = new Date(activity.startTimeLocal);
          const isRecent = activityDate.getFullYear() >= 2018; // Aktiviteter fra 2018 og nyere
          return isRunning && hasMinDistance && isRecent;
        });

        // Sorter etter dato (nyeste først) slik at vi prioriterer nye aktiviteter
        const sortedRunningActivities = runningActivities.sort((a, b) => {
          return new Date(b.startTimeLocal).getTime() - new Date(a.startTimeLocal).getTime();
        });

        console.log(`Henter negativ split for ${sortedRunningActivities.length} løpeaktiviteter fra 2018 og nyere`);

        // Hent negative split for alle kvalifiserte aktiviteter (ingen begrensning)
        const activitiesToCheck = sortedRunningActivities;
        
        const promises = activitiesToCheck.map(async (activity) => {
          try {
            const response = await fetch(`http://localhost:8000/api/activities/${activity.activityId}/negative-split`);
            if (response.ok) {
              const data = await response.json();
              return { id: activity.activityId, negativeSplit: data.negative_split_percent };
            }
            // 404 er forventet for aktiviteter uten FIT-data, så vi logger ikke dette som feil
            return null;
          } catch (error) {
            // Kun log uventede feil
            console.warn(`Uventet feil ved henting av negativ split for ${activity.activityId}:`, error);
            return null;
          }
        });

        const results = await Promise.all(promises);
        
        results.forEach(result => {
          if (result && result.negativeSplit !== null) {
            negativeSplitResults[result.id] = result.negativeSplit;
          }
        });

        console.log(`Hentet negativ split-data for ${Object.keys(negativeSplitResults).length} aktiviteter`);
        setNegativeSplitData(negativeSplitResults);
      } catch (error) {
        console.error('Feil ved henting av negativ split-data:', error);
      } finally {
        setIsLoadingNegativeSplit(false);
      }
    };

    fetchNegativeSplitData();
  }, [activities]);

  useEffect(() => {
    const fetchDecouplingData = async () => {
      if (activities.length === 0) {
        console.log('Ingen aktiviteter å hente decoupling for - avbryter decoupling-henting');
        setDecouplingData({});
        setIsLoadingDecoupling(false);
        return;
      }
      
      setIsLoadingDecoupling(true);
      const decouplingResults: {[activityId: string]: number} = {};
      
      try {
        // Hent decoupling-data for løpeaktiviteter fra 2018 og nyere som er minst 2km
        const runningActivities = activities.filter(activity => {
          const isRunning = activity.activityType?.typeKey?.toLowerCase().includes('running') || 
                           activity.activityType?.typeKey?.toLowerCase().includes('løp');
          const hasMinDistance = (activity.distance || 0) >= 2000; // Minst 2km
          const activityDate = new Date(activity.startTimeLocal);
          const isRecent = activityDate.getFullYear() >= 2018; // Aktiviteter fra 2018 og nyere
          return isRunning && hasMinDistance && isRecent;
        });

        // Sorter etter dato (nyeste først) slik at vi prioriterer nye aktiviteter
        const sortedRunningActivities = runningActivities.sort((a, b) => {
          return new Date(b.startTimeLocal).getTime() - new Date(a.startTimeLocal).getTime();
        });

        console.log(`Henter decoupling for ${sortedRunningActivities.length} løpeaktiviteter fra 2018 og nyere`);

        // Hent decoupling for alle kvalifiserte aktiviteter (ingen begrensning)
        const activitiesToCheck = sortedRunningActivities;
        
        const promises = activitiesToCheck.map(async (activity) => {
          try {
            const response = await fetch(`http://localhost:8000/api/activities/${activity.activityId}/decoupling`);
            if (response.ok) {
              const data = await response.json();
              return { id: activity.activityId, decoupling: data.decoupling_percent };
            }
            // 404 er forventet for aktiviteter uten FIT-data, så vi logger ikke dette som feil
            return null;
          } catch (error) {
            // Kun log uventede feil
            console.warn(`Uventet feil ved henting av decoupling for ${activity.activityId}:`, error);
            return null;
          }
        });

        const results = await Promise.all(promises);
        
        results.forEach(result => {
          if (result && result.decoupling !== null) {
            decouplingResults[result.id] = result.decoupling;
          }
        });

        console.log(`Hentet decoupling-data for ${Object.keys(decouplingResults).length} aktiviteter`);
        setDecouplingData(decouplingResults);
      } catch (error) {
        console.error('Feil ved henting av decoupling-data:', error);
      } finally {
        setIsLoadingDecoupling(false);
      }
    };

    fetchDecouplingData();
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
    
    // Prøv først aktivitetsdato direkte (YYYY-MM-DD format)
    const activityDateOnly = activityDate.split('T')[0];
    let hrv = hrvData.find(h => h.date === activityDateOnly);
    let matchedDate = activityDateOnly;
    
    // Hvis ikke funnet, prøv dagen før (HRV måles om natten)
    if (!hrv) {
      const dayBefore = new Date(activityDate);
      dayBefore.setDate(dayBefore.getDate() - 1);
      const dayBeforeStr = dayBefore.toISOString().split('T')[0];
      hrv = hrvData.find(h => h.date === dayBeforeStr);
      if (hrv) matchedDate = dayBeforeStr;
    }
    
    // Hvis fortsatt ikke funnet, prøv dagen etter
    if (!hrv) {
      const dayAfter = new Date(activityDate);
      dayAfter.setDate(dayAfter.getDate() + 1);
      const dayAfterStr = dayAfter.toISOString().split('T')[0];
      hrv = hrvData.find(h => h.date === dayAfterStr);
      if (hrv) matchedDate = dayAfterStr;
    }
    
    // Debug logging kun hvis HRV ikke finnes (for fremtidige problemer)
    if (!hrv && process.env.NODE_ENV === 'development') {
      console.log(`HRV ikke funnet for aktivitet ${activityDateOnly}. Søkte: ${activityDateOnly}, ${matchedDate}`);
    }
    
    return hrv ? hrv.last_night_avg : null;
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
                value: isLoadingNegativeSplit ? 'Laster...' : formatNegativeSplit(negativeSplitData[activity.activityId])
              },
              {
                key: 'decoupling',
                label: 'Decoupling',
                value: isLoadingDecoupling ? 'Laster...' : formatDecoupling(decouplingData[activity.activityId])
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