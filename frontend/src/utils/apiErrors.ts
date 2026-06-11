import type { AxiosError } from 'axios';

export type ApiErrorKind = 'not_found' | 'server' | 'network' | 'unknown';

export function classifyApiError(error: unknown): ApiErrorKind {
  const axiosError = error as AxiosError | undefined;
  const status = axiosError?.response?.status;

  if (status === 404) {
    return 'not_found';
  }
  if (status != null && status >= 500) {
    return 'server';
  }
  if (!axiosError?.response) {
    return 'network';
  }
  return 'unknown';
}

export function apiErrorMessage(error: unknown, fallback = 'Ukjent API-feil'): string {
  const kind = classifyApiError(error);
  if (kind === 'not_found') {
    return 'Ingen data';
  }
  if (kind === 'server') {
    return 'Serverfeil ved henting av data';
  }
  if (kind === 'network') {
    return 'Kunne ikke nå API-et';
  }

  const axiosError = error as AxiosError<{ detail?: string }> | undefined;
  const detail = axiosError?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  return fallback;
}
