'use client';

import {
  ComposedChart,
  Line,
  ResponsiveContainer,
  ReferenceArea,
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
import { useState } from 'react';
import { format, parseISO } from 'date-fns';
import { nb } from 'date-fns/locale';

interface HrvData {
  date: string;
  last_night_avg: number;
  last_night_5_min_high: number;
  baseline_low_upper: number;
  baseline_balanced_lower: number;
  baseline_balanced_upper: number;
  status: string;
  rolling_avg_7d: number;
}

interface HrvChartProps {
  data: HrvData[];
  title: string;
  subtitle?: string;
}

// Tilpasset tooltip for HRV-data
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-md">
        <p className="font-semibold text-slate-900">{format(parseISO(label), 'dd.MM.yyyy')}</p>
        <p className="text-slate-600">HRV (natt gj.snitt): <span className="font-medium text-red-600">{data.last_night_avg} ms</span></p>
        <p className="text-slate-600">7-dagers snitt: <span className="font-medium text-blue-600">{data.rolling_avg_7d?.toFixed(1)} ms</span></p>
        <p className="text-slate-600">Baseline (balansert): {data.baseline_balanced_lower} – {data.baseline_balanced_upper} ms</p>
        {data.status && <p className="mt-1 text-slate-700">Status: <span className="font-semibold">{data.status}</span></p>}
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

export default function HrvChart({ data, title, subtitle }: HrvChartProps) {
  const [showTrend, setShowTrend] = useState(true);
  const [showBaselines, setShowBaselines] = useState(true);

  if (!data || data.length === 0) {
    return (
      <LegacyChartFrame title={title}>
        <LegacyInfoPanel>
          Ingen HRV-data tilgjengelig. HRV-data er kun tilgjengelig fra 2023 og fremover.
        </LegacyInfoPanel>
      </LegacyChartFrame>
    );
  }

  // Sorter data etter dato
  const sortedData = [...data].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  // Beregn gjennomsnittlig baseline fra alle tilgjengelige verdier
  const baselineValues = sortedData
    .filter(d =>
      d.baseline_balanced_lower != null && !isNaN(d.baseline_balanced_lower) &&
      d.baseline_balanced_upper != null && !isNaN(d.baseline_balanced_upper)
    )
    .map(d => ({ lower: d.baseline_balanced_lower!, upper: d.baseline_balanced_upper! }));

  const avgBaselineLower = baselineValues.length > 0
    ? baselineValues.reduce((sum, v) => sum + v.lower, 0) / baselineValues.length
    : null;
  const avgBaselineUpper = baselineValues.length > 0
    ? baselineValues.reduce((sum, v) => sum + v.upper, 0) / baselineValues.length
    : null;

  // Fyll inn manglende baseline-verdier (forward-fill) slik at linjene tegnes for hele grafen
  const chartDataWithFilledBaselines = sortedData.map((d, i) => {
    const hasBaseline = d.baseline_balanced_lower != null && !isNaN(d.baseline_balanced_lower) &&
      d.baseline_balanced_upper != null && !isNaN(d.baseline_balanced_upper);
    if (hasBaseline) return d;
    // Forward-fill: bruk forrige datapunks verdi
    let prevLower = avgBaselineLower;
    let prevUpper = avgBaselineUpper;
    for (let j = i - 1; j >= 0; j--) {
      const p = sortedData[j];
      if (p.baseline_balanced_lower != null && !isNaN(p.baseline_balanced_lower) &&
          p.baseline_balanced_upper != null && !isNaN(p.baseline_balanced_upper)) {
        prevLower = p.baseline_balanced_lower;
        prevUpper = p.baseline_balanced_upper;
        break;
      }
    }
    // Backward-fill hvis ingen tidligere: bruk neste datapunk
    if (prevLower == null || prevUpper == null) {
      for (let j = i + 1; j < sortedData.length; j++) {
        const n = sortedData[j];
        if (n.baseline_balanced_lower != null && !isNaN(n.baseline_balanced_lower) &&
            n.baseline_balanced_upper != null && !isNaN(n.baseline_balanced_upper)) {
          prevLower = n.baseline_balanced_lower;
          prevUpper = n.baseline_balanced_upper;
          break;
        }
      }
    }
    return {
      ...d,
      baseline_balanced_lower: prevLower ?? avgBaselineLower ?? d.baseline_balanced_lower,
      baseline_balanced_upper: prevUpper ?? avgBaselineUpper ?? d.baseline_balanced_upper,
    };
  });

  const hasBaselineData = baselineValues.length > 0;

  // Beregn Y-akse domene basert på data
  const yAxisDomain = () => {
    const allValues = chartDataWithFilledBaselines.flatMap(d => [
      d.last_night_avg,
      d.rolling_avg_7d,
      showBaselines ? d.baseline_balanced_lower : null,
      showBaselines ? d.baseline_balanced_upper : null
    ]).filter((v): v is number => v != null && !isNaN(v as number));

    if (allValues.length === 0) return [0, 100];

    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    // Redusert padding for å gi mer "zoom" på dataene
    const padding = (max - min) * 0.05; // Redusert fra 0.1 til 0.05

    return [Math.max(0, min - padding), max + padding];
  };

  // Beregn statistikk
  const avgHrv = sortedData.reduce((sum, d) => sum + d.last_night_avg, 0) / sortedData.length;
  const latestHrv = sortedData[sortedData.length - 1]?.last_night_avg;
  const latestTrend = sortedData[sortedData.length - 1]?.rolling_avg_7d;

  const chartData = chartDataWithFilledBaselines;

  return (
    <LegacyChartFrame title={title} height="600px">
      {subtitle ? (
        <LegacyInfoPanel>{subtitle}</LegacyInfoPanel>
      ) : null}
      <LegacyInfoPanel>
        <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <strong>Statistikk:</strong>{' '}
          Siste HRV: {latestHrv}ms |{' '}
          7-dagers snitt: {latestTrend?.toFixed(1)}ms |{' '}
          Gj.snitt alle dager: {avgHrv.toFixed(1)}ms |{' '}
          Antall målinger: {sortedData.length}
        </div>
        <div className="flex flex-wrap gap-2">
          <LegacyChartToggle active={showTrend} onClick={() => setShowTrend(!showTrend)}>
            {showTrend ? 'Skjul' : 'Vis'} 7-dagers snitt
          </LegacyChartToggle>
          <LegacyChartToggle active={showBaselines} onClick={() => setShowBaselines(!showBaselines)}>
            {showBaselines ? 'Skjul' : 'Vis'} normalområde
          </LegacyChartToggle>
        </div>
        </div>
      </LegacyInfoPanel>

      <div className="h-[420px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ ...CHART_MARGIN.labeled, top: 20, right: 30, left: 30, bottom: 80 }}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis 
            dataKey="date" 
            tick={<CustomAxisTick />}
            interval={Math.max(1, Math.floor(chartData.length / 15))}
            height={80}
          />
          <ThemedYAxis
            label={{ value: 'HRV (ms)', angle: -90, position: 'insideLeft' }}
            domain={yAxisDomain()}
            tickFormatter={(tick) => String(Math.round(tick))}
          />
          <ThemedTooltip content={<CustomTooltip />} />
          <ThemedLegend />
          
          {/* Normalområde (skyggelagt) */}
          {showBaselines && avgBaselineLower !== null && avgBaselineUpper !== null && (
            <ReferenceArea
              y1={avgBaselineLower}
              y2={avgBaselineUpper}
              fill="#a8d5ba"
              fillOpacity={0.3}
              label="Normalområde"
            />
          )}

          {/* Daglige HRV-verdier */}
          <Line
            type="monotone"
            dataKey="last_night_avg"
            stroke="none"
            strokeWidth={0}
            dot={{ fill: LEGACY_SERIES_COLORS.vo2, strokeWidth: 1, r: 2.5 }}
            name="HRV (natt gj.snitt)"
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

          {/* Grønne grenselinjer tegnes sist (over) slik at de fremstår som heltrukne linjer */}
          {showBaselines && hasBaselineData && (
            <>
              <Line
                type="monotone"
                dataKey="baseline_balanced_lower"
                stroke="#2e7d32"
                strokeDasharray=""
                dot={false}
                name="Normalområde nedre grense"
                strokeWidth={4.5}
                connectNulls={true}
              />
              <Line
                type="monotone"
                dataKey="baseline_balanced_upper"
                stroke="#2e7d32"
                strokeDasharray=""
                dot={false}
                name="Normalområde øvre grense"
                strokeWidth={4.5}
                connectNulls={true}
              />
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </LegacyChartFrame>
  );
} 