'use client';

import { use } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getIntegration } from '@/lib/api/integrations';
import { PageHeader } from '@/components/layout/PageHeader';
import { Play } from 'lucide-react';

interface PlaygroundPageProps {
  params: Promise<{ id: string }>;
}

export default function PlaygroundPage({ params }: PlaygroundPageProps) {
  const { id } = use(params);

  const { data: integration } = useQuery({
    queryKey: ['integration', id],
    queryFn: () => getIntegration(id),
  });

  return (
    <div>
      <PageHeader
        title={`${integration?.name ?? 'Playground'}`}
        subtitle="Test your RAG pipeline with queries"
      />

      <div className="bg-white rounded-lg p-16 flex flex-col items-center justify-center text-center">
        <div className="w-20 h-20 rounded-full bg-[#F3F4F6] flex items-center justify-center mb-6">
          <Play className="h-10 w-10 text-[#3B82F6]" />
        </div>
        <h2 className="text-xl font-bold text-[#111827] mb-2">
          Playground Coming Soon
        </h2>
        <p className="text-gray-500 max-w-sm">
          The interactive query playground will be available in a future milestone.
          You&apos;ll be able to test your RAG pipeline, view citations, and tune
          retrieval settings here.
        </p>
      </div>
    </div>
  );
}
