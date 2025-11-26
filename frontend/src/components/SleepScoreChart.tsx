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

interface SleepScoreData {
  date: string;
  overall_score: number | null;
  rolling_avg_7d: number | null;
}

interface SleepScoreChartProps {
  data: SleepScoreData[];
  title: string;
}

// Tilpasset tooltip for søvnscore-data
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
        <p>Overall score: <span style={{color: '#e74c3c'}}>{data.overall_score}</span></p>
        {data.rolling_avg_7d && (
          <p>7-dagers snitt: <span style={{color: '#3b82f6'}}>{data.rolling_avg_7d.toFixed(1)}</span></p>
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
      <ChartContainer>
        <InfoPanel>
          Ingen søvnscore-data tilgjengelig.
        </InfoPanel>
      </ChartContainer>
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
    <ChartContainer>
      <InfoPanel style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <strong>Statistikk:</strong> 
          {latestScore !== null && latestScore !== undefined ? (
            <>
              Siste score: {latestScore} | 
              {latestTrend && ` 7-dagers snitt: ${latestTrend.toFixed(1)} | `}
              Gj.snitt alle dager: {avgScore.toFixed(1)} | 
            </>
          ) : null}
          Antall målinger: {validScores.length}
        </div>
        <ButtonContainer style={{ marginBottom: 0 }}>
          <Button $active={showTrend} onClick={() => setShowTrend(!showTrend)}>
            {showTrend ? 'Skjul' : 'Vis'} 7-dagers snitt
          </Button>
        </ButtonContainer>
      </InfoPanel>

      <ResponsiveContainer width="100%" height="75%">
        <ComposedChart data={dataWithRollingAvg} margin={{ top: 20, right: 30, left: 30, bottom: 80 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis 
            dataKey="date" 
            tick={<CustomAxisTick />}
            interval={Math.max(1, Math.floor(dataWithRollingAvg.length / 15))}
            height={80}
          />
          <YAxis
            label={{ value: 'Overall Score', angle: -90, position: 'insideLeft' }}
            domain={yAxisDomain()}
            tickFormatter={(tick) => String(Math.round(tick))}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          
          {/* Daglige overall score-verdier */}
          <Line
            type="monotone"
            dataKey="overall_score"
            stroke="none"
            strokeWidth={0}
            dot={{ fill: '#e74c3c', strokeWidth: 1, r: 2.5 }}
            name="Overall Score"
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
        </ComposedChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}

