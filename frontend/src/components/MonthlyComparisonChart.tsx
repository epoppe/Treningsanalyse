'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import styled from 'styled-components';
import { Activity } from '../types';
import { useEffect, useMemo, useState } from 'react';

const ChartContainer = styled.div`
  background: white;
  padding: 1rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
  height: 400px;
`;

const Title = styled.h3`
  margin: 0 0 1rem 0;
  color: #2c3e50;
`;

interface MonthlyComparisonChartProps {
  activities: Activity[];
  metric: 'distance' | 'time' | 'tss';
  title: string;
  useServerSummaries?: boolean;
  activityTypes?: string[];
}

const monthNames = [
  'Jan', 'Feb', 'Mar', 'Apr', 'Mai', 'Jun',
  'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Des'
];

export default function MonthlyComparisonChart({ activities, metric, title, useServerSummaries = true, activityTypes = [] }: MonthlyComparisonChartProps) {
  const [serverData, setServerData] = useState<any[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // Hent månedlige sammendrag fra server (2022 -> nå)
  useEffect(() => {
    const fetchSummaries = async () => {
      if (!useServerSummaries) {
        setServerData(null);
        return;
      }
      setLoading(true);
      try {
        const start = '2022-01-01';
        const now = new Date();
        const end = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().split('T')[0];
        const params = new URLSearchParams();
        params.append('start_date', start);
        params.append('end_date', end);
        params.append('limit', '60');
        activityTypes.forEach(t => params.append('activity_types', t));
        const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${base}/api/analysis/monthly-summaries?${params.toString()}`);
        if (res.ok) {
          const data = await res.json();
          setServerData(data);
        } else {
          setServerData(null);
        }
      } catch {
        setServerData(null);
      } finally {
        setLoading(false);
      }
    };
    fetchSummaries();
  }, [useServerSummaries, JSON.stringify(activityTypes)]);

  // Vis data fra 2022 til inneværende år
  const currentYear = new Date().getFullYear();
  const years: number[] = [];
  for (let year = 2022; year <= currentYear; year++) {
    years.push(year);
  }
  
  // Bygg datastruktur enten fra server-sammendrag eller fra aktiviteter
  const monthlyData: { [key: string]: { [year: number]: number } } = useMemo(() => {
    // 1) Start med klient-beregnet fallback fra aktiviteter
    const base: { [key: string]: { [year: number]: number } } = {};
    for (let month = 0; month < 12; month++) {
      const monthKey = monthNames[month];
      base[monthKey] = {} as any;
      years.forEach(year => {
        base[monthKey][year] = 0;
      });
    }

    const earliestDate = new Date(2022, 0, 1);
    const relevantActivities = activities.filter(activity => new Date(activity.startTimeLocal) >= earliestDate);
    relevantActivities.forEach(activity => {
      const date = new Date(activity.startTimeLocal);
      const year = date.getFullYear();
      const month = date.getMonth();
      const monthKey = monthNames[month];
      if (years.includes(year)) {
        let value = 0;
        if (metric === 'distance') value = (activity.distance || 0) / 1000;
        else if (metric === 'time') value = (activity.duration || 0) / 60;
        else if (metric === 'tss') value = activity.trainingStressScore || 0;
        base[monthKey][year] += value;
      }
    });

    // 2) Overstyr med server-summaries der de finnes
    if (useServerSummaries && serverData && serverData.length > 0) {
      serverData.forEach((m: any) => {
        const startDate = new Date(m.month_start_date);
        const y = startDate.getFullYear();
        const monthKey = monthNames[startDate.getMonth()];
        if (years.includes(y)) {
          let value = 0;
          if (metric === 'distance') value = (m.total_distance || 0) / 1000;
          else if (metric === 'time') value = (m.total_duration || 0) / 60; // minutter
          else if (metric === 'tss') value = m.total_tss || 0;
          base[monthKey][y] = value; // overstyr
        }
      });
    }

    return base;
  }, [useServerSummaries, JSON.stringify(serverData), JSON.stringify(activities), metric]);

  // Debug logging
  console.log(`[MonthlyComparisonChart] ${title}: source=${useServerSummaries && serverData ? 'server' : 'client'}, years=${years.length}`);

  // Konverter til format som Recharts kan bruke
  const chartData = monthNames.map(month => {
    const monthData: any = { month };
    years.forEach(year => {
      monthData[year.toString()] = monthlyData[month][year];
    });
    return monthData;
  });

  const getYAxisLabel = () => {
    switch (metric) {
      case 'distance':
        return 'Kilometer';
      case 'time':
        return 'Timer';
      case 'tss':
        return 'TSS';
      default:
        return '';
    }
  };

  // Konverter tid til timer hvis nødvendig (TSS trenger ingen konvertering)
  const finalChartData = chartData.map(data => {
    const newData = { ...data };
    if (metric === 'time') {
      years.forEach(year => {
        newData[year.toString()] = newData[year.toString()] / 60; // Konverter minutter til timer
      });
    }
    // TSS brukes direkte uten konvertering
    return newData;
  });

  // Farger for hvert år (dynamisk basert på antall år)
  const baseColors = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#8dd1e1', '#d084d0', '#82d982'];
  const yearColors = baseColors.slice(0, years.length);

  const showNoData = !useServerSummaries && activities.length === 0;

  return (
    <ChartContainer>
      <Title>{title}</Title>
      {loading && <p>Henter serverdata...</p>}
      {showNoData ? (
        <p>Ingen data å vise for denne perioden.</p>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={finalChartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" />
            <YAxis
              label={{
                value: getYAxisLabel(),
                angle: -90,
                position: 'insideLeft'
              }}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  return (
                    <div style={{
                      background: 'white',
                      padding: '0.5rem',
                      border: '1px solid #ddd',
                      borderRadius: '4px'
                    }}>
                      <p><strong>{label}</strong></p>
                    {payload.map((entry, index) => {
                      const rawValue = entry.value as number | string | undefined;
                      let formattedValue: string;
                      if (metric === 'tss') {
                        formattedValue = typeof rawValue === 'number' ? Math.round(rawValue).toString() : String(rawValue ?? '0');
                      } else {
                        formattedValue = typeof rawValue === 'number' ? rawValue.toFixed(1) : String(rawValue ?? '');
                      }
                      const unit = metric === 'tss' ? '' : ` ${getYAxisLabel().toLowerCase()}`;
                      return (
                        <p key={index} style={{ color: entry.color }}>
                          {`${entry.dataKey}: ${formattedValue}${unit}`}
                        </p>
                      );
                    })}
                    </div>
                  );
                }
                return null;
              }}
            />
            <Legend />
            {years.map((year, index) => (
              <Bar 
                key={year}
                dataKey={year.toString()}
                fill={yearColors[index]}
                name={year.toString()}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartContainer>
  );
} 