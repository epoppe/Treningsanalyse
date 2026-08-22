'use client';

import {
  LineChart,
  Line,
  ResponsiveContainer,
} from 'recharts';
import {
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
      <LegacyChartFrame title={title}>
        <p className="text-sm text-slate-500">Ingen løpedata tilgjengelig for denne perioden.</p>
      </LegacyChartFrame>
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
      <LegacyChartFrame title={title}>
        <p className="text-sm text-slate-500">Ingen relevante løpedata for å kalkulere løpsøkonomi.</p>
      </LegacyChartFrame>
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
    <LegacyChartFrame
      title={`${title} ${groupingTitle}`}
      height="400px"
      controls={
        <LegacyChartToggle active={showTrend} onClick={() => setShowTrend(!showTrend)}>
          {showTrend ? 'Skjul trendlinje' : 'Vis trendlinje'}
        </LegacyChartToggle>
      }
    >
      <div className="h-[320px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={dataWithMovingAverage}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis dataKey="date" interval={0} tick={<CustomAxisTick data={dataWithMovingAverage} />} />
          <ThemedYAxis
            label={{ value: 'Hastighet/Puls', angle: -90, position: 'insideLeft' }}
            domain={yAxisDomain()}
            tickFormatter={(tick) => tick.toFixed(2)}
          />
          <ThemedTooltip
            formatter={(value: any, name: any) => {
              const formattedName =
                name === "movingAverage" ? "Gj.snitt" : "Verdi";
              return [typeof value === 'number' ? value.toFixed(2) : value, formattedName];
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
          <ThemedLegend
            formatter={(value) =>
              value === "movingAverage" ? "Gjennomsnitt" : "Hastighet/Puls"
            }
          />
          <Line
            type="monotone"
            dataKey="economy"
            stroke={chartColor(0)}
            name="Løpsøkonomi"
            connectNulls
          />
          {showTrend && (
            <Line
              type="monotone"
              dataKey="movingAverage"
              stroke={LEGACY_SERIES_COLORS.form}
              name="Trend (6mnd snitt)"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          )}
        </LineChart>
      </ResponsiveContainer>
      </div>
    </LegacyChartFrame>
  );
} 