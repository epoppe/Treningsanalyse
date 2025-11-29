'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useState } from 'react';

/**
 * Client Component wrapper for React Query
 * Må være en Client Component for å bruke QueryClient i Next.js App Router
 */
export default function QueryProvider({ children }: { children: React.ReactNode }) {
  // Opprett QueryClient i useState for å sikre at den kun opprettes én gang per request
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        // Data er "fresh" i 5 minutter - ingen refetch i denne perioden
        staleTime: 5 * 60 * 1000,
        
        // Data beholdes i cache i 10 minutter etter siste bruk
        gcTime: 10 * 60 * 1000,
        
        // Ikke refetch automatisk når vinduet får fokus
        refetchOnWindowFocus: false,
        
        // Retry failed requests 1 gang
        retry: 1,
        
        // Refetch on mount hvis data er eldre enn staleTime
        refetchOnMount: true,
        
        // Ikke refetch automatisk på reconnect
        refetchOnReconnect: false,
      },
      mutations: {
        retry: 0,
      },
    },
  }));

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
















