"use client";

import { useState, useEffect } from 'react';
import { Card, Title, Text, Metric, Flex, Badge } from '@tremor/react';
import { analysisApi } from '../utils/api';

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
  const [negativeSplit, setNegativeSplit] = useState<NegativeSplitData | null>(null);
  const [decoupling, setDecoupling] = useState<DecouplingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        // Bare sett loading til true hvis vi ikke har data ennå
        if (!negativeSplit && !decoupling) {
          setLoading(true);
        }
        
        // Hent negativ split data
        try {
          const negativeSplitData = await analysisApi.getNegativeSplit(activityId);
          setNegativeSplit(negativeSplitData);
        } catch (err) {
          console.log('Negative split ikke tilgjengelig for denne aktiviteten');
        }

        // Hent decoupling data
        try {
          const decouplingData = await analysisApi.getDecoupling(activityId);
          setDecoupling(decouplingData);
        } catch (err) {
          console.log('Decoupling ikke tilgjengelig for denne aktiviteten');
        }

      } catch (err) {
        setError('Kunne ikke laste analysdata');
      } finally {
        setLoading(false);
      }
    };

    fetchAnalytics();
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

  if (loading && !negativeSplit && !decoupling) {
    return (
      <Card>
        <Title>Løpsanalyse</Title>
        <Text>Laster analysedata...</Text>
      </Card>
    );
  }

  if (!negativeSplit && !decoupling) {
    return (
      <Card>
        <Title>Løpsanalyse</Title>
        <Text>Ingen analysedata tilgjengelig for denne aktiviteten.</Text>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {negativeSplit && (
        <Card>
          <Flex justifyContent="between" alignItems="center">
            <Title>Negativ Split</Title>
            {getNegativeSplitBadge(negativeSplit.negative_split_percent)}
          </Flex>
          
          <Metric className="mt-4">
            {negativeSplit.negative_split_percent > 0 ? '+' : ''}{negativeSplit.negative_split_percent?.toFixed(2) || '0.00'}%
          </Metric>
          
          <div className="mt-4 space-y-2">
            <div className="flex justify-between">
              <Text>Første halvdel:</Text>
              <Text>{formatPace(negativeSplit.first_half_pace)} min/km</Text>
            </div>
            <div className="flex justify-between">
              <Text>Andre halvdel:</Text>
              <Text>{formatPace(negativeSplit.second_half_pace)} min/km</Text>
            </div>
            <div className="flex justify-between">
              <Text>Datapunkter:</Text>
              <Text>{negativeSplit.data_points?.toLocaleString() || 'N/A'}</Text>
            </div>
            <div className="flex justify-between">
              <Text>Kilde:</Text>
              <Text>{negativeSplit.calculation_method === 'cached' ? 'Cache' : 'FIT-data'}</Text>
            </div>
          </div>
          
          <div className="mt-4">
            <Text className="text-sm text-gray-600">
              {negativeSplit.negative_split_percent && negativeSplit.negative_split_percent < 0 
                ? 'Løp raskere i andre halvdel - bra pacing!' 
                : negativeSplit.negative_split_percent && negativeSplit.negative_split_percent > 0
                ? 'Løp saktere i andre halvdel - vurder pacing-strategi.'
                : 'Ikke nok data for pacing-analyse.'
              }
            </Text>
          </div>
        </Card>
      )}

      {decoupling && (
        <Card>
          <Flex justifyContent="between" alignItems="center">
            <Title>Cardiac-Aerobic Decoupling</Title>
            {getDecouplingBadge(decoupling.decoupling_percent)}
          </Flex>
          
          <Metric className="mt-4">
            {decoupling.decoupling_percent > 0 ? '+' : ''}{decoupling.decoupling_percent?.toFixed(2) || '0.00'}%
          </Metric>
          
          <div className="mt-4 space-y-2">
            <div className="flex justify-between">
              <Text>Første halvdel:</Text>
              <Text>HR {decoupling.first_half_hr?.toFixed(0) || 'N/A'} / Speed {decoupling.first_half_speed?.toFixed(2) || 'N/A'}</Text>
            </div>
            <div className="flex justify-between">
              <Text>Andre halvdel:</Text>
              <Text>HR {decoupling.second_half_hr?.toFixed(0) || 'N/A'} / Speed {decoupling.second_half_speed?.toFixed(2) || 'N/A'}</Text>
            </div>
            <div className="flex justify-between">
              <Text>HR:Speed ratio 1. del:</Text>
              <Text>{decoupling.first_half_ratio?.toFixed(2) || 'N/A'}</Text>
            </div>
            <div className="flex justify-between">
              <Text>HR:Speed ratio 2. del:</Text>
              <Text>{decoupling.second_half_ratio?.toFixed(2) || 'N/A'}</Text>
            </div>
            <div className="flex justify-between">
              <Text>Datapunkter:</Text>
              <Text>{decoupling.data_points?.toLocaleString() || 'N/A'}</Text>
            </div>
            <div className="flex justify-between">
              <Text>Kilde:</Text>
              <Text>{decoupling.calculation_method === 'cached' ? 'Cache' : 'FIT-data'}</Text>
            </div>
          </div>
          
          <div className="mt-4">
            <Text className="text-sm text-gray-600">
              {decoupling.decoupling_percent && decoupling.decoupling_percent > 10 
                ? 'Høy decoupling kan indikere tretthet eller dehydrering.' 
                : decoupling.decoupling_percent && decoupling.decoupling_percent >= 5
                ? 'Moderat decoupling - vær oppmerksom på tretthet.'
                : decoupling.decoupling_percent && decoupling.decoupling_percent < 5
                ? 'Lav decoupling - god aerob effektivitet!'
                : 'Ikke nok data for decoupling-analyse.'
              }
            </Text>
          </div>
        </Card>
      )}

    </div>
  );
};

export default ActivityAnalytics; 