'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../store/hooks';
import { fetchActivities, fetchMoreActivities, fetchActivityCount, fetchAllActivities, fetchNewActivities, setLoadedCount, Activity, resetActivitiesState } from '../store/slices/activitiesSlice';
import { selectAllActivities, selectActivitiesStatus, selectActivitiesError, selectActivitiesTotalCount, selectActivitiesLoadedCount } from '../store/slices/activitiesSlice';
import ActivityList from '../components/ActivityList';
import ActivityChart from '../components/ActivityChart';
import ActivityViewControls from '../components/ActivityViewControls';
import RunningEconomyTable from '../components/RunningEconomyTable';
import { useSyncListener } from '../hooks/useSyncListener';

const MainContainer = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
`;



const FiltersContainer = styled.div`
  margin-bottom: 0.25rem;
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
  align-items: flex-start;
`;

const FilterSection = styled.div`
  background: white;
  padding: 0.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  min-width: 300px;
`;

const FilterTitle = styled.h3`
  margin: 0 0 0.25rem 0;
  color: #2c3e50;
  font-size: 1rem;
`;

const CheckboxContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
`;

const CheckboxLabel = styled.label`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  cursor: pointer;
  padding: 0.125rem 0.25rem;
  border-radius: 4px;
  transition: background-color 0.2s;
  
  &:hover {
    background-color: #f8f9fa;
  }
`;

const Checkbox = styled.input`
  cursor: pointer;
`;

const CheckboxText = styled.span`
  font-size: 0.9rem;
  color: #333;
`;

const SelectAllButton = styled.button`
  padding: 0.25rem 0.5rem;
  background: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
  margin-right: 0.5rem;

  &:hover {
    background: #2980b9;
  }
`;

const ClearAllButton = styled.button`
  padding: 0.25rem 0.5rem;
  background: #e74c3c;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;

  &:hover {
    background: #c0392b;
  }
`;

export default function Home() {
  const dispatch = useAppDispatch();
  const activities = useAppSelector(selectAllActivities);
  const status = useAppSelector(selectActivitiesStatus);
  const error = useAppSelector(selectActivitiesError);
  const totalCount = useAppSelector(selectActivitiesTotalCount);
  const loadedCount = useAppSelector(selectActivitiesLoadedCount);
  const [filteredActivities, setFilteredActivities] = useState<Activity[]>([]);
  const [selectedActivityTypes, setSelectedActivityTypes] = useState<string[]>([]);
  const [hasInitializedTypes, setHasInitializedTypes] = useState(false);
  const [hasRestoredFromStorage, setHasRestoredFromStorage] = useState(false);
  const [timeFilter, setTimeFilter] = useState<'all' | '12months' | '3months'>('all');

  // Callback for å oppdatere data når synkronisering er fullført
  const handleSyncComplete = useCallback(() => {
    console.log('[Home] Synkronisering fullført, henter alle aktiviteter på nytt...');
    
    // Etter synkronisering, hent ALLE aktiviteter på nytt (inkludert historiske)
    // Dette sikrer at både nye og historiske synkroniserte aktiviteter vises
    dispatch(fetchAllActivities({ forceRefresh: true, count: 2000 }));
  }, [dispatch]);

  // Lytter etter synkroniseringshendelser
  useSyncListener(handleSyncComplete);

  // Automatisk sjekk for nye aktiviteter når siden lastes
  useEffect(() => {
    const checkForNewActivities = () => {
      console.log('[Home] Sjekker for nye aktiviteter ved sideinnlasting...');
      
      if (activities.length > 0) {
        // Finn den nyeste aktiviteten
        const latestActivity = activities.reduce((latest, current) => {
          return new Date(current.startTimeLocal) > new Date(latest.startTimeLocal) ? current : latest;
        });
        
        const latestDate = new Date(latestActivity.startTimeLocal);
        const sinceDate = latestDate.toISOString().split('T')[0];
        
        console.log('[Home] Henter nye aktiviteter siden', sinceDate);
        dispatch(fetchNewActivities({ since: sinceDate, forceRefresh: false }));
      } else {
        console.log('[Home] Ingen eksisterende aktiviteter, henter siste 500');
        dispatch(fetchAllActivities({ forceRefresh: false, count: 2000 }));
      }
    };

    // Sjekk for nye aktiviteter når komponenten mountes
    checkForNewActivities();

    // Sjekk også når siden får fokus (bruker kommer tilbake til siden)
    const handleFocus = () => {
      console.log('[Home] Side fikk fokus, sjekker for nye aktiviteter...');
      checkForNewActivities();
    };

    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [dispatch, activities.length]);

  const getReadableActivityTypeName = (typeKey: string): string => {
    const nameMap: { [key: string]: string } = {
      'running': 'Løping',
      'treadmill_running': 'Tredemølle løping',
      'cycling': 'Sykling',
      'resort_skiing': 'Alpin',
      'cross_country_skiing_ws': 'Langrenn',
      'indoor_cardio': 'Innendørs cardio',
      'walking': 'Gåing',
      'hiking': 'Fotturer',
      'mountain_biking': 'Terrengsykling',
      'resort_skiing_snowboarding_ws': 'Alpint/Snowboard',
      'other': 'Annet',
      'trail_running': 'Terrengløp',
      'gravel_cycling': 'Grussykling',
      'lap_swimming': 'Svømming',
      'multi_sport': 'Flerbruk',
      'open_water_swimming': 'Åpent vann svømming',
      'indoor_cycling': 'Innendørs sykling',
      'swimming': 'Svømming',
      'road_biking': 'Landeveissykling',
      'street_running': 'Gateløp',
      'bikeToRunTransition_v2': 'Sykkel-til-løp overgang'
    };
    
    return nameMap[typeKey] || typeKey;
  };

  const activityTypes = useMemo(() => {
    const typeMap = new Map<string, string>();
    
    activities.forEach(activity => {
      const typeKey = activity.activityType?.typeKey;
      if (typeKey) {
        // Mapper til mer lesbare navn
        const readableName = getReadableActivityTypeName(typeKey);
        typeMap.set(typeKey, readableName);
      }
    });
    
    return Array.from(typeMap.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [activities]);

  useEffect(() => {
    if (status === 'idle' && !hasRestoredFromStorage) {
      // Gjenopprett loadedCount fra localStorage
      const savedLoadedCount = localStorage.getItem('activitiesLoadedCount');
      const savedCount = savedLoadedCount ? parseInt(savedLoadedCount, 10) : 2000;
      
      console.log('[Home] Gjenoppretter fra localStorage:', { savedCount });
      
      if (savedCount > 100) {
        // Hvis vi hadde lastet flere aktiviteter, hent dem alle på nytt
        dispatch(fetchAllActivities({ forceRefresh: false, count: savedCount }));
        dispatch(setLoadedCount(savedCount));
      } else {
        // Hent de siste 2000 aktivitetene ved første lasting for å dekke alle
        dispatch(fetchAllActivities({ forceRefresh: false, count: 2000 }));
      }
      
      // Hent aktivitetsantall separat (påvirker ikke hovedstatus)
      dispatch(fetchActivityCount());
      
      // Sett hasRestoredFromStorage til true umiddelbart
      setHasRestoredFromStorage(true);
    }
  }, [dispatch, status, hasRestoredFromStorage]);



  useEffect(() => {
    // Sett alle aktivitetstyper som valgt kun første gang når aktiviteter lastes
    if (loadedCount > 0 && !hasInitializedTypes && activityTypes.length > 0) {
      const allTypes = activityTypes.map(([typeKey]) => typeKey);
      setSelectedActivityTypes(allTypes);
      setHasInitializedTypes(true);
    }
  }, [loadedCount, activityTypes, hasInitializedTypes]);

  useEffect(() => {
    let tempActivities = [...activities];

    // Filtrer på aktivitetstyper - hvis ingen er valgt, vis ingen aktiviteter
    if (selectedActivityTypes.length === 0) {
      tempActivities = [];
    } else {
      tempActivities = tempActivities.filter(activity => 
        selectedActivityTypes.includes(activity.activityType?.typeKey || '')
      );
    }

    // Filtrer på tid
    tempActivities = getFilteredActivitiesByTime(tempActivities);

    setFilteredActivities(tempActivities);
  }, [activities, selectedActivityTypes, loadedCount, timeFilter]);

  useEffect(() => {
    // Lagre loadedCount i localStorage når den endres
    if (loadedCount > 0) {
      localStorage.setItem('activitiesLoadedCount', loadedCount.toString());
      console.log('[Home] Lagret loadedCount i localStorage:', loadedCount);
    }
  }, [loadedCount]);

  const handleActivityTypeChange = (typeKey: string, checked: boolean) => {
    if (checked) {
      setSelectedActivityTypes(prev => [...prev, typeKey]);
    } else {
      setSelectedActivityTypes(prev => prev.filter(t => t !== typeKey));
    }
  };

  const handleSelectAll = () => {
    const allTypes = activityTypes.map(([typeKey]) => typeKey);
    setSelectedActivityTypes(allTypes);
  };

  const handleClearAll = () => {
    console.log('Fjerner alle aktivitetstyper');
    setSelectedActivityTypes([]);
  };

  const handleRefreshActivities = () => {
    // Reset localStorage når vi refresher aktiviteter
    localStorage.removeItem('activitiesLoadedCount');
    
    // Hent ALLE aktiviteter på nytt (inkludert historiske)
    console.log('[Home] Refresh: Henter alle aktiviteter på nytt (2000)');
    dispatch(fetchAllActivities({ forceRefresh: true, count: 2000 }));
    
    // Sett timeFilter til 'all' for å vise alle aktiviteter
    setTimeFilter('all');
  };




  const handleTimeFilterChange = (filter: 'all' | '12months' | '3months') => {
    setTimeFilter(filter);
  };

  const getFilteredActivitiesByTime = (activities: Activity[]) => {
    const now = new Date();
    
    switch (timeFilter) {
      case '12months':
        const twelveMonthsAgo = new Date();
        twelveMonthsAgo.setMonth(now.getMonth() - 12);
        return activities.filter(activity => new Date(activity.startTimeLocal) >= twelveMonthsAgo);
      
      case '3months':
        const threeMonthsAgo = new Date();
        threeMonthsAgo.setMonth(now.getMonth() - 3);
        return activities.filter(activity => new Date(activity.startTimeLocal) >= threeMonthsAgo);
      
      default:
        return activities;
    }
  };

  if (status === 'loading') {
    return <div>Laster aktiviteter...</div>;
  }

  if (status === 'failed') {
    return <div>Error: {error}</div>;
  }

  return (
    <MainContainer>
      <ActivityViewControls 
        onTimeFilterChange={handleTimeFilterChange}
        currentTimeFilter={timeFilter}
        onRefreshActivities={handleRefreshActivities}
        isRefreshing={status === 'loading'}
        activityCount={totalCount !== null ? `Viser ${filteredActivities.length} av ${loadedCount} aktiviteter` : undefined}
      />
      
      
      
      
      <FiltersContainer>
        <FilterSection>
          <FilterTitle>Velg aktivitetstyper</FilterTitle>
          <div>
            <SelectAllButton onClick={handleSelectAll}>Velg alle</SelectAllButton>
            <ClearAllButton onClick={handleClearAll}>Fjern alle</ClearAllButton>
          </div>
          <CheckboxContainer>
            {activityTypes.map(([typeKey, readableName]) => (
              <CheckboxLabel key={typeKey}>
                <Checkbox
                  type="checkbox"
                  checked={selectedActivityTypes.includes(typeKey)}
                  onChange={(e) => handleActivityTypeChange(typeKey, e.target.checked)}
                />
                <CheckboxText>{readableName}</CheckboxText>
              </CheckboxLabel>
            ))}
          </CheckboxContainer>
        </FilterSection>
      </FiltersContainer>


      <ActivityChart 
        activities={filteredActivities} 
        metric="distance" 
        title="Distanse over tid" 
        useDynamicYAxis={timeFilter !== 'all'}
      />
      <RunningEconomyTable activities={filteredActivities} />
      <ActivityList activities={filteredActivities} />
    </MainContainer>
  );
}
