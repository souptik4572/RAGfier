'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Ban, Code2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  type ApiKey,
  type ApiKeyScope,
  type ApiKeyStatus,
  revokeApiKey,
} from '@/lib/api/api-keys';
import type { Integration } from '@/lib/api/integrations';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { CodeExampleDialog } from './CodeExampleDialog';
import { formatDate, cn } from '@/lib/utils';

interface ApiKeyTableProps {
  apiKeys: ApiKey[];
  integrations: Integration[];
}

const statusStyles: Record<ApiKeyStatus, string> = {
  active: 'bg-[#10B981] text-white',
  revoked: 'bg-red-100 text-red-700',
  expired: 'bg-[#F3F4F6] text-[#111827]',
};

const scopeStyles: Record<ApiKeyScope, string> = {
  'query:read': 'bg-[#3B82F6] text-white',
  'documents:read': 'bg-[#10B981] text-white',
  'documents:write': 'bg-[#F59E0B] text-white',
  'analytics:read': 'bg-[#F3F4F6] text-[#111827]',
};

export function ApiKeyTable({ apiKeys, integrations }: ApiKeyTableProps) {
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [targetKey, setTargetKey] = useState<ApiKey | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [codeOpen, setCodeOpen] = useState(false);
  const [codeKey, setCodeKey] = useState<ApiKey | null>(null);

  const integrationNameById = new Map(
    integrations.map((i) => [i.id, i.name])
  );

  const handleRevokeClick = (key: ApiKey) => {
    setTargetKey(key);
    setConfirmOpen(true);
  };

  const handleConfirmRevoke = async () => {
    if (!targetKey) return;
    setRevokingId(targetKey.id);
    try {
      await revokeApiKey(targetKey.id);
      await queryClient.invalidateQueries({ queryKey: ['api-keys'] });
      toast.success(`API key "${targetKey.name}" revoked`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to revoke';
      toast.error(message);
    } finally {
      setRevokingId(null);
      setTargetKey(null);
      setConfirmOpen(false);
    }
  };

  return (
    <>
      <div className="bg-white rounded-lg overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-[#111827] text-white">
              <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Name
              </th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Integration
              </th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Prefix
              </th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Scopes
              </th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Status
              </th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Last Used
              </th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Expires
              </th>
              <th className="text-right text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {apiKeys.map((key, idx) => {
              const isRevoked = key.status === 'revoked';
              return (
                <tr
                  key={key.id}
                  className={cn(
                    'transition-colors duration-150',
                    isRevoked
                      ? 'bg-[#F3F4F6]'
                      : idx % 2 === 0
                      ? 'bg-white'
                      : 'bg-[#F9FAFB]'
                  )}
                >
                  <td className="px-4 py-4 text-sm font-semibold text-[#111827]">
                    {key.name}
                  </td>
                  <td className="px-4 py-4 text-sm text-[#111827]">
                    {integrationNameById.get(key.integration_id) ?? (
                      <span className="text-gray-400 font-mono text-xs">
                        {key.integration_id.slice(0, 8)}…
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-4 text-sm font-mono text-[#111827]">
                    <span className={cn(isRevoked && 'line-through text-gray-400')}>
                      {key.prefix}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-1">
                      {key.scopes.map((scope) => (
                        <span
                          key={scope}
                          className={cn(
                            'rounded-md text-xs font-semibold px-2 py-0.5',
                            scopeStyles[scope] ?? 'bg-[#F3F4F6] text-[#111827]'
                          )}
                        >
                          {scope}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className={cn(
                        'rounded-md text-xs font-semibold uppercase tracking-wider px-2 py-1',
                        statusStyles[key.status] ??
                          'bg-[#F3F4F6] text-[#111827]'
                      )}
                    >
                      {key.status}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-sm text-gray-500">
                    {key.last_used_at ? formatDate(key.last_used_at) : '—'}
                  </td>
                  <td className="px-4 py-4 text-sm text-gray-500">
                    {key.expires_at ? formatDate(key.expires_at) : 'Never'}
                  </td>
                  <td className="px-4 py-4 text-right">
                    <div className="inline-flex items-center gap-1 justify-end">
                      <button
                        onClick={() => {
                          setCodeKey(key);
                          setCodeOpen(true);
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold text-[#3B82F6] hover:bg-blue-50 transition-colors duration-150"
                      >
                        <Code2 className="h-3.5 w-3.5" />
                        View code
                      </button>
                      {!isRevoked && (
                        <button
                          onClick={() => handleRevokeClick(key)}
                          disabled={revokingId === key.id}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold text-red-600 hover:bg-red-50 transition-colors duration-150 disabled:opacity-50"
                        >
                          <Ban className="h-3.5 w-3.5" />
                          Revoke
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Revoke API Key"
        description={`Revoke "${targetKey?.name}"? Applications using this key will stop working immediately. This action cannot be undone.`}
        onConfirm={handleConfirmRevoke}
        confirmLabel="Revoke"
        isDestructive
      />

      {codeKey && (
        <CodeExampleDialog
          open={codeOpen}
          onOpenChange={(open) => {
            setCodeOpen(open);
            if (!open) setCodeKey(null);
          }}
          integrationId={codeKey.integration_id}
          integrationName={
            integrationNameById.get(codeKey.integration_id) ?? 'integration'
          }
          keyName={codeKey.name}
          keyPrefix={codeKey.prefix}
        />
      )}
    </>
  );
}
