'use client';

import StoreProvider from './StoreProvider';
import QueryProvider from './QueryProvider';

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <StoreProvider>
      <QueryProvider>{children}</QueryProvider>
    </StoreProvider>
  );
}
