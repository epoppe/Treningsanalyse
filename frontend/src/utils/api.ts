import axios from 'axios';
import { Activity } from '../types';

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: `${BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

async function apiCall<T>(method: string, url: string, options: any = {}): Promise<T> {
  try {
    const lower = method.toLowerCase();
    const hasExplicitBody = options && Object.prototype.hasOwnProperty.call(options, 'body');
    const data = hasExplicitBody
      ? options.body
      : (lower === 'post' || lower === 'put' || lower === 'patch')
        ? (Object.keys(options || {}).length > 0 && !options.params ? options : undefined)
        : undefined;
    const params = options?.params;

    const response = await apiClient({ url, method, data, params });
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
    console.log('[API] Sender GET request til /activities...');
    console.log('[API] Base URL:', apiClient.defaults.baseURL);
    try {
      const params = new URLSearchParams();
      if (forceRefresh) params.append('force_refresh', 'true');
      if (limit) params.append('limit', limit.toString());
      
      const queryString = params.toString();
      const url = `/activities${queryString ? '?' + queryString : ''}`;
      
      console.log('[API] Full URL:', `${apiClient.defaults.baseURL}${url}`);
      
      const response = await apiClient.get<Activity[]>(url);
      console.log('[API] Mottok response:', response.status, response.data?.length || 0, 'aktiviteter');
      return response.data;
    } catch (error: any) {
      console.error('[API] Feil ved GET /activities:', error);
      console.error('[API] Error response:', error.response?.data);
      console.error('[API] Error status:', error.response?.status);
      console.error('[API] Error message:', error.message);
      throw error;
    }
  },

  // Hent aktiviteter med høyere limit for å vise flere
  getMoreActivities: async (forceRefresh: boolean = false, limit: number = 500, offset: number = 0) => {
    console.log('[API] Sender GET request til /activities med høyere limit og offset...');
    console.log('[API] Base URL:', apiClient.defaults.baseURL);
    try {
      const params = new URLSearchParams();
      if (forceRefresh) params.append('force_refresh', 'true');
      if (limit) params.append('limit', limit.toString());
      if (offset) params.append('offset', offset.toString());
      
      const queryString = params.toString();
      const url = `/activities${queryString ? '?' + queryString : ''}`;
      
      console.log('[API] Full URL:', `${apiClient.defaults.baseURL}${url}`);
      
      const response = await apiClient.get<Activity[]>(url);
      console.log('[API] Mottok response:', response.status, response.data?.length || 0, 'aktiviteter');
      return response.data;
    } catch (error: any) {
      console.error('[API] Feil ved GET /activities med limit/offset:', error);
      console.error('[API] Error response:', error.response?.data);
      console.error('[API] Error status:', error.response?.status);
      console.error('[API] Error message:', error.message);
      throw error;
    }
  },

  // Hent kun nye aktiviteter siden en gitt dato
  getNewActivities: async (since: string, forceRefresh: boolean = false) => {
    console.log('[API] Sender GET request til /activities/new for å hente nye aktiviteter siden', since);
    try {
      const params = new URLSearchParams();
      params.append('since', since);
      if (forceRefresh) params.append('force_refresh', 'true');
      
      const queryString = params.toString();
      const url = `/activities/new?${queryString}`;
      console.log('[API] Full URL:', `${apiClient.defaults.baseURL}${url}`);
      
      const response = await apiClient.get<Activity[]>(url);
      console.log('[API] Mottok response:', response.status, response.data?.length || 0, 'nye aktiviteter');
      return response.data;
    } catch (error: any) {
      console.error('[API] Feil ved GET /activities/new:', error);
      console.error('[API] Error response:', error.response?.data);
      console.error('[API] Error status:', error.response?.status);
      console.error('[API] Error message:', error.message);
      throw error;
    }
  },
  
  // New function to get HRV data for multiple activities
  getHrvForMultipleActivities: async (activityIds: string[]) => {
    console.log('[API] Henter HRV-data for', activityIds.length, 'aktiviteter');
    try {
      const activityIdsParam = activityIds.join(',');
      const response = await apiClient.get(`/analysis/hrv/by-activities?activity_ids=${activityIdsParam}`);
      console.log('[API] HRV-data hentet for', response.data.activities_with_hrv, 'av', response.data.total_activities, 'aktiviteter');
      return response.data;
    } catch (error: any) {
      console.error('[API] Feil ved henting av HRV-data for flere aktiviteter:', error);
      throw error;
    }
  },

  // Hent totalt antall aktiviteter
  getActivityCount: async () => {
    console.log('[API] Sender GET request til /activities/count...');
    console.log('[API] Base URL:', apiClient.defaults.baseURL);
    try {
      const response = await apiClient.get<{count: number}>('/activities/count');
      console.log('[API] Mottok activity count:', response.data.count);
      return response.data.count;
    } catch (error: any) {
      console.error('[API] Feil ved GET /activities/count:', error);
      console.error('[API] Error response:', error.response?.data);
      console.error('[API] Error status:', error.response?.status);
      console.error('[API] Error message:', error.message);
      throw error;
    }
  },

  // Hent aktiviteter for en datoperiode
  getActivitiesByDateRange: async (startDate: string, endDate: string, forceRefresh: boolean = false) => {
    console.log('[API] Sender GET request til /activities/date-range...');
    try {
      const params = new URLSearchParams();
      params.append('start_date', startDate);
      params.append('end_date', endDate);
      if (forceRefresh) params.append('force_refresh', 'true');
      
      const queryString = params.toString();
      const url = `/activities/date-range?${queryString}`;
      
      console.log('[API] Full URL:', `${apiClient.defaults.baseURL}${url}`);
      
      const response = await apiClient.get<Activity[]>(url);
      console.log('[API] Mottok response:', response.status, response.data?.length || 0, 'aktiviteter');
      return { activities: response.data };
    } catch (error: any) {
      console.error('[API] Feil ved GET /activities/date-range:', error);
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

  // Start synkronisering av aktiviteter for en periode
  syncActivities: async (startDate: string, endDate: string) => {
    // Konverter ISO-datoer til YYYY-MM-DD format for Pydantic
    const formatDate = (dateStr: string) => {
      return dateStr.split('T')[0];  // Fjern tidspart og behold bare YYYY-MM-DD
    };
    
    const response = await apiClient.post<ApiResponse<any>>('/sync/activities', {
      start_date: formatDate(startDate),
      end_date: formatDate(endDate),
      ignore_sync_state: true  // Ignorer SyncState for å tillate synkronisering av historiske data
    });
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
  }
};

const healthApi = {
  getStress: (date: string) => apiCall('get', `/health/stress/${date}`),
  getHrv: (date: string) => apiCall('get', `/health/hrv/${date}`),
  
  // Nye metrics basert på Garmy
  getBodyBattery: (date: string) => apiCall('get', `/health/body-battery/${date}`),
  getBodyBatteryRange: (startDate: string, endDate: string) => 
    apiCall('get', `/health/body-battery/range?start_date=${startDate}&end_date=${endDate}`),
  
  getSleep: (date: string) => apiCall('get', `/health/sleep/${date}`),
  getSleepRange: (startDate: string, endDate: string) => 
    apiCall('get', `/health/sleep/range?start_date=${startDate}&end_date=${endDate}`),
  
  getStressRange: (startDate: string, endDate: string) => 
    apiCall('get', `/health/stress/range?start_date=${startDate}&end_date=${endDate}`),
  
  getHrvRange: (startDate: string, endDate: string) => 
    apiCall('get', `/health/hrv/range?start_date=${startDate}&end_date=${endDate}`),
  
  getMetricsSummary: (date: string) => 
    apiCall('get', `/health/metrics/summary?date=${date}`),
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
};

export const syncApi = {
  // --- Aktiviteter ---
  syncActivities: (startDate: string, endDate: string) => apiCall('post', '/sync/activities', { start_date: startDate, end_date: endDate, ignore_sync_state: true }),
  syncNewActivities: () => apiCall('post', '/sync/new-activities'),
  syncAllActivities: () => apiCall('post', '/sync/full-sync'),
  fullSync: (startDate: string, endDate: string) => apiCall('post', '/sync/full-sync', { start_date: startDate, end_date: endDate, ignore_sync_state: true }),
  // Sender data direkte til apiCall (IKKE wrappet i body)
  fullSyncBody: (startDate: string, endDate: string) => apiCall('post', '/sync/full-sync', { start_date: startDate, end_date: endDate, ignore_sync_state: true }),
  
  // --- HRV ---
  syncHrvData: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const queryString = params.toString();
    const url = `/sync/hrv-sync${queryString ? `?${queryString}` : ''}`;
    return apiCall('post', url);
  },
  
  // --- Body Battery ---
  syncBodyBatteryData: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const queryString = params.toString();
    const url = `/sync/body-battery-sync${queryString ? `?${queryString}` : ''}`;
    return apiCall('post', url);
  },
  
  // --- Jobb-status ---
  getSyncStatus: async (jobId: string) => {
    try {
      const response = await apiClient.get<any>(`/sync/status/${jobId}`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        // Jobb ikke funnet - returner en standard status
        return {
          status: "not_found",
          message: "Synkroniseringsjobb ikke funnet (kan være fullført eller slettet)",
          job_id: jobId
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
  ...syncApi,
} as typeof activitiesApi & typeof healthApi & typeof analysisApi & typeof syncApi;

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