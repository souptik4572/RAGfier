'use client';

import { use, useState } from 'react';
import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, Play } from 'lucide-react';
import { getIntegration } from '@/lib/api/integrations';
import { listDocuments, uploadDocument } from '@/lib/api/documents';
import { PageHeader } from '@/components/layout/PageHeader';
import { DocumentList } from '@/components/documents/DocumentList';
import { UploadDropzone } from '@/components/documents/UploadDropzone';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { EmptyState } from '@/components/shared/EmptyState';
import { Button } from '@/components/ui/button';

interface DocumentsPageProps {
  params: Promise<{ id: string }>;
}

export default function DocumentsPage({ params }: DocumentsPageProps) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);

  const { data: integration } = useQuery({
    queryKey: ['integration', id],
    queryFn: () => getIntegration(id),
  });

  const { data: documents, isLoading } = useQuery({
    queryKey: ['documents', id],
    queryFn: () => listDocuments(id),
  });

  const handleUpload = async (file: File, title?: string) => {
    const response = await uploadDocument(id, file, title);
    if (response.job_id) {
      setPendingJobId(response.job_id);
    }
    await queryClient.invalidateQueries({ queryKey: ['documents', id] });
  };

  return (
    <div>
      <PageHeader
        title={integration?.name ?? 'Documents'}
        subtitle="Manage documents for this integration"
        action={
          <Link href={`/integrations/${id}/playground`}>
            <Button variant="outline" className="flex items-center gap-2 h-10 px-4 sm:px-6">
              <Play className="h-4 w-4" />
              <span>Playground</span>
            </Button>
          </Link>
        }
      />

      <div className="mb-8">
        <UploadDropzone
          onUpload={handleUpload}
          pendingJobId={pendingJobId}
          integrationId={id}
        />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-14 w-full bg-white rounded-lg" />
          ))}
        </div>
      ) : documents && documents.length > 0 ? (
        <DocumentList documents={documents} integrationId={id} />
      ) : (
        <EmptyState
          icon={<FileText className="h-16 w-16 text-gray-400" />}
          title="No documents yet"
          subtitle="Upload PDF or Markdown files to get started."
        />
      )}
    </div>
  );
}
