'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import styled from 'styled-components';
import { Activity } from '../store/slices/activitiesSlice';
import { getISOWeek, startOfISOWeek, format, getYear, getMonth, startOfMonth, differenceInYears, parseISO, eachWeekOfInterval, eachMonthOfInterval } from 'date-fns';

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

interface ActivityChartProps {
  activities: Activity[];
  metric: 'distance' | 'duration' | 'calories';
  title: string;
}

const CustomAxisTick = ({ x, y, payload, data }: any) => {
  const currentYear = data[payload.index]?.year;
  const prevYear = payload.index > 0 ? data[payload.index - 1]?.year : null;

  if (currentYear !== prevYear) {
    return (
      <g transform={`translate(${x},${y})`}>
        <text x={0} y={0} dy={16} textAnchor="middle" fill="#666" fontWeight="bold">
          {currentYear}
        </text>
      </g>
    );
  }

  return null;
};

export default function ActivityChart({ activities, metric, title }: ActivityChartProps) {
  if (activities.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen data å vise for denne perioden.</p>
      </ChartContainer>
    );
  }

  const dates = activities.map(a => parseISO(a.startTimeLocal));
  const yearSpan = differenceInYears(Math.max(...dates), Math.min(...dates));
  const groupByMonth = yearSpan >= 2;

  let chartData;
  let groupingTitle = groupByMonth ? '(per måned)' : '(per uke)';

  if (groupByMonth) {
    // Først, grupper eksisterende data per måned
    const monthlyDataMap = activities.reduce((acc, activity) => {
      const date = new Date(activity.startTimeLocal);
      const year = getYear(date);
      const month = getMonth(date);
      const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
      
      if (!acc[monthKey]) {
        acc[monthKey] = {
          date: format(startOfMonth(date), 'MMM yy'),
          groupKey: monthKey,
          year: year,
          [metric]: 0
        };
      }
      acc[monthKey][metric] += activity[metric] || 0;
      return acc;
    }, {} as Record<string, any>);

    // Deretter, generer en komplett liste over alle måneder i tidsrommet
    const allMonths = eachMonthOfInterval({ start: Math.min(...dates), end: Math.max(...dates) });

    chartData = allMonths.map(monthStart => {
      const year = getYear(monthStart);
      const month = getMonth(monthStart);
      const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
      
      return monthlyDataMap[monthKey] || {
        date: format(monthStart, 'MMM yy'),
        groupKey: monthKey,
        year: year,
        [metric]: null // Bruk null for å skape et tomt rom i grafen
      };
    });
  } else {
    // Først, grupper eksisterende data per uke
    const weeklyDataMap = activities.reduce((acc, activity) => {
      const date = new Date(activity.startTimeLocal);
      const week = getISOWeek(date);
      const year = getYear(date);
      const weekKey = `${year}-W${String(week).padStart(2, '0')}`;
      
      if (!acc[weekKey]) {
        acc[weekKey] = {
          date: format(startOfISOWeek(date), 'dd.MM.yy'),
          groupKey: weekKey,
          year: year,
          [metric]: 0
        };
      }
      acc[weekKey][metric] += activity[metric] || 0;
      return acc;
    }, {} as Record<string, any>);

    // Deretter, generer en komplett liste over alle uker i tidsrommet
    const allWeeks = eachWeekOfInterval({ start: Math.min(...dates), end: Math.max(...dates) }, { weekStartsOn: 1 });
    
    chartData = allWeeks.map(weekStart => {
      const year = getYear(weekStart);
      const week = getISOWeek(weekStart);
      const weekKey = `${year}-W${String(week).padStart(2, '0')}`;

      return weeklyDataMap[weekKey] || {
        date: format(weekStart, 'dd.MM.yy'),
        groupKey: weekKey,
        year: year,
        [metric]: null // Bruk null for å skape et tomt rom i grafen
      };
    });
  }

  const getYAxisLabel = () => {
    switch (metric) {
      case 'distance':
        return 'Kilometer';
      case 'duration':
        return 'Minutter';
      case 'calories':
        return 'Kalorier';
      default:
        return '';
    }
  };

  return (
    <ChartContainer>
      <Title>{title} {groupingTitle}</Title>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="groupKey"
            height={50}
            interval={0}
            tick={<CustomAxisTick data={chartData} />}
          />
          <YAxis
            label={{
              value: getYAxisLabel(),
              angle: -90,
              position: 'insideLeft'
            }}
          />
          <Tooltip
            content={({ active, payload, label }) => {
              if (active && payload && payload.length && payload[0].value) {
                return (
                  <div style={{
                    background: 'white',
                    padding: '0.5rem',
                    border: '1px solid #ddd',
                    borderRadius: '4px'
                  }}>
                    <p><strong>{groupByMonth ? 'Måned' : 'Uke (start)'}: {payload[0].payload.date}</strong></p>
                    <p>{`Total ${getYAxisLabel().toLowerCase()}: ${payload[0].value.toFixed(2)}`}</p>
                  </div>
                );
              }
              return null;
            }}
          />
          <Legend />
          <Bar
            dataKey={metric}
            fill="#3498db"
            name={getYAxisLabel()}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
} 