'use client';

import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import { api } from '../../utils/api';
import BodyBatteryChart from '../../components/BodyBatteryChart';
import { format, subDays, subWeeks, subMonths, startOfDay, endOfDay } from 'date-fns';
import { nb } from 'date-fns/locale';

// Styled components
const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Title = styled.h1`
  color: #2c3e50;
  text-align: center;
  margin-bottom: 2rem;
  font-size: 2.5rem;
`;

const FilterContainer = styled.div`
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  align-items: center;
`;

const FilterGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const Label = styled.label`
  font-weight: 500;
  color: #374151;
  font-size: 0.9rem;
`;

const Input = styled.input`
  padding: 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 0.9rem;
  
  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 1px #3b82f6;
  }
`;

const Button = styled.button`
  background-color: #3b82f6;
  color: white;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  height: fit-content;
  margin-top: 1.5rem;
  
  &:hover {
    background-color: #2563eb;
  }
  
  &:disabled {
    background-color: #9ca3af;
    cursor: not-allowed;
  }
`;

const QuickFilterButton = styled.button<{ $active?: boolean }>`
  background-color: ${props => props.$active ? '#2563eb' : '#f3f4f6'};
  color: ${props => props.$active ? 'white' : '#374151'};
  padding: 0.5rem 1rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
  
  &:hover {
    background-color: ${props => props.$active ? '#1d4ed8' : '#e5e7eb'};
  }
`;

const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
  font-size: 1.2rem;
  color: #666;
`;

const ErrorContainer = styled.div`
  background: #fee2e2;
  color: #dc2626;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 2rem;
  text-align: center;
`;

const StatsContainer = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
`;

const StatCard = styled.div`
  background: white;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  text-align: center;
`;

const StatValue = styled.div`
  font-size: 1.5rem;
  font-weight: bold;
  color: #3b82f6;
  margin-bottom: 0.5rem;
`;

const StatLabel = styled.div`
  color: #666;
  font-size: 0.9rem;
`;

interface BodyBatteryData {
  date: string;
  max_body_battery: number | null;
  min_body_battery: number | null;
  body_battery_charged: number | null;
  body_battery_drained: number | null;
  body_battery_charged_start: number | null;
  body_battery_drained_start: number | null;
  net_charge: number | null;
}

interface BodyBatteryResponse {
  body_battery_data: BodyBatteryData[];
  total_records: number;
}

interface BodyBatteryStatistics {
  total_records: number;
  average_max_body_battery: number | null;
  average_min_body_battery: number | null;
  highest_body_battery_ever: number | null;
  lowest_body_battery_ever: number | null;
}

const BodyBatteryPage: React.FC = () => {
  const [data, setData] = useState<BodyBatteryData[]>([]);
  const [statistics, setStatistics] = useState<BodyBatteryStatistics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [activeFilter, setActiveFilter] = useState<string>('');

  useEffect(() => {
    // Sett standard tidsperiode (siste 30 dager)
    const end = new Date();
    const start = subDays(end, 30);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter('30d');
  }, []);

  useEffect(() => {
    if (startDate && endDate) {
      fetchBodyBatteryData();
      fetchStatistics();
    }
  }, [startDate, endDate]);

  const fetchBodyBatteryData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await api.getBodyBatteryData(startDate, endDate) as BodyBatteryResponse;
      setData(response.body_battery_data || []);
    } catch (err: any) {
      setError(err.message || 'Feil ved henting av Body Battery-data');
      console.error('Feil ved henting av Body Battery-data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchStatistics = async () => {
    try {
      const response = await api.getBodyBatteryStatistics() as BodyBatteryStatistics;
      setStatistics(response);
    } catch (err: any) {
      console.error('Feil ved henting av Body Battery-statistikk:', err);
    }
  };

  const handleFilterSubmit = () => {
    if (startDate && endDate) {
      setActiveFilter('custom');
      fetchBodyBatteryData();
      fetchStatistics();
    }
  };

  const handleQuickFilter = (days: number, filterName: string) => {
    const end = new Date();
    const start = subDays(end, days);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter(filterName);
  };

  const handleLoadAll = () => {
    const end = new Date();
    const start = subMonths(end, 12); // Siste 12 måneder
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter('all');
  };

  return (
    <Container>
      <Title>Body Battery</Title>

      <FilterContainer>
        <FilterGroup>
          <Label>Fra dato:</Label>
          <Input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </FilterGroup>

        <FilterGroup>
          <Label>Til dato:</Label>
          <Input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </FilterGroup>

        <Button onClick={handleFilterSubmit} disabled={loading}>
          {loading ? 'Laster...' : 'Hent data'}
        </Button>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '1rem' }}>
          <QuickFilterButton
            $active={activeFilter === '7d'}
            onClick={() => handleQuickFilter(7, '7d')}
          >
            7 dager
          </QuickFilterButton>
          <QuickFilterButton
            $active={activeFilter === '30d'}
            onClick={() => handleQuickFilter(30, '30d')}
          >
            30 dager
          </QuickFilterButton>
          <QuickFilterButton
            $active={activeFilter === '90d'}
            onClick={() => handleQuickFilter(90, '90d')}
          >
            90 dager
          </QuickFilterButton>
          <QuickFilterButton
            $active={activeFilter === 'all'}
            onClick={handleLoadAll}
          >
            Alle data
          </QuickFilterButton>
        </div>
      </FilterContainer>

      {error && (
        <ErrorContainer>
          {error}
        </ErrorContainer>
      )}

      {statistics && (
        <StatsContainer>
          <StatCard>
            <StatValue>{statistics.total_records}</StatValue>
            <StatLabel>Totalt antall dager</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>
              {statistics.average_max_body_battery !== null 
                ? `${statistics.average_max_body_battery.toFixed(1)}%`
                : 'N/A'
              }
            </StatValue>
            <StatLabel>Gjennomsnitt høyeste</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>
              {statistics.average_min_body_battery !== null 
                ? `${statistics.average_min_body_battery.toFixed(1)}%`
                : 'N/A'
              }
            </StatValue>
            <StatLabel>Gjennomsnitt laveste</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>
              {statistics.highest_body_battery_ever !== null 
                ? `${statistics.highest_body_battery_ever}%`
                : 'N/A'
              }
            </StatValue>
            <StatLabel>Høyeste noensinne</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>
              {statistics.lowest_body_battery_ever !== null 
                ? `${statistics.lowest_body_battery_ever}%`
                : 'N/A'
              }
            </StatValue>
            <StatLabel>Laveste noensinne</StatLabel>
          </StatCard>
        </StatsContainer>
      )}

      {loading ? (
        <LoadingContainer>
          Laster Body Battery-data...
        </LoadingContainer>
      ) : (
        <>
          {/* Rå daglig serie */}
          <BodyBatteryChart
            data={data}
            title="Body Battery (daglig)"
          />

          {/* 7-dagers glidende snitt uten punktmarkeringer */}
          <BodyBatteryChart
            data={data}
            title="Body Battery (7-dagers snitt)"
            movingAverageDays={7}
            showMovingAverageOnly
            hideDots
          />
        </>
      )}
    </Container>
  );
};

export default BodyBatteryPage; 