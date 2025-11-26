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

interface RunningEconomyChartProps {
  activities: Activity[];
  title: string;
  timeFilter: string;
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
    const subset = data.slice(start, i + 1).map(d => d.economy).filter(v => v !== null);
    if (subset.length > 0) {
      const avg = subset.reduce((acc, val) => acc + val, 0) / subset.length;
      result.push({ ...data[i], movingAverage: avg });
    } else {
      result.push({ ...data[i], movingAverage: null });
    }
  }
  return result;
};

export default function RunningEconomyChart({
  activities,
  title,
  timeFilter,
}: RunningEconomyChartProps) {
  const [showTrend, setShowTrend] = useState(true);

  if (activities.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen løpedata tilgjengelig for denne perioden.</p>
      </ChartContainer>
    );
  }

  const runningActivities = activities
    .filter(
      (a) =>
        a.activityType?.typeKey &&
        a.activityType.typeKey.includes("running") &&
        !a.activityType.typeKey.includes("treadmill")
    )
    .filter((a) => a.averageHR && a.averageSpeed && a.distance && a.distance > 1)
    .sort(
      (a, b) =>
        new Date(a.startTimeLocal).getTime() - new Date(b.startTimeLocal).getTime()
    );

  if (runningActivities.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen relevante løpedata for å kalkulere løpsøkonomi.</p>
      </ChartContainer>
    );
  }

  let chartData;
  let groupingTitle;

  const processGroup = (activities: Activity[]) => {
    const economyValues = activities
      .map((a) => {
        const speedInKmh = a.averageSpeed! * 3.6; // Konverter fra m/s til km/t
        return (speedInKmh / a.averageHR!) * 100;
      })
      .filter((e) => isFinite(e));

    if (economyValues.length === 0) return null;
    return economyValues.reduce((a, b) => a + b, 0) / economyValues.length;
  };

  if (timeFilter === '3m') {
    groupingTitle = '(per aktivitet)';
    chartData = runningActivities.map((a) => {
      const speedInKmh = a.averageSpeed! * 3.6;
      const economy =
        isFinite(speedInKmh) && a.averageHR! > 0
          ? (speedInKmh / a.averageHR!) * 100
          : null;
      return {
        date: format(parseISO(a.startTimeLocal), 'dd.MM.yy'),
        economy,
        name: a.activityName,
      };
    });
  } else {
    const dates = runningActivities.map((a) => parseISO(a.startTimeLocal));
    const timestamps = dates.map(d => d.getTime());
    const minDate = new Date(Math.min(...timestamps));
    const maxDate = new Date(Math.max(...timestamps));
    const yearSpan = differenceInYears(maxDate, minDate);
    const groupByMonth = yearSpan >= 2;
    groupingTitle = groupByMonth ? '(per måned)' : '(per uke)';
    
    if (groupByMonth) {
      const monthlyDataMap = runningActivities.reduce((acc, activity) => {
        const date = new Date(activity.startTimeLocal);
        const year = getYear(date);
        const month = getMonth(date);
        const monthKey = `${year}-${String(month + 1).padStart(2, "0")}`;

        if (!acc[monthKey]) {
          acc[monthKey] = {
            activities: [],
            date: format(startOfMonth(date), "MMM yy"),
            groupKey: monthKey,
            year: year,
          };
        }
        acc[monthKey].activities.push(activity);
        return acc;
      }, {} as Record<string, any>);
  
      const allMonths = eachMonthOfInterval({
        start: minDate,
        end: maxDate,
      });
  
      chartData = allMonths.map((monthStart) => {
        const year = getYear(monthStart);
        const month = getMonth(monthStart);
        const monthKey = `${year}-${String(month + 1).padStart(2, "0")}`;
        const economy = monthlyDataMap[monthKey]
          ? processGroup(monthlyDataMap[monthKey].activities)
          : null;
  
        return {
          date: format(monthStart, "MMM yy"),
          groupKey: monthKey,
          year: year,
          economy: economy,
        };
      });
    } else {
      const weeklyDataMap = runningActivities.reduce((acc, activity) => {
        const date = new Date(activity.startTimeLocal);
        const week = getISOWeek(date);
        const year = getYear(date);
        const weekKey = `${year}-W${String(week).padStart(2, "0")}`;
  
        if (!acc[weekKey]) {
          acc[weekKey] = {
            activities: [],
            date: format(startOfISOWeek(date), "dd.MM.yy"),
            groupKey: weekKey,
            year: year,
          };
        }
        acc[weekKey].activities.push(activity);
        return acc;
      }, {} as Record<string, any>);
  
      const allWeeks = eachWeekOfInterval(
        { start: minDate, end: maxDate },
        { weekStartsOn: 1 }
      );
  
      chartData = allWeeks.map((weekStart) => {
        const year = getYear(weekStart);
        const week = getISOWeek(weekStart);
        const weekKey = `${year}-W${String(week).padStart(2, "0")}`;
        const economy = weeklyDataMap[weekKey]
          ? processGroup(weeklyDataMap[weekKey].activities)
          : null;
  
        return {
          date: format(weekStart, "dd.MM.yy"),
          groupKey: weekKey,
          year: year,
          economy: economy,
        };
      });
    }
  }

  const movingAveragePeriod = timeFilter === '3m' ? 10 : 24;
  const dataWithMovingAverage = calculateMovingAverage(chartData, movingAveragePeriod);

  const yAxisDomain = () => {
    const allValues = dataWithMovingAverage
      .flatMap(d => [d.economy, d.movingAverage])
      .filter(v => v !== null && isFinite(v));
    
    if (allValues.length === 0) return [0, 1];

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
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" interval={0} tick={<CustomAxisTick data={dataWithMovingAverage} />} />
          <YAxis
            label={{ value: 'Hastighet/Puls', angle: -90, position: 'insideLeft' }}
            domain={yAxisDomain()}
            tickFormatter={(tick) => tick.toFixed(2)}
          />
          <Tooltip
            contentStyle={{ 
              backgroundColor: 'white', 
              border: '1px solid #ccc',
              borderRadius: '4px',
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
              color: '#333'
            }}
            formatter={(value: number, name: string) => {
              const formattedName =
                name === "movingAverage" ? "Gj.snitt" : "Verdi";
              return [value.toFixed(2), formattedName];
            }}
            labelFormatter={(label, payload) => {
              if (
                timeFilter === "3m" &&
                payload &&
                payload.length > 0 &&
                payload[0].payload.name
              ) {
                return `${label}: ${payload[0].payload.name}`;
              }
              return `Dato: ${label}`;
            }}
          />
          <Legend
            formatter={(value) =>
              value === "movingAverage" ? "Gjennomsnitt" : "Hastighet/Puls"
            }
          />
          <Line
            type="monotone"
            dataKey="economy"
            stroke="#8884d8"
            name="Løpsøkonomi"
            connectNulls
          />
          {showTrend && (
            <Line
              type="monotone"
              dataKey="movingAverage"
              stroke="#82ca9d"
              name="Trend (6mnd snitt)"
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