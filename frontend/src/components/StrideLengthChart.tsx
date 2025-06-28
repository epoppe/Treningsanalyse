'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import styled from 'styled-components';
import { Activity } from '../store/slices/activitiesSlice';
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

interface StrideLengthChartProps {
  activities: Activity[];
  title: string;
}

const CustomAxisTick = ({ x, y, payload, data }: any) => {
  const item = data[payload.index];
  if (!item || !data || data.length === 0) return null;

  const dateLabel = item.date;
  // Viser ca. 8-10 ticks for å unngå at aksen blir for rotete
  const tickInterval = Math.max(1, Math.floor(data.length / 9));

  if (payload.index % tickInterval === 0 || payload.index === data.length - 1) {
    return (
      <g transform={`translate(${x},${y})`}>
        <text x={0} y={0} dy={16} textAnchor="end" fill="#666" transform="rotate(-35)">
          {dateLabel}
        </text>
      </g>
    );
  }
  return null;
};

const calculateMovingAverage = (data: any[], period: number) => {
  const result = [];
  for (let i = 0; i < data.length; i++) {
    const start = Math.max(0, i - period + 1);
    const subset = data.slice(start, i + 1).map(d => d.strideLength).filter(v => v !== null);
    if (subset.length > 0) {
      const avg = subset.reduce((acc, val) => acc + val, 0) / subset.length;
      result.push({ ...data[i], movingAverage: avg });
    } else {
      result.push({ ...data[i], movingAverage: null });
    }
  }
  return result;
};

export default function StrideLengthChart({ activities, title }: StrideLengthChartProps) {
  const [showTrend, setShowTrend] = useState(true);

  if (activities.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen data å vise for denne perioden.</p>
      </ChartContainer>
    );
  }

  const activitiesWithStrideLength = activities.filter(a => a.avgStrideLength && a.avgStrideLength > 0);

  if (activitiesWithStrideLength.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen data for skrittlengde tilgjengelig for denne perioden.</p>
      </ChartContainer>
    );
  }

  const dates = activitiesWithStrideLength.map(a => parseISO(a.startTimeLocal));
  const yearSpan = differenceInYears(Math.max(...dates), Math.min(...dates));
  const groupByMonth = yearSpan >= 2;

  let chartData;
  let groupingTitle = groupByMonth ? '(per måned)' : '(per uke)';
  
  const calculateAverage = (data: number[]) => {
    if (data.length === 0) return 0;
    const sum = data.reduce((a, b) => a + b, 0);
    return sum / data.length;
  }

  if (groupByMonth) {
    const monthlyDataMap = activitiesWithStrideLength.reduce((acc, activity) => {
      const date = new Date(activity.startTimeLocal);
      const year = getYear(date);
      const month = getMonth(date);
      const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
      
      if (!acc[monthKey]) {
        acc[monthKey] = {
          date: format(startOfMonth(date), 'MMM yy'),
          groupKey: monthKey,
          year: year,
          values: []
        };
      }
      acc[monthKey].values.push(activity.avgStrideLength || 0);
      return acc;
    }, {} as Record<string, any>);

    const allMonths = eachMonthOfInterval({ start: Math.min(...dates), end: Math.max(...dates) });

    chartData = allMonths.map(monthStart => {
      const year = getYear(monthStart);
      const month = getMonth(monthStart);
      const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
      
      if (monthlyDataMap[monthKey] && monthlyDataMap[monthKey].values.length > 0) {
        return {
          date: format(monthStart, 'MMM yy'),
          groupKey: monthKey,
          year: year,
          strideLength: calculateAverage(monthlyDataMap[monthKey].values)
        };
      }
      return {
        date: format(monthStart, 'MMM yy'),
        groupKey: monthKey,
        year: year,
        strideLength: null
      };
    });
  } else {
    const weeklyDataMap = activitiesWithStrideLength.reduce((acc, activity) => {
      const date = new Date(activity.startTimeLocal);
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
      acc[weekKey].values.push(activity.avgStrideLength || 0);
      return acc;
    }, {} as Record<string, any>);

    const allWeeks = eachWeekOfInterval({ start: Math.min(...dates), end: Math.max(...dates) }, { weekStartsOn: 1 });
    
    chartData = allWeeks.map(weekStart => {
      const year = getYear(weekStart);
      const week = getISOWeek(weekStart);
      const weekKey = `${year}-W${String(week).padStart(2, '0')}`;

      if (weeklyDataMap[weekKey] && weeklyDataMap[weekKey].values.length > 0) {
        return {
          date: format(weekStart, 'dd.MM.yy'),
          groupKey: weekKey,
          year: year,
          strideLength: calculateAverage(weeklyDataMap[weekKey].values)
        };
      }
      return {
        date: format(weekStart, 'dd.MM.yy'),
        groupKey: weekKey,
        year: year,
        strideLength: null
      };
    });
  }
  
  const dataWithMovingAverage = calculateMovingAverage(chartData, 24);

  const yAxisDomain = () => {
    const allValues = dataWithMovingAverage
      .flatMap(d => [d.strideLength, d.movingAverage])
      .filter(v => v !== null && isFinite(v));
    
    if (allValues.length === 0) return [0.8, 1.5]; // Sensible default for stride length in meters

    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const padding = (max - min) * 0.1;

    return [Math.max(0, min - padding), max + padding];
  };

  return (
    <ChartContainer>
      <Title>{title} {groupingTitle}</Title>
      <ButtonContainer>
        <Button $active={showTrend} onClick={() => setShowTrend(true)}>
          Vis trendlinje
        </Button>
        <Button $active={!showTrend} onClick={() => setShowTrend(false)}>
          Skjul trendlinje
        </Button>
      </ButtonContainer>
      <ResponsiveContainer width="100%" height="80%">
        <LineChart data={dataWithMovingAverage}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" interval={0} tick={<CustomAxisTick data={dataWithMovingAverage} />} />
          <YAxis
            label={{ value: 'Skrittlengde (m)', angle: -90, position: 'insideLeft' }}
            domain={yAxisDomain()}
            tickFormatter={(tick) => typeof tick === 'number' ? tick.toFixed(2) : tick}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#333', border: 'none' }}
            formatter={(value: number, name: string) => {
              const formattedValue = value.toFixed(2) + ' m';
              if (name === 'strideLength') return [formattedValue, 'Skrittlengde'];
              if (name === 'movingAverage') return [formattedValue, 'Trend (24p snitt)'];
              return [formattedValue, name];
            }}
            labelStyle={{ color: '#fff' }}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="strideLength"
            name="Skrittlengde"
            stroke="#8884d8"
            connectNulls
            dot={false}
          />
          {showTrend && (
            <Line
              type="monotone"
              dataKey="movingAverage"
              name="Trend (24p snitt)"
              stroke="#82ca9d"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
} 