'use client';

import React, { useState } from 'react';
import dynamic from 'next/dynamic';
import { HrvData } from '../../types/hrv';
import styled from 'styled-components';

// Dynamisk import for å unngå SSR-problemer med Plotly
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

const ChartContainer = styled.div`
  position: relative;
`;

const ToggleButton = styled.button`
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 10;
  padding: 5px 10px;
  background-color: #f0f0f0;
  border: 1px solid #ccc;
  border-radius: 5px;
  cursor: pointer;

  &:hover {
    background-color: #e0e0e0;
  }
`;

interface HrvChartProps {
  hrvData: HrvData[];
}

const HrvChart: React.FC<HrvChartProps> = ({ hrvData }) => {
  const [show7DayAvg, setShow7DayAvg] = useState(true);

  if (!hrvData || hrvData.length === 0) {
    return <p>Ingen HRV-data tilgjengelig for den valgte perioden.</p>;
  }

  // Sorter data etter dato for å sikre at grafen tegnes korrekt
  const sortedData = [...hrvData].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  const dates = sortedData.map(d => d.date);
  const lastNightAvg = sortedData.map(d => d.last_night_avg);
  const baselineLow = sortedData.map(d => d.baseline_low_upper);
  const baselineBalancedLower = sortedData.map(d => d.baseline_balanced_lower);
  const baselineBalancedUpper = sortedData.map(d => d.baseline_balanced_upper);
  const rollingAvg7d = sortedData.map(d => d.rolling_avg_7d);

  const traces: Partial<Plotly.Data>[] = [
    {
      x: dates,
      y: lastNightAvg,
      mode: 'markers',
      name: 'Nattlig snitt',
      type: 'scatter',
      marker: { color: 'rgba(52, 152, 219, 0.7)', size: 8 },
    },
    // Baseline-områder
    {
      x: dates,
      y: baselineLow,
      fill: 'tozeroy',
      mode: 'none',
      name: 'Under baseline',
      type: 'scatter',
      fillcolor: 'rgba(231, 76, 60, 0.2)',
    },
    {
      x: dates,
      y: baselineBalancedLower,
      fill: 'tonexty',
      mode: 'none',
      name: 'Lav baseline',
      type: 'scatter',
      fillcolor: 'rgba(241, 196, 15, 0.2)',
    },
    {
      x: dates,
      y: baselineBalancedUpper,
      fill: 'tonexty',
      mode: 'none',
      name: 'Balansert',
      type: 'scatter',
      fillcolor: 'rgba(46, 204, 113, 0.2)',
    },
  ];

  if (show7DayAvg) {
    traces.push({
      x: dates,
      y: rollingAvg7d,
      mode: 'lines',
      name: '7-dagers snitt',
      type: 'scatter',
      line: { color: 'orange', width: 2 },
    });
  }

  const layout: Partial<Plotly.Layout> = {
    title: 'HRV over tid',
    xaxis: {
      title: 'Dato',
      type: 'date',
      range: [dates[0], dates[dates.length - 1]],
    },
    yaxis: {
      title: 'ms',
    },
    showlegend: true,
    legend: {
      orientation: 'h',
      yanchor: 'bottom',
      y: 1.02,
      xanchor: 'right',
      x: 1,
    },
    autosize: true,
  };

  return (
    <ChartContainer>
      <ToggleButton onClick={() => setShow7DayAvg(!show7DayAvg)}>
        {show7DayAvg ? 'Skjul' : 'Vis'} 7-dagers snitt
      </ToggleButton>
      <Plot
        key={`hrv-chart-${hrvData.length}-${show7DayAvg}`}
        data={traces}
        layout={layout}
        style={{ width: '100%', height: '500px' }}
        useResizeHandler={true}
      />
    </ChartContainer>
  );
};

export default HrvChart; 