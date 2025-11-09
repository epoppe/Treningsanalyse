'use client';

import { memo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';
import { Activity } from '../store/slices/activitiesSlice';
import { getISOWeek, startOfISOWeek, format, getYear, getMonth, startOfMonth, differenceInYears, parseISO, eachWeekOfInterval, eachMonthOfInterval } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface ActivityChartProps {
  activities: Activity[];
  metric: 'distance' | 'duration' | 'calories';
  title: string;
  useDynamicYAxis?: boolean;
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

function ActivityChart({ activities, metric, title, useDynamicYAxis = false }: ActivityChartProps) {
  if (activities.length === 0) {
    return (
      <Card
        className="h-[280px]"
        style={{
          border: '1px solid rgba(226, 232, 240, 0.9)',
          borderRadius: '18px',
          background: '#fff',
          marginBottom: '1rem',
          height: '280px',
        }}
      >
        <CardHeader style={{ padding: '1rem 1rem 0.15rem 1rem' }}>
          <CardTitle className="text-lg font-semibold" style={{ fontSize: '1.05rem', fontWeight: 600, color: '#0f172a' }}>
            {title}
          </CardTitle>
        </CardHeader>
        <CardContent
          className="flex h-full items-center justify-center text-sm text-muted-foreground"
          style={{ padding: '0 1rem 0.4rem 1rem', color: '#475569', fontSize: '0.95rem' }}
        >
          Ingen data å vise for denne perioden.
        </CardContent>
      </Card>
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

    // Konverter til kilometer hvis metrikken er distanse
    if (metric === 'distance') {
      for (const key in monthlyDataMap) {
        monthlyDataMap[key][metric] /= 1000;
      }
    }

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

    // Konverter til kilometer hvis metrikken er distanse
    if (metric === 'distance') {
      for (const key in weeklyDataMap) {
        weeklyDataMap[key][metric] /= 1000;
      }
    }

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

  // Beregn dynamisk Y-akse hvis ønsket
  const getYAxisDomain = () => {
    if (useDynamicYAxis && metric === 'distance') {
      const maxValue = Math.max(...chartData.map(d => d[metric] || 0));
      // Bruk mindre intervaller for bedre skala
      const roundedMax = Math.ceil(maxValue / 25) * 25; // Runder opp til nærmeste 25
      return [0, Math.max(roundedMax, 50)]; // Minimum 50km
    }
    return [0, 450]; // Fast maksimum for "vis alle"
  };

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
    <Card
      className="h-[280px]"
      style={{
        border: '1px solid rgba(226, 232, 240, 0.9)',
        borderRadius: '18px',
        background: '#fff',
        marginBottom: '1rem',
        height: '280px',
      }}
    >
      <CardHeader className="pb-2" style={{ padding: '1rem 1rem 0.15rem 1rem' }}>
        <CardTitle className="text-lg font-semibold" style={{ fontSize: '1.05rem', fontWeight: 600, color: '#0f172a' }}>
          {title} {groupingTitle}
        </CardTitle>
      </CardHeader>
      <CardContent className="h-[260px]" style={{ padding: '0 1rem 0.4rem 1rem', height: '260px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
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
                position: 'insideLeft',
                fill: '#64748b',
                fontSize: 12,
              }}
              domain={getYAxisDomain()}
              tick={{ fill: '#64748b', fontSize: 12 }}
              axisLine={{ stroke: '#e2e8f0' }}
              tickLine={{ stroke: '#e2e8f0' }}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length && payload[0].value) {
                  return (
                    <div className="rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md">
                      <p className="font-semibold text-foreground">
                        {groupByMonth ? 'Måned' : 'Uke (start)'}: {payload[0].payload.date}
                      </p>
                      <p className="text-muted-foreground">
                        {`Total ${getYAxisLabel().toLowerCase()}: ${Number(payload[0].value).toFixed(2)}`}
                      </p>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Bar
              dataKey={metric}
              fill="hsl(var(--primary))"
              name={getYAxisLabel()}
              radius={[6, 6, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

// Wrap component with React.memo for performance
export default memo(ActivityChart); 