'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import styled from 'styled-components';
import {
  Area,
  Bar,
  BarChart,
  ComposedChart,
  Line,
  ResponsiveContainer,
} from 'recharts';
import { CHART_MARGIN, chartColor } from '@/components/charts/chartTheme';
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from '@/components/charts/ThemedRecharts';
import { LegacyChartFrame, LegacyChartToggle } from '@/components/charts/ChartShell';
import { axisLabelProps, formatMinutesValue } from '@/lib/chartFormatters';
import { getMetricDefinition, SERIES_LABELS } from '@/lib/metrics';
import { api } from '../../utils/api';
import { format, subDays, subMonths, startOfDay } from 'date-fns';
import { nb } from 'date-fns/locale';

const stressDef = getMetricDefinition('stressLevel');

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

interface StressData {
  date: string;
  stress_level?: number;
  stress_time?: number;
  rest_time?: number;
  low_stress_time?: number;
  medium_stress_time?: number;
  high_stress_time?: number;
  total_time?: number;
}

const formatTime = (minutes: number | null | undefined): string => {
  if (minutes === null || minutes === undefined) return '0 min';
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  if (hours > 0) {
    return `${hours}t ${mins}m`;
  }
  return `${mins} min`;
};

const calculateMovingAverage = (data: StressData[], period: number, field: keyof StressData): number[] => {
  const result: number[] = [];
  for (let i = 0; i < data.length; i++) {
    const start = Math.max(0, i - period + 1);
    const subset = data.slice(start, i + 1)
      .map(d => d[field] as number)
      .filter(v => v !== null && v !== undefined);
    if (subset.length > 0) {
      const avg = subset.reduce((acc, val) => acc + val, 0) / subset.length;
      result.push(avg);
    } else {
      result.push(NaN);
    }
  }
  return result;
};

export default function StressPage() {
  const [data, setData] = useState<StressData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [activeFilter, setActiveFilter] = useState<string>('');
  const [showTrend, setShowTrend] = useState(true);

  useEffect(() => {
    // Sett standard tidsperiode (siste 30 dager) - VIKTIG: Vi er i 2024
    const end = new Date();
    const start = subDays(end, 30);
    
    console.log('Setting dates - Start:', format(start, 'yyyy-MM-dd'), 'End:', format(end, 'yyyy-MM-dd'));
    
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter('30d');
  }, []);

  const fetchStressData = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await api.getStressRange(startDate, endDate) as StressData[];
      setData(response || []);
    } catch (err: any) {
      setError(err.message || 'Feil ved henting av stress-data');
      console.error('Feil ved henting av stress-data:', err);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  useEffect(() => {
    if (startDate && endDate) {
      fetchStressData();
    }
  }, [startDate, endDate, fetchStressData]);

  const handleQuickFilter = (days: number, filterName: string) => {
    const end = new Date();
    const start = subDays(end, days);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter(filterName);
  };

  const chartData = useMemo(() => {
    const movingAvgStressLevel = calculateMovingAverage(data, 7, 'stress_level');
    const movingAvgStressTime = calculateMovingAverage(data, 7, 'stress_time');
    
    return data.map((item, index) => {
      const stressTime = item.stress_time || 0;
      const restTime = item.rest_time || 0;
      const totalTime = item.total_time || (stressTime + restTime);
      const stressPercent = totalTime > 0 ? (stressTime / totalTime) * 100 : 0;
      
      return {
        date: format(new Date(item.date), 'dd.MM.yyyy'),
        fullDate: item.date,
        stress_level: item.stress_level || null,
        stress_time: stressTime,
        rest_time: restTime,
        low_stress_time: item.low_stress_time || 0,
        medium_stress_time: item.medium_stress_time || 0,
        high_stress_time: item.high_stress_time || 0,
        total_time: totalTime,
        stress_percent: stressPercent,
        movingAverage7d: !isNaN(movingAvgStressLevel[index]) ? movingAvgStressLevel[index] : null,
        movingAverage7dTime: !isNaN(movingAvgStressTime[index]) ? movingAvgStressTime[index] : null
      };
    });
  }, [data]);

  const statistics = useMemo(() => {
    if (data.length === 0) return null;
    
    const stressTimes = data.map(d => d.stress_time || 0).filter(v => v > 0);
    const restTimes = data.map(d => d.rest_time || 0).filter(v => v > 0);
    const highStressTimes = data.map(d => d.high_stress_time || 0).filter(v => v > 0);
    const stressLevels = data.map(d => d.stress_level).filter(v => v !== null && v !== undefined) as number[];
    
    if (stressTimes.length === 0 && stressLevels.length === 0) return null;
    
    const avgStress = stressTimes.length > 0 ? stressTimes.reduce((a, b) => a + b, 0) / stressTimes.length : 0;
    const avgRest = restTimes.length > 0 ? restTimes.reduce((a, b) => a + b, 0) / restTimes.length : 0;
    const avgHighStress = highStressTimes.length > 0 ? highStressTimes.reduce((a, b) => a + b, 0) / highStressTimes.length : 0;
    const maxStress = stressTimes.length > 0 ? Math.max(...stressTimes) : 0;
    const avgStressLevel = stressLevels.length > 0 ? stressLevels.reduce((a, b) => a + b, 0) / stressLevels.length : null;
    const maxStressLevel = stressLevels.length > 0 ? Math.max(...stressLevels) : null;
    const minStressLevel = stressLevels.length > 0 ? Math.min(...stressLevels) : null;
    const totalDays = data.length;
    const daysWithStress = stressTimes.length;
    
    return {
      total_days: totalDays,
      days_with_stress: daysWithStress,
      average_stress: avgStress,
      average_rest: avgRest,
      average_high_stress: avgHighStress,
      max_stress: maxStress,
      average_stress_level: avgStressLevel,
      max_stress_level: maxStressLevel,
      min_stress_level: minStressLevel
    };
  }, [data]);

  return (
    <PageContainer>
      <Title>Stress Historikk</Title>

      <FilterContainer>
        <FilterGroup>
          <Label>Fra dato:</Label>
          <Input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            min="2020-01-01"
          />
        </FilterGroup>

        <FilterGroup>
          <Label>Til dato:</Label>
          <Input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            min="2020-01-01"
          />
        </FilterGroup>

        <Button onClick={fetchStressData} disabled={loading || !startDate || !endDate}>
          {loading ? 'Laster...' : 'Hent data'}
        </Button>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '1rem', width: '100%' }}>
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
            $active={activeFilter === '180d'}
            onClick={() => handleQuickFilter(180, '180d')}
          >
            180 dager
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
          {statistics.average_stress_level !== null && (
            <>
              <StatCard>
                <StatValue>{statistics.average_stress_level.toFixed(1)}</StatValue>
                <StatLabel>Gjennomsnittlig stress-nivå</StatLabel>
              </StatCard>
              <StatCard>
                <StatValue>{statistics.max_stress_level?.toFixed(0)}</StatValue>
                <StatLabel>Høyeste stress-nivå</StatLabel>
              </StatCard>
              <StatCard>
                <StatValue>{statistics.min_stress_level?.toFixed(0)}</StatValue>
                <StatLabel>Laveste stress-nivå</StatLabel>
              </StatCard>
            </>
          )}
          <StatCard>
            <StatValue>{statistics.total_days}</StatValue>
            <StatLabel>Totalt antall dager</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{formatTime(statistics.average_stress)}</StatValue>
            <StatLabel>Gjennomsnittlig stressektid/dag</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{formatTime(statistics.average_rest)}</StatValue>
            <StatLabel>Gjennomsnittlig hviletid/dag</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{formatTime(statistics.average_high_stress)}</StatValue>
            <StatLabel>Gjennomsnittlig høy stress/dag</StatLabel>
          </StatCard>
        </StatsContainer>
      )}

      {loading ? (
        <LoadingContainer>
          Laster stress-data...
        </LoadingContainer>
      ) : data.length > 0 ? (
        <>
          <LegacyChartFrame
            title="Stressnivå over tid"
            controls={
              <LegacyChartToggle active={showTrend} onClick={() => setShowTrend(!showTrend)}>
                {showTrend ? 'Skjul' : 'Vis'} 7-dagers glidende gjennomsnitt
              </LegacyChartToggle>
            }
          >
            <div className="h-[450px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={chartData}
                margin={CHART_MARGIN.labeled}
              >
                <defs>
                  <linearGradient id="gridGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f8fafc" stopOpacity={0.9} />
                    <stop offset="100%" stopColor="#e2e8f0" stopOpacity={0.5} />
                  </linearGradient>
                </defs>
                <ThemedCartesianGrid fill="url(#gridGradient)" />
                <ThemedXAxis
                  dataKey="date"
                  angle={-45}
                  textAnchor="end"
                  height={80}
                  interval="preserveStartEnd"
                />
                <ThemedYAxis
                  domain={['dataMin - 3', 'dataMax + 3']}
                  label={axisLabelProps(stressDef.axisLabel)}
                />
                <ThemedTooltip
                  formatter={(value: any, name: any) => {
                    const key = String(name);
                    if (key === 'stress_level') return [`${Number(value).toFixed(0)} poeng`, 'Daglig stressnivå'];
                    if (key === 'movingAverage7d') return [`${Number(value).toFixed(1)} poeng`, SERIES_LABELS.rollingAvg7d];
                    return [value, key];
                  }}
                  labelFormatter={(label) => `Dato: ${label}`}
                />
                <ThemedLegend wrapperStyle={{ paddingTop: '20px' }} iconType="circle" />
                <Line
                  type="monotone"
                  dataKey="stress_level"
                  stroke="none"
                  fill={chartColor(1)}
                  dot={{ fill: chartColor(1), r: 4, strokeWidth: 0, fillOpacity: 0.7 }}
                  name="Daglig stressnivå"
                  isAnimationActive={false}
                />
                {showTrend && (
                  <Line
                    type="monotone"
                    dataKey="movingAverage7d"
                    stroke={chartColor(2)}
                    strokeWidth={2.5}
                    dot={false}
                    name={SERIES_LABELS.rollingAvg7d}
                    isAnimationActive
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
            </div>
          </LegacyChartFrame>

          <LegacyChartFrame
            title="Total stressektid per dag"
            controls={
              <LegacyChartToggle active={showTrend} onClick={() => setShowTrend(!showTrend)}>
                {showTrend ? 'Skjul' : 'Vis'} 7-dagers snitt
              </LegacyChartToggle>
            }
          >
            <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={CHART_MARGIN.legacy}>
                <ThemedCartesianGrid />
                <ThemedXAxis
                  dataKey="date"
                  angle={-45}
                  textAnchor="end"
                  height={80}
                  interval="preserveStartEnd"
                />
                <ThemedYAxis label={axisLabelProps('Tid (min)')} />
                <ThemedTooltip
                  formatter={(value: any, name: any) => {
                    const key = String(name);
                    if (key === 'stress_time') return [formatMinutesValue(value), 'Stresstid'];
                    if (key === 'rest_time') return [formatMinutesValue(value), 'Hviletid'];
                    if (key === 'movingAverage7dTime') return [formatMinutesValue(value), SERIES_LABELS.rollingAvg7d];
                    return [value, key];
                  }}
                  labelFormatter={(label) => `Dato: ${label}`}
                />
                <ThemedLegend />
                <Bar dataKey="stress_time" fill="#ef4444" name="Stresstid" />
                <Bar dataKey="rest_time" fill="#10b981" name="Hviletid" />
                {showTrend && (
                  <Line 
                    type="monotone" 
                    dataKey="movingAverage7dTime" 
                    stroke="#3b82f6" 
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    dot={false}
                    name={SERIES_LABELS.rollingAvg7d}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
            </div>
          </LegacyChartFrame>

          <LegacyChartFrame title="Stress-nivåer per dag (lav/middels/høy)">
            <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={CHART_MARGIN.legacy}>
                <ThemedCartesianGrid />
                <ThemedXAxis
                  dataKey="date"
                  angle={-45}
                  textAnchor="end"
                  height={80}
                  interval="preserveStartEnd"
                />
                <ThemedYAxis label={axisLabelProps('Tid (min)')} />
                <ThemedTooltip
                  formatter={(value: any, name: any) => {
                    const key = String(name);
                    if (key === 'low_stress_time') return [formatMinutesValue(value), 'Lav stress'];
                    if (key === 'medium_stress_time') return [formatMinutesValue(value), 'Middels stress'];
                    if (key === 'high_stress_time') return [formatMinutesValue(value), 'Høy stress'];
                    return [value, key];
                  }}
                  labelFormatter={(label) => `Dato: ${label}`}
                />
                <ThemedLegend />
                <Bar dataKey="low_stress_time" stackId="stress" fill="#fbbf24" name="Lav stress" />
                <Bar dataKey="medium_stress_time" stackId="stress" fill="#f59e0b" name="Middels stress" />
                <Bar dataKey="high_stress_time" stackId="stress" fill="#dc2626" name="Høy stress" />
              </BarChart>
            </ResponsiveContainer>
            </div>
          </LegacyChartFrame>
        </>
      ) : (
        <ErrorContainer>
          Ingen stress-data funnet for valgt periode.
        </ErrorContainer>
      )}
    </PageContainer>
  );
}
