'use client';

import { useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '../../store/hooks';
import { fetchActivities } from '../../store/slices/activitiesSlice';
import ActivityChart from '../../components/ActivityChart';
import styled from 'styled-components';

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

export default function GraferPage() {
  const dispatch = useAppDispatch();
  const { items, status, error } = useAppSelector((state) => state.activities);

  useEffect(() => {
    if (status === 'idle') {
      dispatch(fetchActivities());
    }
  }, [status, dispatch]);

  if (status === 'loading') {
    return <div>Laster aktiviteter...</div>;
  }

  if (status === 'failed') {
    return <div>Error: {error}</div>;
  }

  return (
    <Container>
      <Header>
        <Title>Treningsgrafer</Title>
        <Subtitle>Visualisering av treningsdata over tid</Subtitle>
      </Header>

      <ActivityChart
        activities={items}
        metric="distance"
        title="Distanse over tid"
      />

      <ActivityChart
        activities={items}
        metric="duration"
        title="Varighet over tid"
      />

      <ActivityChart
        activities={items}
        metric="average_hr"
        title="Gjennomsnittspuls over tid"
      />

      <ActivityChart
        activities={items}
        metric="calories"
        title="Kalorier over tid"
      />
    </Container>
  );
} 