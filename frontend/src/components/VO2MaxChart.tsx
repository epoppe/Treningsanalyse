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

interface VO2MaxChartProps {
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
    const subset = data.slice(start, i + 1).map(d => d.vo2Max).filter(v => v !== null);
    if (subset.length > 0) {
      const avg = subset.reduce((acc, val) => acc + val, 0) / subset.length;
      result.push({ ...data[i], movingAverage: avg });
    } else {
      result.push({ ...data[i], movingAverage: null });
    }
  }
  return result;
};

export default function VO2MaxChart({
  activities,
  title,
  timeFilter,
}: VO2MaxChartProps) {
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
    .filter((a) => a.vO2MaxValue && a.vO2MaxValue > 0)
    .sort(
      (a, b) =>
        new Date(a.startTimeLocal).getTime() - new Date(b.startTimeLocal).getTime()
    );

  if (runningActivities.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen VO2Max-data tilgjengelig for denne perioden.</p>
      </ChartContainer>
    );
  }

  let chartData;
  let groupingTitle;

  const processGroup = (activities: Activity[]) => {
    const vo2MaxValues = activities
      .map((a) => a.vO2MaxValue!)
      .filter((v) => v > 0);

    if (vo2MaxValues.length === 0) return null;
    return vo2MaxValues.reduce((a, b) => a + b, 0) / vo2MaxValues.length;
  };

  if (timeFilter === '3m') {
    groupingTitle = '(per aktivitet)';
    chartData = runningActivities.map((a) => {
      return {
        date: format(parseISO(a.startTimeLocal), 'dd.MM.yy'),
        vo2Max: a.vO2MaxValue,
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
        const vo2Max = monthlyDataMap[monthKey]
          ? processGroup(monthlyDataMap[monthKey].activities)
          : null;
  
        return {
          date: format(monthStart, "MMM yy"),
          groupKey: monthKey,
          vo2Max,
        };
      });
    } else {
      const weeklyDataMap = runningActivities.reduce((acc, activity) => {
        const date = new Date(activity.startTimeLocal);
        const year = getYear(date);
        const week = getISOWeek(date);
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

      const allWeeks = eachWeekOfInterval({
        start: minDate,
        end: maxDate,
      }, { weekStartsOn: 1 });

      chartData = allWeeks.map((weekStart) => {
        const year = getYear(weekStart);
        const week = getISOWeek(weekStart);
        const weekKey = `${year}-W${String(week).padStart(2, "0")}`;
        const vo2Max = weeklyDataMap[weekKey]
          ? processGroup(weeklyDataMap[weekKey].activities)
          : null;

        return {
          date: format(weekStart, "dd.MM.yy"),
          groupKey: weekKey,
          vo2Max,
        };
      });
    }
  }

  // Beregn glidende gjennomsnitt
  const dataWithMovingAverage = calculateMovingAverage(chartData, 4);

  // Beregn y-akse domene
  const vo2MaxValues = chartData
    .map(d => d.vo2Max)
    .filter((v): v is number => v !== null && v !== undefined);
  const yAxisDomain = () => {
    if (vo2MaxValues.length === 0) return [0, 100];
    const min = Math.min(...vo2MaxValues);
    const max = Math.max(...vo2MaxValues);
    const padding = (max - min) * 0.1;
    return [
      Math.max(0, min - padding),
      max + padding
    ];
  };

  return (
    <ChartContainer>
      <Title>{title} {groupingTitle}</Title>
      <ButtonContainer>
        <Button $active={showTrend} onClick={() => setShowTrend(!showTrend)}>
          {showTrend ? 'Skjul' : 'Vis'} trendlinje
        </Button>
      </ButtonContainer>
      <ResponsiveContainer width="100%" height="90%">
        <LineChart data={dataWithMovingAverage}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="date" 
            tick={<CustomAxisTick data={dataWithMovingAverage} />}
            height={60}
          />
          <YAxis 
            domain={yAxisDomain()}
            label={{ value: 'VO2 Max', angle: -90, position: 'insideLeft' }}
          />
          <Tooltip
            labelFormatter={(value) => `Dato: ${value}`}
            formatter={(value: any, name: string) => {
              if (name === 'vo2Max') {
                return [value ? `${value.toFixed(1)}` : 'N/A', 'VO2 Max'];
              }
              if (name === 'movingAverage') {
                return [value ? `${value.toFixed(1)}` : 'N/A', 'Glidende gjennomsnitt (4 perioder)'];
              }
              return [value, name];
            }}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="vo2Max"
            stroke="#e74c3c"
            strokeWidth={2}
            dot={{ fill: '#e74c3c', strokeWidth: 2, r: 4 }}
            connectNulls={false}
            name="VO2 Max"
          />
          {showTrend && (
            <Line
              type="monotone"
              dataKey="movingAverage"
              stroke="#3498db"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              connectNulls={false}
              name="Glidende gjennomsnitt (4 perioder)"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
} 