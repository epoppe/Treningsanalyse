'use client';

import { useEffect, useMemo, useState } from 'react';
import { format, subMonths, startOfYear } from 'date-fns';
import { nb } from 'date-fns/locale';
import { useSleepData } from '../../hooks/useHealthData';
import SleepScoreChart from '../../components/SleepScoreChart';
import {
  Bar,
  BarChart,
  Line,
  LineChart,
  ResponsiveContainer,
} from 'recharts';
import { CHART_MARGIN } from '@/components/charts/chartTheme';
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from '@/components/charts/ThemedRecharts';
import { LegacyChartFrame } from '@/components/charts/ChartShell';
import {
  MetricAlert,
  MetricDateField,
  MetricFilterCard,
  MetricLoading,
  MetricPageLayout,
  MetricPeriodChip,
  MetricPrimaryButton,
} from '@/components/layout/MetricPageLayout';

type SleepDay = {
  date: string;
  sleep_time?: number | null;   // minutter
  sleep_goal?: number | null;   // minutter
  sleep_score?: number | null;  // score
  overall_score?: number | null;  // overall score fra sleep_scores
  deep_sleep?: number | null;   // minutter
  light_sleep?: number | null;  // minutter
  rem_sleep?: number | null;    // minutter
  awake_time?: number | null;   // minutter
  total_sleep?: number | null;  // minutter
};

const PERIODS = [
  { id: '3m', label: '3 mnd' },
  { id: '6m', label: '6 mnd' },
  { id: 'ytd', label: 'År til dato' },
  { id: '12m', label: '12 mnd' },
  { id: '3y', label: '3 år' },
  { id: 'all', label: 'Alt' },
] as const;

const formatDateShort = (iso: string) => format(new Date(iso), 'dd.MM', { locale: nb });

export default function SovnPage() {
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [activePeriod, setActivePeriod] = useState<string>('');

  // Sett standard datoer - siste 3 måneder
  useEffect(() => {
    const today = new Date();
    const threeMonthsAgo = subMonths(today, 3);

    setStartDate(format(threeMonthsAgo, 'yyyy-MM-dd'));
    setEndDate(format(today, 'yyyy-MM-dd'));
    setActivePeriod('3m');
  }, []);

  // Bruk React Query for data fetching med automatisk caching
  const { data: sleepData, isLoading: loading, error: queryError } = useSleepData(
    startDate,
    endDate,
    !!startDate && !!endDate
  );

  const error = queryError ? String(queryError) : null;
  const days: SleepDay[] = useMemo(() => (
    sleepData
      ? [...(sleepData as any[])].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
      : []
  ), [sleepData]);

  const handlePeriodChange = (period: string) => {
    const today = new Date();
    let newStartDate: Date;

    switch (period) {
      case '3m':
        newStartDate = subMonths(today, 3);
        break;
      case '6m':
        newStartDate = subMonths(today, 6);
        break;
      case 'ytd':
        newStartDate = startOfYear(today);
        break;
      case '12m':
        newStartDate = subMonths(today, 12);
        break;
      case '3y':
        newStartDate = subMonths(today, 36);
        break;
      case 'all':
        newStartDate = new Date('2020-01-01');
        break;
      default:
        newStartDate = subMonths(today, 3);
    }

    setStartDate(format(newStartDate, 'yyyy-MM-dd'));
    setEndDate(format(today, 'yyyy-MM-dd'));
    setActivePeriod(period);
  };

  const handleFilterSubmit = () => {
    setActivePeriod('');
  };

  // Mapp for grafer: konverter minutter til timer for faser og søvntid
  const chartData = useMemo(() => {
    return days.map(d => {
      const sleep_hours_raw = d.sleep_time != null ? d.sleep_time / 60 : null;
      const total_sleep_hours_raw = d.total_sleep != null ? d.total_sleep / 60 : null;

      // Rå verdier for faser (i timer). 0 timer regnes som "mangler" for linjegrafen.
      const deep_val = d.deep_sleep != null ? d.deep_sleep / 60 : null;
      const light_val = d.light_sleep != null ? d.light_sleep / 60 : null;
      const rem_val = d.rem_sleep != null ? d.rem_sleep / 60 : null;

      const phase_sum_raw = (deep_val || 0) + (light_val || 0) + (rem_val || 0);

      // Gyldige verdier for linjegrafen: > 0
      const sleep_hours_valid = sleep_hours_raw && sleep_hours_raw > 0 ? sleep_hours_raw : null;
      const total_sleep_hours_valid = total_sleep_hours_raw && total_sleep_hours_raw > 0 ? total_sleep_hours_raw : null;
      const phase_sum_valid = phase_sum_raw > 0 ? phase_sum_raw : null;

      const merged = (sleep_hours_valid ?? total_sleep_hours_valid ?? phase_sum_valid) ?? null;

      // Bar-grafene: behold 0 for å vise "ingen data" eksplisitt i stacken,
      // men dette påvirker ikke linjen (som bruker merged)
      const deep_hours = deep_val ?? 0;
      const light_hours = light_val ?? 0;
      const rem_hours = rem_val ?? 0;

      return {
        date: d.date,
        sleep_hours: sleep_hours_raw,
        sleep_goal_hours: d.sleep_goal != null ? d.sleep_goal / 60 : null,
        total_sleep_hours: total_sleep_hours_raw,
        sleep_hours_merged: merged,
        deep_hours,
        light_hours,
        rem_hours,
        awake_hours: d.awake_time != null ? d.awake_time / 60 : 0,
        score: d.sleep_score ?? null,
      };
    });
  }, [days]);

  return (
    <MetricPageLayout
      title="Søvn"
      subtitle="Søvntid, faser og søvnscore over tid"
    >
      <MetricFilterCard>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-wrap gap-2">
            {PERIODS.map((p) => (
              <MetricPeriodChip
                key={p.id}
                active={activePeriod === p.id}
                onClick={() => handlePeriodChange(p.id)}
              >
                {p.label}
              </MetricPeriodChip>
            ))}
          </div>
          <div className="ml-auto flex flex-wrap items-end gap-3">
            <MetricDateField
              id="sovn-start"
              label="Fra dato"
              value={startDate}
              onChange={(v) => {
                setStartDate(v);
                setActivePeriod('');
              }}
            />
            <MetricDateField
              id="sovn-end"
              label="Til dato"
              value={endDate}
              onChange={(v) => {
                setEndDate(v);
                setActivePeriod('');
              }}
            />
            <MetricPrimaryButton
              onClick={handleFilterSubmit}
              disabled={!startDate || !endDate || loading}
            >
              {loading ? 'Laster...' : 'Filtrer periode'}
            </MetricPrimaryButton>
          </div>
        </div>
      </MetricFilterCard>

      {error ? <MetricAlert>{error}</MetricAlert> : null}

      {loading ? (
        <MetricLoading>Laster søvndata...</MetricLoading>
      ) : (
        <>
          {/* Overall Score graf */}
          <SleepScoreChart
            data={days.map(d => ({
              date: d.date,
              overall_score: d.overall_score ?? null,
              rolling_avg_7d: null
            }))}
            title="Søvnscore"
          />

          {/* Søvntid vs mål */}
          <LegacyChartFrame title="Søvntid (timer) og søvnmål" height="400px">
            <div className="h-[400px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={CHART_MARGIN.default}>
                  <ThemedCartesianGrid />
                  <ThemedXAxis dataKey="date" tickFormatter={formatDateShort} />
                  <ThemedYAxis yAxisId="left" label={{ value: 'Timer', angle: -90, position: 'insideLeft' }} />
                  <ThemedTooltip formatter={(v: any, n: any) => [n?.toLowerCase().includes('score') ? v : `${v?.toFixed ? v.toFixed(1) : v} t`, n]} labelFormatter={(l) => format(new Date(l), 'EEEE, dd. MMMM yyyy', { locale: nb })} />
                  <ThemedLegend />
                  <Line yAxisId="left" type="monotone" dataKey="sleep_hours_merged" name="Søvntid" stroke="#3498db" dot={false} strokeWidth={2} connectNulls />
                  <Line yAxisId="left" type="monotone" dataKey="sleep_goal_hours" name="Mål" stroke="#95a5a6" dot={false} strokeDasharray="5 5" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </LegacyChartFrame>

          {/* Søvnfaser */}
          <LegacyChartFrame title="Søvnfaser per dag (timer)" height="400px">
            <div className="h-[400px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={CHART_MARGIN.default}>
                  <ThemedCartesianGrid />
                  <ThemedXAxis dataKey="date" tickFormatter={formatDateShort} />
                  <ThemedYAxis label={{ value: 'Timer', angle: -90, position: 'insideLeft' }} />
                  <ThemedTooltip formatter={(v: any, n: any) => [`${v?.toFixed ? v.toFixed(1) : v} t`, n]} labelFormatter={(l) => format(new Date(l), 'EEEE, dd. MMMM yyyy', { locale: nb })} />
                  <ThemedLegend />
                  <Bar stackId="sleep" dataKey="deep_hours" name="Dyp" fill="#2ecc71" />
                  <Bar stackId="sleep" dataKey="light_hours" name="Lett" fill="#3498db" />
                  <Bar stackId="sleep" dataKey="rem_hours" name="REM" fill="#9b59b6" />
                  <Bar stackId="sleep" dataKey="awake_hours" name="Våken" fill="#e74c3c" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </LegacyChartFrame>
        </>
      )}
    </MetricPageLayout>
  );
}
