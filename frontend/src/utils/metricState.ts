export type MetricStatus = 'loading' | 'ready' | 'missing' | 'error';

export interface MetricState<T> {
  status: MetricStatus;
  data: T | null;
  error: string | null;
}

export const initialMetricState = <T,>(): MetricState<T> => ({
  status: 'loading',
  data: null,
  error: null,
});

export type AsyncLoadState = 'loading' | 'ready' | 'missing' | 'error';

export interface AsyncLoadSurfaceProps {
  state: AsyncLoadState;
  error?: string | null;
  loadingMessage?: string;
  missingMessage?: string;
}

export function getAsyncLoadMessage({
  state,
  error,
  loadingMessage = 'Laster…',
  missingMessage = 'Ingen data tilgjengelig.',
}: AsyncLoadSurfaceProps): string | null {
  if (state === 'loading') {
    return loadingMessage;
  }
  if (state === 'missing') {
    return missingMessage;
  }
  if (state === 'error') {
    return error ?? 'En feil oppstod ved henting av data.';
  }
  return null;
}
