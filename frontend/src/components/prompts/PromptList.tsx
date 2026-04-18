'use client';

import { Globe, CheckCircle2 } from 'lucide-react';
import type { PromptSummary } from '@/lib/api/prompts';
import { cn } from '@/lib/utils';

interface PromptListProps {
  prompts: PromptSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function formatDate(ts?: string | null): string {
  if (!ts) return '—';
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(ts));
}

export function PromptList({ prompts, selectedId, onSelect }: PromptListProps) {
  const grouped = prompts.reduce<Record<string, PromptSummary[]>>((acc, p) => {
    (acc[p.name] ??= []).push(p);
    return acc;
  }, {});

  Object.values(grouped).forEach((versions) =>
    versions.sort((a, b) => b.version - a.version)
  );

  const groupNames = Object.keys(grouped).sort();

  return (
    <div className="space-y-5">
      {groupNames.map((name) => (
        <div key={name}>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 px-1 mb-2">
            {name}
          </p>
          <div className="space-y-1.5">
            {grouped[name].map((p) => {
              const isSelected = p.id === selectedId;
              const isGlobal = !p.tenant_id;
              return (
                <button
                  key={p.id}
                  onClick={() => onSelect(p.id)}
                  className={cn(
                    'w-full text-left rounded-lg p-3 transition-colors duration-150',
                    isSelected
                      ? 'bg-[#111827] text-white'
                      : 'bg-white text-[#111827] hover:bg-[#F3F4F6]'
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-bold">v{p.version}</span>
                    <div className="flex items-center gap-1.5">
                      {isGlobal && (
                        <span
                          className={cn(
                            'inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded',
                            isSelected
                              ? 'bg-white/20 text-white'
                              : 'bg-[#F3F4F6] text-gray-600'
                          )}
                        >
                          <Globe className="h-2.5 w-2.5" />
                          Global
                        </span>
                      )}
                      {p.is_active && (
                        <span
                          className={cn(
                            'inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded',
                            isSelected
                              ? 'bg-[#10B981] text-white'
                              : 'bg-[#10B981] text-white'
                          )}
                        >
                          <CheckCircle2 className="h-2.5 w-2.5" />
                          Active
                        </span>
                      )}
                    </div>
                  </div>
                  <p
                    className={cn(
                      'text-xs font-mono',
                      isSelected ? 'text-gray-300' : 'text-gray-500'
                    )}
                  >
                    {formatDate(p.created_at)}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
