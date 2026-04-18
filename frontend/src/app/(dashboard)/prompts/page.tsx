'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileText, Plus } from 'lucide-react';
import { listPrompts } from '@/lib/api/prompts';
import { getErrorMessage } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/shared/EmptyState';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { Button } from '@/components/ui/button';
import { PromptList } from '@/components/prompts/PromptList';
import { PromptDetail } from '@/components/prompts/PromptDetail';
import { CreatePromptDialog } from '@/components/prompts/CreatePromptDialog';

export default function PromptsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data: prompts, isLoading, error } = useQuery({
    queryKey: ['prompts'],
    queryFn: listPrompts,
  });

  const sortedPrompts = useMemo(() => {
    if (!prompts) return [];
    return [...prompts].sort((a, b) => {
      if (a.name !== b.name) return a.name.localeCompare(b.name);
      return b.version - a.version;
    });
  }, [prompts]);

  useEffect(() => {
    if (!selectedId && sortedPrompts.length > 0) {
      setSelectedId(sortedPrompts[0].id);
    } else if (
      selectedId &&
      sortedPrompts.length > 0 &&
      !sortedPrompts.some((p) => p.id === selectedId)
    ) {
      setSelectedId(sortedPrompts[0].id);
    }
  }, [sortedPrompts, selectedId]);

  const selected = sortedPrompts.find((p) => p.id === selectedId) ?? null;

  return (
    <div>
      <PageHeader
        title="Prompts"
        subtitle="Version, compare, and roll out your RAG prompts"
        action={
          <Button
            variant="primary"
            size="sm"
            onClick={() => setDialogOpen(true)}
            className="gap-2"
          >
            <Plus className="h-4 w-4" />
            New Version
          </Button>
        }
      />

      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
          <div className="space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <LoadingBlock key={i} className="h-16 w-full bg-white rounded-lg" />
            ))}
          </div>
          <LoadingBlock className="h-96 w-full bg-white rounded-lg" />
        </div>
      ) : error ? (
        <EmptyState
          icon={<FileText className="h-16 w-16 text-gray-400" />}
          title="Could not load prompts"
          subtitle={getErrorMessage(error, 'Please try again.')}
        />
      ) : sortedPrompts.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-16 w-16 text-gray-400" />}
          title="No prompts yet"
          subtitle="Create your first prompt version to get started."
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 items-start">
          <div className="lg:sticky lg:top-6">
            <PromptList
              prompts={sortedPrompts}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>
          {selected ? (
            <PromptDetail prompt={selected} />
          ) : (
            <EmptyState
              icon={<FileText className="h-16 w-16 text-gray-400" />}
              title="Select a prompt"
              subtitle="Choose a version from the list to view its details."
            />
          )}
        </div>
      )}

      <CreatePromptDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        defaultName={selected?.name ?? ''}
      />
    </div>
  );
}
