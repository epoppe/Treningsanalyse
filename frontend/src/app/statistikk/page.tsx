'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useAppDispatch, useAppSelector } from '../../store/hooks';
import { fetchAllActivities, fetchNewActivities, Activity } from '../../store/slices/activitiesSlice';
import styled from 'styled-components';
import ActivityChart from '../../components/ActivityChart';
import MonthlyComparisonChart from '../../components/MonthlyComparisonChart';
import SummaryTables from '../../components/SummaryTables';
import { useSyncListener } from '../../hooks/useSyncListener';
import { api } from '../../utils/api';

const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Header = styled.header`
  margin-bottom: 2rem;
  text-align: center;
`;

const Title = styled.h1`
  color: #2c3e50;
  font-size: 2rem;
  margin-bottom: 0.5rem;
`;

const Subtitle = styled.p`
  color: #666;
  font-size: 1.125rem;
`;

const FiltersContainer = styled.div`
  margin-bottom: 2rem;
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
`;

const FilterSection = styled.div`
  background: white;
  padding: 1rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  min-width: 300px;
`;

const FilterTitle = styled.h3`
  margin: 0 0 0.5rem 0;
  color: #2c3e50;
  font-size: 1rem;
`;

const CheckboxContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
`;

const CheckboxLabel = styled.label`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
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

const SelectedTypesDisplay = styled.div`
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: #f8f9fa;
  border-radius: 4px;
  font-size: 0.9rem;
  color: #666;
  min-height: 1.5rem;
`;

const Select = styled.select`
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  min-width: 200px;
  font-size: 1rem;
`;

const FilterButton = styled.button`
  padding: 0.5rem 1rem;
  background: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;

  &:hover {
    background: #2980b9;
  }

  &:disabled {
    background: #bdc3c7;
    cursor: not-allowed;
  }
`;

const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
`;

const StatCard = styled.div`
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const StatTitle = styled.h3`
  color: #2c3e50;
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
`;

const StatValue = styled.p`
  color: #3498db;
  font-size: 2rem;
  font-weight: bold;
  margin: 0;
`;

const StatUnit = styled.span`
  color: #666;
  font-size: 1rem;
  font-weight: normal;
`;

const PeriodSection = styled.div`
  margin-bottom: 2rem;
`;

const PeriodTitle = styled.h2`
  color: #2c3e50;
  font-size: 1.5rem;
  margin-bottom: 1rem;
  text-align: center;
`;

const ChartsContainer = styled.div`
  margin-top: 2rem;
`;

const LoadingSpinner = styled.div`
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  animation: spin 1s linear infinite;
  margin: 0 auto;

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;

const StatistikkPage = () => {
  const dispatch = useAppDispatch();
  const { items: activities, status, error } = useAppSelector((state) => state.activities);
  const [selectedActivityTypes, setSelectedActivityTypes] = useState<string[]>([]);
  const [historicalActivities, setHistoricalActivities] = useState<Activity[]>([]);

  // Hent unike aktivitetstyper
  const activityTypes = useMemo(() => {
    const types = activities.map(a => a.activityType?.typeKey).filter(Boolean);
    return Array.from(new Set(types as string[]));
  }, [activities]);

  // Beregn datoer for trailing 12 måneder
  const trailing12MonthsDate = useMemo(() => {
    const date = new Date();
    date.setMonth(date.getMonth() - 12);
    return date;
  }, []);

  // Beregn datoer for trailing 24 måneder (for å sammenligne med året før)
  const trailing24MonthsDate = useMemo(() => {
    const date = new Date();
    date.setMonth(date.getMonth() - 24);
    return date;
  }, []);

  // Beregn datoer for trailing 48 måneder (4 år for grafene)
  const trailing48MonthsDate = useMemo(() => {
    const date = new Date();
    date.setMonth(date.getMonth() - 48);
    return date;
  }, []);

  // Beregn startdato for 2022 (for grafene)
  const startOf2022Date = useMemo(() => {
    return new Date('2022-01-01');
  }, []);

  // Hent eksplisitt aktiviteter for de siste 3 årene (i tillegg til det som allerede er lastet)
  useEffect(() => {
    const loadHistorical = async () => {
      try {
        const now = new Date();
        const start = new Date(now.getFullYear() - 3, 0, 1); // 1. jan for tre år siden
        const startStr = start.toISOString().split('T')[0];
        const endStr = now.toISOString().split('T')[0];
        const res = await api.getActivitiesByDateRange(startStr, endStr, false);
        const extra = (res as any)?.activities || [];
        setHistoricalActivities(extra as Activity[]);
      } catch (e) {
        // stille feil – vi bruker uansett det vi allerede har
        console.warn('[Statistikk] Klarte ikke hente historiske aktiviteter for 3 år', e);
      }
    };
    loadHistorical();
  }, []);

  // Kombiner eksisterende aktiviteter med eksplisitt hentede historiske (fjern duplikater)
  const combinedActivities = useMemo(() => {
    const byId = new Map<string, Activity>();
    [...activities, ...historicalActivities].forEach(a => {
      if (a && a.activityId) {
        byId.set(a.activityId, a);
      }
    });
    return Array.from(byId.values());
  }, [activities, historicalActivities]);
  // Filtrer aktiviteter basert på valgte typer og siste 12 måneder
  const filteredActivities = useMemo(() => {
    let tempActivities = combinedActivities.filter(activity => {
      const activityDate = new Date(activity.startTimeLocal);
      return activityDate >= trailing12MonthsDate;
    });

    if (selectedActivityTypes.length > 0) {
      tempActivities = tempActivities.filter(a => 
        selectedActivityTypes.includes(a.activityType?.typeKey || '')
      );
    }

    return tempActivities;
  }, [combinedActivities, selectedActivityTypes, trailing12MonthsDate]);

  // Filtrer aktiviteter basert på valgte typer for 2022-2024 (for grafene)
  const allFilteredActivities = useMemo(() => {
    let tempActivities = combinedActivities.filter(activity => {
      const activityDate = new Date(activity.startTimeLocal);
      return activityDate >= startOf2022Date;
    });

    if (selectedActivityTypes.length > 0) {
      tempActivities = tempActivities.filter(a => 
        selectedActivityTypes.includes(a.activityType?.typeKey || '')
      );
    }

    return tempActivities;
  }, [combinedActivities, selectedActivityTypes, startOf2022Date]);

  // Alle aktiviteter for siste 4 år (for grafene - ufiltrert)
  const allActivitiesForCharts = useMemo(() => {
    const tempActivities = combinedActivities.filter(activity => {
      const activityDate = new Date(activity.startTimeLocal);
      return activityDate >= trailing48MonthsDate;
    });

    return tempActivities;
  }, [combinedActivities, trailing48MonthsDate]);

  // Initialiser med alle aktivitetstyper valgt kun første gang
  const [hasInitialized, setHasInitialized] = useState(false);
  
  useEffect(() => {
    if (activityTypes.length > 0 && selectedActivityTypes.length === 0 && !hasInitialized) {
      setSelectedActivityTypes(activityTypes);
      setHasInitialized(true);
    }
  }, [activityTypes, selectedActivityTypes.length, hasInitialized]);

  // Callback for å oppdatere data når synkronisering er fullført
  const handleSyncComplete = useCallback(async () => {
    console.log('[Statistikk] Synkronisering fullført, oppdaterer data...');
    
    // Hent datoen for siste aktivitet hvis vi har noen
    if (activities.length > 0) {
      // Finn den nyeste aktiviteten
      const latestActivity = activities.reduce((latest, current) => {
        return new Date(current.startTimeLocal) > new Date(latest.startTimeLocal) ? current : latest;
      });
      
      const latestDate = new Date(latestActivity.startTimeLocal);
      const sinceDate = latestDate.toISOString().split('T')[0]; // Format: YYYY-MM-DD
      
      console.log('[Statistikk] Henter nye aktiviteter siden', sinceDate);
                dispatch(fetchNewActivities({ since: sinceDate, forceRefresh: true }));
    } else {
      // Hvis vi ikke har noen aktiviteter, hent de siste 100
      console.log('[Statistikk] Ingen eksisterende aktiviteter, henter siste 100');
      dispatch(fetchAllActivities({ count: 100 }));
    }
    
    // Oppdater sammendragstabeller i backend
    try {
      const response = await fetch('http://localhost:8000/api/analysis/refresh-summaries', {
        method: 'POST',
      });
      if (response.ok) {
        console.log('[Statistikk] Sammendragstabeller oppdatert');
      }
    } catch (error) {
      console.error('[Statistikk] Feil ved oppdatering av sammendragstabeller:', error);
    }
  }, [dispatch, activities]);

  // Lytter etter synkroniseringshendelser
  useSyncListener(handleSyncComplete);

  // Automatisk sjekk for nye aktiviteter når siden lastes
  useEffect(() => {
    const checkForNewActivities = () => {
      console.log('[Statistikk] Sjekker for nye aktiviteter ved sideinnlasting...');
      
      if (activities.length > 0) {
        // Finn den nyeste aktiviteten
        const latestActivity = activities.reduce((latest, current) => {
          return new Date(current.startTimeLocal) > new Date(latest.startTimeLocal) ? current : latest;
        });
        
        const latestDate = new Date(latestActivity.startTimeLocal);
        const sinceDate = latestDate.toISOString().split('T')[0];
        
        console.log('[Statistikk] Henter nye aktiviteter siden', sinceDate);
        dispatch(fetchNewActivities({ since: sinceDate, forceRefresh: false }));
      } else {
        console.log('[Statistikk] Ingen eksisterende aktiviteter, henter siste 100');
        dispatch(fetchAllActivities({ count: 100 }));
      }
    };

    // Sjekk for nye aktiviteter når komponenten mountes
    checkForNewActivities();

    // Sjekk også når siden får fokus (bruker kommer tilbake til siden)
    const handleFocus = () => {
      console.log('[Statistikk] Side fikk fokus, sjekker for nye aktiviteter...');
      checkForNewActivities();
    };

    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [dispatch, activities.length]);

  useEffect(() => {
    if (status === 'idle') {
      dispatch(fetchAllActivities({ count: 1000 })); // Hent alle aktiviteter
    }
  }, [status, dispatch]);

  useEffect(() => {
    // Sjekk for duplikater i activities-arrayet
    const ids = activities.map(a => a.activityId);
    const uniqueIds = new Set(ids);
    if (ids.length !== uniqueIds.size) {
      const duplicates = ids.filter((id, idx) => ids.indexOf(id) !== idx);
      console.warn('[Statistikk] Duplikater funnet i activities-arrayet:', duplicates);
    }
    console.log(`[Statistikk] Antall aktiviteter: ${ids.length}, unike: ${uniqueIds.size}`);
  }, [activities]);

  const handleActivityTypeChange = (type: string, checked: boolean) => {
    if (checked) {
      setSelectedActivityTypes(prev => [...prev, type]);
    } else {
      setSelectedActivityTypes(prev => prev.filter(t => t !== type));
    }
  };

  const handleSelectAll = () => {
    setSelectedActivityTypes(activityTypes);
  };

  const handleClearAll = () => {
    setSelectedActivityTypes([]);
  };



  const isLoading = status === 'loading';

  // Beregn månedlig statistikk for trailing 12 måneder og sammenlign med året før
  const getMonthlyStats = useMemo(() => {
    const monthlyData: { [key: string]: { distance: number; time: number; count: number } } = {};
    const monthlyDataLastYear: { [key: string]: { distance: number; time: number; count: number } } = {};
    
    // Opprett strukturen for siste 12 måneder
    for (let i = 11; i >= 0; i--) {
      const date = new Date();
      date.setMonth(date.getMonth() - i);
      const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      monthlyData[monthKey] = { distance: 0, time: 0, count: 0 };
    }

    // Opprett strukturen for samme måneder året før
    for (let i = 23; i >= 12; i--) {
      const date = new Date();
      date.setMonth(date.getMonth() - i);
      const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      monthlyDataLastYear[monthKey] = { distance: 0, time: 0, count: 0 };
    }

    // Hent alle aktiviteter for de siste 24 månedene for sammenligning
    const allActivitiesFor24Months = combinedActivities.filter(activity => {
      const activityDate = new Date(activity.startTimeLocal);
      return activityDate >= trailing24MonthsDate && 
             (selectedActivityTypes.length === 0 || selectedActivityTypes.includes(activity.activityType?.typeKey || ''));
    });

    allActivitiesFor24Months.forEach(activity => {
      const activityDate = new Date(activity.startTimeLocal);
      const monthKey = `${activityDate.getFullYear()}-${String(activityDate.getMonth() + 1).padStart(2, '0')}`;
      
      if (monthlyData[monthKey]) {
        monthlyData[monthKey].distance += (activity.distance || 0) / 1000;
        monthlyData[monthKey].time += (activity.duration || 0) / 60;
        monthlyData[monthKey].count += 1;
      } else if (monthlyDataLastYear[monthKey]) {
        monthlyDataLastYear[monthKey].distance += (activity.distance || 0) / 1000;
        monthlyDataLastYear[monthKey].time += (activity.duration || 0) / 60;
        monthlyDataLastYear[monthKey].count += 1;
      }
    });

    return { current: monthlyData, lastYear: monthlyDataLastYear };
  }, [combinedActivities, selectedActivityTypes, trailing24MonthsDate]);

  const monthlyStats = getMonthlyStats;
  
  // Hjelpefunksjon for å beregne endring i prosent
  const calculatePercentChange = useMemo(() => {
    return (current: number, previous: number) => {
      if (previous === 0) return current > 0 ? 100 : 0;
      return ((current - previous) / previous) * 100;
    };
  }, []);

  // Hjelpefunksjon for å finne tilsvarende måned året før
  const getLastYearMonth = useMemo(() => {
    return (currentMonthKey: string) => {
      const [year, month] = currentMonthKey.split('-');
      const lastYearKey = `${parseInt(year) - 1}-${month}`;
      return monthlyStats.lastYear[lastYearKey] || { distance: 0, time: 0, count: 0 };
    };
  }, [monthlyStats]);

  if (error) {
    return (
      <Container>
        <div style={{ color: '#e74c3c', textAlign: 'center', padding: '2rem' }}>
          Error: {error}
        </div>
      </Container>
    );
  }

  return (
    <Container>
      <Header>
        <Title>Treningsstatistikk - Siste 12 måneder</Title>
      </Header>

      <FiltersContainer>
        <FilterSection>
          <FilterTitle>Velg aktivitetstyper</FilterTitle>
          <div style={{ marginBottom: '0.5rem' }}>
            <SelectAllButton onClick={handleSelectAll} disabled={isLoading}>
              Velg alle
            </SelectAllButton>
            <ClearAllButton onClick={handleClearAll} disabled={isLoading}>
              Fjern alle
            </ClearAllButton>
          </div>
          <CheckboxContainer>
            {activityTypes.map((type) => (
              <CheckboxLabel key={type}>
                <Checkbox
                  type="checkbox"
                  checked={selectedActivityTypes.includes(type)}
                  onChange={(e) => handleActivityTypeChange(type, e.target.checked)}
                  disabled={isLoading}
                />
                <CheckboxText>{type}</CheckboxText>
              </CheckboxLabel>
            ))}
          </CheckboxContainer>
          <SelectedTypesDisplay>
            {selectedActivityTypes.length > 0 
              ? `Valgte typer: ${selectedActivityTypes.join(', ')}`
              : 'Ingen aktivitetstyper valgt'}
          </SelectedTypesDisplay>
        </FilterSection>
        

      </FiltersContainer>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '2rem' }}>
          <LoadingSpinner />
          <p>Laster data...</p>
        </div>
      ) : (
        <>
          <PeriodSection>
            <PeriodTitle>
              Totalt siste 12 måneder
              {selectedActivityTypes.length > 0 && selectedActivityTypes.length < activityTypes.length && (
                <span style={{ fontSize: '1rem', color: '#666', fontWeight: 'normal' }}>
                  {' '}({selectedActivityTypes.length} av {activityTypes.length} aktivitetstyper)
                </span>
              )}
            </PeriodTitle>
            <StatsGrid>
              <StatCard>
                <StatTitle>Total distanse</StatTitle>
                <StatValue>
                  {(filteredActivities.reduce((sum, act) => sum + (act.distance || 0), 0) / 1000).toFixed(1)} <StatUnit>km</StatUnit>
                </StatValue>
              </StatCard>

              <StatCard>
                <StatTitle>Total treningstid</StatTitle>
                <StatValue>
                  {Math.round(filteredActivities.reduce((sum, act) => sum + (act.duration || 0), 0) / 3600)} <StatUnit>timer</StatUnit>
                </StatValue>
              </StatCard>

              <StatCard>
                <StatTitle>Antall aktiviteter</StatTitle>
                <StatValue>
                  {filteredActivities.length} <StatUnit>økter</StatUnit>
                </StatValue>
              </StatCard>

              <StatCard>
                <StatTitle>Gjennomsnitt per måned</StatTitle>
                <StatValue>
                  {(filteredActivities.length / 12).toFixed(1)} <StatUnit>økter/måned</StatUnit>
                </StatValue>
              </StatCard>
            </StatsGrid>
          </PeriodSection>

          <PeriodSection>
            <PeriodTitle>Månedlig fordeling</PeriodTitle>
            <StatsGrid>
              {Object.entries(monthlyStats.current).map(([month, stats]) => {
                const lastYearStats = getLastYearMonth(month);
                const distanceChange = calculatePercentChange(stats.distance, lastYearStats.distance);
                const timeChange = calculatePercentChange(stats.time, lastYearStats.time);
                const countChange = calculatePercentChange(stats.count, lastYearStats.count);
                
                return (
                  <StatCard key={month}>
                    <StatTitle>{month}</StatTitle>
                    <StatValue style={{ fontSize: '1.2rem' }}>
                      {stats.distance.toFixed(1)} <StatUnit>km</StatUnit>
                    </StatValue>
                    <div style={{ fontSize: '0.9rem', color: '#666', marginTop: '0.5rem' }}>
                      <div>{Math.round(stats.time / 60)} timer</div>
                      <div>{stats.count} aktiviteter</div>
                    </div>
                    
                    {/* Sammenligning med året før */}
                    <div style={{ fontSize: '0.8rem', marginTop: '0.5rem', borderTop: '1px solid #eee', paddingTop: '0.5rem' }}>
                      <div style={{ fontWeight: 'bold', marginBottom: '0.25rem', color: '#2c3e50' }}>
                        Vs. {parseInt(month.split('-')[0]) - 1}:
                      </div>
                      <div style={{ color: distanceChange >= 0 ? '#27ae60' : '#e74c3c' }}>
                        {distanceChange >= 0 ? '+' : ''}{distanceChange.toFixed(0)}% km
                      </div>
                      <div style={{ color: timeChange >= 0 ? '#27ae60' : '#e74c3c' }}>
                        {timeChange >= 0 ? '+' : ''}{timeChange.toFixed(0)}% tid
                      </div>
                      <div style={{ color: countChange >= 0 ? '#27ae60' : '#e74c3c' }}>
                        {countChange >= 0 ? '+' : ''}{countChange.toFixed(0)}% økter
                      </div>
                    </div>
                  </StatCard>
                );
              })}
            </StatsGrid>
          </PeriodSection>

          <SummaryTables selectedActivityTypes={selectedActivityTypes} />

          <ChartsContainer>
            <MonthlyComparisonChart 
              activities={allFilteredActivities} 
              metric="distance"
              title="Månedlig distanse fra 2022 (valgte aktivitetstyper)"
            />
            <MonthlyComparisonChart 
              activities={allFilteredActivities} 
              metric="time"
              title="Månedlig treningstid fra 2022 (valgte aktivitetstyper)"
            />
          </ChartsContainer>
        </>
      )}
    </Container>
  );
};

export default StatistikkPage; 