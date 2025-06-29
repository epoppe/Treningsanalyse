import axios from 'axios';
import { Activity } from '../types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

async function apiCall<T>(method: string, url: string, options: any = {}): Promise<T> {
  try {
    const response = await api({
      url,
      method,
      data: options.body,
      params: options.params,
    });
    return response.data;
  } catch (error) {
    console.error(`API call failed: ${method} ${url}`, error);
    // Her kan du legge til mer robust feilhåndtering
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



export const activitiesApi = {
  // Hent alle aktiviteter
  getActivities: async (forceRefresh: boolean = false) => {
    const response = await api.get<Activity[]>(`/activities${forceRefresh ? '?force_refresh=true' : ''}`);
    return response.data;
  },

  // Hent aktiviteter for en spesifikk periode
  getActivitiesByDateRange: async (startDate: string, endDate: string, forceRefresh: boolean = false) => {
    const days = Math.ceil((new Date(endDate).getTime() - new Date(startDate).getTime()) / (1000 * 60 * 60 * 24));
    const response = await api.get<ActivityResponse>(
      `/activities?days=${days}${forceRefresh ? '&force_refresh=true' : ''}`
    );
    return response.data;
  },

  // Hent hvilepulsdata
  getRestingHeartRate: async (date: string) => {
    const response = await api.get<ApiResponse<any>>(`/resting-heart-rate/${date}`);
    return response.data;
  },

  // Start synkronisering av historiske data
  syncHistoricalData: async (startYear: number) => {
    const response = await api.post<ApiResponse<any>>(`/sync/historical/${startYear}`);
    return response.data;
  },

  // Start synkronisering fra JSON til DB
  syncDatabase: async () => {
    const response = await api.post<any>('/sync/database');
    return response.data;
  },

  // Hent treningsstatus
  getTrainingStatus: async () => {
    const response = await api.get<ApiResponse<any>>('/training-status');
    return response.data;
  },

  // Start synkronisering av aktiviteter for en periode
  syncActivities: async (startDate: string, endDate: string) => {
    // Konverter ISO-datoer til YYYY-MM-DD format for Pydantic
    const formatDate = (dateStr: string) => {
      return dateStr.split('T')[0];  // Fjern tidspart og behold bare YYYY-MM-DD
    };
    
    const response = await api.post<ApiResponse<any>>('/sync/activities', {
      start_date: formatDate(startDate),
      end_date: formatDate(endDate)
    });
    return response.data;
  },



  // Hent status for en synk-jobb
  getSyncStatus: async (jobId: string) => {
    const response = await api.get<any>(`/sync/status/${jobId}`);
    return response.data;
  }
};

export const healthApi = {
  getStress: (date: string) => apiCall('get', `/health/stress/${date}`),
  getHrv: (date: string) => apiCall('get', `/health/hrv/${date}`),
};

export const analysisApi = {
  getRunningEconomy: (forceRefresh: boolean = false) => apiCall('get', `/analysis/running-economy?force_refresh=${forceRefresh}`),
  getHrv: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    return apiCall('get', `/analysis/hrv?${params.toString()}`);
  },
  getStrideLengthData: (activityId: number) => apiCall('get', `/analysis/stride-length/${activityId}`),
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
  getSyncStatus: (jobId: string) => {
    return apiCall('get', `/sync/status/${jobId}`);
  },
};

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