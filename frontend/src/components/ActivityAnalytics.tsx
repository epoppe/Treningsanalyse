"use client";

import { useState, useEffect } from 'react';
import { Card, Title, Text, Metric, Flex, Badge } from '@tremor/react';
import { analysisApi } from '../utils/api';
import { apiErrorMessage, classifyApiError } from '../utils/apiErrors';
import { initialMetricState, type MetricState } from '../utils/metricState';

interface NegativeSplitData {
  activity_id: number;
  negative_split_percent: number;
  first_half_pace: number;
  second_half_pace: number;
  data_points: number;
  calculation_method: string;
}

interface DecouplingData {
  activity_id: number;
  decoupling_percent: number;
  first_half_hr: number;
  first_half_speed: number;
  second_half_hr: number;
  second_half_speed: number;
  first_half_ratio: number;
  second_half_ratio: number;
  data_points: number;
  calculation_method: string;
}

interface ActivityAnalyticsProps {
  activityId: number;
}

const ActivityAnalytics = ({ activityId }: ActivityAnalyticsProps) => {
  const [negativeSplit, setNegativeSplit] = useState<MetricState<NegativeSplitData>>(
    initialMetricState<NegativeSplitData>(),
  );
  const [decoupling, setDecoupling] = useState<MetricState<DecouplingData>>(
    initialMetricState<DecouplingData>(),
  );

  useEffect(() => {
    let cancelled = false;

    const loadMetric = async <T,>(
      fetcher: () => Promise<T>,
      setter: (state: MetricState<T>) => void,
    ) => {
      setter({ status: 'loading', data: null, error: null });
      try {
        const data = await fetcher();
        if (!cancelled) {
          setter({ status: 'ready', data, error: null });
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        if (classifyApiError(error) === 'not_found') {
          setter({ status: 'missing', data: null, error: null });
          return;
        }
        setter({
          status: 'error',
          data: null,
          error: apiErrorMessage(error),
        });
      }
    };

    void Promise.all([
      loadMetric(
        () => analysisApi.getNegativeSplit(activityId) as Promise<NegativeSplitData>,
        setNegativeSplit,
      ),
      loadMetric(
        () => analysisApi.getDecoupling(activityId) as Promise<DecouplingData>,
        setDecoupling,
      ),
    ]);

    return () => {
      cancelled = true;
    };
  }, [activityId]);

  const formatPace = (pace: number | null | undefined) => {
    if (pace === null || pace === undefined || isNaN(pace)) {
      return 'N/A';
    }
    const minutes = Math.floor(pace);
    const seconds = Math.round((pace - minutes) * 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const getNegativeSplitBadge = (value: number | null | undefined) => {
    if (value === null || value === undefined || isNaN(value)) {
      return <Badge color="gray">Ingen data</Badge>;
    }
    if (value < 0) {
      return <Badge color="green">Negativ Split</Badge>;
    } else if (value > 0) {
      return <Badge color="red">Positiv Split</Badge>;
    } else {
      return <Badge color="gray">Jevn Split</Badge>;
    }
  };

  const getDecouplingBadge = (value: number | null | undefined) => {
    if (value === null || value === undefined || isNaN(value)) {
      return <Badge color="gray">Ingen data</Badge>;
    }
    if (value > 10) {
      return <Badge color="red">Høy Decoupling</Badge>;
    } else if (value >= 5) {
      return <Badge color="yellow">Moderat Decoupling</Badge>;
    } else {
      return <Badge color="green">Lav Decoupling</Badge>;
    }
  };

  const isLoading =
    negativeSplit.status === 'loading' || decoupling.status === 'loading';
  const hasApiErrors =
    negativeSplit.status === 'error' || decoupling.status === 'error';
  const hasAnyData =
    negativeSplit.status === 'ready' || decoupling.status === 'ready';

  if (isLoading && !hasAnyData) {
    return (
      <Card>
        <Title>Løpsanalyse</Title>
        <Text>Laster analysedata...</Text>
      </Card>
    );
  }

  if (hasApiErrors && !hasAnyData) {
    return (
      <Card>
        <Title>Løpsanalyse</Title>
        <Text className="text-red-600">
          Kunne ikke laste analysedata fra API-et.
        </Text>
        {negativeSplit.error && <Text className="mt-2">Negativ split: {negativeSplit.error}</Text>}
        {decoupling.error && <Text className="mt-2">Decoupling: {decoupling.error}</Text>}
      </Card>
    );
  }

  if (!hasAnyData && !hasApiErrors) {
    return (
      <Card>
        <Title>Løpsanalyse</Title>
        <Text>Ingen analysedata tilgjengelig for denne aktiviteten.</Text>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {hasApiErrors && (
        <Card>
          <Text className="text-amber-700">
            Noen analysedata kunne ikke hentes.
            {negativeSplit.error ? ` Negativ split: ${negativeSplit.error}.` : ''}
            {decoupling.error ? ` Decoupling: ${decoupling.error}.` : ''}
          </Text>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {negativeSplit.status === 'ready' && negativeSplit.data && (
          <Card>
            <Flex justifyContent="between" alignItems="center">
              <Title>Negativ Split</Title>
              {getNegativeSplitBadge(negativeSplit.data.negative_split_percent)}
            </Flex>

            <Metric className="mt-4">
              {negativeSplit.data.negative_split_percent > 0 ? '+' : ''}
              {negativeSplit.data.negative_split_percent?.toFixed(2) || '0.00'}%
            </Metric>

            <div className="mt-4 space-y-2">
              <div className="flex justify-between">
                <Text>Første halvdel:</Text>
                <Text>{formatPace(negativeSplit.data.first_half_pace)} min/km</Text>
              </div>
              <div className="flex justify-between">
                <Text>Andre halvdel:</Text>
                <Text>{formatPace(negativeSplit.data.second_half_pace)} min/km</Text>
              </div>
              <div className="flex justify-between">
                <Text>Datapunkter:</Text>
                <Text>{negativeSplit.data.data_points?.toLocaleString() || 'N/A'}</Text>
              </div>
              <div className="flex justify-between">
                <Text>Kilde:</Text>
                <Text>
                  {negativeSplit.data.calculation_method === 'cached' ? 'Cache' : 'FIT-data'}
                </Text>
              </div>
            </div>

            <div className="mt-4">
              <Text className="text-sm text-gray-600">
                {negativeSplit.data.negative_split_percent &&
                negativeSplit.data.negative_split_percent < 0
                  ? 'Løp raskere i andre halvdel - bra pacing!'
                  : negativeSplit.data.negative_split_percent &&
                      negativeSplit.data.negative_split_percent > 0
                    ? 'Løp saktere i andre halvdel - vurder pacing-strategi.'
                    : 'Ikke nok data for pacing-analyse.'}
              </Text>
            </div>
          </Card>
        )}

        {decoupling.status === 'ready' && decoupling.data && (
          <Card>
            <Flex justifyContent="between" alignItems="center">
              <Title>Cardiac-Aerobic Decoupling</Title>
              {getDecouplingBadge(decoupling.data.decoupling_percent)}
            </Flex>

            <Metric className="mt-4">
              {decoupling.data.decoupling_percent > 0 ? '+' : ''}
              {decoupling.data.decoupling_percent?.toFixed(2) || '0.00'}%
            </Metric>

            <div className="mt-4 space-y-2">
              <div className="flex justify-between">
                <Text>Første halvdel:</Text>
                <Text>
                  HR {decoupling.data.first_half_hr?.toFixed(0) || 'N/A'} / Speed{' '}
                  {decoupling.data.first_half_speed?.toFixed(2) || 'N/A'}
                </Text>
              </div>
              <div className="flex justify-between">
                <Text>Andre halvdel:</Text>
                <Text>
                  HR {decoupling.data.second_half_hr?.toFixed(0) || 'N/A'} / Speed{' '}
                  {decoupling.data.second_half_speed?.toFixed(2) || 'N/A'}
                </Text>
              </div>
              <div className="flex justify-between">
                <Text>HR:Speed ratio 1. del:</Text>
                <Text>{decoupling.data.first_half_ratio?.toFixed(2) || 'N/A'}</Text>
              </div>
              <div className="flex justify-between">
                <Text>HR:Speed ratio 2. del:</Text>
                <Text>{decoupling.data.second_half_ratio?.toFixed(2) || 'N/A'}</Text>
              </div>
              <div className="flex justify-between">
                <Text>Datapunkter:</Text>
                <Text>{decoupling.data.data_points?.toLocaleString() || 'N/A'}</Text>
              </div>
              <div className="flex justify-between">
                <Text>Kilde:</Text>
                <Text>
                  {decoupling.data.calculation_method === 'cached' ? 'Cache' : 'FIT-data'}
                </Text>
              </div>
            </div>

            <div className="mt-4">
              <Text className="text-sm text-gray-600">
                {decoupling.data.decoupling_percent && decoupling.data.decoupling_percent > 10
                  ? 'Høy decoupling kan indikere tretthet eller dehydrering.'
                  : decoupling.data.decoupling_percent &&
                      decoupling.data.decoupling_percent >= 5
                    ? 'Moderat decoupling - vær oppmerksom på tretthet.'
                    : decoupling.data.decoupling_percent &&
                        decoupling.data.decoupling_percent < 5
                      ? 'Lav decoupling - god aerob effektivitet!'
                      : 'Ikke nok data for decoupling-analyse.'}
              </Text>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};

export default ActivityAnalytics;
