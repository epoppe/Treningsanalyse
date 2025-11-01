import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { activitiesApi } from '../utils/api';
import { Activity } from '../types';

// Query keys for activities
export const activitiesKeys = {
  all: ['activities'] as const,
  lists: () => [...activitiesKeys.all, 'list'] as const,
  list: (filters: Record<string, any>) => [...activitiesKeys.lists(), filters] as const,
  details: () => [...activitiesKeys.all, 'detail'] as const,
  detail: (id: string) => [...activitiesKeys.details(), id] as const,
  count: () => [...activitiesKeys.all, 'count'] as const,
};

// Hook for fetching all activities with pagination
export function useActivities(limit: number = 100, offset: number = 0) {
  return useQuery({
    queryKey: activitiesKeys.list({ limit, offset }),
    queryFn: async () => {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/activities?limit=${limit}&offset=${offset}`);
      if (!response.ok) throw new Error('Failed to fetch activities');
      return response.json() as Promise<Activity[]>;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (formerly cacheTime)
  });
}

// Hook for infinite scrolling activities
export function useInfiniteActivities(pageSize: number = 100) {
  return useInfiniteQuery({
    queryKey: activitiesKeys.lists(),
    queryFn: async ({ pageParam = 0 }) => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/activities?limit=${pageSize}&offset=${pageParam}`
      );
      if (!response.ok) throw new Error('Failed to fetch activities');
      const data = await response.json() as Activity[];
      return {
        data,
        nextOffset: data.length === pageSize ? pageParam + pageSize : undefined,
      };
    },
    getNextPageParam: (lastPage) => lastPage.nextOffset,
    initialPageParam: 0,
    staleTime: 5 * 60 * 1000,
  });
}

// Hook for fetching activity count
export function useActivityCount() {
  return useQuery({
    queryKey: activitiesKeys.count(),
    queryFn: async () => {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/activities/count`);
      if (!response.ok) throw new Error('Failed to fetch activity count');
      const data = await response.json();
      return data.count as number;
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

// Hook for fetching single activity by ID
export function useActivity(id: string, enabled: boolean = true) {
  return useQuery({
    queryKey: activitiesKeys.detail(id),
    queryFn: async () => {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/activities/${id}`);
      if (!response.ok) throw new Error('Failed to fetch activity');
      return response.json() as Promise<Activity>;
    },
    enabled: enabled && !!id,
    staleTime: 10 * 60 * 1000,
  });
}

// Hook for fetching new activities since a date
export function useNewActivities(sinceDate: string | null, enabled: boolean = true) {
  return useQuery({
    queryKey: [...activitiesKeys.lists(), 'since', sinceDate],
    queryFn: async () => {
      if (!sinceDate) return [];
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/activities?since=${sinceDate}&limit=100`
      );
      if (!response.ok) throw new Error('Failed to fetch new activities');
      return response.json() as Promise<Activity[]>;
    },
    enabled: enabled && !!sinceDate,
    staleTime: 1 * 60 * 1000, // 1 minute (more frequent for new data)
  });
}

// Mutation for syncing activities
export function useSyncActivities() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async () => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/sync/garmin`,
        { method: 'POST' }
      );
      if (!response.ok) throw new Error('Failed to sync activities');
      return response.json();
    },
    onSuccess: () => {
      // Invalidate all activities queries to refetch
      queryClient.invalidateQueries({ queryKey: activitiesKeys.all });
    },
  });
}

// Helper hook for filtering activities client-side
export function useFilteredActivities(
  activities: Activity[],
  selectedTypes: string[],
  timeFilter: 'all' | '12months' | '3months'
) {
  const now = new Date();
  
  let filtered = activities;
  
  // Filter by activity types
  if (selectedTypes.length > 0) {
    filtered = filtered.filter(activity => 
      selectedTypes.includes(activity.activityType?.typeKey || '')
    );
  }
  
  // Filter by time
  switch (timeFilter) {
    case '12months':
      const twelveMonthsAgo = new Date();
      twelveMonthsAgo.setMonth(now.getMonth() - 12);
      filtered = filtered.filter(activity => 
        new Date(activity.startTimeLocal) >= twelveMonthsAgo
      );
      break;
    
    case '3months':
      const threeMonthsAgo = new Date();
      threeMonthsAgo.setMonth(now.getMonth() - 3);
      filtered = filtered.filter(activity => 
        new Date(activity.startTimeLocal) >= threeMonthsAgo
      );
      break;
  }
  
  return filtered;
}
