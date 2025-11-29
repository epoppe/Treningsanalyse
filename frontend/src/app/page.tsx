'use client';

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../store/hooks';
import { fetchActivities, fetchMoreActivities, fetchActivityCount, fetchNewActivities, setLoadedCount } from '../store/slices/activitiesSlice';
import { Activity } from '../types';
import { selectAllActivities, selectActivitiesStatus, selectActivitiesError, selectActivitiesTotalCount, selectActivitiesLoadedCount } from '../store/slices/activitiesSlice';
import ActivityList from '../components/ActivityList';
import ActivityChart from '../components/ActivityChart';
import ActivityViewControls from '../components/ActivityViewControls';
import RunningEconomyTable from '../components/RunningEconomyTable';
import SkeletonLoader from '../components/SkeletonLoader';
import { useSyncListener } from '../hooks/useSyncListener';

const MainContainer = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
`;



const FilterSection = styled.div`
  width: 100%;
  box-sizing: border-box;
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
  const isRefreshing = status === 'loading';
  const [filteredActivities, setFilteredActivities] = useState<Activity[]>([]);
  const [selectedActivityTypes, setSelectedActivityTypes] = useState<string[]>([]);
  const [hasInitializedTypes, setHasInitializedTypes] = useState(false);
  const [hasRestoredFromStorage, setHasRestoredFromStorage] = useState(false);
  const [timeFilter, setTimeFilter] = useState<'all' | '12months' | '3months'>('all');
  const syncRefreshTimeout = useRef<NodeJS.Timeout | null>(null);

  // Callback for å oppdatere data når synkronisering er fullført
  const handleSyncComplete = useCallback(() => {
    console.log('[Home] Synkronisering fullført, oppdaterer aktiviteter...');
    // Rydd opp eventuell tidligere refresh-timeout for å unngå overlappende kall
    if (syncRefreshTimeout.current) {
      clearTimeout(syncRefreshTimeout.current);
    }

    // Kjør en full oppfriskning av aktivitetslisten med force refresh
    // Hent først de første 100 for rask visning (inkluderer flere nye aktiviteter)
    dispatch(fetchActivities({ forceRefresh: true, limit: 100 }));
    dispatch(fetchActivityCount());
    
    // Vent litt lenger (1500ms) for å sikre at første batch er ferdig før vi henter resten
    syncRefreshTimeout.current = setTimeout(() => {
      console.log('[Home] Henter resten av aktivitetene etter synkronisering...');
      // Hent alle resterende aktiviteter (opp til 5000)
      dispatch(fetchMoreActivities({ forceRefresh: true, limit: 5000, offset: 100 }));
      syncRefreshTimeout.current = null;
    }, 1500);
  }, [dispatch]);

  // Lytter etter synkroniseringshendelser
  useSyncListener(handleSyncComplete);

  useEffect(() => {
    return () => {
      if (syncRefreshTimeout.current) {
        clearTimeout(syncRefreshTimeout.current);
      }
    };
  }, []);

  // Automatisk sjekk for nye aktiviteter når siden får fokus (ikke ved initial load)
  useEffect(() => {
    const checkForNewActivities = () => {
      console.log('[Home] Side fikk fokus, sjekker for nye aktiviteter...');
      
      if (activities.length > 0) {
        // Finn den nyeste aktiviteten
        const latestActivity = activities.reduce((latest, current) => {
          return new Date(current.startTimeLocal) > new Date(latest.startTimeLocal) ? current : latest;
        });
        
        const latestDate = new Date(latestActivity.startTimeLocal);
        const sinceDate = latestDate.toISOString().split('T')[0];
        
        console.log('[Home] Henter nye aktiviteter siden', sinceDate);
        dispatch(fetchNewActivities({ since: sinceDate, forceRefresh: false }));
      }
    };

    // Sjekk for nye aktiviteter når siden får fokus (bruker kommer tilbake til siden)
    // IKKE ved initial mount - det håndteres av progressive loading
    const handleFocus = () => {
      if (hasRestoredFromStorage) {
        checkForNewActivities();
      }
    };

    // Håndter visibilitychange for å oppdatere når brukeren navigerer tilbake til fanen
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && hasRestoredFromStorage) {
        console.log('[Home] Side ble synlig, tvinger full oppdatering...');
        dispatch(fetchActivities({ forceRefresh: true, limit: 50 }));
        dispatch(fetchActivityCount());
        setTimeout(() => {
          dispatch(fetchMoreActivities({ forceRefresh: true, limit: 5000, offset: 50 }));
        }, 500);
      }
    };

    window.addEventListener('focus', handleFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      window.removeEventListener('focus', handleFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [dispatch, activities.length, hasRestoredFromStorage]);

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
      console.log('[Home] 🚀 Progressive loading: Henter første 50 aktiviteter...');
      
      // 1. Last FØRST 50 aktiviteter for rask visning (uten details for ytelse)
      dispatch(fetchActivities({ limit: 50 }));
      dispatch(setLoadedCount(50));
      
      // 2. Hent total count
      dispatch(fetchActivityCount());
      
      // 3. Last resten i bakgrunnen etter kort pause
      setTimeout(() => {
        console.log('[Home] 📥 Laster resten av aktivitetene i bakgrunnen...');
        // Øk limit til 5000 for å sikre at vi får alle aktiviteter
        dispatch(fetchMoreActivities({ limit: 5000, offset: 50 }));
      }, 500); // 500ms pause slik at bruker får se siden først
      
      setHasRestoredFromStorage(true);
    }
  }, [dispatch, status, hasRestoredFromStorage]);



  useEffect(() => {
    // Sett standard aktivitetstyper som valgt kun første gang når aktiviteter lastes
    // Standard: Løping, Tredemølle løping, Trail running og Terrengløp (hvis den finnes)
    if (loadedCount > 0 && !hasInitializedTypes && activityTypes.length > 0) {
      const defaultTypes = ['running', 'treadmill_running', 'trail_running'];
      
      // Finn også terrengløp-varianten (kan ha forskjellige navn/typeKeys)
      const terrenglopTypes = activityTypes
        .filter(([typeKey, readableName]) => 
          readableName.toLowerCase().includes('terrengløp') || 
          readableName.toLowerCase().includes('terrenglop') ||
          typeKey.toLowerCase().includes('terrenglop') ||
          typeKey.toLowerCase().includes('terrengløp')
        )
        .map(([typeKey]) => typeKey);
      
      // Kombiner default types med terrengløp-varianten
      const allDefaultTypes = [...defaultTypes, ...terrenglopTypes];
      
      // Filtre for å bare inkludere typer som faktisk finnes i aktivitetene
      const availableDefaultTypes = allDefaultTypes.filter(type => 
        activityTypes.some(([typeKey]) => typeKey === type)
      );
      
      // Fjern duplikater
      const uniqueDefaultTypes = Array.from(new Set(availableDefaultTypes));
      
      setSelectedActivityTypes(uniqueDefaultTypes);
      setHasInitializedTypes(true);
    }
  }, [loadedCount, activityTypes, hasInitializedTypes]);

  useEffect(() => {
    let tempActivities = [...activities];

    // Filtrer på aktivitetstyper - hvis ingen er valgt, vis ingen aktiviteter
    if (selectedActivityTypes.length === 0) {
      tempActivities = [];
    } else {
      tempActivities = tempActivities.filter(activity => {
        const typeKey = activity.activityType?.typeKey;
        // Hvis aktivitet mangler type (f.eks. eldre økter eller aktiviteter som ikke har blitt mappet riktig),
        // så viser vi den uansett så lenge brukeren har minst én type valgt.
        // Dette sikrer at tredemølle-økter og andre «ukjente» typer ikke faller ut av aktivitetslisten.
        if (!typeKey) {
          return true;
        }
        return selectedActivityTypes.includes(typeKey);
      });
    }

    // Filtrer på tid
    tempActivities = getFilteredActivitiesByTime(tempActivities);

    setFilteredActivities(tempActivities);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activities, selectedActivityTypes, loadedCount, timeFilter]);

  useEffect(() => {
    // Lagre loadedCount i localStorage når den endres
    if (loadedCount > 0) {
      localStorage.setItem('activitiesLoadedCount', loadedCount.toString());
    }
  }, [loadedCount]);

  const handleActivityTypeChange = useCallback((typeKey: string, checked: boolean) => {
    if (checked) {
      setSelectedActivityTypes(prev => [...prev, typeKey]);
    } else {
      setSelectedActivityTypes(prev => prev.filter(t => t !== typeKey));
    }
  }, []);

  const handleSelectAll = useCallback(() => {
    const allTypes = activityTypes.map(([typeKey]) => typeKey);
    setSelectedActivityTypes(allTypes);
  }, [activityTypes]);

  const handleClearAll = useCallback(() => {
    console.log('Fjerner alle aktivitetstyper');
    setSelectedActivityTypes([]);
  }, []);

  const handleRefreshActivities = useCallback(() => {
    localStorage.removeItem('activitiesLoadedCount');

    if (syncRefreshTimeout.current) {
      clearTimeout(syncRefreshTimeout.current);
    }

    console.log('[Home] Refresh: Tvinger full oppdatering av aktivitetslisten');
    dispatch(fetchActivities({ forceRefresh: true, limit: 50 }));
    dispatch(fetchActivityCount());

    syncRefreshTimeout.current = setTimeout(() => {
      // Øk limit til 5000 for å sikre at vi får alle aktiviteter
      dispatch(fetchMoreActivities({ forceRefresh: true, limit: 5000, offset: 50 }));
      syncRefreshTimeout.current = null;
    }, 500);
    
    setTimeFilter('all');
  }, [dispatch]);




  const handleTimeFilterChange = useCallback((filter: 'all' | '12months' | '3months') => {
    setTimeFilter(filter);
  }, []);

  const getFilteredActivitiesByTime = useCallback((activities: Activity[]) => {
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
  }, [timeFilter]);

  if (status === 'loading') {
    return (
      <MainContainer>
        <SkeletonLoader type="chart" />
        <SkeletonLoader type="list" count={5} />
      </MainContainer>
    );
  }

  if (status === 'failed') {
    return (
      <MainContainer>
        <div style={{ 
          padding: '2rem', 
          textAlign: 'center', 
          color: '#e74c3c',
          backgroundColor: '#ffe5e5',
          borderRadius: '8px',
          margin: '2rem 0'
        }}>
          <h2>Feil ved lasting av aktiviteter</h2>
          <p>{error}</p>
          <button 
            onClick={() => window.location.reload()}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: '#3498db',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              marginTop: '1rem'
            }}
          >
            Prøv igjen
          </button>
        </div>
      </MainContainer>
    );
  }

  return (
    <MainContainer>
      <div style={{ width: '100%', marginBottom: '0.25rem' }}>
        <ActivityViewControls 
          onTimeFilterChange={handleTimeFilterChange}
          currentTimeFilter={timeFilter}
          onRefreshActivities={handleRefreshActivities}
          isRefreshing={isRefreshing}
          activityCount={totalCount !== null ? `Viser ${filteredActivities.length} av ${loadedCount} aktiviteter` : undefined}
        />
      </div>
      
      
      <FilterSection style={{ width: '100%', boxSizing: 'border-box', marginBottom: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
          <FilterTitle style={{ margin: 0 }}>Velg aktivitetstyper</FilterTitle>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <SelectAllButton onClick={handleSelectAll}>Velg alle</SelectAllButton>
            <ClearAllButton onClick={handleClearAll}>Fjern alle</ClearAllButton>
          </div>
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

      <ActivityChart 
        activities={filteredActivities} 
        metric="distance" 
        title="Distanse over tid" 
        useDynamicYAxis={timeFilter !== 'all'}
      />
      
      {/* Activity list section */}
      <div style={{ marginTop: '2rem' }}>
        <ActivityList activities={filteredActivities} />
      </div>
    </MainContainer>
  );
}
