'use client';

import { use, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText } from 'lucide-react';
import { getIntegration } from '@/lib/api/integrations';
import { listDocuments, uploadDocument } from '@/lib/api/documents';
import { PageHeader } from '@/components/layout/PageHeader';
import { DocumentList } from '@/components/documents/DocumentList';
import { UploadDropzone } from '@/components/documents/UploadDropzone';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { EmptyState } from '@/components/shared/EmptyState';

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
