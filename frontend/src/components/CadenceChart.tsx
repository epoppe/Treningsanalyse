'use client';

import {
  LineChart,
  Line,
  ResponsiveContainer,
} from 'recharts';
import {
  LEGACY_SERIES_COLORS,
} from '@/components/charts/chartTheme';
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from '@/components/charts/ThemedRecharts';
import styled from 'styled-components';
import { Activity } from '../types';
import { getISOWeek, startOfISOWeek, format, getYear, getMonth, startOfMonth, differenceInYears, parseISO, eachWeekOfInterval, eachMonthOfInterval } from 'date-fns';
import { useState } from 'react';

const ChartContainer = styled.div`
  background: white;
  padding: 1rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
  height: 400px;
`;

const Title = styled.h3`
  margin: 0 0 1rem 0;
  color: #2c3e50;
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

interface CadenceChartProps {
  activities: Activity[];
  title: string;
  timeFilter?: string;
}

const CustomAxisTick = ({ x, y, payload, data }: any) => {
  const item = data[payload.index];
  if (!item || !data || data.length === 0) return null;

  const dateLabel = item.date;
  // Viser ca. 8-10 ticks for å unngå at aksen blir for rotete
  const tickInterval = Math.max(1, Math.floor(data.length / 9));
  
  if (payload.index % tickInterval !== 0) return null;

  return (
    <g transform={`translate(${x},${y})`}>
      <text x={0} y={0} dy={16} textAnchor="middle" fill="#666" fontSize={12}>
        {dateLabel}
      </text>
    </g>
  );
};

const calculateMovingAverage = (data: any[], period: number) => {
  const result = [];
  for (let i = 0; i < data.length; i++) {
    const start = Math.max(0, i - period + 1);
    const subset = data.slice(start, i + 1).map(d => d.cadence).filter(v => v !== null);
    if (subset.length > 0) {
      const avg = subset.reduce((acc, val) => acc + val, 0) / subset.length;
      result.push({ ...data[i], movingAverage: avg });
    } else {
      result.push({ ...data[i], movingAverage: null });
    }
  }
  return result;
};

export default function CadenceChart({ activities, title, timeFilter }: CadenceChartProps) {
  const [showTrend, setShowTrend] = useState(true);

  if (activities.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen data å vise for denne perioden.</p>
      </ChartContainer>
    );
  }

  const activitiesWithCadence = activities.filter(a => a.averageRunningCadenceInStepsPerMinute && a.averageRunningCadenceInStepsPerMinute > 0);

  if (activitiesWithCadence.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen kadensdata tilgjengelig for denne perioden.</p>
      </ChartContainer>
    );
  }

  const dates = activitiesWithCadence.map(a => parseISO(a.startTimeLocal));
  const timestamps = dates.map(d => d.getTime());
  const minDate = new Date(Math.min(...timestamps));
  const maxDate = new Date(Math.max(...timestamps));

  const showPerActivity = timeFilter === '3m';
  const groupByWeek = !showPerActivity; // Alltid ukeverdier når ikke per aktivitet

  let chartData;
  let groupingTitle = showPerActivity ? '(per økt)' : '(per uke)';
  
  const calculateAverage = (data: number[]) => {
    if (data.length === 0) return 0;
    const sum = data.reduce((a, b) => a + b, 0);
    return sum / data.length;
  }

  if (showPerActivity) {
    chartData = activitiesWithCadence
      .map(activity => ({
        date: format(parseISO(activity.startTimeLocal), 'dd.MM.yy'),
        cadence: activity.averageRunningCadenceInStepsPerMinute,
        activityId: activity.activityId
      }));
  } else {
    // Alltid ukeverdier
    const weeklyDataMap = activitiesWithCadence.reduce((acc, activity) => {
      const date = parseISO(activity.startTimeLocal);
      const week = getISOWeek(date);
      const year = getYear(date);
      const weekKey = `${year}-W${String(week).padStart(2, '0')}`;
      
      if (!acc[weekKey]) {
        acc[weekKey] = {
          date: format(startOfISOWeek(date), 'dd.MM.yy'),
          groupKey: weekKey,
          year: year,
          values: []
        };
      }
      acc[weekKey].values.push(activity.averageRunningCadenceInStepsPerMinute || 0);
      return acc;
    }, {} as Record<string, any>);

    const allWeeks = eachWeekOfInterval({ start: minDate, end: maxDate }, { weekStartsOn: 1 });
    
    chartData = allWeeks.map(weekStart => {
      const year = getYear(weekStart);
      const week = getISOWeek(weekStart);
      const weekKey = `${year}-W${String(week).padStart(2, '0')}`;

      if (weeklyDataMap[weekKey] && weeklyDataMap[weekKey].values.length > 0) {
        return {
          date: format(weekStart, 'dd.MM.yy'),
          groupKey: weekKey,
          year: year,
          cadence: calculateAverage(weeklyDataMap[weekKey].values)
        };
      }
      return {
        date: format(weekStart, 'dd.MM.yy'),
        groupKey: weekKey,
        year: year,
        cadence: null
      };
    });
  }
  
  const dataWithMovingAverage = calculateMovingAverage(chartData, 24);

  const yAxisDomain = () => {
    const allValues = dataWithMovingAverage
      .flatMap(d => [d.cadence, d.movingAverage])
      .filter(v => v !== null && isFinite(v));
    
    if (allValues.length === 0) return [140, 190];

    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const padding = (max - min) * 0.1;

    return [Math.max(0, min - padding), max + padding];
  };

  return (
    <ChartContainer>
      <Title>{title} {groupingTitle}</Title>
      <ButtonContainer>
        <Button $active={showTrend} onClick={() => setShowTrend(!showTrend)}>
          {showTrend ? 'Skjul trendlinje' : 'Vis trendlinje'}
        </Button>
      </ButtonContainer>
      <ResponsiveContainer width="100%" height="80%">
        <LineChart data={dataWithMovingAverage}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis dataKey="date" interval={0} tick={<CustomAxisTick data={dataWithMovingAverage} />} />
          <ThemedYAxis
            label={{ value: 'Skritt/min', angle: -90, position: 'insideLeft' }}
            domain={yAxisDomain()}
            tickFormatter={(tick) => String(Math.round(tick))}
          />
          <ThemedTooltip
            formatter={(value: any, name: any) => {
              const formattedName = name === 'movingAverage' ? 'Gj.snitt' : 'Verdi';
              return [typeof value === 'number' ? value.toFixed(1) : value, formattedName];
            }}
            labelFormatter={(label) => `Dato: ${label}`}
          />
          <ThemedLegend formatter={(value) => value === 'movingAverage' ? 'Gjennomsnitt' : 'Kadens'} />
          <Line
            type="monotone"
            dataKey="cadence"
            stroke={LEGACY_SERIES_COLORS.cadence}
            name="Kadens"
            dot={{ r: 4, fill: LEGACY_SERIES_COLORS.cadence }}
            connectNulls
          />
          {showTrend && (
            <Line
              type="monotone"
              dataKey="movingAverage"
              stroke={LEGACY_SERIES_COLORS.vo2}
              name="movingAverage"
              dot={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
} 