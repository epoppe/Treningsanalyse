'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../utils/api';
import BodyBatteryChart from '../../components/BodyBatteryChart';
import { format, subDays, subMonths } from 'date-fns';
import {
  MetricAlert,
  MetricDateField,
  MetricFilterCard,
  MetricLoading,
  MetricPageLayout,
  MetricPeriodChip,
  MetricPrimaryButton,
  MetricStatCard,
  MetricStatGrid,
} from '@/components/layout/MetricPageLayout';

interface BodyBatteryData {
  date: string;
  max_body_battery: number | null;
  min_body_battery: number | null;
  body_battery_charged: number | null;
  body_battery_drained: number | null;
  body_battery_charged_start: number | null;
  body_battery_drained_start: number | null;
  net_charge: number | null;
}

interface BodyBatteryResponse {
  body_battery_data: BodyBatteryData[];
  total_records: number;
}

interface BodyBatteryStatistics {
  total_records: number;
  average_max_body_battery: number | null;
  average_min_body_battery: number | null;
  highest_body_battery_ever: number | null;
  lowest_body_battery_ever: number | null;
}

const BodyBatteryPage: React.FC = () => {
  const [data, setData] = useState<BodyBatteryData[]>([]);
  const [statistics, setStatistics] = useState<BodyBatteryStatistics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [activeFilter, setActiveFilter] = useState('30d');

  useEffect(() => {
    const end = new Date();
    const start = subDays(end, 30);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter('30d');
  }, []);

  const fetchBodyBatteryData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = (await api.getBodyBatteryData(startDate, endDate)) as BodyBatteryResponse;
      setData(response.body_battery_data || []);
    } catch (err: any) {
      setError(err.message || 'Feil ved henting av Body Battery-data');
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  const fetchStatistics = useCallback(async () => {
    try {
      const response = (await api.getBodyBatteryStatistics()) as BodyBatteryStatistics;
      setStatistics(response);
    } catch {
      // Statistikk er valgfri
    }
  }, []);

  useEffect(() => {
    if (startDate && endDate) {
      fetchBodyBatteryData();
      fetchStatistics();
    }
  }, [startDate, endDate, fetchBodyBatteryData, fetchStatistics]);

  const handleQuickFilter = (days: number, filterName: string) => {
    const end = new Date();
    const start = subDays(end, days);
    setStartDate(format(start, 'yyyy-MM-dd'));
    setEndDate(format(end, 'yyyy-MM-dd'));
    setActiveFilter(filterName);
  };

  const formatScore = (value: number | null | undefined) =>
    value != null ? value.toFixed(1) : '—';

  return (
    <MetricPageLayout
      title="Body Battery"
      subtitle="Energireserve gjennom dagen (skala 0–100)"
    >
      <MetricFilterCard>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-wrap gap-2">
            <MetricPeriodChip
              active={activeFilter === '7d'}
              onClick={() => handleQuickFilter(7, '7d')}
            >
              7 dager
            </MetricPeriodChip>
            <MetricPeriodChip
              active={activeFilter === '30d'}
              onClick={() => handleQuickFilter(30, '30d')}
            >
              30 dager
            </MetricPeriodChip>
            <MetricPeriodChip
              active={activeFilter === '90d'}
              onClick={() => handleQuickFilter(90, '90d')}
            >
              90 dager
            </MetricPeriodChip>
            <MetricPeriodChip
              active={activeFilter === 'all'}
              onClick={() => {
                const end = new Date();
                setStartDate(format(subMonths(end, 12), 'yyyy-MM-dd'));
                setEndDate(format(end, 'yyyy-MM-dd'));
                setActiveFilter('all');
              }}
            >
              12 mnd
            </MetricPeriodChip>
          </div>
          <div className="ml-auto flex flex-wrap items-end gap-3">
            <MetricDateField
              id="bb-start"
              label="Fra dato"
              value={startDate}
              onChange={(v) => {
                setStartDate(v);
                setActiveFilter('custom');
              }}
            />
            <MetricDateField
              id="bb-end"
              label="Til dato"
              value={endDate}
              onChange={(v) => {
                setEndDate(v);
                setActiveFilter('custom');
              }}
            />
            <MetricPrimaryButton onClick={fetchBodyBatteryData} disabled={loading}>
              {loading ? 'Laster...' : 'Oppdater'}
            </MetricPrimaryButton>
          </div>
        </div>
      </MetricFilterCard>

      {error ? <MetricAlert>{error}</MetricAlert> : null}

      {statistics ? (
        <MetricStatGrid>
          <MetricStatCard label="Dager med data" value={statistics.total_records} />
          <MetricStatCard
            label="Snitt høyeste"
            value={formatScore(statistics.average_max_body_battery)}
          />
          <MetricStatCard
            label="Snitt laveste"
            value={formatScore(statistics.average_min_body_battery)}
          />
          <MetricStatCard
            label="Høyeste noensinne"
            value={
              statistics.highest_body_battery_ever != null
                ? String(statistics.highest_body_battery_ever)
                : '—'
            }
          />
          <MetricStatCard
            label="Laveste noensinne"
            value={
              statistics.lowest_body_battery_ever != null
                ? String(statistics.lowest_body_battery_ever)
                : '—'
            }
          />
        </MetricStatGrid>
      ) : null}

      {loading ? (
        <MetricLoading>Laster Body Battery-data...</MetricLoading>
      ) : (
        <>
          <BodyBatteryChart data={data} title="Body Battery (daglig)" />
          <BodyBatteryChart
            data={data}
            title="Body Battery (7-dagers snitt)"
            movingAverageDays={7}
            showMovingAverageOnly
            hideDots
          />
        </>
      )}
    </MetricPageLayout>
  );
};

export default BodyBatteryPage;
