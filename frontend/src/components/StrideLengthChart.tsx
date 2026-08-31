'use client';

import {
  LineChart,
  Line,
  ResponsiveContainer,
} from 'recharts';
import {
  CHART_MARGIN,
  chartColor,
  LEGACY_SERIES_COLORS,
} from '@/components/charts/chartTheme';
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from '@/components/charts/ThemedRecharts';
import { LegacyChartFrame, LegacyChartToggle } from '@/components/charts/ChartShell';
import { Activity } from '../types';
import { getISOWeek, startOfISOWeek, format, getYear, getMonth, startOfMonth, differenceInYears, parseISO, eachWeekOfInterval, eachMonthOfInterval } from 'date-fns';
import { useState } from 'react';
import { axisLabelProps } from '@/lib/chartFormatters';
import { getMetricDefinition, SERIES_LABELS } from '@/lib/metrics';

const strideDef = getMetricDefinition('strideLength');

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
      <LegacyChartFrame title={title}>
        <p className="text-sm text-slate-500">Ingen data å vise for denne perioden.</p>
      </LegacyChartFrame>
    );
  }

  const activitiesWithStrideLength = activities.filter(a => a.avgStrideLength && a.avgStrideLength > 0);

  if (activitiesWithStrideLength.length === 0) {
    return (
      <LegacyChartFrame title={title}>
        <p className="text-sm text-slate-500">Ingen data for skrittlengde tilgjengelig for denne perioden.</p>
      </LegacyChartFrame>
    );
  }

  const dates = activitiesWithStrideLength.map(a => parseISO(a.startTimeLocal));
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
    chartData = activitiesWithStrideLength
      .map(activity => ({
        date: format(parseISO(activity.startTimeLocal), 'dd.MM.yy'),
        strideLength: activity.avgStrideLength,
        activityId: activity.activityId
      }));
  } else {
    // Alltid ukeverdier
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
    <LegacyChartFrame
      title={`${title} ${groupingTitle}`}
      height="400px"
      controls={
        <LegacyChartToggle active={showTrend} onClick={() => setShowTrend(!showTrend)}>
          {showTrend ? 'Skjul trend' : 'Vis trend'}
        </LegacyChartToggle>
      }
    >
      <div className="h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={dataWithMovingAverage} margin={{ ...CHART_MARGIN.labeled, left: -10, bottom: 40 }}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis 
            dataKey="date" 
            tick={<CustomAxisTick data={dataWithMovingAverage} />}
            interval={0}
            />
          <ThemedYAxis 
            yAxisId="left" 
            domain={yAxisDomain()}
            label={axisLabelProps(strideDef.axisLabel)}
            tickFormatter={(value) => value.toFixed(2)}
            />
          <ThemedTooltip content={<CustomTooltip />} />
          <ThemedLegend />
          <Line 
            yAxisId="left" 
            type="monotone" 
            dataKey="strideLength" 
            name="Skrittlengde (m)" 
            stroke={chartColor(0)} 
            dot={{ r: 4, fill: chartColor(0) }}
            connectNulls
            />
          {showTrend && <Line 
            yAxisId="left"
            type="monotone" 
            dataKey="movingAverage" 
            name={SERIES_LABELS.trend4p} 
            stroke={LEGACY_SERIES_COLORS.form} 
            strokeWidth={2}
            dot={false}
            connectNulls
            />}
        </LineChart>
      </ResponsiveContainer>
      </div>
    </LegacyChartFrame>
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