'use client';

import { useMemo, useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { ScrollText, Search } from 'lucide-react';
import { listAuditLogs } from '@/lib/api/audit';
import { getErrorMessage } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/shared/EmptyState';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { AuditLogTable } from '@/components/audit/AuditLogTable';

const PAGE_SIZES = [50, 100, 200, 500];

export default function AuditLogsPage() {
  const [pageSize, setPageSize] = useState(100);
  const [actionQuery, setActionQuery] = useState('');
  const [actorFilter, setActorFilter] = useState<string>('all');

  const { data: logs, isLoading, error, isFetching } = useQuery({
    queryKey: ['audit-logs', pageSize],
    queryFn: () => listAuditLogs({ limit: pageSize }),
    placeholderData: keepPreviousData,
  });

  const actorTypes = useMemo(() => {
    const types = new Set<string>();
    logs?.forEach((log) => types.add(log.actor_type));
    return Array.from(types);
  }, [logs]);

  const filtered = useMemo(() => {
    if (!logs) return [];
    return logs.filter((log) => {
      if (actorFilter !== 'all' && log.actor_type !== actorFilter) return false;
      if (actionQuery.trim()) {
        const q = actionQuery.trim().toLowerCase();
        if (!log.action.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [logs, actorFilter, actionQuery]);

  const actorOptions = [
    { value: 'all', label: 'All actors' },
    ...actorTypes.map((t) => ({ value: t, label: t })),
  ];

  const pageSizeOptions = PAGE_SIZES.map((n) => ({
    value: String(n),
    label: `${n} entries`,
  }));

  return (
    <div>
      <PageHeader
        title="Audit Logs"
        subtitle="Track all platform activity across your tenant"
      />

      <div className="bg-[#F3F4F6] rounded-lg p-4 mb-6 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-60">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input
            value={actionQuery}
            onChange={(e) => setActionQuery(e.target.value)}
            placeholder="Filter by action…"
            className="pl-9 bg-white"
          />
        </div>
        <div className="w-48">
          <Select
            value={actorFilter}
            onValueChange={setActorFilter}
            options={actorOptions}
            placeholder="All actors"
            className="bg-white"
          />
        </div>
        <div className="w-40">
          <Select
            value={String(pageSize)}
            onValueChange={(v) => setPageSize(Number(v))}
            options={pageSizeOptions}
            className="bg-white"
          />
        </div>
        {isFetching && !isLoading && (
          <span className="text-xs text-gray-400 ml-auto">Refreshing…</span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <LoadingBlock key={i} className="h-12 w-full bg-white rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <EmptyState
          icon={<ScrollText className="h-16 w-16 text-gray-400" />}
          title="Could not load audit logs"
          subtitle={getErrorMessage(error, 'Please try again.')}
        />
      ) : filtered.length > 0 ? (
        <AuditLogTable logs={filtered} />
      ) : logs && logs.length > 0 ? (
        <EmptyState
          icon={<ScrollText className="h-16 w-16 text-gray-400" />}
          title="No matches"
          subtitle="Try adjusting the filter or actor type."
        />
      ) : (
        <EmptyState
          icon={<ScrollText className="h-16 w-16 text-gray-400" />}
          title="No audit logs yet"
          subtitle="Activity across integrations, API keys, and queries appears here."
        />
      )}
    </div>
  );
}
