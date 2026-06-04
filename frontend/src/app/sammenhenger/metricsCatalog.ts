import type { FactorRelationshipMetricMeta } from '../../utils/api';

/** Speiler backend METRICS i factor_relationships.py (for dropdown før første API-svar). */
export const FACTOR_RELATIONSHIP_METRICS: Record<string, FactorRelationshipMetricMeta> = {
  distance: { source: 'activity', label: 'Distanse', unit: 'km' },
  duration: { source: 'activity', label: 'Varighet', unit: 'min' },
  average_hr: { source: 'activity', label: 'Snittpuls', unit: 'bpm' },
  average_power: { source: 'activity', label: 'Snitteffekt', unit: 'W' },
  training_stress_score: { source: 'activity', label: 'TSS', unit: 'score' },
  epoc: { source: 'activity', label: 'EPOC', unit: 'load' },
  total_training_effect: { source: 'activity', label: 'Aerob treningseffekt', unit: 'score' },
  total_anaerobic_training_effect: { source: 'activity', label: 'Anaerob treningseffekt', unit: 'score' },
  negative_split_percent: { source: 'activity', label: 'Negative split', unit: '%' },
  decoupling_percent: { source: 'activity', label: 'Decoupling', unit: '%' },
  training_readiness_score: { source: 'activity', label: 'Training readiness', unit: 'score' },
  body_battery_start: { source: 'activity', label: 'Body Battery start', unit: 'score' },
  sleep_score: { source: 'health', label: 'Søvnskår', unit: 'score' },
  sleep_time: { source: 'health', label: 'Søvnlengde', unit: 'timer' },
  hrv: { source: 'health', label: 'HRV', unit: 'ms' },
  body_battery: { source: 'health', label: 'Body Battery', unit: 'score' },
  stress_avg: { source: 'health', label: 'Stress', unit: 'score' },
};
