'use client';

import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceArea,
} from 'recharts';
import styled from 'styled-components';
import { useState } from 'react';
import { format, parseISO } from 'date-fns';
import { nb } from 'date-fns/locale';

const ChartContainer = styled.div`
  background: white;
  padding: 0.75rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 1rem;
  height: 600px;
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

const InfoPanel = styled.div`
  background: #f8f9fa;
  padding: 0.75rem;
  border-radius: 4px;
  margin-bottom: 0.75rem;
  font-size: 0.9rem;
  color: #495057;
`;

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
      <div style={{
        backgroundColor: 'white',
        padding: '0.75rem',
        border: '1px solid #ccc',
        borderRadius: '4px',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
        color: '#333'
      }}>
        <p><strong>Dato: {format(parseISO(label), 'dd.MM.yyyy')}</strong></p>
        <p>HRV (natt gj.snitt): <span style={{color: '#e74c3c'}}>{data.last_night_avg}ms</span></p>
        <p>7-dagers snitt: <span style={{color: '#3b82f6'}}>{data.rolling_avg_7d?.toFixed(1)}ms</span></p>
        <p>Baseline (balansert): {data.baseline_balanced_lower} - {data.baseline_balanced_upper}ms</p>
        {data.status && <p>Status: <span style={{fontWeight: 'bold'}}>{data.status}</span></p>}
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
      <ChartContainer>
        <InfoPanel>
          Ingen HRV-data tilgjengelig. HRV-data er kun tilgjengelig fra 2023 og fremover.
        </InfoPanel>
      </ChartContainer>
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
    <ChartContainer>
      <InfoPanel style={{ marginBottom: '0.5rem' }}>
        <div><strong>{title}</strong></div>
        {subtitle && <div style={{ marginTop: '0.25rem' }}>{subtitle}</div>}
      </InfoPanel>
      <InfoPanel style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <strong>Statistikk:</strong> 
          Siste HRV: {latestHrv}ms | 
          7-dagers snitt: {latestTrend?.toFixed(1)}ms | 
          Gj.snitt alle dager: {avgHrv.toFixed(1)}ms | 
          Antall målinger: {sortedData.length}
        </div>
        <ButtonContainer style={{ marginBottom: 0 }}>
          <Button $active={showTrend} onClick={() => setShowTrend(!showTrend)}>
            {showTrend ? 'Skjul' : 'Vis'} 7-dagers snitt
          </Button>
          <Button $active={showBaselines} onClick={() => setShowBaselines(!showBaselines)}>
            {showBaselines ? 'Skjul' : 'Vis'} normalområde
          </Button>
        </ButtonContainer>
      </InfoPanel>

      <ResponsiveContainer width="100%" height="75%">
        <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 30, bottom: 80 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis 
            dataKey="date" 
            tick={<CustomAxisTick />}
            interval={Math.max(1, Math.floor(chartData.length / 15))}
            height={80}
          />
          <YAxis
            label={{ value: 'HRV (ms)', angle: -90, position: 'insideLeft' }}
            domain={yAxisDomain()}
            tickFormatter={(tick) => String(Math.round(tick))}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          
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
            dot={{ fill: '#e74c3c', strokeWidth: 1, r: 2.5 }}
            name="HRV (natt gj.snitt)"
            connectNulls={false}
          />

          {/* 7-dagers trendlinje */}
          {showTrend && (
            <Line
              type="monotone"
              dataKey="rolling_avg_7d"
              stroke="#3b82f6"
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
    </ChartContainer>
  );
} 