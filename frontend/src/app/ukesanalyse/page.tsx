'use client';

import { useEffect, useMemo, useState, useCallback } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import styled from 'styled-components';
import { fetchActivitiesByDateRange, selectAllActivities, selectActivitiesStatus } from '../../store/slices/activitiesSlice';
import { AppDispatch, RootState } from '../../store';
import RunningEconomyTable from '../../components/RunningEconomyTable';
import { LegacyChartToggle } from '@/components/charts/ChartShell';
import { useSyncListener } from '../../hooks/useSyncListener';

import RunningEconomyChart from '../../components/RunningEconomyChart';
import PowerPerHeartRateChart from '../../components/PowerPerHeartRateChart';
import CadenceChart from '../../components/CadenceChart';
import StrideLengthChart from '../../components/StrideLengthChart';

const PageContainer = styled.div`
  padding: 0;
  max-width: none;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

const Title = styled.h1`
  color: #0f172a;
  margin-bottom: 0.25rem;
  font-size: 1.5rem;
  font-weight: 600;
`;

const ButtonContainer = styled.div`
  margin-bottom: 0.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 1rem 1.25rem;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 0.75rem;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
`;

const TIME_FILTERS: Array<{ id: string; label: string }> = [
  { id: '3m', label: 'Siste 3 mnd' },
  { id: '6m', label: 'Siste 6 mnd' },
  { id: 'ytd', label: 'År til dato' },
  { id: '12m', label: 'Siste 12 mnd' },
  { id: '3y', label: 'Siste 3 år' },
  { id: 'all', label: 'All historikk' },
];

export default function RunningEconomyPage() {
  const dispatch = useDispatch<AppDispatch>();
  const activities = useSelector(selectAllActivities);
  const status = useSelector(selectActivitiesStatus);
  const [timeFilter, setTimeFilter] = useState('all');

  // Callback for å oppdatere data når synkronisering er fullført
  const handleSyncComplete = useCallback(() => {
    console.log('[RunningEconomy] Synkronisering fullført, henter aktiviteter fra 2010...');
    const end = new Date();
    dispatch(fetchActivitiesByDateRange({
      startDate: '2010-01-01',
      endDate: end.toISOString().split('T')[0],
      forceRefresh: true,
    }));
  }, [dispatch]);

  // Lytter etter synkroniseringshendelser
  useSyncListener(handleSyncComplete);

  // Hent aktiviteter fra 2010 for løpsøkonomi-visualisering
  useEffect(() => {
    const loadActivities = () => {
      const end = new Date();
      const endStr = end.toISOString().split('T')[0];
      console.log('[RunningEconomy] Henter aktiviteter fra 2010-01-01 til', endStr);
      dispatch(fetchActivitiesByDateRange({
        startDate: '2010-01-01',
        endDate: endStr,
        forceRefresh: false,
      }));
    };

    loadActivities();

    const handleFocus = () => {
      console.log('[RunningEconomy] Side fikk fokus, oppdaterer aktiviteter fra 2010...');
      loadActivities();
    };

    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [dispatch]);

  const filteredActivities = useMemo(() => {
    const now = new Date();
    let startDate = new Date();

    switch (timeFilter) {
      case '3m':
        startDate.setMonth(now.getMonth() - 3);
        break;
      case '6m':
        startDate.setMonth(now.getMonth() - 6);
        break;
      case 'ytd':
        startDate = new Date(now.getFullYear(), 0, 1);
        break;
      case '12m':
        startDate.setFullYear(now.getFullYear() - 1);
        break;
      case '3y':
        startDate.setFullYear(now.getFullYear() - 3);
        break;
      case 'all':
        startDate = new Date(0); // Epoch
        break;
      default:
        startDate.setFullYear(now.getFullYear() - 1);
    }
    
    return activities.filter(a => new Date(a.startTimeLocal) >= startDate && a.activityType?.typeKey?.includes('running'));
  }, [activities, timeFilter]);

  if (status === 'loading') {
    return <PageContainer>Laster inn data...</PageContainer>;
  }

  if (status === 'failed') {
    return <PageContainer>Klarte ikke hente data.</PageContainer>;
  }

  const runningActivities = filteredActivities.filter(
          a => a.activityType?.typeKey && a.activityType.typeKey.includes('running') && !a.activityType.typeKey.includes('treadmill')
  );

  return (
    <PageContainer>
      <Title>Løpsøkonomi</Title>
      
      <ButtonContainer>
        {TIME_FILTERS.map((filter) => (
          <LegacyChartToggle
            key={filter.id}
            active={timeFilter === filter.id}
            onClick={() => setTimeFilter(filter.id)}
          >
            {filter.label}
          </LegacyChartToggle>
        ))}
      </ButtonContainer>

      {runningActivities.length === 0 ? (
        <p>Ingen løpedata tilgjengelig for valgt periode.</p>
      ) : (
        <>
          <RunningEconomyChart
            activities={runningActivities}
            title="Løpsøkonomi"
            timeFilter={timeFilter}
          />
          <PowerPerHeartRateChart
            activities={runningActivities}
            title="Kraft per hjertefrekvens"
            timeFilter={timeFilter}
          />
          <CadenceChart
            activities={runningActivities}
            title="Løpskadens"
            timeFilter={timeFilter}
          />
          <StrideLengthChart
            activities={runningActivities}
            title="Skrittlengde"
            timeFilter={timeFilter}
          />
          <RunningEconomyTable activities={runningActivities} />
        </>
      )}
    </PageContainer>
  );
} 