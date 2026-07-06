import axios from 'axios';
import { Activity } from '../types';
import type { SyncJobStatusResponse } from '../types/syncJob';

// Bruk relativ URL slik at Next.js proxy (rewrite) sender til backend – unngår CORS
export const BASE_URL = typeof window !== 'undefined' ? '' : (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');

const apiClient = axios.create({
  baseURL: typeof window !== 'undefined' ? '/api' : `${BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

/** Timeout for POST som kun returnerer 202 + jobb-id (server kan bruke tid før svar). */
const SYNC_TRIGGER_TIMEOUT_MS = 120_000;

/** Løpeanalyse kan trigge tung FIT-beregning ved recalculate=true. */
const ANALYTICS_TIMEOUT_MS = 120_000;

async function apiCall<T>(method: string, url: string, options: any = {}): Promise<T> {
  try {
    const lower = method.toLowerCase();
    const hasExplicitBody = options && Object.prototype.hasOwnProperty.call(options, 'body');
    const timeout = options?.timeout;
    const params = options?.params;

    let data: unknown;
    if (hasExplicitBody) {
      data = options.body;
    } else if (lower === 'post' || lower === 'put' || lower === 'patch') {
      const payload = { ...(options || {}) };
      delete payload.timeout;
      delete payload.params;
      delete payload.body;
      data = Object.keys(payload).length ? payload : undefined;
    } else {
      data = undefined;
    }

    const response = await apiClient({
      url,
      method,
      data,
      params,
      ...(timeout != null && { timeout }),
    });
    return response.data;
  } catch (error: any) {
    // For HRV endepunkter, er 404 forventet når det ikke finnes HRV-data
    if (error?.response?.status === 404 && url.includes('/hrv/by-activity/')) {
      // Log som info i stedet for error
      console.info(`Ingen HRV-data tilgjengelig for ${url}`);
    } else {
      console.error(`API call failed: ${method} ${url}`, error);
    }
    throw error;
  }
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
  error?: string;
}

export interface ActivityResponse {
  activities: any[];
  count: number;
  period: {
    start: string;
    end: string;
  };
}

export interface HrvByActivityResponse {
  last_night_avg: number | null;
}



export const activitiesApi = {
  // Hent alle aktiviteter
  getActivities: async (forceRefresh: boolean = false, limit: number = 100) => {
    try {
      const params = new URLSearchParams();
      if (forceRefresh) params.append('force_refresh', 'true');
      if (limit) params.append('limit', limit.toString());
      
      const queryString = params.toString();
      const url = `/activities${queryString ? '?' + queryString : ''}`;

      const response = await apiClient.get<Activity[]>(url);
      return response.data;
    } catch (error: any) {
      throw error;
    }
  },

  getActivitiesByIds: async (activityIds: string[], forceRefresh: boolean = false) => {
    if (!activityIds.length) return [];
    const params = new URLSearchParams();
    params.append('activity_ids', activityIds.join(','));
    if (forceRefresh) params.append('force_refresh', 'true');
    const response = await apiClient.get<Activity[]>(`/activities?${params.toString()}`);
    return response.data;
  },

  // Hent aktiviteter med høyere limit for å vise flere
  getMoreActivities: async (forceRefresh: boolean = false, limit: number = 500, offset: number = 0) => {
    try {
      const params = new URLSearchParams();
      if (forceRefresh) params.append('force_refresh', 'true');
      if (limit) params.append('limit', limit.toString());
      if (offset) params.append('offset', offset.toString());
      
      const queryString = params.toString();
      const url = `/activities${queryString ? '?' + queryString : ''}`;

      const response = await apiClient.get<Activity[]>(url);
      return response.data;
    } catch (error: any) {
      throw error;
    }
  },

  // Hent kun nye aktiviteter siden en gitt dato
  getNewActivities: async (since: string, forceRefresh: boolean = false) => {
    try {
      const params = new URLSearchParams();
      params.append('since', since);
      if (forceRefresh) params.append('force_refresh', 'true');
      
      const queryString = params.toString();
      const url = `/activities/new?${queryString}`;

      const response = await apiClient.get<Activity[]>(url);
      return response.data;
    } catch (error: any) {
      throw error;
    }
  },
  
  // New function to get HRV data for multiple activities
  getHrvForMultipleActivities: async (activityIds: string[]) => {
    try {
      const activityIdsParam = activityIds.join(',');
      const response = await apiClient.get(`/analysis/hrv/by-activities?activity_ids=${activityIdsParam}`);
      return response.data;
    } catch (error: any) {
      throw error;
    }
  },

  // Hent totalt antall aktiviteter
  getActivityCount: async () => {
    try {
      const response = await apiClient.get<{count: number}>('/activities/count');
      return response.data.count;
    } catch (error: any) {
      throw error;
    }
  },

  // Hent aktiviteter for en datoperiode
  getActivitiesByDateRange: async (startDate: string, endDate: string, forceRefresh: boolean = false) => {
    try {
      const params = new URLSearchParams();
      params.append('start_date', startDate);
      params.append('end_date', endDate);
      if (forceRefresh) params.append('force_refresh', 'true');
      
      const queryString = params.toString();
      const url = `/activities/date-range?${queryString}`;

      const response = await apiClient.get<Activity[]>(url);
      return { activities: response.data };
    } catch (error: any) {
      throw error;
    }
  },

  // Hent hvilepulsdata
  getRestingHeartRate: async (date: string) => {
    const response = await apiClient.get<ApiResponse<any>>(`/resting-heart-rate/${date}`);
    return response.data;
  },

  // Start synkronisering av historiske data
  syncHistoricalData: async (startYear: number) => {
    const response = await apiClient.post<ApiResponse<any>>(`/sync/historical/${startYear}`);
    return response.data;
  },

  // Start synkronisering fra JSON til DB
  syncDatabase: async () => {
    const response = await apiClient.post<any>('/sync/database');
    return response.data;
  },

  // Hent treningsstatus
  getTrainingStatus: async () => {
    const response = await apiClient.get<ApiResponse<any>>('/training-status');
    return response.data;
  },

  // Training Readiness API
  getTrainingReadiness: async (date?: string) => {
    const timestamp = new Date().getTime();
    const params = date ? `?target_date=${date}&_t=${timestamp}` : `?_t=${timestamp}`;
    const response = await apiClient.get<ApiResponse<any>>(`/training-readiness${params}`);
    return response.data;
  },

  getWeeklyTrainingReadiness: async (endDate?: string) => {
    const params = endDate ? `?end_date=${endDate}` : '';
    const response = await apiClient.get<ApiResponse<any>>(`/training-readiness/weekly${params}`);
    return response.data;
  },

  getTrainingReadinessStatus: async (date?: string) => {
    const params = date ? `?target_date=${date}` : '';
    const response = await apiClient.get<ApiResponse<any>>(`/training-readiness/status${params}`);
    return response.data;
  },

  getReadinessChatResponse: async (message: string, date: string) => {
    // Bruk Next.js API-rute /readiness-chat som fallback (backend chat gir 404 på noen systemer)
    const res = await fetch('/readiness-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, date }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.response || 'Chat-feil');
    return data.response;
  }
};

const healthApi = {
  getStress: (date: string) => apiCall('get', `/health/stress/${date}`),
  getHrv: (date: string) => apiCall('get', `/health/hrv/${date}`),
  
  // Nye metrics basert på Garmy
  getBodyBattery: (date: string) => apiCall('get', `/health/body-battery/${date}`),
  getBodyBatteryRange: (startDate: string, endDate: string) =>
    apiCall('get', `/health/body-battery/range?start_date=${startDate}&end_date=${endDate}`, { timeout: 90000 }),
  
  getSleep: (date: string) => apiCall('get', `/health/sleep/${date}`),
  getSleepRange: (startDate: string, endDate: string) =>
    apiCall('get', `/health/sleep/range?start_date=${startDate}&end_date=${endDate}`, { timeout: 90000 }),
  
  getStressRange: (startDate: string, endDate: string) =>
    apiCall('get', `/health/stress/range?start_date=${startDate}&end_date=${endDate}`, { timeout: 90000 }),
  
  getHrvRange: (startDate: string, endDate: string) =>
    apiCall('get', `/health/hrv/range?start_date=${startDate}&end_date=${endDate}`, { timeout: 90000 }),
};

export interface BodyBatteryByActivityResponse {
  activity_id: number;
  body_battery_start: number;
  calculation_method: string;
  factors?: {
    base: number;
    sleep: number;
    hrv: number;
    stress: number;
    recovery: number;
  };
}

export interface FactorRelationshipsResponse {
  x_metric: string;
  y_metric: string;
  days: number;
  activity_type?: string | null;
  point_count: number;
  correlation: number | null;
  correlation_strength: string;
  x_meta: { label: string; unit: string };
  y_meta: { label: string; unit: string };
  summary: { avg_x: number | null; avg_y: number | null };
  available_metrics: Record<string, FactorRelationshipMetricMeta>;
  points: Array<{
    activity_id: string;
    activity_name?: string;
    activity_type?: string;
    date: string;
    x: number;
    y: number;
    distance_km?: number;
    duration_min?: number;
  }>;
}

export interface FactorRelationshipMetricMeta {
  label: string;
  unit: string;
  source: string;
  availability?: 'supported' | 'computed' | 'not_ingested' | 'empty_source' | 'unsupported';
  availability_reason?: string;
  selectable?: boolean;
  value_count?: number;
}

export interface EfficiencyTrendItem {
  activityId: string;
  activityName?: string | null;
  startTimeLocal: string;
  avgEfficiencyFactor?: number | null;
  medianEfficiencyFactor?: number | null;
  steadyStateEfficiencyFactor?: number | null;
  efficiencyDataQuality?: number | null;
  distance?: number | null;
  duration?: number | null;
}

export interface DecouplingTrendItem {
  activityId: string;
  activityName?: string | null;
  startTimeLocal: string;
  decouplingPercent?: number | null;
  decouplingSuitabilityFlag?: string | null;
  decouplingReasonIfUnsuitable?: string | null;
  decouplingDataQualityScore?: number | null;
  avgEfficiencyFactor?: number | null;
  distance?: number | null;
  duration?: number | null;
}

export interface FatigueResistanceItem {
  activityId: string;
  activityName?: string | null;
  startTimeLocal: string;
  fatigueResistanceScore?: number | null;
  paceDropPct?: number | null;
  hrDriftPct?: number | null;
  cadenceDropPct?: number | null;
  efDropPct?: number | null;
  distance?: number | null;
  duration?: number | null;
}

export interface AnalyticsListResponse<T> {
  activities: T[];
  count: number;
}

export interface CriticalSpeedEffort {
  duration_seconds: number;
  speed_mps?: number;
  pace_sec_per_km?: number | null;
  activity_id?: string;
  activity_name?: string;
}

export interface CriticalSpeedPaceByYearCell {
  pace_sec_per_km: number | null;
  speed_mps?: number | null;
  activity_id?: string | null;
  source?: 'year_best' | 'anchor_activity';
}

export interface CriticalSpeedPaceByYearRow {
  duration_seconds: number;
  paces_by_year: Record<string, CriticalSpeedPaceByYearCell | null>;
}

export interface CriticalSpeedPaceByYearResponse {
  years: number[];
  rows: CriticalSpeedPaceByYearRow[];
  include_treadmill?: boolean;
}

export interface CriticalSpeedResponse {
  critical_speed_mps: number | null;
  critical_pace_sec_per_km: number | null;
  d_prime: number | null;
  model_r2: number | null;
  model_quality: string;
  efforts?: CriticalSpeedEffort[];
  include_treadmill?: boolean;
  lookback_days?: number | null;
  calculated_at?: string | null;
  data_quality_score?: number | null;
}

export type DurationCurveMetric = 'speed' | 'power';
export type DurationCurveScope = 'all_time' | 'last_90_days' | 'last_365_days';

export interface DurationCurvePoint {
  duration_seconds: number;
  speed_mps?: number | null;
  pace_sec_per_km?: number | null;
  power_watts?: number | null;
  activity_id?: string | null;
  activity_name?: string | null;
  activity_start_time?: string | null;
}

export interface DurationCurveResponse {
  metric: DurationCurveMetric;
  scope: DurationCurveScope;
  points: DurationCurvePoint[];
  effort_count: number;
  calculated_at?: string | null;
}

export interface DurationCurveYearSeries {
  year: number;
  points: DurationCurvePoint[];
  effort_count: number;
}

export interface DurationCurveYearComparisonResponse {
  metric: DurationCurveMetric;
  years: DurationCurveYearSeries[];
  calculated_at?: string | null;
}

export interface AnalyticsQueryParams {
  days?: number;
  limit?: number;
  includeTreadmill?: boolean;
}

const appendAnalyticsQuery = (search: URLSearchParams, params: AnalyticsQueryParams = {}) => {
  if (params.days != null) search.append('days', String(params.days));
  if (params.limit != null) search.append('limit', String(params.limit));
  if (params.includeTreadmill) search.append('include_treadmill', 'true');
};

export const analyticsApi = {
  getEfficiencyTrends: (params: AnalyticsQueryParams = {}) => {
    const search = new URLSearchParams();
    appendAnalyticsQuery(search, params);
    const query = search.toString();
    return apiCall<AnalyticsListResponse<EfficiencyTrendItem>>(
      'get',
      `/analytics/efficiency${query ? `?${query}` : ''}`,
      { timeout: ANALYTICS_TIMEOUT_MS },
    );
  },

  getDecouplingTrends: (params: AnalyticsQueryParams = {}) => {
    const search = new URLSearchParams();
    appendAnalyticsQuery(search, params);
    const query = search.toString();
    return apiCall<AnalyticsListResponse<DecouplingTrendItem>>(
      'get',
      `/analytics/decoupling${query ? `?${query}` : ''}`,
      { timeout: ANALYTICS_TIMEOUT_MS },
    );
  },

  getCriticalSpeedPaceByYear: (years = 3, includeTreadmill = false) => {
    const search = new URLSearchParams();
    search.append('years', String(years));
    if (includeTreadmill) search.append('include_treadmill', 'true');
    return apiCall<CriticalSpeedPaceByYearResponse>(
      'get',
      `/analytics/critical-speed/pace-by-year?${search.toString()}`,
      { timeout: ANALYTICS_TIMEOUT_MS },
    );
  },

  getCriticalSpeed: (recalculate = false, includeTreadmill = false) => {
    const search = new URLSearchParams();
    if (recalculate) search.append('recalculate', 'true');
    if (includeTreadmill) search.append('include_treadmill', 'true');
    const query = search.toString();
    return apiCall<CriticalSpeedResponse>(
      'get',
      `/analytics/critical-speed${query ? `?${query}` : ''}`,
      { timeout: ANALYTICS_TIMEOUT_MS },
    );
  },

  getFatigueResistance: (params: AnalyticsQueryParams = {}) => {
    const search = new URLSearchParams();
    appendAnalyticsQuery(search, params);
    const query = search.toString();
    return apiCall<AnalyticsListResponse<FatigueResistanceItem>>(
      'get',
      `/analytics/fatigue-resistance${query ? `?${query}` : ''}`,
      { timeout: ANALYTICS_TIMEOUT_MS },
    );
  },

  getDurationCurve: (
    metric: DurationCurveMetric = 'speed',
    scope: DurationCurveScope = 'all_time',
    includeTreadmill = false,
    recalculate = false,
  ) => {
    const search = new URLSearchParams();
    search.append('metric', metric);
    search.append('scope', scope);
    if (includeTreadmill) search.append('include_treadmill', 'true');
    if (recalculate) search.append('recalculate', 'true');
    return apiCall<DurationCurveResponse>(
      'get',
      `/analytics/duration-curve?${search.toString()}`,
      { timeout: ANALYTICS_TIMEOUT_MS },
    );
  },

  getDurationCurveYearComparison: (
    metric: DurationCurveMetric = 'speed',
    years = 3,
    includeTreadmill = false,
    recalculate = false,
  ) => {
    const search = new URLSearchParams();
    search.append('metric', metric);
    search.append('years', String(years));
    if (includeTreadmill) search.append('include_treadmill', 'true');
    if (recalculate) search.append('recalculate', 'true');
    return apiCall<DurationCurveYearComparisonResponse>(
      'get',
      `/analytics/duration-curve/year-comparison?${search.toString()}`,
      { timeout: ANALYTICS_TIMEOUT_MS },
    );
  },
};

export const analysisApi = {
  getVo2MaxHistory: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    return apiCall('get', `/analysis/vo2max/history?${params.toString()}`);
  },
  
  getTrainingOverview: (days: number = 30) => 
    apiCall('get', `/analysis/training-overview?days=${days}`),
  getRunningEconomy: (forceRefresh: boolean = false) => apiCall('get', `/analysis/running-economy?force_refresh=${forceRefresh}`),
  getNegativeSplit: (activityId: number) => apiCall('get', `/activities/${activityId}/negative-split`),
  getDecoupling: (activityId: number) => apiCall('get', `/activities/${activityId}/decoupling`),
  getHrvByActivity: (activityId: number): Promise<HrvByActivityResponse> => apiCall<HrvByActivityResponse>('get', `/analysis/hrv/by-activity/${activityId}`),
  getStrideLengthData: (activityId: number) => apiCall('get', `/analysis/stride-length/${activityId}`),
  getBodyBatteryByActivity: (activityId: number): Promise<BodyBatteryByActivityResponse> => apiCall<BodyBatteryByActivityResponse>('get', `/analysis/body-battery/by-activity/${activityId}`),
  
  // Body Battery fra database
  getBodyBatteryData: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const queryString = params.toString();
    const url = `/analysis/body-battery${queryString ? `?${queryString}` : ''}`;
    return apiCall('get', url);
  },
  getBodyBatteryStatistics: () => apiCall('get', '/analysis/body-battery/statistics'),
  getFactorRelationships: async (params: {
    xMetric: string;
    yMetric: string;
    days: number;
    activityType?: string;
    minDistanceKm?: number;
  }) => {
    const search = new URLSearchParams();
    search.append('x_metric', params.xMetric);
    search.append('y_metric', params.yMetric);
    search.append('days', String(params.days));
    if (params.activityType) search.append('activity_type', params.activityType);
    if (params.minDistanceKm != null) search.append('min_distance_km', String(params.minDistanceKm));
    try {
      const response = await apiClient.get<FactorRelationshipsResponse>(
        `/analysis/factor-relationships?${search.toString()}`,
      );
      return response.data;
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      if (
        error?.response?.status === 400
        && detail
        && typeof detail === 'object'
        && detail.error === 'unknown_metric'
      ) {
        throw new Error('Ukjent måling på X- eller Y-aksen.');
      }
      throw error;
    }
  },
};

export const syncApi = {
  /**
   * Aktiviteter + FIT for datointervall (POST /sync/activities).
   * Tar ikke med full helsesynk/TE/HRV som «full»-jobben.
   */
  syncActivitiesForPeriod: (startDate: string, endDate: string) =>
    apiCall('post', '/sync/activities', {
      start_date: startDate,
      end_date: endDate,
      ignore_sync_state: true,
      timeout: SYNC_TRIGGER_TIMEOUT_MS,
    }),

  /** Nye aktiviteter fra siste lagrede aktivitet + tilhørende helse/TE/BB (tung jobb). */
  syncNewActivities: () =>
    apiCall('post', '/sync/new-activities', { timeout: SYNC_TRIGGER_TIMEOUT_MS }),

  /**
   * Full synkronisering for periode: aktivitet, FIT, helse, TE, HRV, Body Battery, beregninger (POST /sync/full-sync).
   */
  fullSyncForPeriod: (startDate: string, endDate: string) =>
    apiCall('post', '/sync/full-sync', {
      start_date: startDate,
      end_date: endDate,
      ignore_sync_state: true,
      timeout: SYNC_TRIGGER_TIMEOUT_MS,
    }),
  
  // --- HRV ---
  syncHrvData: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const queryString = params.toString();
    const url = `/sync/hrv-sync${queryString ? `?${queryString}` : ''}`;
    return apiCall('post', url, { timeout: SYNC_TRIGGER_TIMEOUT_MS });
  },
  
  // --- Training Effect (aerob/anaerob effekt) ---
  refreshTrainingEffect: (force?: boolean) =>
    apiCall('post', `/sync/training-effect/refresh${force ? '?force=true' : ''}`, {
      timeout: SYNC_TRIGGER_TIMEOUT_MS,
    }),

  /** Garmin VO2max, treningsstatus, load m.m. for siste 90 dager. */
  syncGarminPerformanceRecent: () =>
    apiCall('post', '/sync/garmin-performance/recent', { timeout: SYNC_TRIGGER_TIMEOUT_MS }),

  // --- Body Battery ---
  syncBodyBatteryData: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const queryString = params.toString();
    const url = `/sync/body-battery-sync${queryString ? `?${queryString}` : ''}`;
    return apiCall('post', url, { timeout: SYNC_TRIGGER_TIMEOUT_MS });
  },
  
  // --- Jobb-status ---
  getSyncStatus: async (jobId: string): Promise<SyncJobStatusResponse> => {
    try {
      const response = await apiClient.get<SyncJobStatusResponse>(`/sync/status/${jobId}`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return {
          status: 'not_found',
          message: 'Synkroniseringsjobb ikke funnet (kan være fullført eller slettet)',
          job_id: jobId,
        };
      }
      throw error;
    }
  },
};

export const api = {
  ...activitiesApi,
  ...healthApi,
  ...analysisApi,
  ...analyticsApi,
  ...syncApi,
} as typeof activitiesApi & typeof healthApi & typeof analysisApi & typeof analyticsApi & typeof syncApi;

export const errorHandler = (error: any) => {
  if (error.response) {
    // Server returnerte en feilkode
    return {
      error: error.response.data.detail || 'En feil oppstod på serveren',
      status: error.response.status
    };
  } else if (error.request) {
    // Ingen respons mottatt
    return {
      error: 'Kunne ikke nå serveren. Sjekk internettforbindelsen.',
      status: 0
    };
  } else {
    // Noe gikk galt med forespørselen
    return {
      error: error.message || 'En ukjent feil oppstod',
      status: 0
    };
  }
}; 
