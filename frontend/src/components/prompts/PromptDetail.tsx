'use client';

import { Globe, CheckCircle2 } from 'lucide-react';
import type { PromptSummary } from '@/lib/api/prompts';
import { CopyButton } from '@/components/shared/CopyButton';

interface PromptDetailProps {
  prompt: PromptSummary;
}

function formatTimestamp(ts?: string | null): string {
  if (!ts) return '—';
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(ts));
}

function Section({
  title,
  body,
  copyValue,
}: {
  title: string;
  body: string;
  copyValue?: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          {title}
        </p>
        {copyValue && <CopyButton text={copyValue} />}
      </div>
      <pre className="font-mono text-xs text-[#111827] bg-[#F3F4F6] rounded-lg p-4 overflow-x-auto whitespace-pre-wrap wrap-break-word">
        {body || '—'}
      </pre>
    </div>
  );
}

export function PromptDetail({ prompt }: PromptDetailProps) {
  const isGlobal = !prompt.tenant_id;
  const metaEntries = Object.entries(prompt.metadata ?? {});

  return (
    <div className="bg-white rounded-lg p-4 sm:p-6 space-y-5 sm:space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 sm:gap-4">
        <div className="min-w-0">
          <h2 className="text-xl font-bold text-[#111827] break-all">{prompt.name}</h2>
          <p className="text-sm text-gray-500 font-mono mt-1">
            v{prompt.version} · {formatTimestamp(prompt.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {isGlobal && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider px-2 py-1 rounded-md bg-[#F3F4F6] text-gray-600">
              <Globe className="h-3 w-3" />
              Global
            </span>
          )}
          {prompt.is_active && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider px-2 py-1 rounded-md bg-[#10B981] text-white">
              <CheckCircle2 className="h-3 w-3" />
              Active
            </span>
          )}
        </div>
      </div>

      {isGlobal && (
        <div className="bg-[#FEF3C7] border-l-4 border-[#F59E0B] rounded-md p-3 text-sm text-[#111827]">
          Global prompts are read-only. Create a new tenant version to customize.
        </div>
      )}

      <Section
        title="System prompt"
        body={prompt.system_prompt ?? ''}
        copyValue={prompt.system_prompt}
      />

      <Section
        title="User prompt template"
        body={prompt.user_prompt_template ?? ''}
        copyValue={prompt.user_prompt_template}
      />

      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
          Metadata
        </p>
        {metaEntries.length === 0 ? (
          <p className="text-sm text-gray-400">No metadata set.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {metaEntries.map(([key, value]) => (
              <div
                key={key}
                className="bg-[#F3F4F6] rounded-md px-3 py-2"
              >
                <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  {key}
                </p>
                <p className="text-sm text-[#111827] font-mono wrap-break-word">
                  {typeof value === 'object'
                    ? JSON.stringify(value)
                    : String(value)}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
