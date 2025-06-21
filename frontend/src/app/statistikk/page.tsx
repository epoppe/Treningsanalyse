'use client';

import { useEffect, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../../store/hooks';
import { fetchActivitiesByDateRange } from '../../store/slices/activitiesSlice';
import styled from 'styled-components';
import ActivityChart from '../../components/ActivityChart';

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

const DateFilterContainer = styled.div`
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  justify-content: center;
  align-items: center;
`;

const DateInput = styled.input`
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
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
`;

const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin-top: 2rem;
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

const ChartsContainer = styled.div`
  margin-top: 2rem;
`;

const ButtonContainer = styled.div`
  display: flex;
  gap: 1rem;
  justify-content: center;
`;

const Button = styled.button`
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

export default function StatistikkPage() {
  const dispatch = useAppDispatch();
  const { items: activities, status, error } = useAppSelector((state) => state.activities);
  
  // Sett standard datoperiode til siste 30 dager
  const [startDate, setStartDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 30);
    return date.toISOString().split('T')[0];
  });
  
  const [endDate, setEndDate] = useState(() => {
    return new Date().toISOString().split('T')[0];
  });

  useEffect(() => {
    if (status === 'idle') {
      dispatch(fetchActivitiesByDateRange({ startDate, endDate }));
    }
  }, [status, dispatch, startDate, endDate]);

  const handleFilterClick = () => {
    dispatch(fetchActivitiesByDateRange({ startDate, endDate }));
  };

  const handleForceRefresh = () => {
    dispatch(fetchActivitiesByDateRange({ startDate, endDate, forceRefresh: true }));
  };

  const isLoading = status === 'loading';

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
        <Title>Treningsstatistikk</Title>
        <Subtitle>Oversikt over dine treningsprestasjoner</Subtitle>
      </Header>

      <DateFilterContainer>
        <DateInput
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          disabled={isLoading}
        />
        <span>til</span>
        <DateInput
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          disabled={isLoading}
        />
        <ButtonContainer>
          <Button onClick={handleFilterClick} disabled={isLoading}>
            {isLoading ? <LoadingSpinner /> : 'Oppdater periode'}
          </Button>
          <Button 
            onClick={handleForceRefresh} 
            disabled={isLoading}
            style={{ background: '#e74c3c' }}
          >
            {isLoading ? <LoadingSpinner /> : 'Oppdater fra Garmin'}
          </Button>
        </ButtonContainer>
      </DateFilterContainer>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '2rem' }}>
          <LoadingSpinner />
          <p>Laster data...</p>
        </div>
      ) : (
        <>
          <StatsGrid>
            <StatCard>
              <StatTitle>Total distanse</StatTitle>
              <StatValue>
                {activities.reduce((sum, act) => sum + (act.distance || 0), 0).toFixed(1)} <StatUnit>km</StatUnit>
              </StatValue>
            </StatCard>

            <StatCard>
              <StatTitle>Total treningstid</StatTitle>
              <StatValue>
                {Math.round(activities.reduce((sum, act) => sum + (act.duration || 0), 0))} <StatUnit>min</StatUnit>
              </StatValue>
            </StatCard>

            <StatCard>
              <StatTitle>Totalt kaloriforbruk</StatTitle>
              <StatValue>
                {Math.round(activities.reduce((sum, act) => sum + (act.calories || 0), 0))} <StatUnit>kcal</StatUnit>
              </StatValue>
            </StatCard>

            <StatCard>
              <StatTitle>Gjennomsnittlig puls</StatTitle>
              <StatValue>
                {Math.round(
                  activities.reduce((sum, act) => sum + (act.average_hr || 0), 0) / 
                  activities.filter(act => act.average_hr).length || 0
                )} <StatUnit>bpm</StatUnit>
              </StatValue>
            </StatCard>

            <StatCard>
              <StatTitle>Antall aktiviteter</StatTitle>
              <StatValue>
                {activities.length} <StatUnit>økter</StatUnit>
              </StatValue>
            </StatCard>

            <StatCard>
              <StatTitle>Mest populære aktivitet</StatTitle>
              <StatValue style={{ fontSize: '1.5rem' }}>
                {Object.entries(
                  activities.reduce((acc, act) => {
                    acc[act.type] = (acc[act.type] || 0) + 1;
                    return acc;
                  }, {} as Record<string, number>)
                ).sort(([,a], [,b]) => b - a)[0]?.[0] || 'Ingen aktiviteter'}
              </StatValue>
            </StatCard>
          </StatsGrid>

          <ChartsContainer>
            <ActivityChart
              activities={activities}
              metric="distance"
              title="Distanse over tid"
            />

            <ActivityChart
              activities={activities}
              metric="duration"
              title="Treningstid over tid"
            />

            <ActivityChart
              activities={activities}
              metric="average_hr"
              title="Gjennomsnittspuls over tid"
            />

            <ActivityChart
              activities={activities}
              metric="calories"
              title="Kaloriforbruk over tid"
            />
          </ChartsContainer>
        </>
      )}
    </Container>
  );
} 