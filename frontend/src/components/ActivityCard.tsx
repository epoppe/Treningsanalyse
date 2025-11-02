'use client';

import { memo } from 'react';
import styled from 'styled-components';
import { Activity } from '../types';
import { useRouter } from 'next/navigation';

const ActivityCardWrapper = styled.div`
  background: white;
  border-radius: 8px;
  padding: 0.75rem;
  margin-bottom: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: box-shadow 0.2s;
  
  &:hover {
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
  }
`;

const ActivityTitle = styled.h3`
  margin: 0 0 0.5rem 0;
  color: #2c3e50;
  font-size: 1.1rem;
`;

const ActivityDetails = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
  gap: 0.5rem;
  color: #666;
  font-size: 0.9rem;
`;

const ActivityStat = styled.div<{ $statKey?: string; $value?: number | null }>`
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem;
  border-radius: 4px;
  min-height: 60px;
  justify-content: center;
  background-color: ${({ $statKey, $value }) => {
    if ($value === null || $value === undefined) return '#f8f9fa'; // default gray

    if ($statKey === 'decoupling') {
      if ($value > 10) return '#fee2e2'; // red-100 for high decoupling
      if ($value >= 5) return '#fef9c3'; // yellow-100 for moderate decoupling
      return '#dcfce7'; // green-100 for low decoupling
    }
    
    if ($statKey === 'negative_split') {
      return $value > 0 ? '#fee2e2' : '#dcfce7'; // red-100 for positive, green-100 for negative
    }

    if ($statKey === 'hrv') {
      if ($value < 35) return '#fee2e2'; // red-100
      if ($value <= 37) return '#fef9c3'; // yellow-100
      return '#dcfce7'; // green-100
    }

    if ($statKey === 'aerobic_effect') {
      if ($value < 2.0) return '#f8f9fa'; // gray - Minimal effect
      if ($value < 3.0) return '#dbeafe'; // blue-100 - Aerobic benefit
      if ($value < 4.0) return '#dcfce7'; // green-100 - High aerobic benefit
      if ($value < 5.0) return '#fef9c3'; // yellow-100 - Very high aerobic benefit
      return '#fee2e2'; // red-100 - Overreaching
    }

    if ($statKey === 'anaerobic_effect') {
      if ($value < 2.0) return '#f8f9fa'; // gray - Minimal effect
      if ($value < 3.0) return '#dbeafe'; // blue-100 - Anaerobic benefit
      if ($value < 4.0) return '#dcfce7'; // green-100 - High anaerobic benefit
      if ($value < 5.0) return '#fef9c3'; // yellow-100 - Very high anaerobic benefit
      return '#fee2e2'; // red-100 - Overreaching
    }

    if ($statKey === 'tss') {
      if ($value < 50) return '#f8f9fa'; // gray - Very low load
      if ($value < 100) return '#dbeafe'; // blue-100 - Low load
      if ($value < 200) return '#dcfce7'; // green-100 - Moderate load
      if ($value < 300) return '#fef9c3'; // yellow-100 - High load
      if ($value < 400) return '#fee2e2'; // red-100 - Very high load
      return '#7f1d1d'; // red-900 - Extremely high load
    }

    if ($statKey === 'power') {
      if (!$value || $value <= 0) return '#f8f9fa'; // gray - No power data
      if ($value < 200) return '#dbeafe'; // blue-100 - Low power
      if ($value < 300) return '#dcfce7'; // green-100 - Moderate power
      if ($value < 400) return '#fef9c3'; // yellow-100 - High power
      if ($value < 500) return '#fee2e2'; // red-100 - Very high power
      return '#7f1d1d'; // red-900 - Extremely high power
    }

    return '#f8f9fa'; // default gray
  }};
`;

const StatLabel = styled.span`
  font-size: 0.75rem;
  color: #666;
  margin-bottom: 0.25rem;
  font-weight: 500;
  text-align: center;
`;

const StatValue = styled.span`
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
  text-align: center;
`;

// Utility functions
const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleDateString('nb-NO', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  });
};

const calculateRunningEconomy = (averageSpeed?: number, averageHR?: number, activityType?: any) => {
  const isRunningActivity = activityType?.typeKey?.toLowerCase().includes('running') && 
                           !activityType?.typeKey?.toLowerCase().includes('treadmill');
  
  if (!isRunningActivity) return null;
  if (!averageSpeed || !averageHR || averageSpeed <= 0 || averageHR <= 0) return null;
  
  const speedInKmh = averageSpeed * 3.6;
  return (speedInKmh / averageHR) * 100;
};

const formatRunningEconomy = (economy?: number, activityType?: any) => {
  const isRunningActivity = activityType?.typeKey?.toLowerCase().includes('running') && 
                           !activityType?.typeKey?.toLowerCase().includes('treadmill');
  
  if (!isRunningActivity) return 'N/A';
  if (!economy) return 'N/A';
  return `${economy.toFixed(2)}`;
};

const formatVO2Max = (vo2Max?: number, activityType?: any) => {
  const isRunningActivity = activityType?.typeKey?.toLowerCase().includes('running') && 
                           !activityType?.typeKey?.toLowerCase().includes('treadmill');
  
  if (!isRunningActivity) return 'N/A';
  if (!vo2Max || vo2Max <= 0) return 'N/A';
  return Math.round(vo2Max).toString();
};

const formatHrv = (hrv?: number | null) => {
  if (!hrv) return 'N/A';
  return `${Math.round(hrv)}`;
};

const formatAerobicEffect = (aerobicEffect?: number) => {
  if (!aerobicEffect || aerobicEffect <= 0) return 'N/A';
  return aerobicEffect.toFixed(1);
};

const formatAnaerobicEffect = (anaerobicEffect?: number) => {
  if (!anaerobicEffect || anaerobicEffect <= 0) return 'N/A';
  return anaerobicEffect.toFixed(1);
};

const formatTSS = (tss?: number, epoc?: number) => {
  const value = tss ?? epoc;
  if (!value || value <= 0) return 'N/A';
  return Math.round(value).toString();
};

const formatPower = (powerWatts?: number) => {
  if (!powerWatts || powerWatts <= 0) return 'N/A';
  return `${Math.round(powerWatts)} W`;
};

const formatLactateThreshold = (lactateSpeed?: number) => {
  if (lactateSpeed === null || lactateSpeed === undefined || isNaN(lactateSpeed)) {
    return 'N/A';
  }
  const paceMinPerKm = 60 / (lactateSpeed * 3.6);
  const minutes = Math.floor(paceMinPerKm);
  const seconds = Math.round((paceMinPerKm - minutes) * 60);
  return `${minutes}:${seconds.toString().padStart(2, '0')} min/km`;
};

const calculatePace = (distance?: number, duration?: number) => {
  if (!distance || !duration || distance <= 0 || duration <= 0) return null;
  
  const distanceKm = distance / 1000;
  const durationMin = duration / 60;
  
  return durationMin / distanceKm;
};

const formatPace = (pace?: number) => {
  if (!pace) return 'N/A';
  
  const minutes = Math.floor(pace);
  const seconds = Math.round((pace - minutes) * 60);
  
  return `${minutes}:${seconds.toString().padStart(2, '0')} min/km`;
};

const formatNegativeSplit = (negativeSplitPercent?: number) => {
  if (negativeSplitPercent === undefined || negativeSplitPercent === null) return 'N/A';
  
  const sign = negativeSplitPercent >= 0 ? '+' : '';
  return `${sign}${negativeSplitPercent.toFixed(1)}%`;
};

const formatDecoupling = (decouplingPercent?: number) => {
  if (decouplingPercent === undefined || decouplingPercent === null) return 'N/A';
  
  const sign = decouplingPercent >= 0 ? '+' : '';
  return `${sign}${decouplingPercent.toFixed(1)}%`;
};

interface ActivityCardProps {
  activity: Activity;
  hrvValue?: number | null;
  isLoadingHrv?: boolean;
}

const ActivityCard: React.FC<ActivityCardProps> = ({ activity, hrvValue, isLoadingHrv }) => {
  const router = useRouter();

  const handleClick = () => {
    router.push(`/activities/${activity.activityId}`);
  };

  const stats = [
    {
      key: 'date',
      label: 'Dato',
      value: formatDate(activity.startTimeLocal)
    },
    {
      key: 'distance',
      label: 'Distanse',
      value: `${((activity.distance || 0) / 1000).toFixed(2)} km`
    },
    {
      key: 'duration',
      label: 'Varighet',
      value: `${Math.round((activity.duration || 0) / 60)} min`
    },
    {
      key: 'pace',
      label: 'Pace',
      value: formatPace(calculatePace(activity.distance, activity.duration))
    },
    ...(activity.averageHR > 0 ? [{
      key: 'average_hr',
      label: 'Snitt puls',
      value: `${Math.round(activity.averageHR)} bpm`
    }] : []),
    {
      key: 'vo2_max',
      label: 'VO2 Max',
      value: formatVO2Max(activity.vO2MaxValue, activity.activityType)
    },
    {
      key: 'running_economy',
      label: 'Løpsøkonomi',
      value: formatRunningEconomy(calculateRunningEconomy(activity.averageSpeed, activity.averageHR, activity.activityType), activity.activityType)
    },
    {
      key: 'negative_split',
      label: 'Negativ Split',
      value: formatNegativeSplit(activity.negativeSplitPercent),
      rawValue: activity.negativeSplitPercent
    },
    {
      key: 'decoupling',
      label: 'Decoupling',
      value: formatDecoupling(activity.decouplingPercent),
      rawValue: activity.decouplingPercent
    },
    {
      key: 'hrv',
      label: 'HRV',
      value: isLoadingHrv ? 'Laster...' : formatHrv(hrvValue),
      rawValue: hrvValue
    },
    {
      key: 'aerobic_effect',
      label: 'Aerob effekt',
      value: formatAerobicEffect(activity.totalTrainingEffect),
      rawValue: activity.totalTrainingEffect
    },
    {
      key: 'anaerobic_effect',
      label: 'Anaerob effekt',
      value: formatAnaerobicEffect(activity.totalAnaerobicTrainingEffect),
      rawValue: activity.totalAnaerobicTrainingEffect
    },
    {
      key: 'power',
      label: 'Power',
      value: formatPower(activity.averagePowerWatts),
      rawValue: activity.averagePowerWatts
    },
    {
      key: 'tss',
      label: 'TSS',
      value: formatTSS(activity.trainingStressScore, activity.epoc),
      rawValue: activity.trainingStressScore ?? activity.epoc
    },
    {
      key: 'lactateThresholdSpeed',
      label: 'Lactate Threshold',
      value: formatLactateThreshold(activity.lactateThresholdSpeed),
      rawValue: activity.lactateThresholdSpeed
    },
  ];

  return (
    <ActivityCardWrapper onClick={handleClick}>
      <ActivityTitle>{activity.activityName}</ActivityTitle>
      <ActivityDetails>
        {stats.map(stat => (
          <ActivityStat 
            key={stat.key} 
            $statKey={stat.key}
            $value={stat.rawValue as number | undefined}
          >
            <StatLabel>{stat.label}</StatLabel>
            <StatValue>{stat.value}</StatValue>
          </ActivityStat>
        ))}
      </ActivityDetails>
    </ActivityCardWrapper>
  );
};

// Memoize for performance - only re-render if props change
export default memo(ActivityCard, (prevProps, nextProps) => {
  return (
    prevProps.activity.activityId === nextProps.activity.activityId &&
    prevProps.hrvValue === nextProps.hrvValue &&
    prevProps.isLoadingHrv === nextProps.isLoadingHrv
  );
});







