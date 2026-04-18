'use client';

import { use } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getIntegration } from '@/lib/api/integrations';
import { PageHeader } from '@/components/layout/PageHeader';
import { ChatWindow } from '@/components/chat/ChatWindow';

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
    <div className="flex flex-col h-full">
      <PageHeader
        title={integration?.name ?? 'Playground'}
        subtitle="Test your RAG pipeline with queries"
      />
      <ChatWindow integrationId={id} />
    </div>
  );
}
