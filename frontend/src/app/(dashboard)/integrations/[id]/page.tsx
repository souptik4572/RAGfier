'use client';

import { use, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { getIntegration } from '@/lib/api/integrations';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { formatDate } from '@/lib/utils';
import { FileText, Play, Calendar, Tag, Pencil, Trash2, Sparkles } from 'lucide-react';
import { EditIntegrationDialog } from '@/components/integrations/EditIntegrationDialog';
import { DeleteIntegrationDialog } from '@/components/integrations/DeleteIntegrationDialog';

interface IntegrationDetailPageProps {
  params: Promise<{ id: string }>;
}

export default function IntegrationDetailPage({
  params,
}: IntegrationDetailPageProps) {
  const { id } = use(params);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const { data: integration, isLoading } = useQuery({
    queryKey: ['integration', id],
    queryFn: () => getIntegration(id),
  });

  if (isLoading) {
    return (
      <div>
        <LoadingBlock className="h-10 w-64 bg-white rounded-lg mb-8" />
        <div className="bg-white rounded-lg p-8 space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <LoadingBlock key={i} className="h-8 w-full bg-[#F3F4F6] rounded-md" />
          ))}
        </div>
      </div>
    );
  }

  if (!integration) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500 text-lg">Integration not found.</p>
      </div>
    );
  }

  const environmentBadgeVariant: Record<
    typeof integration.environment,
    'primary' | 'secondary' | 'accent'
  > = {
    production: 'primary',
    staging: 'accent',
    development: 'secondary',
  };

  return (
    <div>
      <PageHeader
        title={integration.name}
        subtitle="Integration details and configuration"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Details Card */}
        <div className="lg:col-span-2 bg-white rounded-lg p-8">
          <h2 className="text-lg font-bold text-[#111827] mb-6">Details</h2>
          <dl className="space-y-5">
            <div className="flex items-center gap-4">
              <dt className="w-32 text-sm font-semibold text-gray-500 flex items-center gap-2">
                <Tag className="h-4 w-4" />
                Name
              </dt>
              <dd className="text-sm font-medium text-[#111827]">
                {integration.name}
              </dd>
            </div>

            <div className="flex items-center gap-4">
              <dt className="w-32 text-sm font-semibold text-gray-500">
                Environment
              </dt>
              <dd>
                <Badge
                  variant={environmentBadgeVariant[integration.environment]}
                >
                  {integration.environment}
                </Badge>
              </dd>
            </div>

            {integration.is_default && (
              <div className="flex items-center gap-4">
                <dt className="w-32 text-sm font-semibold text-gray-500">
                  Type
                </dt>
                <dd>
                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-100 text-emerald-700">
                    Default
                  </span>
                </dd>
              </div>
            )}

            <div className="flex items-center gap-4">
              <dt className="w-32 text-sm font-semibold text-gray-500 flex items-center gap-2">
                <Sparkles className="h-4 w-4" />
                Prompt
              </dt>
              <dd className="text-sm font-mono text-[#111827]">
                {integration.prompt_name ?? '—'}
              </dd>
            </div>

            <div className="flex items-center gap-4">
              <dt className="w-32 text-sm font-semibold text-gray-500 flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                Created
              </dt>
              <dd className="text-sm text-gray-500">
                {formatDate(integration.created_at)}
              </dd>
            </div>

            <div className="flex items-center gap-4">
              <dt className="w-32 text-sm font-semibold text-gray-500">
                Updated
              </dt>
              <dd className="text-sm text-gray-500">
                {formatDate(integration.updated_at)}
              </dd>
            </div>

            {integration.metadata && Object.keys(integration.metadata).length > 0 && (
              <div className="flex gap-4">
                <dt className="w-32 text-sm font-semibold text-gray-500">
                  Metadata
                </dt>
                <dd className="text-sm text-gray-500 flex-1 font-mono break-all">
                  {JSON.stringify(integration.metadata)}
                </dd>
              </div>
            )}
          </dl>
        </div>

        {/* Actions Card */}
        <div className="bg-white rounded-lg p-8">
          <h2 className="text-lg font-bold text-[#111827] mb-6">Actions</h2>
          <div className="flex flex-col gap-4">
            <Link
              href={`/integrations/${integration.id}/documents`}
              className="block"
            >
              <Button
                variant="primary"
                className="w-full flex items-center gap-2 h-12"
              >
                <FileText className="h-4 w-4" />
                View Documents
              </Button>
            </Link>
            <Link
              href={`/integrations/${integration.id}/playground`}
              className="block"
            >
              <Button
                variant="outline"
                className="w-full flex items-center gap-2 h-12"
              >
                <Play className="h-4 w-4" />
                Open Playground
              </Button>
            </Link>

            <div className="h-px bg-[#F3F4F6] my-2" />

            <Button
              variant="secondary"
              onClick={() => setEditOpen(true)}
              className="w-full flex items-center gap-2 h-12"
            >
              <Pencil className="h-4 w-4" />
              Edit Integration
            </Button>
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(true)}
              className="w-full flex items-center gap-2 h-12 border-red-300 text-red-600 hover:bg-red-50"
            >
              <Trash2 className="h-4 w-4" />
              Delete Integration
            </Button>
          </div>
        </div>
      </div>

      <EditIntegrationDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        integration={integration}
      />
      <DeleteIntegrationDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        integration={integration}
      />
    </div>
  );
}
