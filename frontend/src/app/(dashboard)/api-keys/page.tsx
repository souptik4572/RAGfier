'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Key, Plus } from 'lucide-react';
import { listApiKeys, type ApiKeyWithSecret } from '@/lib/api/api-keys';
import { listIntegrations } from '@/lib/api/integrations';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/shared/EmptyState';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { ApiKeyTable } from '@/components/api-keys/ApiKeyTable';
import { CreateApiKeyDialog } from '@/components/api-keys/CreateApiKeyDialog';
import { SecretRevealBanner } from '@/components/api-keys/SecretRevealBanner';

export default function ApiKeysPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [revealedKey, setRevealedKey] = useState<ApiKeyWithSecret | null>(null);

  const { data: apiKeys, isLoading: keysLoading } = useQuery({
    queryKey: ['api-keys'],
    queryFn: listApiKeys,
  });

  const { data: integrations, isLoading: integrationsLoading } = useQuery({
    queryKey: ['integrations'],
    queryFn: listIntegrations,
  });

  const isLoading = keysLoading || integrationsLoading;

  return (
    <div>
      <PageHeader
        title="API Keys"
        subtitle="Create and manage API keys for programmatic access"
        action={
          <Button
            variant="primary"
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Create API Key
          </Button>
        }
      />

      {revealedKey && (
        <SecretRevealBanner
          secret={revealedKey.secret}
          prefix={revealedKey.prefix}
          onDismiss={() => setRevealedKey(null)}
        />
      )}

      {isLoading ? (
        <div className="space-y-3">
          <LoadingBlock className="h-12 w-full bg-white rounded-lg" />
          {[1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-14 w-full bg-white rounded-lg" />
          ))}
        </div>
      ) : apiKeys && apiKeys.length > 0 ? (
        <ApiKeyTable
          apiKeys={apiKeys}
          integrations={integrations ?? []}
        />
      ) : (
        <EmptyState
          icon={<Key className="h-16 w-16 text-gray-400" />}
          title="No API keys yet"
          subtitle="Create your first API key to start making programmatic queries against your RAG integrations."
          action={
            <Button
              variant="primary"
              onClick={() => setCreateOpen(true)}
              disabled={!integrations || integrations.length === 0}
            >
              Create API Key
            </Button>
          }
        />
      )}

      <CreateApiKeyDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        integrations={integrations ?? []}
        onCreated={setRevealedKey}
      />
    </div>
  );
}
