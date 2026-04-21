'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getJobStatus } from '@/lib/api/documents';

export function useJobPoller(jobId: string | null, integrationId: string) {
  const queryClient = useQueryClient();

  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'completed' || status === 'failed') {
        queryClient.invalidateQueries({
          queryKey: ['documents', integrationId],
        });
        return false;
      }
      return 2000;
    },
  });
}
