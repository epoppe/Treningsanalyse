'use client';

import { useEffect, useState } from 'react';
import HrvChart from '../../components/HrvChart';
import { useHrvData } from '../../hooks/useHealthData';
import { subMonths, startOfYear, format } from 'date-fns';
import {
  MetricAlert,
  MetricDateField,
  MetricFilterCard,
  MetricLoading,
  MetricPageLayout,
  MetricPeriodChip,
  MetricPrimaryButton,
} from '@/components/layout/MetricPageLayout';

const PERIODS = [
  { id: '3m', label: 'Siste 3 mnd' },
  { id: '6m', label: 'Siste 6 mnd' },
  { id: 'ytd', label: 'År til dato' },
  { id: '12m', label: 'Siste 12 mnd' },
  { id: '3y', label: 'Siste 3 år' },
  { id: 'all', label: 'All historikk' },
] as const;

export default function HrvPage() {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [activePeriod, setActivePeriod] = useState('6m');

  useEffect(() => {
    const today = new Date();
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(today.getMonth() - 6);
    const minDate = new Date('2023-01-01');
    const actualStart = sixMonthsAgo < minDate ? minDate : sixMonthsAgo;
    setStartDate(actualStart.toISOString().split('T')[0]);
    setEndDate(today.toISOString().split('T')[0]);
    setActivePeriod('6m');
  }, []);

  const { data, isLoading: loading, error: queryError } = useHrvData(
    startDate,
    endDate,
    Boolean(startDate && endDate),
  );
  const error = queryError ? String(queryError) : null;
  const hrvData = data ? (data as { hrv_data?: unknown[] }).hrv_data || [] : [];

  const handlePeriodChange = (period: string) => {
    setActivePeriod(period);
    const today = new Date();
    const minDate = new Date('2023-01-01');
    let start: Date;
    switch (period) {
      case '3m':
        start = subMonths(today, 3);
        break;
      case '6m':
        start = subMonths(today, 6);
        break;
      case 'ytd':
        start = startOfYear(today);
        break;
      case '12m':
        start = subMonths(today, 12);
        break;
      case '3y':
        start = subMonths(today, 36);
        break;
      case 'all':
        start = minDate;
        break;
      default:
        return;
    }
    const actualStart = start < minDate ? minDate : start;
    setStartDate(format(actualStart, 'yyyy-MM-dd'));
    setEndDate(format(today, 'yyyy-MM-dd'));
  };

  if (loading && !hrvData.length) {
    return (
      <MetricPageLayout title="HRV" subtitle="Heart rate variability over tid">
        <MetricLoading>Laster HRV-data...</MetricLoading>
      </MetricPageLayout>
    );
  }

  return (
    <MetricPageLayout
      title="HRV"
      subtitle="Nattlig HRV, 7-dagers snitt og normalområde"
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
              id="hrv-start"
              label="Fra dato"
              value={startDate}
              min="2023-01-01"
              onChange={(v) => {
                setStartDate(v);
                setActivePeriod('');
              }}
            />
            <MetricDateField
              id="hrv-end"
              label="Til dato"
              value={endDate}
              min="2023-01-01"
              onChange={(v) => {
                setEndDate(v);
                setActivePeriod('');
              }}
            />
            <MetricPrimaryButton
              onClick={() => setActivePeriod('')}
              disabled={!startDate || !endDate}
            >
              Oppdater
            </MetricPrimaryButton>
          </div>
        </div>
      </MetricFilterCard>

      {error ? <MetricAlert>{error}</MetricAlert> : null}

      {!loading && !error && hrvData.length > 0 ? (
        <HrvChart
          data={hrvData as Parameters<typeof HrvChart>[0]['data']}
          title="HRV over tid"
          subtitle={`${hrvData.length} målinger i valgt periode`}
        />
      ) : null}

      {!loading && !error && hrvData.length === 0 ? (
        <MetricAlert tone="empty">
          Ingen HRV-data funnet for valgt periode. HRV er typisk tilgjengelig fra 2023 og fremover.
        </MetricAlert>
      ) : null}
    </MetricPageLayout>
  );
}
