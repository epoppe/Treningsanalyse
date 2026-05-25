'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import styled from 'styled-components';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts';
import { analysisApi } from '../../utils/api';
import { format, subDays, subMonths, startOfDay } from 'date-fns';
import { nb } from 'date-fns/locale';

const PageContainer = styled.div`
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
`;

const Title = styled.h1`
  color: #2c3e50;
  margin-bottom: 2rem;
  text-align: center;
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

const ChartContainer = styled.div`
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
`;

const ChartTitle = styled.h3`
  margin: 0 0 1rem 0;
  color: #2c3e50;
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

interface VO2MaxData {
  date: string;
  datetime: string;
  vo2max: number;
  activity_id: string;
  activity_name: string;
  distance?: number;
  duration?: number;
  average_pace?: number;
  average_heart_rate?: number;
}

interface VO2MaxResponse {
  vo2max_history: VO2MaxData[];
  total_records: number;
}

export default function VO2MaxPage() {
  const [data, setData] = useState<VO2MaxData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [activeFilter, setActiveFilter] = useState<string>('');

  useEffect(() => {
    // Sett standard tidsperiode (siste 12 måneder)
    const end = new Date();
    const start = subMonths(end, 12);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter('12m');
  }, []);

  const fetchVO2MaxData = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response: VO2MaxResponse = await analysisApi.getVo2MaxHistory(startDate, endDate) as VO2MaxResponse;
      setData(response.vo2max_history || []);
    } catch (err: any) {
      setError(err.message || 'Feil ved henting av VO2Max-data');
      console.error('Feil ved henting av VO2Max-data:', err);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  useEffect(() => {
    if (startDate && endDate) {
      fetchVO2MaxData();
    }
  }, [startDate, endDate, fetchVO2MaxData]);

  const handleQuickFilter = (months: number, filterName: string) => {
    const end = new Date();
    const start = subMonths(end, months);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter(filterName);
  };

  const chartData = useMemo(() => {
    return data.map((item) => {
      return {
        date: format(new Date(item.date), 'dd.MM.yyyy'),
        fullDate: item.date,
        vo2max: item.vo2max,
        activity_name: item.activity_name
      };
    });
  }, [data]);

  const statistics = useMemo(() => {
    if (data.length === 0) return null;
    
    const values = data.map(d => d.vo2max).filter(v => v !== null && v !== undefined);
    if (values.length === 0) return null;
    
    const sorted = [...values].sort((a, b) => a - b);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const min = sorted[0];
    const max = sorted[sorted.length - 1];
    
    // Beregn endring (første vs siste)
    const first = data[0]?.vo2max;
    const last = data[data.length - 1]?.vo2max;
    const change = first && last ? last - first : null;
    const changePercent = first && last ? ((change! / first) * 100) : null;
    
    return {
      total_records: data.length,
      average: avg,
      min,
      max,
      change,
      changePercent
    };
  }, [data]);

  return (
    <PageContainer>
      <Title>VO2Max Historikk</Title>

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

        <Button onClick={fetchVO2MaxData} disabled={loading || !startDate || !endDate}>
          {loading ? 'Laster...' : 'Hent data'}
        </Button>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '1rem', width: '100%' }}>
          <QuickFilterButton
            $active={activeFilter === '3m'}
            onClick={() => handleQuickFilter(3, '3m')}
          >
            3 mnd
          </QuickFilterButton>
          <QuickFilterButton
            $active={activeFilter === '6m'}
            onClick={() => handleQuickFilter(6, '6m')}
          >
            6 mnd
          </QuickFilterButton>
          <QuickFilterButton
            $active={activeFilter === '12m'}
            onClick={() => handleQuickFilter(12, '12m')}
          >
            12 mnd
          </QuickFilterButton>
          <QuickFilterButton
            $active={activeFilter === '24m'}
            onClick={() => handleQuickFilter(24, '24m')}
          >
            24 mnd
          </QuickFilterButton>
          <QuickFilterButton
            $active={activeFilter === 'all'}
            onClick={() => {
              setStartDate('2020-01-01');
              setEndDate(format(new Date(), 'yyyy-MM-dd'));
              setActiveFilter('all');
            }}
          >
            All historikk
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
            <StatLabel>Totalt antall målinger</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{statistics.average.toFixed(1)}</StatValue>
            <StatLabel>Gjennomsnittlig VO2Max</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{statistics.max.toFixed(1)}</StatValue>
            <StatLabel>Høyeste VO2Max</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{statistics.min.toFixed(1)}</StatValue>
            <StatLabel>Laveste VO2Max</StatLabel>
          </StatCard>
          {statistics.change !== null && (
            <StatCard>
              <StatValue style={{ color: statistics.change! >= 0 ? '#10b981' : '#ef4444' }}>
                {statistics.change! >= 0 ? '+' : ''}{statistics.change!.toFixed(1)}
                {statistics.changePercent !== null && ` (${statistics.changePercent!.toFixed(1)}%)`}
              </StatValue>
              <StatLabel>Endring (første → siste)</StatLabel>
            </StatCard>
          )}
        </StatsContainer>
      )}

      {loading ? (
        <LoadingContainer>
          Laster VO2Max-data...
        </LoadingContainer>
      ) : data.length > 0 ? (
        <>
          <ChartContainer>
            <ChartTitle>VO2Max over tid</ChartTitle>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="date" 
                  angle={-45}
                  textAnchor="end"
                  height={80}
                  interval="preserveStartEnd"
                />
                <YAxis 
                  label={{ value: 'VO2Max', angle: -90, position: 'insideLeft' }}
                  domain={['dataMin - 2', 'dataMax + 2']}
                />
                <Tooltip 
                  formatter={(value: any, name: string) => {
                    if (name === 'vo2max') return [value.toFixed(1), 'VO2Max'];
                    return [value, name];
                  }}
                  labelFormatter={(label) => `Dato: ${label}`}
                />
                <Legend />
                <Line 
                  type="monotone" 
                  dataKey="vo2max" 
                  stroke="#3b82f6" 
                  strokeWidth={2}
                  dot={false}
                  name="VO2Max"
                />
              </LineChart>
            </ResponsiveContainer>
          </ChartContainer>
        </>
      ) : (
        <ErrorContainer>
          Ingen VO2Max-data funnet for valgt periode.
        </ErrorContainer>
      )}
    </PageContainer>
  );
}

