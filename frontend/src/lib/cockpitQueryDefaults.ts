/** Shared React Query defaults for cockpit dashboard hooks. */

export const COCKPIT_QUERY_DEFAULTS = {
  staleTime: 60_000,
  retry: 1,
  refetchOnWindowFocus: false,
} as const;

export const COCKPIT_DELTA_STALE_MS = 30_000;
