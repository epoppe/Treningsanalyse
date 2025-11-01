import { useQuery } from '@tanstack/react-query';
import { api } from '../utils/api';

/**
 * Query keys for health data
 */
export const healthKeys = {
  all: ['health'] as const,
  hrv: (startDate: string, endDate: string) => 
    [...healthKeys.all, 'hrv', startDate, endDate] as const,
  bodyBattery: (startDate: string, endDate: string) => 
    [...healthKeys.all, 'bodyBattery', startDate, endDate] as const,
  sleep: (startDate: string, endDate: string) => 
    [...healthKeys.all, 'sleep', startDate, endDate] as const,
  stress: (startDate: string, endDate: string) => 
    [...healthKeys.all, 'stress', startDate, endDate] as const,
};

/**
 * Hook for å hente HRV-data for en periode
 */
export function useHrvData(startDate: string, endDate: string, enabled: boolean = true) {
  return useQuery({
    queryKey: healthKeys.hrv(startDate, endDate),
    queryFn: async () => {
      const data = await api.getHrvRange(startDate, endDate);
      // Backend returnerer en flat array, men komponenten forventer { hrv_data: [...] }
      // Transformer til forventet format hvis nødvendig
      if (Array.isArray(data)) {
        return {
          hrv_data: data.map((item: any) => ({
            ...item,
            date: item.date?.split('T')[0] || item.date // Normaliser dato
          })),
          total_records: data.length
        };
      }
      return data;
    },
    enabled: enabled && !!startDate && !!endDate,
    staleTime: 10 * 60 * 1000, // 10 minutter
    retry: 1,
  });
}

/**
 * Hook for å hente Body Battery-data for en periode
 */
export function useBodyBatteryData(startDate: string, endDate: string, enabled: boolean = true) {
  return useQuery({
    queryKey: healthKeys.bodyBattery(startDate, endDate),
    queryFn: () => api.getBodyBatteryRange(startDate, endDate),
    enabled: enabled && !!startDate && !!endDate,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

/**
 * Hook for å hente søvndata for en periode
 */
export function useSleepData(startDate: string, endDate: string, enabled: boolean = true) {
  return useQuery({
    queryKey: healthKeys.sleep(startDate, endDate),
    queryFn: () => api.getSleepRange(startDate, endDate),
    enabled: enabled && !!startDate && !!endDate,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

/**
 * Hook for å hente stressdata for en periode
 */
export function useStressData(startDate: string, endDate: string, enabled: boolean = true) {
  return useQuery({
    queryKey: healthKeys.stress(startDate, endDate),
    queryFn: () => api.getStressRange(startDate, endDate),
    enabled: enabled && !!startDate && !!endDate,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

