'use client';

import { useMemo, useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import {
  BarChart3,
  Activity,
  AlertTriangle,
  Zap,
  Clock,
  CircleDollarSign,
} from 'lucide-react';
import { listUsage, type UsageBucket } from '@/lib/api/usage';
import { cn, getErrorMessage } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/shared/EmptyState';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { Select } from '@/components/ui/select';

const WINDOW_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '14', label: 'Last 14 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '60', label: 'Last 60 days' },
  { value: '90', label: 'Last 90 days' },
];

// Rough cost estimate consistent with backend: $0.0002 per 1K tokens
const COST_PER_1K_TOKENS = 0.0002;

function formatInt(n: number): string {
  return new Intl.NumberFormat('en-US').format(n);
}

function formatCurrency(n: number): string {
  return `$${n.toFixed(4)}`;
}

function formatDay(ts?: string | null): string {
  if (!ts) return '—';
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  }).format(new Date(ts));
}

function SummaryStat({
  icon,
  label,
  value,
  tone = 'primary',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: 'primary' | 'secondary' | 'accent' | 'muted';
}) {
  const toneClasses = {
    primary: 'bg-[#3B82F6] text-white',
    secondary: 'bg-[#10B981] text-white',
    accent: 'bg-[#F59E0B] text-white',
    muted: 'bg-[#F3F4F6] text-[#111827]',
  }[tone];

  return (
    <div className={cn('rounded-lg p-5', toneClasses)}>
      <div className="flex items-center gap-2 mb-2 opacity-90">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wider">
          {label}
        </span>
      </div>
      <p className="text-2xl font-extrabold tracking-tight">{value}</p>
    </div>
  );
}

export default function UsagePage() {
  const [days, setDays] = useState(30);

  const { data: buckets, isLoading, error, isFetching } = useQuery({
    queryKey: ['usage', days],
    queryFn: () => listUsage({ days }),
    placeholderData: keepPreviousData,
  });

  const totals = useMemo(() => {
    if (!buckets || buckets.length === 0) {
      return {
        requests: 0,
        success: 0,
        errors: 0,
        inputTokens: 0,
        outputTokens: 0,
        totalTokens: 0,
        cost: 0,
        avgLatency: 0,
      };
    }
    const sums = buckets.reduce(
      (acc, b) => {
        acc.requests += b.request_count;
        acc.success += b.success_count;
        acc.errors += b.error_count;
        acc.inputTokens += b.total_input_tokens;
        acc.outputTokens += b.total_output_tokens;
        acc.latencySum += b.avg_latency_ms * b.request_count;
        return acc;
      },
      {
        requests: 0,
        success: 0,
        errors: 0,
        inputTokens: 0,
        outputTokens: 0,
        latencySum: 0,
      }
    );
    const totalTokens = sums.inputTokens + sums.outputTokens;
    return {
      requests: sums.requests,
      success: sums.success,
      errors: sums.errors,
      inputTokens: sums.inputTokens,
      outputTokens: sums.outputTokens,
      totalTokens,
      cost: Number(((totalTokens / 1000) * COST_PER_1K_TOKENS).toFixed(6)),
      avgLatency: sums.requests > 0 ? sums.latencySum / sums.requests : 0,
    };
  }, [buckets]);

  const sortedBuckets: UsageBucket[] = useMemo(() => {
    if (!buckets) return [];
    return [...buckets].sort((a, b) => {
      const aT = a.window_start ? new Date(a.window_start).getTime() : 0;
      const bT = b.window_start ? new Date(b.window_start).getTime() : 0;
      return bT - aT;
    });
  }, [buckets]);

  return (
    <div>
      <PageHeader
        title="Usage"
        subtitle="Requests, tokens, and latency across your tenant"
      />

      <div className="bg-[#F3F4F6] rounded-lg p-4 mb-6 flex items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Window
        </span>
        <div className="w-48">
          <Select
            value={String(days)}
            onValueChange={(v) => setDays(Number(v))}
            options={WINDOW_OPTIONS}
            className="bg-white"
          />
        </div>
        {isFetching && !isLoading && (
          <span className="text-xs text-gray-400 ml-auto">Refreshing…</span>
        )}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {[1, 2, 3, 4].map((i) => (
            <LoadingBlock key={i} className="h-24 w-full bg-white rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <EmptyState
          icon={<BarChart3 className="h-16 w-16 text-gray-400" />}
          title="Could not load usage"
          subtitle={getErrorMessage(error, 'Please try again.')}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <SummaryStat
              icon={<Activity className="h-4 w-4" />}
              label="Total requests"
              value={formatInt(totals.requests)}
              tone="primary"
            />
            <SummaryStat
              icon={<Zap className="h-4 w-4" />}
              label="Total tokens"
              value={formatInt(totals.totalTokens)}
              tone="secondary"
            />
            <SummaryStat
              icon={<CircleDollarSign className="h-4 w-4" />}
              label="Estimated cost"
              value={formatCurrency(totals.cost)}
              tone="accent"
            />
            <SummaryStat
              icon={<Clock className="h-4 w-4" />}
              label="Avg latency"
              value={`${Math.round(totals.avgLatency)} ms`}
              tone="muted"
            />
          </div>

          {totals.errors > 0 && (
            <div className="bg-[#FEF3C7] border-2 border-[#F59E0B] rounded-lg p-4 mb-6 flex items-center gap-3">
              <AlertTriangle className="h-5 w-5 text-[#F59E0B] shrink-0" />
              <p className="text-sm text-[#111827]">
                <span className="font-bold">
                  {formatInt(totals.errors)}
                </span>{' '}
                failed request{totals.errors === 1 ? '' : 's'} in this window.
              </p>
            </div>
          )}

          {sortedBuckets.length === 0 ? (
            <EmptyState
              icon={<BarChart3 className="h-16 w-16 text-gray-400" />}
              title="No usage data"
              subtitle="No requests recorded in this window yet."
            />
          ) : (
            <div className="bg-white rounded-lg overflow-hidden">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-[#111827] text-white">
                    <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                      Day
                    </th>
                    <th className="text-right text-xs font-semibold uppercase tracking-wider px-4 py-3">
                      Requests
                    </th>
                    <th className="text-right text-xs font-semibold uppercase tracking-wider px-4 py-3">
                      Success
                    </th>
                    <th className="text-right text-xs font-semibold uppercase tracking-wider px-4 py-3">
                      Errors
                    </th>
                    <th className="text-right text-xs font-semibold uppercase tracking-wider px-4 py-3">
                      Input tokens
                    </th>
                    <th className="text-right text-xs font-semibold uppercase tracking-wider px-4 py-3">
                      Output tokens
                    </th>
                    <th className="text-right text-xs font-semibold uppercase tracking-wider px-4 py-3">
                      Avg latency
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedBuckets.map((b, idx) => (
                    <tr
                      key={b.window_start ?? idx}
                      className={idx % 2 === 0 ? 'bg-white' : 'bg-[#F9FAFB]'}
                    >
                      <td className="px-4 py-3 text-sm font-semibold text-[#111827]">
                        {formatDay(b.window_start)}
                      </td>
                      <td className="px-4 py-3 text-sm text-[#111827] text-right font-mono">
                        {formatInt(b.request_count)}
                      </td>
                      <td className="px-4 py-3 text-sm text-[#10B981] text-right font-mono">
                        {formatInt(b.success_count)}
                      </td>
                      <td
                        className={cn(
                          'px-4 py-3 text-sm text-right font-mono',
                          b.error_count > 0 ? 'text-red-500' : 'text-gray-400'
                        )}
                      >
                        {formatInt(b.error_count)}
                      </td>
                      <td className="px-4 py-3 text-sm text-[#111827] text-right font-mono">
                        {formatInt(b.total_input_tokens)}
                      </td>
                      <td className="px-4 py-3 text-sm text-[#111827] text-right font-mono">
                        {formatInt(b.total_output_tokens)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 text-right font-mono">
                        {Math.round(b.avg_latency_ms)} ms
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
