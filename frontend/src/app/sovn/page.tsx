'use client';

import React, { useEffect, useMemo, useState } from 'react';
import styled from 'styled-components';
import { api } from '../../utils/api';
import { format, subDays } from 'date-fns';
import { nb } from 'date-fns/locale';
import { useSleepData } from '../../hooks/useHealthData';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  BarChart,
  Bar
} from 'recharts';

const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Title = styled.h1`
  color: #2c3e50;
  text-align: center;
  margin-bottom: 2rem;
  font-size: 2.2rem;
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
  &:hover { background-color: #2563eb; }
  &:disabled { background-color: #9ca3af; cursor: not-allowed; }
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
  &:hover { background-color: ${props => props.$active ? '#1d4ed8' : '#e5e7eb'}; }
`;

const ChartCard = styled.div`
  background: white;
  padding: 1rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
  height: 400px;
`;

const ChartTitle = styled.h3`
  margin: 0 0 1rem 0;
  color: #2c3e50;
`;

const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: 120px;
  font-size: 1.1rem;
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

type SleepDay = {
  date: string;
  sleep_time?: number | null;   // minutter
  sleep_goal?: number | null;   // minutter
  sleep_score?: number | null;  // score
  deep_sleep?: number | null;   // minutter
  light_sleep?: number | null;  // minutter
  rem_sleep?: number | null;    // minutter
  awake_time?: number | null;   // minutter
  total_sleep?: number | null;  // minutter
};

const formatDateShort = (iso: string) => format(new Date(iso), 'dd.MM', { locale: nb });

export default function SovnPage() {
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [activeFilter, setActiveFilter] = useState<string>('');

  useEffect(() => {
    const end = new Date();
    const start = subDays(end, 30);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter('30d');
  }, []);

  // Bruk React Query for data fetching med automatisk caching
  const { data: sleepData, isLoading: loading, error: queryError } = useSleepData(
    startDate,
    endDate,
    !!startDate && !!endDate
  );

  const error = queryError ? String(queryError) : null;
  const days: SleepDay[] = sleepData 
    ? (sleepData as any[]).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    : [];

  const handleQuickFilter = (days: number, name: string) => {
    const end = new Date();
    const start = subDays(end, days);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter(name);
  };

  const handleSubmit = () => {
    setActiveFilter('custom');
    // Effekt vil trigge last
  };

  // Mapp for grafer: konverter minutter til timer for faser og søvntid
  const chartData = useMemo(() => {
    return days.map(d => {
      const sleep_hours_raw = d.sleep_time != null ? d.sleep_time / 60 : null;
      const total_sleep_hours_raw = d.total_sleep != null ? d.total_sleep / 60 : null;

      // Rå verdier for faser (i timer). 0 timer regnes som "mangler" for linjegrafen.
      const deep_val = d.deep_sleep != null ? d.deep_sleep / 60 : null;
      const light_val = d.light_sleep != null ? d.light_sleep / 60 : null;
      const rem_val = d.rem_sleep != null ? d.rem_sleep / 60 : null;

      const phase_sum_raw = (deep_val || 0) + (light_val || 0) + (rem_val || 0);

      // Gyldige verdier for linjegrafen: > 0
      const sleep_hours_valid = sleep_hours_raw && sleep_hours_raw > 0 ? sleep_hours_raw : null;
      const total_sleep_hours_valid = total_sleep_hours_raw && total_sleep_hours_raw > 0 ? total_sleep_hours_raw : null;
      const phase_sum_valid = phase_sum_raw > 0 ? phase_sum_raw : null;

      const merged = (sleep_hours_valid ?? total_sleep_hours_valid ?? phase_sum_valid) ?? null;

      // Bar-grafene: behold 0 for å vise "ingen data" eksplisitt i stacken,
      // men dette påvirker ikke linjen (som bruker merged)
      const deep_hours = deep_val ?? 0;
      const light_hours = light_val ?? 0;
      const rem_hours = rem_val ?? 0;

      return {
        date: d.date,
        sleep_hours: sleep_hours_raw,
        sleep_goal_hours: d.sleep_goal != null ? d.sleep_goal / 60 : null,
        total_sleep_hours: total_sleep_hours_raw,
        sleep_hours_merged: merged,
        deep_hours,
        light_hours,
        rem_hours,
        awake_hours: d.awake_time != null ? d.awake_time / 60 : 0,
        score: d.sleep_score ?? null,
      };
    });
  }, [days]);

  return (
    <Container>
      <Title>Søvn</Title>

      <FilterContainer>
        <FilterGroup>
          <Label>Fra dato:</Label>
          <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
        </FilterGroup>
        <FilterGroup>
          <Label>Til dato:</Label>
          <Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
        </FilterGroup>
        <Button onClick={handleSubmit} disabled={loading}>{loading ? 'Laster...' : 'Hent data'}</Button>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '1rem' }}>
          <QuickFilterButton $active={activeFilter==='7d'} onClick={() => handleQuickFilter(7,'7d')}>7 dager</QuickFilterButton>
          <QuickFilterButton $active={activeFilter==='30d'} onClick={() => handleQuickFilter(30,'30d')}>30 dager</QuickFilterButton>
          <QuickFilterButton $active={activeFilter==='90d'} onClick={() => handleQuickFilter(90,'90d')}>90 dager</QuickFilterButton>
        </div>
      </FilterContainer>

      {error && <ErrorContainer>{error}</ErrorContainer>}

      {loading ? (
        <LoadingContainer>Laster søvndata...</LoadingContainer>
      ) : (
        <>
          {/* Søvntid vs mål */}
          <ChartCard>
            <ChartTitle>Søvntid (timer) og søvnmål</ChartTitle>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tickFormatter={formatDateShort} />
                <YAxis yAxisId="left" label={{ value: 'Timer', angle: -90, position: 'insideLeft' }} />
                <Tooltip formatter={(v: any, n: any) => [n?.toLowerCase().includes('score') ? v : `${v?.toFixed ? v.toFixed(1) : v} t`, n]} labelFormatter={(l) => format(new Date(l), 'EEEE, dd. MMMM yyyy', { locale: nb })} />
                <Legend />
                <Line yAxisId="left" type="monotone" dataKey="sleep_hours_merged" name="Søvntid" stroke="#3498db" dot={false} strokeWidth={2} connectNulls />
                <Line yAxisId="left" type="monotone" dataKey="sleep_goal_hours" name="Mål" stroke="#95a5a6" dot={false} strokeDasharray="5 5" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Søvnfaser */}
          <ChartCard>
            <ChartTitle>Søvnfaser per dag (timer)</ChartTitle>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tickFormatter={formatDateShort} />
                <YAxis label={{ value: 'Timer', angle: -90, position: 'insideLeft' }} />
                <Tooltip formatter={(v: any, n: any) => [`${v?.toFixed ? v.toFixed(1) : v} t`, n]} labelFormatter={(l) => format(new Date(l), 'EEEE, dd. MMMM yyyy', { locale: nb })} />
                <Legend />
                <Bar stackId="sleep" dataKey="deep_hours" name="Dyp" fill="#2ecc71" />
                <Bar stackId="sleep" dataKey="light_hours" name="Lett" fill="#3498db" />
                <Bar stackId="sleep" dataKey="rem_hours" name="REM" fill="#9b59b6" />
                <Bar stackId="sleep" dataKey="awake_hours" name="Våken" fill="#e74c3c" />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          
        </>
      )}
    </Container>
  );
}


