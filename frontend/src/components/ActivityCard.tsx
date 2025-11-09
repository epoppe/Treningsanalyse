'use client';

import { memo } from 'react';
import { useRouter } from 'next/navigation';
import { Activity } from '../types';

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
  return `${minutes}:${seconds.toString().padStart(2, '0')} m/km`;
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
  
  return `${minutes}:${seconds.toString().padStart(2, '0')} m/km`;
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

const formatActivityType = (typeKey?: string) => {
  if (!typeKey) return null;
  const map: Record<string, string> = {
    running: 'Løping',
    treadmill_running: 'Tredemølle',
    cycling: 'Sykling',
    trail_running: 'Terrengløp',
    walking: 'Gåing',
    hiking: 'Fottur',
  };
  return map[typeKey] ?? typeKey.replace(/_/g, ' ');
};

const getStatTone = (statKey: string, value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return {
      backgroundColor: '#e2e8f0', // slate-200
      color: '#1e293b',
      border: '1px solid #cbd5f5',
    };
  }

  const toneMap: Record<'emerald' | 'amber' | 'rose' | 'sky' | 'orange' | 'slate', { backgroundColor: string; color: string; border: string }> = {
    emerald: {
      backgroundColor: '#d1fae5',
      color: '#065f46',
      border: '1px solid #a7f3d0',
    },
    amber: {
      backgroundColor: '#fef3c7',
      color: '#92400e',
      border: '1px solid #fde68a',
    },
    rose: {
      backgroundColor: '#ffe4e6',
      color: '#9f1239',
      border: '1px solid #fecdd3',
    },
    sky: {
      backgroundColor: '#e0f2fe',
      color: '#075985',
      border: '1px solid #bae6fd',
    },
    orange: {
      backgroundColor: '#ffedd5',
      color: '#9a3412',
      border: '1px solid #fed7aa',
    },
    slate: {
      backgroundColor: '#e2e8f0',
      color: '#1e293b',
      border: '1px solid #cbd5f5',
    },
  };

  const accent = (tone: keyof typeof toneMap) => toneMap[tone];

  switch (statKey) {
    case 'decoupling':
      if (value > 10) return accent('rose');
      if (value >= 5) return accent('amber');
      return accent('emerald');
    case 'negative_split':
      return value > 0 ? accent('rose') : accent('emerald');
    case 'hrv':
      if (value < 35) return accent('rose');
      if (value <= 37) return accent('amber');
      return accent('emerald');
    case 'aerobic_effect':
    case 'anaerobic_effect':
      if (value < 2) return accent('slate');
      if (value < 3) return accent('sky');
      if (value < 4) return accent('emerald');
      if (value < 5) return accent('amber');
      return accent('rose');
    case 'tss':
      if (value < 50) return accent('slate');
      if (value < 100) return accent('sky');
      if (value < 200) return accent('emerald');
      if (value < 300) return accent('amber');
      if (value < 400) return accent('orange');
      return accent('rose');
    case 'power':
      if (value <= 0) return accent('slate');
      if (value < 200) return accent('sky');
      if (value < 300) return accent('emerald');
      if (value < 400) return accent('amber');
      if (value < 500) return accent('orange');
      return accent('rose');
    default:
      return accent('slate');
  }
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

  const activityTypeLabel = formatActivityType(activity.activityType?.typeKey);

  const stats = [
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
      label: 'Løps-\nøkonomi',
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
    <div
      onClick={handleClick}
      className="group cursor-pointer transition hover:bg-accent/30"
      style={{
        marginBottom: '0.125rem',
        padding: '0.25rem 0',
        borderBottom: '1px solid rgba(226, 232, 240, 0.6)',
      }}
    >
      <div className="mb-1 flex items-center">
        <span
          className="text-sm font-semibold"
          style={{ color: '#475569', whiteSpace: 'nowrap', fontSize: '0.875rem', marginRight: '1rem', fontWeight: 600 }}
        >
          {formatDate(activity.startTimeLocal)}
        </span>
        <span
          className="flex-1 text-base font-semibold tracking-tight"
          style={{ fontSize: '0.95rem', fontWeight: 600, color: '#0f172a' }}
        >
          {activity.activityName}
        </span>
      </div>
      <div style={{ padding: '0' }}>
        <div
          className="grid gap-2"
          style={{
            display: 'grid',
            gap: '8px',
            gridTemplateColumns: 'repeat(14, minmax(0, 1fr))',
            paddingBottom: '0.25rem',
          }}
        >
          {stats.map((stat) => (
            <div
              key={stat.key}
              className="min-h-[64px] rounded-lg px-2 py-2 text-xs shadow-sm transition duration-150"
              style={{
                display: 'grid',
                gridTemplateRows: 'repeat(3, minmax(0, 1fr))',
                ...getStatTone(stat.key, stat.rawValue as number | null | undefined),
              }}
            >
              <div
                className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
                style={{
                  fontSize: '0.625rem',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  color: '#475569',
                  letterSpacing: '0.05em',
                  marginBottom: '0.2rem',
                  whiteSpace: 'pre-line',
                  lineHeight: 1.2,
                  display: 'block',
                  gridRow: '1 / span 2',
                  alignSelf: 'start',
                }}
              >
                {stat.label}
              </div>
              <div
                className="text-xs font-semibold"
                style={{
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: '#0f172a',
                  lineHeight: 1.25,
                  wordBreak: 'break-word',
                  whiteSpace: 'normal',
                  display: 'block',
                  gridRow: '3 / span 1',
                  alignSelf: 'end',
                }}
              >
                {stat.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
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











