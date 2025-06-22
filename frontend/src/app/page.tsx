'use client';

import { useState, useEffect, useMemo } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../store/hooks';
import { fetchActivities, Activity } from '../store/slices/activitiesSlice';
import ActivityList from '../components/ActivityList';
import ActivityChart from '../components/ActivityChart';
import ActivityFilters from '../components/ActivityFilters';
import DataSyncPanel from '../components/DataSyncPanel';
import RunningEconomyTable from '../components/RunningEconomyTable';

const MainContainer = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Title = styled.h1`
  font-size: 2.5rem;
  color: #333;
  margin-bottom: 2rem;
`;

const Header = styled.header`
  margin-bottom: 2rem;
  text-align: center;
`;

const Subtitle = styled.p`
  color: #666;
  font-size: 1.125rem;
`;

export default function Home() {
  const dispatch = useAppDispatch();
  const { items: activities, status, error } = useAppSelector((state) => state.activities);
  const [filteredActivities, setFilteredActivities] = useState<Activity[]>([]);

  const activityTypes = useMemo(() => {
    const types = activities.map(a => a.activityType?.typeKey).filter(Boolean);
    return Array.from(new Set(types as string[]));
  }, [activities]);

  useEffect(() => {
    if (status === 'idle') {
      dispatch(fetchActivities());
    }
  }, [status, dispatch]);

  useEffect(() => {
    setFilteredActivities(activities);
  }, [activities]);

  const handleFilterChange = (filters: { type: string; startDate: string; endDate: string; }) => {
    let tempActivities = [...activities];

    if (filters.type && filters.type !== 'all') {
      tempActivities = tempActivities.filter(a => a.activityType?.typeKey === filters.type);
    }
    if (filters.startDate) {
      tempActivities = tempActivities.filter(a => new Date(a.startTimeLocal) >= new Date(filters.startDate));
    }
    if (filters.endDate) {
      const endDate = new Date(filters.endDate);
      endDate.setDate(endDate.getDate() + 1);
      tempActivities = tempActivities.filter(a => new Date(a.startTimeLocal) < endDate);
    }
    setFilteredActivities(tempActivities);
  };

  if (status === 'loading') {
    return <div>Laster aktiviteter...</div>;
  }

  if (status === 'failed') {
    return <div>Error: {error}</div>;
  }

  return (
    <MainContainer>
      <Title>Treningsdagbok</Title>
      <DataSyncPanel />
      <ActivityFilters onFilterChange={handleFilterChange} activityTypes={activityTypes} />
      <ActivityChart activities={filteredActivities} metric="distance" title="Distanse over tid" />
      <RunningEconomyTable activities={filteredActivities} />
      <ActivityList />
    </MainContainer>
  );
}
