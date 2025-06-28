'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import styled from 'styled-components';
import { fetchActivities, selectAllActivities, selectActivitiesStatus } from '../../store/slices/activitiesSlice';
import { AppDispatch, RootState } from '../../store';
import RunningEconomyTable from '../../components/RunningEconomyTable';
import DataSyncPanel from '../../components/DataSyncPanel';
import RunningEconomyChart from '../../components/RunningEconomyChart';
import CadenceChart from '../../components/CadenceChart';
import StrideLengthChart from '../../components/StrideLengthChart';

const PageContainer = styled.div`
  padding: 2rem;
  background-color: #f4f7f6;
`;

const Title = styled.h1`
  color: #2c3e50;
  margin-bottom: 2rem;
`;

const ButtonContainer = styled.div`
  margin-bottom: 1rem;
  display: flex;
  gap: 0.5rem;
`;

const Button = styled.button<{ $active: boolean }>`
  background-color: ${props => (props.$active ? '#3498db' : '#ecf0f1')};
  color: ${props => (props.$active ? 'white' : '#2c3e50')};
  border: 1px solid ${props => (props.$active ? '#3498db' : '#bdc3c7')};
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background-color: ${props => (props.$active ? '#2980b9' : '#e0e5e9')};
  }
`;

export default function RunningEconomyPage() {
  const dispatch = useDispatch<AppDispatch>();
  const activities = useSelector(selectAllActivities);
  const status = useSelector(selectActivitiesStatus);
  const [timeFilter, setTimeFilter] = useState('12m');

  useEffect(() => {
    if (status === 'idle') {
      dispatch(fetchActivities());
    }
  }, [status, dispatch]);

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
    
    return activities.filter(a => new Date(a.startTimeLocal) >= startDate && a.activityType.typeKey.includes('running'));
  }, [activities, timeFilter]);

  if (status === 'loading') {
    return <PageContainer>Laster inn data...</PageContainer>;
  }

  if (status === 'failed') {
    return <PageContainer>Klarte ikke hente data.</PageContainer>;
  }

  const runningActivities = filteredActivities.filter(
    a => a.activityType.typeKey && a.activityType.typeKey.includes('running') && !a.activityType.typeKey.includes('treadmill')
  );

  return (
    <PageContainer>
      <Title>Løpsøkonomi</Title>
      <DataSyncPanel />
      
      <ButtonContainer>
        <Button $active={timeFilter === '3m'} onClick={() => setTimeFilter('3m')}>Siste 3 mnd</Button>
        <Button $active={timeFilter === '6m'} onClick={() => setTimeFilter('6m')}>Siste 6 mnd</Button>
        <Button $active={timeFilter === 'ytd'} onClick={() => setTimeFilter('ytd')}>År til dato</Button>
        <Button $active={timeFilter === '12m'} onClick={() => setTimeFilter('12m')}>Siste 12 mnd</Button>
        <Button $active={timeFilter === '3y'} onClick={() => setTimeFilter('3y')}>Siste 3 år</Button>
        <Button $active={timeFilter === 'all'} onClick={() => setTimeFilter('all')}>All historikk</Button>
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