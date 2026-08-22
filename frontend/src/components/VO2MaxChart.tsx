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
import { LegacyChartFrame, LegacyChartToggle } from '@/components/charts/ChartShell';
import { Activity } from '../types';
import { getISOWeek, startOfISOWeek, format, getYear, getMonth, startOfMonth, differenceInYears, parseISO, eachWeekOfInterval, eachMonthOfInterval } from 'date-fns';
import { useState } from 'react';

const getEffectiveVo2Max = (activity: Activity): number | undefined => {
  const value = activity.vO2MaxPreciseValue ?? activity.vO2MaxValue;
  return value != null && value > 0 ? value : undefined;
};

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
    .filter((a) => getEffectiveVo2Max(a) != null)
    .sort(
      (a, b) =>
        new Date(a.startTimeLocal).getTime() - new Date(b.startTimeLocal).getTime()
    );

  if (runningActivities.length === 0) {
    return (
      <LegacyChartFrame title={title}>
        <p className="text-sm text-slate-500">Ingen VO2Max-data tilgjengelig for denne perioden.</p>
      </LegacyChartFrame>
    );
  }

  let chartData;
  let groupingTitle;

  const processGroup = (activities: Activity[]) => {
    const vo2MaxValues = activities
      .map((a) => getEffectiveVo2Max(a)!)
      .filter((v) => v > 0);

    if (vo2MaxValues.length === 0) return null;
    return vo2MaxValues.reduce((a, b) => a + b, 0) / vo2MaxValues.length;
  };

  if (timeFilter === '3m') {
    groupingTitle = '(per aktivitet)';
    chartData = runningActivities.map((a) => {
      return {
        date: format(parseISO(a.startTimeLocal), 'dd.MM.yy'),
        vo2Max: getEffectiveVo2Max(a),
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
    <LegacyChartFrame
      title={`${title} ${groupingTitle}`}
      height="400px"
      controls={
        <LegacyChartToggle active={showTrend} onClick={() => setShowTrend(!showTrend)}>
          {showTrend ? 'Skjul' : 'Vis'} trendlinje
        </LegacyChartToggle>
      }
    >
      <div className="h-[320px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={dataWithMovingAverage}>
          <ThemedCartesianGrid />
          <ThemedXAxis 
            dataKey="date" 
            tick={<CustomAxisTick data={dataWithMovingAverage} />}
            height={60}
          />
          <ThemedYAxis 
            domain={yAxisDomain()}
            label={{ value: 'VO2 Max', angle: -90, position: 'insideLeft' }}
          />
          <ThemedTooltip
            labelFormatter={(value) => `Dato: ${value}`}
            formatter={(value: any, name: any) => {
              if (name === 'vo2Max') {
                return [value ? `${value.toFixed(1)}` : 'N/A', 'VO2 Max'];
              }
              if (name === 'movingAverage') {
                return [value ? `${value.toFixed(1)}` : 'N/A', 'Glidende gjennomsnitt (4 perioder)'];
              }
              return [value, name];
            }}
          />
          <ThemedLegend />
          <Line
            type="monotone"
            dataKey="vo2Max"
            stroke={LEGACY_SERIES_COLORS.vo2}
            strokeWidth={2}
            dot={{ fill: LEGACY_SERIES_COLORS.vo2, strokeWidth: 2, r: 4 }}
            connectNulls={false}
            name="VO2 Max"
          />
          {showTrend && (
            <Line
              type="monotone"
              dataKey="movingAverage"
              stroke={LEGACY_SERIES_COLORS.ctl}
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              connectNulls={false}
              name="Glidende gjennomsnitt (4 perioder)"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
      </div>
    </LegacyChartFrame>
  );
} 