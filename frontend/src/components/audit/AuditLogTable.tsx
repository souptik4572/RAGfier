'use client';

import { Fragment, useState } from 'react';
import { ChevronDown, ChevronRight, User, Bot } from 'lucide-react';
import type { AuditLogEntry } from '@/lib/api/audit';
import { cn } from '@/lib/utils';

interface AuditLogTableProps {
  logs: AuditLogEntry[];
}

function formatTimestamp(ts?: string | null): string {
  if (!ts) return '—';
  const d = new Date(ts);
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(d);
}

function actionTone(action: string): string {
  if (action.includes('fail') || action.includes('error') || action.includes('denied')) {
    return 'bg-red-100 text-red-700';
  }
  if (action.includes('created') || action.includes('success')) {
    return 'bg-[#10B981] text-white';
  }
  if (action.includes('revoked') || action.includes('deleted')) {
    return 'bg-[#F59E0B] text-white';
  }
  return 'bg-[#F3F4F6] text-[#111827]';
}

export function AuditLogTable({ logs }: AuditLogTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="bg-white rounded-lg overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse">
        <thead>
          <tr className="bg-[#111827] text-white">
            <th className="w-8 px-3 py-3" />
            <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
              Timestamp
            </th>
            <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
              Actor
            </th>
            <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
              Action
            </th>
            <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
              Resource
            </th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log, idx) => {
            const isOpen = expanded.has(log.id);
            const rowBg = idx % 2 === 0 ? 'bg-white' : 'bg-[#F9FAFB]';
            const hasMetadata = Object.keys(log.metadata ?? {}).length > 0;
            return (
              <Fragment key={log.id}>
                <tr
                  className={cn(
                    rowBg,
                    'transition-colors duration-150',
                    hasMetadata && 'cursor-pointer hover:bg-[#F3F4F6]'
                  )}
                  onClick={() => hasMetadata && toggle(log.id)}
                >
                  <td className="px-3 py-3 align-top">
                    {hasMetadata ? (
                      isOpen ? (
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-gray-400" />
                      )
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-sm text-[#111827] font-mono align-top whitespace-nowrap">
                    {formatTimestamp(log.created_at)}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <div className="flex items-center gap-2">
                      {log.actor_type === 'user' ? (
                        <User className="h-3.5 w-3.5 text-[#3B82F6]" />
                      ) : (
                        <Bot className="h-3.5 w-3.5 text-[#10B981]" />
                      )}
                      <div className="text-sm text-[#111827]">
                        <p className="font-semibold">{log.actor_type}</p>
                        {log.actor_id && (
                          <p className="text-xs text-gray-500 font-mono">
                            {log.actor_id.slice(0, 8)}…
                          </p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span
                      className={cn(
                        'inline-flex items-center rounded-md text-xs font-semibold px-2 py-0.5',
                        actionTone(log.action)
                      )}
                    >
                      {log.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-[#111827] align-top">
                    {log.resource_type ? (
                      <>
                        <p className="font-semibold">{log.resource_type}</p>
                        {log.resource_id && (
                          <p className="text-xs text-gray-500 font-mono">
                            {log.resource_id.slice(0, 8)}…
                          </p>
                        )}
                      </>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                </tr>
                {isOpen && hasMetadata && (
                  <tr className="bg-[#F3F4F6]">
                    <td />
                    <td colSpan={4} className="px-4 py-3">
                      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">
                        Metadata
                      </p>
                      <pre className="font-mono text-xs text-[#111827] bg-white rounded-md p-3 overflow-x-auto">
                        {JSON.stringify(log.metadata, null, 2)}
                      </pre>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
