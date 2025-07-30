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

export default function StrideLengthChart({ activities, title, timeFilter }: StrideLengthChartProps) {
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
  
  const showPerActivity = timeFilter === '3m';
  const groupByMonth = !showPerActivity && yearSpan >= 2;

  let chartData;
  let groupingTitle = showPerActivity ? '(per økt)' : (groupByMonth ? '(per måned)' : '(per uke)');
  
  const calculateAverage = (data: number[]) => {
    if (data.length === 0) return 0;
    const sum = data.reduce((a, b) => a + b, 0);
    return sum / data.length;
  }

  if (showPerActivity) {
    chartData = activitiesWithStrideLength
      .map(activity => ({
        date: format(parseISO(activity.startTimeLocal), 'dd.MM.yy'),
        strideLength: activity.avgStrideLength,
        activityId: activity.activityId
      }))
      .sort((a, b) => (a.activityId && b.activityId) ? a.activityId - b.activityId : 0);
  } else if (groupByMonth) {
    const monthlyDataMap = activitiesWithStrideLength.reduce((acc, activity) => {
      const date = parseISO(activity.startTimeLocal);
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

  const dataWithMovingAverage = calculateMovingAverage(chartData, 4);

  const yAxisDomain = () => {
    const allValues = dataWithMovingAverage.map(d => d.strideLength).filter(v => v !== null) as number[];
    if (allValues.length === 0) return [0.8, 2.2];
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const padding = (max - min) * 0.1;
    return [Math.max(0, min - padding), max + padding];
  };

  return (
    <ChartContainer>
      <Title>{title} <span style={{fontSize: '0.8em', color: '#666'}}>{groupingTitle}</span></Title>
      
      <ButtonContainer>
        <Button $active={showTrend} onClick={() => setShowTrend(!showTrend)}>
          {showTrend ? 'Skjul trend' : 'Vis trend'}
        </Button>
      </ButtonContainer>

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={dataWithMovingAverage} margin={{ top: 5, right: 20, left: -10, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis 
            dataKey="date" 
            tick={<CustomAxisTick data={dataWithMovingAverage} />}
            interval={0}
            />
          <YAxis 
            yAxisId="left" 
            domain={yAxisDomain()}
            tickFormatter={(value) => value.toFixed(2)}
            />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Line 
            yAxisId="left" 
            type="monotone" 
            dataKey="strideLength" 
            name="Skrittlengde (m)" 
            stroke="#8884d8" 
            dot={{ r: 4, fill: '#8884d8' }}
            connectNulls
            />
          {showTrend && <Line 
            yAxisId="left"
            type="monotone" 
            dataKey="movingAverage" 
            name="Trend (4 punkter)" 
            stroke="#82ca9d" 
            strokeWidth={2}
            dot={false}
            connectNulls
            />}
        </LineChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-tooltip" style={{ backgroundColor: 'white', padding: '10px', border: '1px solid #ccc' }}>
        <p><strong>Dato:</strong> {label}</p>
        <p><strong>Skrittlengde:</strong> {data.strideLength ? `${data.strideLength.toFixed(2)} m` : 'N/A'}</p>
        {data.movingAverage && <p><strong>Trend:</strong> {data.movingAverage.toFixed(2)} m</p>}
      </div>
    );
  }

  return null;
};