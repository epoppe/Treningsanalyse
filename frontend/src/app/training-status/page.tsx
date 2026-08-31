'use client';

import { useCallback, useEffect, useState } from 'react';
import { analysisApi } from '../../utils/api';
import {
  MetricAlert,
  MetricFilterCard,
  MetricLoading,
  MetricPageLayout,
  MetricPeriodChip,
  MetricStatCard,
  MetricStatGrid,
} from '@/components/layout/MetricPageLayout';

interface TrainingOverview {
  period_days: number;
  start_date: string;
  end_date: string;
  vo2max: {
    average: number | null;
    recent_values: Array<{date: string; vo2max: number; activity_name: string}>;
    trend: string;
  };
  training_frequency: {
    total_activities: number;
    activities_per_week: number;
  };
  training_volume: {
    total_time_minutes: number;
    total_distance_km: number;
    avg_time_per_week_minutes: number;
  };
  recovery_metrics: {
    avg_body_battery: number | null;
    avg_hrv: number | null;
    avg_stress: number | null;
  };
}

function trendAccent(trend: string): string | undefined {
  if (trend === 'improving') return '#065f46';
  if (trend === 'declining') return '#991b1b';
  return undefined;
}

export default function TrainingStatusPage() {
  const [data, setData] = useState<TrainingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState(30);

  const fetchTrainingOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await analysisApi.getTrainingOverview(selectedPeriod) as TrainingOverview;
      console.log('Training Overview Response:', response);
      setData(response);
    } catch (err: any) {
      setError(err.message || 'Feil ved henting av treningsoversikt');
      console.error('Feil ved henting av treningsoversikt:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedPeriod]);

  useEffect(() => {
    fetchTrainingOverview();
  }, [fetchTrainingOverview]);

  return (
    <MetricPageLayout
      title="Treningsstatus"
      subtitle="VO2Max, frekvens, volum og restitusjon"
    >
      <MetricAlert tone="info">
        Her får du en oversikt over treningen din basert på VO2Max, treningsfrekvens, volum og restitusjonsmetrikker.
      </MetricAlert>

      <MetricFilterCard>
        <div className="flex flex-wrap gap-2">
          <MetricPeriodChip
            active={selectedPeriod === 7}
            onClick={() => setSelectedPeriod(7)}
          >
            7 dager
          </MetricPeriodChip>
          <MetricPeriodChip
            active={selectedPeriod === 30}
            onClick={() => setSelectedPeriod(30)}
          >
            30 dager
          </MetricPeriodChip>
          <MetricPeriodChip
            active={selectedPeriod === 90}
            onClick={() => setSelectedPeriod(90)}
          >
            90 dager
          </MetricPeriodChip>
        </div>
      </MetricFilterCard>

      {error ? <MetricAlert>{error}</MetricAlert> : null}

      {loading ? (
        <MetricLoading>Laster treningsoversikt...</MetricLoading>
      ) : !data ? (
        <MetricAlert tone="empty">Ingen treningsdata tilgjengelig</MetricAlert>
      ) : (
        <MetricStatGrid>
          <MetricStatCard
            label="VO2Max gjennomsnitt"
            value={data.vo2max.average ? `${data.vo2max.average} ml/kg/min` : 'Ingen data'}
          />
          <MetricStatCard
            label="VO2Max trend"
            value={data.vo2max.trend === 'improving' ? '📈 Forbedring' : '➡️ Stabil'}
            accent={trendAccent(data.vo2max.trend)}
          />
          <MetricStatCard
            label="VO2Max målinger"
            value={data.vo2max.recent_values.length}
          />
          <MetricStatCard
            label="Totalt aktiviteter"
            value={data.training_frequency.total_activities}
          />
          <MetricStatCard
            label="Per uke"
            value={`${data.training_frequency.activities_per_week} økter`}
          />
          <MetricStatCard
            label="Total tid"
            value={`${Math.floor(data.training_volume.total_time_minutes / 60)}t ${data.training_volume.total_time_minutes % 60}min`}
          />
          <MetricStatCard
            label="Total distanse"
            value={`${data.training_volume.total_distance_km} km`}
          />
          <MetricStatCard
            label="Tid per uke"
            value={`${Math.floor(data.training_volume.avg_time_per_week_minutes / 60)}t ${Math.round(data.training_volume.avg_time_per_week_minutes % 60)}min`}
          />
          <MetricStatCard
            label="Snitt Body Battery"
            value={
              data.recovery_metrics.avg_body_battery
                ? `${data.recovery_metrics.avg_body_battery}`
                : 'Ingen data'
            }
          />
          <MetricStatCard
            label="Snitt HRV"
            value={
              data.recovery_metrics.avg_hrv
                ? `${data.recovery_metrics.avg_hrv} ms`
                : 'Ingen data'
            }
          />
          <MetricStatCard
            label="Snitt stress"
            value={
              data.recovery_metrics.avg_stress
                ? `${data.recovery_metrics.avg_stress}`
                : 'Ingen data'
            }
          />
        </MetricStatGrid>
      )}
    </MetricPageLayout>
  );
}
