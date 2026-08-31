'use client';

import {
  ComposedChart,
  Line,
  ResponsiveContainer,
} from 'recharts';
import {
  CHART_MARGIN,
  LEGACY_SERIES_COLORS,
} from '@/components/charts/chartTheme';
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from '@/components/charts/ThemedRecharts';
import {
  LegacyChartFrame,
  LegacyChartToggle,
  LegacyInfoPanel,
} from '@/components/charts/ChartShell';
import { axisLabelProps, formatChartTooltipDate, formatWithUnit } from '@/lib/chartFormatters';
import { useState } from 'react';
import { format, parseISO } from 'date-fns';
import { getMetricDefinition, SERIES_LABELS } from '@/lib/metrics';

interface SleepScoreData {
  date: string;
  overall_score: number | null;
  rolling_avg_7d: number | null;
}

interface SleepScoreChartProps {
  data: SleepScoreData[];
  title: string;
}

const sleepScoreDef = getMetricDefinition('sleepScore');

// Tilpasset tooltip for søvnscore-data
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-md">
        <p className="font-semibold text-slate-900">{formatChartTooltipDate(label)}</p>
        <p className="text-slate-600">
          {sleepScoreDef.displayName}: {formatWithUnit(data.overall_score, sleepScoreDef.unit, 0)}
        </p>
        {data.rolling_avg_7d != null && (
          <p className="text-slate-600">
            {SERIES_LABELS.rollingAvg7d}: {formatWithUnit(data.rolling_avg_7d, sleepScoreDef.unit, 1)}
          </p>
        )}
      </div>
    );
  }
  return null;
};

// Tilpasset akse-tick for bedre datovisning
const CustomAxisTick = ({ x, y, payload }: any) => {
  if (!payload?.value) return null;
  
  try {
    const date = parseISO(payload.value);
    const formattedDate = format(date, 'd. MMM yyyy', { locale: nb });
    
    return (
      <g transform={`translate(${x},${y})`}>
        <text 
          x={0} 
          y={0} 
          dy={16} 
          textAnchor="middle" 
          fill="#666" 
          fontSize={12}
          transform="rotate(-45)"
        >
          {formattedDate}
        </text>
      </g>
    );
  } catch (error) {
    return null;
  }
};

export default function SleepScoreChart({ data, title }: SleepScoreChartProps) {
  const [showTrend, setShowTrend] = useState(true);

  if (!data || data.length === 0) {
    return (
      <LegacyChartFrame title={title}>
        <LegacyInfoPanel>
          Ingen søvnscore-data tilgjengelig.
        </LegacyInfoPanel>
      </LegacyChartFrame>
    );
  }

  // Sorter data etter dato
  const sortedData = [...data].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
  
  // Beregn 7-dagers glidende gjennomsnitt
  const dataWithRollingAvg = sortedData.map((item, index) => {
    if (index < 6) {
      return { ...item, rolling_avg_7d: null };
    }
    
    const windowData = sortedData.slice(Math.max(0, index - 6), index + 1);
    const validValues = windowData
      .map(d => d.overall_score)
      .filter((v): v is number => v !== null && v !== undefined && !isNaN(v as number));
    
    if (validValues.length >= 4) {
      const avg = validValues.reduce((sum, v) => sum + v, 0) / validValues.length;
      return { ...item, rolling_avg_7d: avg };
    }
    
    return { ...item, rolling_avg_7d: null };
  });

  // Beregn Y-akse domene basert på data
  const yAxisDomain = () => {
    const allValues = dataWithRollingAvg.flatMap(d => [
      d.overall_score,
      d.rolling_avg_7d
    ]).filter((v): v is number => v !== null && v !== undefined && !isNaN(v as number));
    
    if (allValues.length === 0) return [0, 100];

    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const padding = (max - min) * 0.1;

    return [Math.max(0, min - padding), Math.min(100, max + padding)];
  };

  // Beregn statistikk
  const validScores = dataWithRollingAvg
    .map(d => d.overall_score)
    .filter((v): v is number => v !== null && v !== undefined && !isNaN(v as number));
  
  const avgScore = validScores.length > 0 
    ? validScores.reduce((sum, v) => sum + v, 0) / validScores.length 
    : 0;
  
  const latestScore = dataWithRollingAvg[dataWithRollingAvg.length - 1]?.overall_score;
  const latestTrend = dataWithRollingAvg[dataWithRollingAvg.length - 1]?.rolling_avg_7d;

  return (
    <LegacyChartFrame title={title} height="600px">
      <LegacyInfoPanel>
        <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <strong>Statistikk:</strong>{' '}
          {latestScore !== null && latestScore !== undefined ? (
            <>
              Siste score: {latestScore} |{' '}
              {latestTrend && ` 7-dagers snitt: ${latestTrend.toFixed(1)} | `}
              Gj.snitt alle dager: {avgScore.toFixed(1)} |{' '}
            </>
          ) : null}
          Antall målinger: {validScores.length}
        </div>
        <LegacyChartToggle active={showTrend} onClick={() => setShowTrend(!showTrend)}>
          {showTrend ? 'Skjul' : 'Vis'} 7-dagers snitt
        </LegacyChartToggle>
        </div>
      </LegacyInfoPanel>

      <div className="h-[420px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={dataWithRollingAvg} margin={{ ...CHART_MARGIN.labeled, top: 20, right: 30, left: 30, bottom: 80 }}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis 
            dataKey="date" 
            tick={<CustomAxisTick />}
            interval={Math.max(1, Math.floor(dataWithRollingAvg.length / 15))}
            height={80}
          />
          <ThemedYAxis
            label={axisLabelProps(sleepScoreDef.axisLabel)}
            domain={yAxisDomain()}
            tickFormatter={(tick) => String(Math.round(tick))}
          />
          <ThemedTooltip content={<CustomTooltip />} />
          <ThemedLegend />
          
          {/* Daglige overall score-verdier */}
          <Line
            type="monotone"
            dataKey="overall_score"
            stroke="none"
            strokeWidth={0}
            dot={{ fill: LEGACY_SERIES_COLORS.vo2, strokeWidth: 1, r: 2.5 }}
            name="Søvnscore"
            connectNulls={false}
          />

          {/* 7-dagers trendlinje */}
          {showTrend && (
            <Line
              type="monotone"
              dataKey="rolling_avg_7d"
              stroke={LEGACY_SERIES_COLORS.ctl}
              strokeWidth={3}
              dot={false}
              name="7-dagers snitt"
              connectNulls={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </LegacyChartFrame>
  );
}

