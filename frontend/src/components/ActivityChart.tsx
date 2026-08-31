'use client';

import { memo } from 'react';
import {
  Bar,
  BarChart,
  ResponsiveContainer,
} from 'recharts';
import {
  CHART_BAR,
  CHART_MARGIN,
  chartColor,
} from '@/components/charts/chartTheme';
import {
  ThemedCartesianGrid,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from '@/components/charts/ThemedRecharts';
import { ChartShell } from '@/components/charts/ChartShell';
import { Activity } from '../types';
import { getISOWeek, startOfISOWeek, format, getYear, getMonth, startOfMonth, differenceInYears, parseISO, eachWeekOfInterval, eachMonthOfInterval } from 'date-fns';
import { axisLabelProps, formatChartNumber, formatWithUnit } from '@/lib/chartFormatters';
import { getMetricDefinition } from '@/lib/metrics';

interface ActivityChartProps {
  activities: Activity[];
  metric: 'distance' | 'duration' | 'calories';
  title: string;
  useDynamicYAxis?: boolean;
}

const METRIC_KEYS = {
  distance: 'distance',
  duration: 'duration',
  calories: 'calories',
} as const;

const CustomAxisTick = ({ x, y, payload, data }: any) => {
  const currentYear = data[payload.index]?.year;
  const prevYear = payload.index > 0 ? data[payload.index - 1]?.year : null;

  if (currentYear !== prevYear) {
    return (
      <g transform={`translate(${x},${y})`}>
        <text x={0} y={0} dy={16} textAnchor="middle" fill="#64748b" fontWeight="bold" fontSize={10}>
          {currentYear}
        </text>
      </g>
    );
  }

  return null;
};

function normalizeMetricValue(metric: ActivityChartProps['metric'], raw: number): number {
  if (metric === 'distance') return raw / 1000;
  if (metric === 'duration') return raw / 60;
  return raw;
}

function ActivityChart({ activities, metric, title, useDynamicYAxis = false }: ActivityChartProps) {
  const def = getMetricDefinition(METRIC_KEYS[metric]);
  const groupingSuffix = activities.length === 0 ? '' : '';

  if (activities.length === 0) {
    return (
      <ChartShell title={title} isEmpty heightClassName="h-[280px]" />
    );
  }

  const dates = activities.map(a => parseISO(a.startTimeLocal));
  const timestamps = dates.map(d => d.getTime());
  const maxDate = new Date(Math.max(...timestamps));
  const minDate = new Date(Math.min(...timestamps));
  const yearSpan = differenceInYears(maxDate, minDate);
  const groupByMonth = yearSpan >= 2;

  let chartData;
  const groupingTitle = groupByMonth ? '(per måned)' : '(per uke)';

  if (groupByMonth) {
    const monthlyDataMap = activities.reduce((acc, activity) => {
      const date = new Date(activity.startTimeLocal);
      const year = getYear(date);
      const month = getMonth(date);
      const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;

      if (!acc[monthKey]) {
        acc[monthKey] = {
          date: format(startOfMonth(date), 'MMM yy'),
          groupKey: monthKey,
          year,
          [metric]: 0,
        };
      }
      acc[monthKey][metric] += activity[metric] || 0;
      return acc;
    }, {} as Record<string, any>);

    for (const key in monthlyDataMap) {
      monthlyDataMap[key][metric] = normalizeMetricValue(metric, monthlyDataMap[key][metric]);
    }

    const allMonths = eachMonthOfInterval({ start: minDate, end: maxDate });

    chartData = allMonths.map(monthStart => {
      const year = getYear(monthStart);
      const month = getMonth(monthStart);
      const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;

      return monthlyDataMap[monthKey] || {
        date: format(monthStart, 'MMM yy'),
        groupKey: monthKey,
        year,
        [metric]: null,
      };
    });
  } else {
    const weeklyDataMap = activities.reduce((acc, activity) => {
      const date = new Date(activity.startTimeLocal);
      const week = getISOWeek(date);
      const year = getYear(date);
      const weekKey = `${year}-W${String(week).padStart(2, '0')}`;

      if (!acc[weekKey]) {
        acc[weekKey] = {
          date: format(startOfISOWeek(date), 'dd.MM.yy'),
          groupKey: weekKey,
          year,
          [metric]: 0,
        };
      }
      acc[weekKey][metric] += activity[metric] || 0;
      return acc;
    }, {} as Record<string, any>);

    for (const key in weeklyDataMap) {
      weeklyDataMap[key][metric] = normalizeMetricValue(metric, weeklyDataMap[key][metric]);
    }

    const allWeeks = eachWeekOfInterval({ start: minDate, end: maxDate }, { weekStartsOn: 1 });

    chartData = allWeeks.map(weekStart => {
      const year = getYear(weekStart);
      const week = getISOWeek(weekStart);
      const weekKey = `${year}-W${String(week).padStart(2, '0')}`;

      return weeklyDataMap[weekKey] || {
        date: format(weekStart, 'dd.MM.yy'),
        groupKey: weekKey,
        year,
        [metric]: null,
      };
    });
  }

  const getYAxisDomain = (): [number, number] => {
    const values = chartData.map((d) => d[metric]).filter((v): v is number => v != null && Number.isFinite(v));
    const maxValue = values.length ? Math.max(...values) : 0;
    if (useDynamicYAxis) {
      const step = metric === 'distance' ? 25 : metric === 'duration' ? 60 : 100;
      const roundedMax = Math.ceil(maxValue / step) * step;
      const floor = metric === 'distance' ? 50 : metric === 'duration' ? 30 : 200;
      return [0, Math.max(roundedMax, floor)];
    }
    if (metric === 'distance') return [0, Math.max(Math.ceil(maxValue / 25) * 25, 50)];
    if (metric === 'duration') return [0, Math.max(Math.ceil(maxValue / 60) * 60, 120)];
    return [0, Math.max(Math.ceil(maxValue / 50) * 50, 450)];
  };

  return (
    <ChartShell title={`${title} ${groupingTitle}${groupingSuffix}`} heightClassName="h-[280px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={CHART_MARGIN.labeled}>
          <ThemedCartesianGrid />
          <ThemedXAxis
            dataKey="groupKey"
            height={50}
            interval={0}
            tick={<CustomAxisTick data={chartData} />}
          />
          <ThemedYAxis
            label={axisLabelProps(def.axisLabel)}
            domain={getYAxisDomain()}
            tickFormatter={(tick) => formatChartNumber(Number(tick), def.decimals ?? 0)}
          />
          <ThemedTooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length && payload[0].value != null) {
                return (
                  <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm shadow-md">
                    <p className="font-semibold text-slate-900">
                      {groupByMonth ? 'Måned' : 'Uke (start)'}: {payload[0].payload.date}
                    </p>
                    <p className="text-slate-600">
                      {def.displayName}: {formatWithUnit(Number(payload[0].value), def.unit, def.decimals ?? 1)}
                    </p>
                  </div>
                );
              }
              return null;
            }}
          />
          <Bar
            dataKey={metric}
            fill={chartColor(0)}
            name={def.displayName}
            radius={CHART_BAR.radius}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

export default memo(ActivityChart);
