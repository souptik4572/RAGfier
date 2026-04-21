'use client';

import { useState } from 'react';
import { Terminal, FileCode2, X } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from '@/components/ui/dialog';
import { CopyButton } from '@/components/shared/CopyButton';
import { cn } from '@/lib/utils';

const KEY_PLACEHOLDER = 'YOUR_API_KEY';

interface CodeExampleDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  integrationId: string;
  integrationName: string;
  keyName: string;
  keyPrefix: string;
}

type Tab = 'curl' | 'javascript' | 'python';

const TABS: { id: Tab; label: string; icon: typeof Terminal }[] = [
  { id: 'curl', label: 'cURL', icon: Terminal },
  { id: 'javascript', label: 'JavaScript', icon: FileCode2 },
  { id: 'python', label: 'Python', icon: FileCode2 },
];

function buildBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured) return configured.replace(/\/$/, '');
  return 'http://localhost:8000';
}

function buildCurl(baseUrl: string, integrationId: string): string {
  return `curl -X POST '${baseUrl}/v1/integrations/${integrationId}/query' \\
  -H 'Authorization: Bearer ${KEY_PLACEHOLDER}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "query": "What are the key findings in the uploaded documents?",
    "match_count": 5,
    "rerank": true,
    "include_sources": true
  }'`;
}

function buildJavaScript(baseUrl: string, integrationId: string): string {
  return `const response = await fetch(
  '${baseUrl}/v1/integrations/${integrationId}/query',
  {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ${KEY_PLACEHOLDER}',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query: 'What are the key findings in the uploaded documents?',
      match_count: 5,
      rerank: true,
      include_sources: true,
    }),
  }
);

const data = await response.json();
console.log(data.answer);
console.log(data.citations);`;
}

function buildPython(baseUrl: string, integrationId: string): string {
  return `import requests

response = requests.post(
    '${baseUrl}/v1/integrations/${integrationId}/query',
    headers={
        'Authorization': 'Bearer ${KEY_PLACEHOLDER}',
        'Content-Type': 'application/json',
    },
    json={
        'query': 'What are the key findings in the uploaded documents?',
        'match_count': 5,
        'rerank': True,
        'include_sources': True,
    },
)

data = response.json()
print(data['answer'])
print(data['citations'])`;
}

export function CodeExampleDialog({
  open,
  onOpenChange,
  integrationId,
  integrationName,
  keyName,
  keyPrefix,
}: CodeExampleDialogProps) {
  const [tab, setTab] = useState<Tab>('curl');
  const baseUrl = buildBaseUrl();

  const snippets: Record<Tab, string> = {
    curl: buildCurl(baseUrl, integrationId),
    javascript: buildJavaScript(baseUrl, integrationId),
    python: buildPython(baseUrl, integrationId),
  };

  const snippet = snippets[tab];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl p-0" hideDefaultClose>
        <DialogHeader className="bg-[#111827] text-white p-5 sm:p-6 rounded-t-lg relative pr-14">
          <DialogTitle className="text-white">
            How to use this API key
          </DialogTitle>
          <DialogDescription className="text-gray-400 mt-1">
            Key{' '}
            <span className="font-mono text-[#F59E0B] font-semibold">
              {keyName}
            </span>{' '}
            ({keyPrefix}…) authenticates against{' '}
            <span className="font-semibold text-white">{integrationName}</span>.
            Replace{' '}
            <span className="font-mono bg-white/10 px-1.5 py-0.5 rounded text-xs">
              {KEY_PLACEHOLDER}
            </span>{' '}
            with your actual key.
          </DialogDescription>

          <DialogClose
            className="absolute right-4 top-4 p-2 rounded-md text-white/70 hover:text-white hover:bg-white/10 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-white/40"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </DialogClose>
        </DialogHeader>

        <div className="p-4 sm:p-6 pt-5">
          {/* Tabs */}
          <div className="flex items-center gap-1 sm:gap-2 mb-4 border-b-2 border-[#E5E7EB] overflow-x-auto">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={cn(
                  'flex items-center gap-2 px-3 sm:px-4 py-2.5 text-sm font-semibold transition-colors duration-150 border-b-2 -mb-0.5 shrink-0',
                  tab === id
                    ? 'text-[#3B82F6] border-[#3B82F6]'
                    : 'text-gray-400 border-transparent hover:text-[#111827]'
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>

          {/* Code block */}
          <div className="relative bg-[#111827] rounded-lg overflow-hidden">
            <div className="absolute top-3 right-3 z-10">
              <CopyButton
                text={snippet}
                className="text-gray-400 hover:text-white hover:bg-white/10"
              />
            </div>
            <pre className="p-5 pr-14 overflow-x-auto text-xs leading-relaxed text-gray-100 font-mono">
              <code>{snippet}</code>
            </pre>
          </div>

          {/* Helper notes */}
          <div className="mt-5 space-y-2 text-sm text-[#111827]">
            <div className="flex items-start gap-2">
              <span className="text-[#10B981] font-bold mt-0.5">•</span>
              <p>
                The <span className="font-mono text-xs bg-[#F3F4F6] px-1.5 py-0.5 rounded">
                  /query
                </span>{' '}
                endpoint returns an answer grounded in your uploaded documents,
                plus citations pointing to the source chunks.
              </p>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-[#10B981] font-bold mt-0.5">•</span>
              <p>
                Set{' '}
                <span className="font-mono text-xs bg-[#F3F4F6] px-1.5 py-0.5 rounded">
                  rerank: true
                </span>{' '}
                for higher-precision retrieval, or{' '}
                <span className="font-mono text-xs bg-[#F3F4F6] px-1.5 py-0.5 rounded">
                  false
                </span>{' '}
                for lower latency.
              </p>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-[#F59E0B] font-bold mt-0.5">•</span>
              <p>
                Append{' '}
                <span className="font-mono text-xs bg-[#F3F4F6] px-1.5 py-0.5 rounded">
                  /stream
                </span>{' '}
                to the URL for Server-Sent Events token streaming instead of a
                single JSON response.
              </p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
