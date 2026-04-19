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
import { formatDate, cn, getErrorMessage } from '@/lib/utils';

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
      toast.error(getErrorMessage(err, 'Failed to revoke'));
    } finally {
      setRevokingId(null);
      setTargetKey(null);
      setConfirmOpen(false);
    }
  };

  return (
    <>
      {/* Mobile card view */}
      <div className="md:hidden space-y-3">
        {apiKeys.map((key) => {
          const isRevoked = key.status === 'revoked';
          return (
            <div
              key={key.id}
              className={cn(
                'rounded-lg p-4 space-y-3',
                isRevoked ? 'bg-[#F3F4F6]' : 'bg-white'
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-bold text-[#111827] truncate">
                    {key.name}
                  </p>
                  <p className="text-xs text-gray-500 truncate mt-0.5">
                    {integrationNameById.get(key.integration_id) ?? (
                      <span className="font-mono">
                        {key.integration_id.slice(0, 8)}…
                      </span>
                    )}
                  </p>
                </div>
                <span
                  className={cn(
                    'shrink-0 rounded-md text-xs font-semibold uppercase tracking-wider px-2 py-1',
                    statusStyles[key.status] ?? 'bg-[#F3F4F6] text-[#111827]'
                  )}
                >
                  {key.status}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                <div>
                  <p className="font-semibold uppercase tracking-wider text-gray-400 mb-0.5">
                    Prefix
                  </p>
                  <p
                    className={cn(
                      'font-mono text-[#111827]',
                      isRevoked && 'line-through text-gray-400'
                    )}
                  >
                    {key.prefix}
                  </p>
                </div>
                <div>
                  <p className="font-semibold uppercase tracking-wider text-gray-400 mb-0.5">
                    Expires
                  </p>
                  <p className="text-gray-500">
                    {key.expires_at ? formatDate(key.expires_at) : 'Never'}
                  </p>
                </div>
                <div className="col-span-2">
                  <p className="font-semibold uppercase tracking-wider text-gray-400 mb-1">
                    Last used
                  </p>
                  <p className="text-gray-500">
                    {key.last_used_at ? formatDate(key.last_used_at) : '—'}
                  </p>
                </div>
              </div>

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

              <div className="flex items-center gap-2 pt-1 border-t border-[#E5E7EB]">
                <button
                  onClick={() => {
                    setCodeKey(key);
                    setCodeOpen(true);
                  }}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-xs font-semibold text-[#3B82F6] hover:bg-blue-50 transition-colors duration-150"
                >
                  <Code2 className="h-3.5 w-3.5" />
                  View code
                </button>
                {!isRevoked && (
                  <button
                    onClick={() => handleRevokeClick(key)}
                    disabled={revokingId === key.id}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-xs font-semibold text-red-600 hover:bg-red-50 transition-colors duration-150 disabled:opacity-50"
                  >
                    <Ban className="h-3.5 w-3.5" />
                    Revoke
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Tablet/Desktop table */}
      <div className="hidden md:block bg-white rounded-lg overflow-x-auto">
        <table className="w-full min-w-[900px] border-collapse">
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
              <th className="hidden lg:table-cell text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
                Last Used
              </th>
              <th className="hidden lg:table-cell text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
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
                  <td className="hidden lg:table-cell px-4 py-4 text-sm text-gray-500">
                    {key.last_used_at ? formatDate(key.last_used_at) : '—'}
                  </td>
                  <td className="hidden lg:table-cell px-4 py-4 text-sm text-gray-500">
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
