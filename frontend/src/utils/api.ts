import axios from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

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

export interface SleepResponse {
  sleep: any[];
  count: number;
  period: {
    start: string;
    end: string;
  };
}

export const activitiesApi = {
  // Hent alle aktiviteter
  getActivities: async (forceRefresh: boolean = false) => {
    const response = await api.get<ActivityResponse>(`/activities${forceRefresh ? '?force_refresh=true' : ''}`);
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
  }
};

export const sleepApi = {
  // Hent søvndata for en spesifikk periode
  getSleepByDateRange: async (startDate: string, endDate: string, forceRefresh: boolean = false) => {
    const days = Math.ceil((new Date(endDate).getTime() - new Date(startDate).getTime()) / (1000 * 60 * 60 * 24));
    const response = await api.get<SleepResponse>(
      `/sleep?days=${days}${forceRefresh ? '&force_refresh=true' : ''}`
    );
    return response.data;
  }
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