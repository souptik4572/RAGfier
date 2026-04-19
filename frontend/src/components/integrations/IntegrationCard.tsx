'use client';

import Link from 'next/link';
import { FileText, Play, Sparkles } from 'lucide-react';
import { type Integration } from '@/lib/api/integrations';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/utils';

interface IntegrationCardProps {
  integration: Integration;
}

const environmentBadgeVariant: Record<
  Integration['environment'],
  'primary' | 'secondary' | 'accent'
> = {
  production: 'primary',
  staging: 'accent',
  development: 'secondary',
};

export function IntegrationCard({ integration }: IntegrationCardProps) {
  return (
    <div className="relative bg-white rounded-lg p-6 hover:scale-[1.02] transition-all duration-200 flex flex-col gap-4 group">
      <Link
        href={`/integrations/${integration.id}`}
        aria-label={`Open ${integration.name}`}
        className="absolute inset-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6] focus-visible:ring-offset-2"
      />

      <div className="relative flex items-start justify-between gap-2 pointer-events-none">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-xl font-bold text-[#111827] truncate group-hover:text-[#3B82F6] transition-colors duration-150">
              {integration.name}
            </h3>
            {integration.is_default && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-100 text-emerald-700">
                Default
              </span>
            )}
          </div>
        </div>
        <Badge variant={environmentBadgeVariant[integration.environment]}>
          {integration.environment}
        </Badge>
      </div>

      <div className="relative pointer-events-none">
        <p className="text-sm text-gray-500">
          Created {formatDate(integration.created_at)}
        </p>
        {integration.prompt_name && (
          <p className="mt-1 text-sm text-gray-500 flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5" />
            <span className="font-mono truncate">{integration.prompt_name}</span>
          </p>
        )}
        {integration.metadata && Object.keys(integration.metadata).length > 0 && (
          <p className="mt-1 text-sm text-gray-400 truncate font-mono">
            {JSON.stringify(integration.metadata)}
          </p>
        )}
      </div>

      <div className="relative z-10 flex items-center gap-3 mt-auto pt-3 border-t border-[#E5E7EB]">
        <Link
          href={`/integrations/${integration.id}/documents`}
          className="flex-1"
        >
          <Button variant="secondary" className="w-full flex items-center gap-2 h-10">
            <FileText className="h-4 w-4" />
            Documents
          </Button>
        </Link>
        <Link
          href={`/integrations/${integration.id}/playground`}
          className="flex-1"
        >
          <Button variant="outline" className="w-full flex items-center gap-2 h-10">
            <Play className="h-4 w-4" />
            Playground
          </Button>
        </Link>
      </div>
    </div>
  );
}
