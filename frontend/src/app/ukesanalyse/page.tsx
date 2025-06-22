'use client';

import React, { useState, useMemo } from 'react';
import styled from 'styled-components';
import { useSelector } from 'react-redux';
import { subMonths, subYears } from 'date-fns';
import { RootState } from '@/store';
import WeeklyRunningAnalysis from '@/components/WeeklyRunningAnalysis';
import RunningEconomyTable from '@/components/RunningEconomyTable';
import DataSyncPanel from '@/components/DataSyncPanel';

const PageContainer = styled.div`
  padding: 20px;
  background-color: #1a1a1a;
  color: #f0f0f0;
`;

const Title = styled.h1`
  color: #f0f0f0;
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
`;

const FilterButton = styled.button<{ $isActive: boolean }>`
  background-color: ${props => props.$isActive ? '#007bff' : '#555'};
  color: white;
  border: none;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  &:hover {
    background-color: ${props => props.$isActive ? '#0056b3' : '#666'};
  }
`;

const UkeanalysePage = () => {
  const { items: activities } = useSelector((state: RootState) => state.activities);
  const [filter, setFilter] = useState<'all' | '12m' | '3y' | '5y' | '10y'>('all');

  const filteredActivities = useMemo(() => {
    if (filter === 'all') {
      return activities;
    }

    const now = new Date();
    let startDate: Date;

    switch (filter) {
      case '12m':
        startDate = subMonths(now, 12);
        break;
      case '3y':
        startDate = subYears(now, 3);
        break;
      case '5y':
        startDate = subYears(now, 5);
        break;
      case '10y':
        startDate = subYears(now, 10);
        break;
      default:
        return activities;
    }

    return activities.filter(a => new Date(a.start_time) >= startDate);
  }, [activities, filter]);

  return (
    <PageContainer>
      <DataSyncPanel />
      <Title>Løpsøkonomi</Title>

      <ButtonGroup>
        <FilterButton $isActive={filter === 'all'} onClick={() => setFilter('all')}>Alle data</FilterButton>
        <FilterButton $isActive={filter === '12m'} onClick={() => setFilter('12m')}>Siste 12 mnd</FilterButton>
        <FilterButton $isActive={filter === '3y'} onClick={() => setFilter('3y')}>Siste 3 år</FilterButton>
        <FilterButton $isActive={filter === '5y'} onClick={() => setFilter('5y')}>Siste 5 år</FilterButton>
        <FilterButton $isActive={filter === '10y'} onClick={() => setFilter('10y')}>Siste 10 år</FilterButton>
      </ButtonGroup>

      <WeeklyRunningAnalysis activities={filteredActivities} />
      <RunningEconomyTable activities={filteredActivities} />
    </PageContainer>
  );
};

export default UkeanalysePage; 