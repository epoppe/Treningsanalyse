import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { analysisApi } from '../utils/api';

/**
 * Query keys for analysis data
 */
export const analysisKeys = {
  all: ['analysis'] as const,
  runningEconomy: (forceRefresh?: boolean) => 
    [...analysisKeys.all, 'runningEconomy', forceRefresh] as const,
  negativeSplit: (activityId: number) => 
    [...analysisKeys.all, 'negativeSplit', activityId] as const,
  decoupling: (activityId: number) => 
    [...analysisKeys.all, 'decoupling', activityId] as const,
  hrvByActivity: (activityId: number) => 
    [...analysisKeys.all, 'hrvByActivity', activityId] as const,
  strideLength: (activityId: number) => 
    [...analysisKeys.all, 'strideLength', activityId] as const,
  bodyBatteryByActivity: (activityId: number) => 
    [...analysisKeys.all, 'bodyBatteryByActivity', activityId] as const,
};

/**
 * Hook for å hente running economy data
 */
export function useRunningEconomy(forceRefresh: boolean = false) {
  return useQuery({
    queryKey: analysisKeys.runningEconomy(forceRefresh),
    queryFn: () => analysisApi.getRunningEconomy(forceRefresh),
    staleTime: forceRefresh ? 0 : 15 * 60 * 1000, // 15 minutter hvis ikke force refresh
    gcTime: 30 * 60 * 1000, // 30 minutter
  });
}

/**
 * Hook for å hente negative split data for en aktivitet
 */
export function useNegativeSplit(activityId: number, enabled: boolean = true) {
  return useQuery({
    queryKey: analysisKeys.negativeSplit(activityId),
    queryFn: () => analysisApi.getNegativeSplit(activityId),
    enabled,
    staleTime: 60 * 60 * 1000, // 1 time - historiske data endrer seg ikke
  });
}

/**
 * Hook for å hente decoupling data for en aktivitet
 */
export function useDecoupling(activityId: number, enabled: boolean = true) {
  return useQuery({
    queryKey: analysisKeys.decoupling(activityId),
    queryFn: () => analysisApi.getDecoupling(activityId),
    enabled,
    staleTime: 60 * 60 * 1000, // 1 time
  });
}

/**
 * Hook for å hente HRV data for en aktivitet
 */
export function useHrvByActivity(activityId: number, enabled: boolean = true) {
  return useQuery({
    queryKey: analysisKeys.hrvByActivity(activityId),
    queryFn: () => analysisApi.getHrvByActivity(activityId),
    enabled,
    staleTime: 10 * 60 * 1000, // 10 minutter
    retry: false, // Ikke retry for HRV - data kan mangle
  });
}

/**
 * Hook for å hente stride length data for en aktivitet
 */
export function useStrideLength(activityId: number, enabled: boolean = true) {
  return useQuery({
    queryKey: analysisKeys.strideLength(activityId),
    queryFn: () => analysisApi.getStrideLengthData(activityId),
    enabled,
    staleTime: 60 * 60 * 1000, // 1 time
  });
}

/**
 * Hook for å hente body battery data for en aktivitet
 */
export function useBodyBatteryByActivity(activityId: number, enabled: boolean = true) {
  return useQuery({
    queryKey: analysisKeys.bodyBatteryByActivity(activityId),
    queryFn: () => analysisApi.getBodyBatteryByActivity(activityId),
    enabled,
    staleTime: 10 * 60 * 1000, // 10 minutter
  });
}















