'use client';

import { QueryClient, QueryClientProvider, QueryCache } from '@tanstack/react-query';
import { useState } from 'react';
import { Toaster, toast } from 'sonner';
import { getErrorMessage } from '@/lib/utils';

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error, query) => {
            // Only toast for background refetch failures when data already exists.
            // Initial-load errors are handled inline per-page.
            if (query.state.data !== undefined) {
              toast.error(getErrorMessage(error, 'Failed to refresh data'));
            }
          },
        }),
        defaultOptions: {
          queries: {
            staleTime: 30_000,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster richColors position="top-right" />
    </QueryClientProvider>
  );
}
