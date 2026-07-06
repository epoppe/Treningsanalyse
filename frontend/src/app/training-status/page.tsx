'use client';

import { useCallback, useEffect, useState } from 'react';
import styled from 'styled-components';
import { analysisApi } from '../../utils/api';

const PageContainer = styled.div`
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
`;

const Title = styled.h1`
  color: #2c3e50;
  margin-bottom: 2rem;
  text-align: center;
`;

const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
  font-size: 1.2rem;
  color: #666;
`;

const ErrorContainer = styled.div`
  background: #fee2e2;
  color: #dc2626;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 2rem;
  text-align: center;
`;

const PeriodSelector = styled.div`
  display: flex;
  gap: 1rem;
  justify-content: center;
  margin-bottom: 2rem;
`;

const PeriodButton = styled.button<{ $active?: boolean }>`
  padding: 0.5rem 1.5rem;
  border: 2px solid ${props => props.$active ? '#3b82f6' : '#e5e7eb'};
  background: ${props => props.$active ? '#3b82f6' : 'white'};
  color: ${props => props.$active ? 'white' : '#374151'};
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;

  &:hover {
    border-color: #3b82f6;
    transform: translateY(-1px);
  }
`;

const GridContainer = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
`;

const Card = styled.div`
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const CardTitle = styled.h3`
  color: #2c3e50;
  margin-bottom: 1rem;
  font-size: 1.1rem;
  border-bottom: 2px solid #3b82f6;
  padding-bottom: 0.5rem;
`;

const MetricRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #f3f4f6;

  &:last-child {
    border-bottom: none;
  }
`;

const MetricLabel = styled.span`
  color: #6b7280;
  font-size: 0.9rem;
`;

const MetricValue = styled.span`
  color: #1f2937;
  font-weight: 600;
  font-size: 1.1rem;
`;

const TrendBadge = styled.span<{ $trend?: string }>`
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 600;
  background: ${props => {
    if (props.$trend === 'improving') return '#d1fae5';
    if (props.$trend === 'declining') return '#fee2e2';
    return '#e5e7eb';
  }};
  color: ${props => {
    if (props.$trend === 'improving') return '#065f46';
    if (props.$trend === 'declining') return '#991b1b';
    return '#374151';
  }};
`;

const InfoBox = styled.div`
  background: #dbeafe;
  border-left: 4px solid #3b82f6;
  padding: 1rem;
  border-radius: 4px;
  margin-bottom: 2rem;
`;

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

  if (loading) {
    return (
      <PageContainer>
        <Title>Treningsoversikt</Title>
        <LoadingContainer>
          Laster treningsoversikt...
        </LoadingContainer>
      </PageContainer>
    );
  }

  if (error) {
    return (
      <PageContainer>
        <Title>Treningsoversikt</Title>
        <ErrorContainer>
          {error}
        </ErrorContainer>
      </PageContainer>
    );
  }

  if (!data) {
    return (
      <PageContainer>
        <Title>Treningsoversikt</Title>
        <InfoBox>
          Ingen treningsdata tilgjengelig
        </InfoBox>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <Title>Treningsoversikt</Title>

      <InfoBox>
        Her får du en oversikt over treningen din basert på VO2Max, treningsfrekvens, volum og restitusjonsmetrikker.
      </InfoBox>

      <PeriodSelector>
        <PeriodButton $active={selectedPeriod === 7} onClick={() => setSelectedPeriod(7)}>
          7 dager
        </PeriodButton>
        <PeriodButton $active={selectedPeriod === 30} onClick={() => setSelectedPeriod(30)}>
          30 dager
        </PeriodButton>
        <PeriodButton $active={selectedPeriod === 90} onClick={() => setSelectedPeriod(90)}>
          90 dager
        </PeriodButton>
      </PeriodSelector>

      <GridContainer>
        {/* VO2Max Card */}
        <Card>
          <CardTitle>VO2Max</CardTitle>
          <MetricRow>
            <MetricLabel>Gjennomsnitt</MetricLabel>
            <MetricValue>
              {data.vo2max.average != null
                ? `${Number(data.vo2max.average).toFixed(1)} ml/kg/min`
                : 'Ingen data'}
            </MetricValue>
          </MetricRow>
          <MetricRow>
            <MetricLabel>Trend</MetricLabel>
            <TrendBadge $trend={data.vo2max.trend}>
              {data.vo2max.trend === 'improving' ? '📈 Forbedring' : '➡️ Stabil'}
            </TrendBadge>
          </MetricRow>
          <MetricRow>
            <MetricLabel>Målinger</MetricLabel>
            <MetricValue>{data.vo2max.recent_values.length}</MetricValue>
          </MetricRow>
        </Card>

        {/* Training Frequency Card */}
        <Card>
          <CardTitle>Treningsfrekvens</CardTitle>
          <MetricRow>
            <MetricLabel>Totalt aktiviteter</MetricLabel>
            <MetricValue>{data.training_frequency.total_activities}</MetricValue>
          </MetricRow>
          <MetricRow>
            <MetricLabel>Per uke</MetricLabel>
            <MetricValue>{data.training_frequency.activities_per_week} økter</MetricValue>
          </MetricRow>
        </Card>

        {/* Training Volume Card */}
        <Card>
          <CardTitle>Treningsvolum</CardTitle>
          <MetricRow>
            <MetricLabel>Total tid</MetricLabel>
            <MetricValue>{Math.floor(data.training_volume.total_time_minutes / 60)}t {data.training_volume.total_time_minutes % 60}min</MetricValue>
          </MetricRow>
          <MetricRow>
            <MetricLabel>Total distanse</MetricLabel>
            <MetricValue>{data.training_volume.total_distance_km} km</MetricValue>
          </MetricRow>
          <MetricRow>
            <MetricLabel>Tid per uke</MetricLabel>
            <MetricValue>{Math.floor(data.training_volume.avg_time_per_week_minutes / 60)}t {Math.round(data.training_volume.avg_time_per_week_minutes % 60)}min</MetricValue>
          </MetricRow>
        </Card>

        {/* Recovery Metrics Card */}
        <Card>
          <CardTitle>Restitusjonsmetrikker</CardTitle>
          <MetricRow>
            <MetricLabel>Snitt Body Battery</MetricLabel>
            <MetricValue>
              {data.recovery_metrics.avg_body_battery ? `${data.recovery_metrics.avg_body_battery}` : 'Ingen data'}
            </MetricValue>
          </MetricRow>
          <MetricRow>
            <MetricLabel>Snitt HRV</MetricLabel>
            <MetricValue>
              {data.recovery_metrics.avg_hrv ? `${data.recovery_metrics.avg_hrv} ms` : 'Ingen data'}
            </MetricValue>
          </MetricRow>
          <MetricRow>
            <MetricLabel>Snitt stress</MetricLabel>
            <MetricValue>
              {data.recovery_metrics.avg_stress ? `${data.recovery_metrics.avg_stress}` : 'Ingen data'}
            </MetricValue>
          </MetricRow>
        </Card>
      </GridContainer>
    </PageContainer>
  );
}
