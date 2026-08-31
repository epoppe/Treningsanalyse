'use client';

import {
  Bar,
  BarChart,
  ResponsiveContainer,
} from 'recharts';
import {
  CHART_MARGIN,
  yearComparisonColors,
} from '@/components/charts/chartTheme';
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from '@/components/charts/ThemedRecharts';
import { LegacyChartFrame } from '@/components/charts/ChartShell';
import { axisLabelProps, formatWithUnit } from '@/lib/chartFormatters';
import { Activity } from '../types';
import { useEffect, useMemo, useState } from 'react';

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
  const years = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: currentYear - 2022 + 1 }, (_, index) => 2022 + index);
  }, []);

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
        const res = await fetch(`/api/analysis/monthly-summaries?${params.toString()}`);
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
  }, [useServerSummaries, activityTypes]);
  
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
  }, [activities, metric, serverData, useServerSummaries, years]);

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
        return 'Distanse (km)';
      case 'time':
        return 'Tid (timer)';
      case 'tss':
        return 'TSS';
      default:
        return '';
    }
  };

  const getUnit = () => {
    if (metric === 'distance') return 'km';
    if (metric === 'time') return 'timer';
    return 'TSS';
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

  const yearColors = yearComparisonColors(years.length);

  const showNoData = !useServerSummaries && activities.length === 0;

  return (
    <LegacyChartFrame title={title} height="400px">
      {loading && <p className="mb-2 text-sm text-slate-500">Henter serverdata...</p>}
      {showNoData ? (
        <p className="text-sm text-slate-500">Ingen data å vise for denne perioden.</p>
      ) : (
        <div className="h-[320px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={finalChartData} margin={CHART_MARGIN.labeled}>
            <ThemedCartesianGrid />
            <ThemedXAxis dataKey="month" />
            <ThemedYAxis label={axisLabelProps(getYAxisLabel())} />
            <ThemedTooltip
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm shadow-md">
                      <p className="font-semibold text-slate-900">{label}</p>
                      {payload.map((entry, index) => {
                        const rawValue = Number(entry.value ?? 0);
                        const decimals = metric === 'tss' ? 0 : 1;
                        return (
                          <p key={index} style={{ color: entry.color }} className="text-slate-700">
                            {String(entry.dataKey)}: {formatWithUnit(rawValue, getUnit(), decimals)}
                          </p>
                        );
                      })}
                    </div>
                  );
                }
                return null;
              }}
            />
            <ThemedLegend />
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
        </div>
      )}
    </LegacyChartFrame>
  );
} 
