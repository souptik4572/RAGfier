'use client';

import { useQuery } from '@tanstack/react-query';
import { getHealth } from '@/lib/api/health';
import { listIntegrations, countIntegrations } from '@/lib/api/integrations';
import { countApiKeys } from '@/lib/api/api-keys';
import { countEvalRuns } from '@/lib/api/eval';
import { PageHeader } from '@/components/layout/PageHeader';
import { StatusDot } from '@/components/shared/StatusDot';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { formatDate } from '@/lib/utils';
import { Layers } from 'lucide-react';
import Link from 'next/link';

export default function DashboardPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
  });

  const { data: integrations, isLoading: integrationsLoading } = useQuery({
    queryKey: ['integrations'],
    queryFn: listIntegrations,
  });

  const { data: integrationCountData, isLoading: integrationCountLoading } =
    useQuery({
      queryKey: ['integrations', 'count'],
      queryFn: countIntegrations,
    });

  const { data: apiKeyCount, isLoading: apiKeyCountLoading } = useQuery({
    queryKey: ['api-keys', 'count'],
    queryFn: countApiKeys,
  });

  const { data: evalRunCount, isLoading: evalRunCountLoading } = useQuery({
    queryKey: ['eval-runs', 'count'],
    queryFn: countEvalRuns,
  });

  const integrationCount = integrationCountData ?? integrations?.length ?? 0;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Overview of your RAGfier platform"
      />

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6 mb-10">
        {/* Integrations */}
        <Link
          href="/integrations"
          className="bg-[#3B82F6] rounded-lg p-6 text-white hover:scale-[1.02] transition-all duration-200 block"
        >
          {integrationsLoading || integrationCountLoading ? (
            <LoadingBlock className="h-12 w-20 bg-white/30 rounded-md mb-2" />
          ) : (
            <p className="text-5xl font-extrabold">{integrationCount}</p>
          )}
          <p className="mt-2 text-base font-semibold text-white/80">
            Integrations
          </p>
        </Link>

        {/* API Keys */}
        <Link
          href="/api-keys"
          className="bg-[#10B981] rounded-lg p-6 text-white hover:scale-[1.02] transition-all duration-200 block"
        >
          {apiKeyCountLoading ? (
            <LoadingBlock className="h-12 w-20 bg-white/30 rounded-md mb-2" />
          ) : (
            <p className="text-5xl font-extrabold">{apiKeyCount ?? 0}</p>
          )}
          <p className="mt-2 text-base font-semibold text-white/80">API Keys</p>
        </Link>

        {/* Eval Runs */}
        <Link
          href="/eval"
          className="bg-[#F59E0B] rounded-lg p-6 text-[#111827] hover:scale-[1.02] transition-all duration-200 block"
        >
          {evalRunCountLoading ? (
            <LoadingBlock className="h-12 w-20 bg-[#111827]/20 rounded-md mb-2" />
          ) : (
            <p className="text-5xl font-extrabold">{evalRunCount ?? 0}</p>
          )}
          <p className="mt-2 text-base font-semibold text-[#111827]/70">
            Eval Runs
          </p>
        </Link>

        {/* System Health */}
        <div className="bg-white rounded-lg p-6 hover:scale-[1.02] transition-all duration-200">
          {healthLoading ? (
            <LoadingBlock className="h-12 w-20 bg-[#F3F4F6] rounded-md mb-2" />
          ) : (
            <div className="flex items-center gap-3">
              <StatusDot
                status={
                  health?.status === 'ok'
                    ? 'up'
                    : health?.status === 'down'
                    ? 'down'
                    : 'unknown'
                }
              />
              <p className="text-2xl font-extrabold text-[#111827] capitalize">
                {health?.status ?? 'Unknown'}
              </p>
            </div>
          )}
          <p className="mt-2 text-base font-semibold text-gray-500">
            System Health
          </p>
        </div>
      </div>

      {/* Recent Integrations */}
      <div>
        <h2 className="text-xl font-bold text-[#111827] mb-4">
          Recent Integrations
        </h2>
        {integrationsLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <LoadingBlock
                key={i}
                className="h-16 w-full bg-white rounded-lg"
              />
            ))}
          </div>
        ) : integrations && integrations.length > 0 ? (
          <div className="bg-white rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="bg-[#111827]">
                  <th className="text-left px-6 py-3 text-sm font-semibold text-white">
                    Name
                  </th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-white">
                    Environment
                  </th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-white">
                    Created
                  </th>
                  <th className="text-right px-6 py-3 text-sm font-semibold text-white">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {integrations.slice(0, 5).map((integration, idx) => (
                  <tr
                    key={integration.id}
                    className={idx % 2 === 1 ? 'bg-[#F3F4F6]' : 'bg-white'}
                  >
                    <td className="px-6 py-4 text-sm font-semibold text-[#111827]">
                      <div className="flex items-center gap-2">
                        <Layers className="h-4 w-4 text-[#3B82F6]" />
                        {integration.name}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-xs font-semibold uppercase tracking-wider px-2 py-1 rounded-md bg-[#F3F4F6] text-[#111827]">
                        {integration.environment}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {formatDate(integration.created_at)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        href={`/integrations/${integration.id}/documents`}
                        className="text-sm font-semibold text-[#3B82F6] hover:underline"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="bg-white rounded-lg p-12 text-center">
            <p className="text-gray-500">
              No integrations yet.{' '}
              <Link
                href="/integrations"
                className="text-[#3B82F6] font-semibold hover:underline"
              >
                Create one
              </Link>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
