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
    const response = await apiClient({
      url,
      method,
      data: options.body,
      params: options.params,
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
    console.log('[API] Sender GET request til /activities...');
    try {
      const params = new URLSearchParams();
      if (forceRefresh) params.append('force_refresh', 'true');
      if (limit) params.append('limit', limit.toString());
      
      const queryString = params.toString();
      const url = `/activities${queryString ? '?' + queryString : ''}`;
      
      const response = await apiClient.get<Activity[]>(url);
      console.log('[API] Mottok response:', response.status, response.data?.length || 0, 'aktiviteter');
      return response.data;
    } catch (error) {
      console.error('[API] Feil ved GET /activities:', error);
      throw error;
    }
  },

  // Hent aktiviteter med høyere limit for å vise flere
  getMoreActivities: async (forceRefresh: boolean = false, limit: number = 500, offset: number = 0) => {
    console.log('[API] Sender GET request til /activities med høyere limit og offset...');
    try {
      const params = new URLSearchParams();
      if (forceRefresh) params.append('force_refresh', 'true');
      if (limit) params.append('limit', limit.toString());
      if (offset) params.append('offset', offset.toString());
      
      const queryString = params.toString();
      const url = `/activities${queryString ? '?' + queryString : ''}`;
      
      const response = await apiClient.get<Activity[]>(url);
      console.log('[API] Mottok response:', response.status, response.data?.length || 0, 'aktiviteter');
      return response.data;
    } catch (error) {
      console.error('[API] Feil ved GET /activities med høyere limit:', error);
      throw error;
    }
  },

  // Hent totalt antall aktiviteter
  getActivityCount: async () => {
    console.log('[API] Sender GET request til /activities/count...');
    try {
      const response = await apiClient.get<{count: number}>('/activities/count');
      console.log('[API] Mottok activity count:', response.data.count);
      return response.data.count;
    } catch (error) {
      console.error('[API] Feil ved GET /activities/count:', error);
      throw error;
    }
  },

  // Hent aktiviteter for en spesifikk periode
  getActivitiesByDateRange: async (startDate: string, endDate: string, forceRefresh: boolean = false) => {
    const days = Math.ceil((new Date(endDate).getTime() - new Date(startDate).getTime()) / (1000 * 60 * 60 * 24));
    const response = await apiClient.get<ActivityResponse>(
      `/activities?days=${days}${forceRefresh ? '&force_refresh=true' : ''}`
    );
    return response.data;
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
      end_date: formatDate(endDate)
    });
    return response.data;
  }
};

const healthApi = {
  getStress: (date: string) => apiCall('get', `/health/stress/${date}`),
  getHrv: (date: string) => apiCall('get', `/health/hrv/${date}`),
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
  getRunningEconomy: (forceRefresh: boolean = false) => apiCall('get', `/analysis/running-economy?force_refresh=${forceRefresh}`),
  getNegativeSplit: (activityId: number) => apiCall('get', `/activities/${activityId}/negative-split`),
  getDecoupling: (activityId: number) => apiCall('get', `/activities/${activityId}/decoupling`),
  getHrvByActivity: (activityId: number): Promise<HrvByActivityResponse> => apiCall<HrvByActivityResponse>('get', `/analysis/hrv/by-activity/${activityId}`),
  getStrideLengthData: (activityId: number) => apiCall('get', `/analysis/stride-length/${activityId}`),
  getBodyBatteryByActivity: (activityId: number): Promise<BodyBatteryByActivityResponse> => apiCall<BodyBatteryByActivityResponse>('get', `/analysis/body-battery/by-activity/${activityId}`),
};

export const syncApi = {
  // --- Aktiviteter ---
  syncActivities: (startDate: string, endDate: string) => {
    const body = {
      start_date: startDate.split('T')[0],
      end_date: endDate.split('T')[0],
    };
    return apiCall('post', '/sync/activities', { body });
  },
  syncRecentActivities: () => {
    return apiCall('post', '/sync/activities/recent');
  },
  
  // --- Helsedata ---
  syncHealthData: (startDate: string, endDate: string) => {
    const body = {
      start_date: startDate.split('T')[0],
      end_date: endDate.split('T')[0],
    };
    return apiCall('post', '/sync/health', { body });
  },
  syncHealthLast90Days: () => {
    return apiCall('post', '/sync/health/recent');
  },

  // --- Felles ---
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
  }
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