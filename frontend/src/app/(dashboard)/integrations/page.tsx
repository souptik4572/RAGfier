'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listIntegrations } from '@/lib/api/integrations';
import { PageHeader } from '@/components/layout/PageHeader';
import { IntegrationCard } from '@/components/integrations/IntegrationCard';
import { CreateIntegrationDialog } from '@/components/integrations/CreateIntegrationDialog';
import { EmptyState } from '@/components/shared/EmptyState';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { Button } from '@/components/ui/button';
import { Layers, Plus } from 'lucide-react';

export default function IntegrationsPage() {
  const [createOpen, setCreateOpen] = useState(false);

  const { data: integrations, isLoading } = useQuery({
    queryKey: ['integrations'],
    queryFn: listIntegrations,
  });

  return (
    <div>
      <PageHeader
        title="Integrations"
        subtitle="Manage your RAG integrations and document pipelines"
        action={
          <Button
            variant="primary"
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            New Integration
          </Button>
        }
      />

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-56 w-full bg-white rounded-lg" />
          ))}
        </div>
      ) : integrations && integrations.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {integrations.map((integration) => (
            <IntegrationCard key={integration.id} integration={integration} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Layers className="h-16 w-16 text-gray-400" />}
          title="No integrations yet"
          subtitle="Create your first integration to start ingesting documents into your RAG pipeline."
          action={
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              Create Integration
            </Button>
          }
        />
      )}

      <CreateIntegrationDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
    </div>
  );
}
