'use client';

import { useEffect, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../../store/hooks';
import { fetchSleepByDateRange } from '../../store/slices/sleepSlice';
import styled from 'styled-components';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';

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
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

const ChartCard = styled.div`
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  height: 400px;
`;

const ChartTitle = styled.h3`
  color: #2c3e50;
  margin: 0 0 1rem 0;
  font-size: 1.1rem;
  text-align: center;
`;

const COLORS = ['#3498db', '#2ecc71', '#9b59b6', '#e74c3c'];

interface Averages {
  totalSleep: number;
  deepSleep: number;
  lightSleep: number;
  remSleep: number;
  awake: number;
}

export default function SovnPage() {
  const dispatch = useAppDispatch();
  const { items: sleepData, status, error } = useAppSelector((state) => state.sleep);
  
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
      dispatch(fetchSleepByDateRange({ startDate, endDate }));
    }
  }, [status, dispatch, startDate, endDate]);

  const handleFilterClick = () => {
    dispatch(fetchSleepByDateRange({ startDate, endDate }));
  };

  const handleForceRefresh = () => {
    dispatch(fetchSleepByDateRange({ startDate, endDate, forceRefresh: true }));
  };

  const isLoading = status === 'loading';

  // Beregn gjennomsnittsverdier
  const averages = sleepData.reduce((acc, sleep) => {
    acc.totalSleep += sleep.duration || 0;
    acc.deepSleep += sleep.deep_sleep || 0;
    acc.lightSleep += sleep.light_sleep || 0;
    acc.remSleep += sleep.rem_sleep || 0;
    acc.awake += sleep.awake || 0;
    return acc;
  }, {
    totalSleep: 0,
    deepSleep: 0,
    lightSleep: 0,
    remSleep: 0,
    awake: 0
  } as Averages);

  const count = sleepData.length;
  if (count > 0) {
    (Object.keys(averages) as Array<keyof Averages>).forEach(key => {
      averages[key] = averages[key] / count;
    });
  }

  // Data for søvnfordelingsgraf
  const sleepDistribution = [
    { name: 'Dyp søvn', value: averages.deepSleep },
    { name: 'Lett søvn', value: averages.lightSleep },
    { name: 'REM søvn', value: averages.remSleep },
    { name: 'Våken', value: averages.awake }
  ];

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
        <Title>Søvnanalyse</Title>
        <Subtitle>Oversikt over søvnmønstre og kvalitet</Subtitle>
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
          <p>Laster søvndata...</p>
        </div>
      ) : (
        <>
          <StatsGrid>
            <StatCard>
              <StatTitle>Gjennomsnittlig søvn</StatTitle>
              <StatValue>
                {averages.totalSleep.toFixed(1)} <StatUnit>timer</StatUnit>
              </StatValue>
            </StatCard>

            <StatCard>
              <StatTitle>Gjennomsnittlig dyp søvn</StatTitle>
              <StatValue>
                {averages.deepSleep.toFixed(1)} <StatUnit>timer</StatUnit>
              </StatValue>
            </StatCard>

            <StatCard>
              <StatTitle>Gjennomsnittlig REM søvn</StatTitle>
              <StatValue>
                {averages.remSleep.toFixed(1)} <StatUnit>timer</StatUnit>
              </StatValue>
            </StatCard>

            <StatCard>
              <StatTitle>Antall netter registrert</StatTitle>
              <StatValue>
                {sleepData.length} <StatUnit>netter</StatUnit>
              </StatValue>
            </StatCard>
          </StatsGrid>

          <ChartsContainer>
            <ChartCard>
              <ChartTitle>Søvnlengde over tid</ChartTitle>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sleepData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="date" 
                    angle={-45}
                    textAnchor="end"
                    height={70}
                    tickFormatter={(date) => new Date(date).toLocaleDateString('no-NO')}
                  />
                  <YAxis label={{ value: 'Timer', angle: -90, position: 'insideLeft' }} />
                  <Tooltip
                    formatter={(value: number) => [`${value.toFixed(1)} timer`]}
                    labelFormatter={(date) => new Date(date).toLocaleDateString('no-NO')}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="duration" name="Total søvn" stroke="#3498db" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard>
              <ChartTitle>Gjennomsnittlig søvnfordeling</ChartTitle>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sleepDistribution}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ name, value }) => `${name}: ${value.toFixed(1)}t`}
                  >
                    {sleepDistribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => `${value.toFixed(1)} timer`} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>
          </ChartsContainer>
        </>
      )}
    </Container>
  );
} 