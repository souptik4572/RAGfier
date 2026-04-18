'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { type Document, deleteDocument } from '@/lib/api/documents';
import { JobStatusBadge } from './JobStatusBadge';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { formatDate, getErrorMessage, truncate } from '@/lib/utils';

interface DocumentListProps {
  documents: Document[];
  integrationId: string;
}

export function DocumentList({ documents, integrationId }: DocumentListProps) {
  const queryClient = useQueryClient();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [targetDoc, setTargetDoc] = useState<Document | null>(null);

  const handleDeleteClick = (doc: Document) => {
    setTargetDoc(doc);
    setConfirmOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!targetDoc) return;
    setDeletingId(targetDoc.id);
    try {
      await deleteDocument(integrationId, targetDoc.id);
      await queryClient.invalidateQueries({ queryKey: ['documents', integrationId] });
      toast.success('Document deleted');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Delete failed'));
    } finally {
      setDeletingId(null);
      setTargetDoc(null);
      setConfirmOpen(false);
    }
  };

  return (
    <>
      <div className="bg-white rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[#111827] text-white">
              <th className="text-left px-6 py-3 font-semibold tracking-tight">File Name</th>
              <th className="text-left px-6 py-3 font-semibold tracking-tight">Title</th>
              <th className="text-left px-6 py-3 font-semibold tracking-tight">Status</th>
              <th className="text-left px-6 py-3 font-semibold tracking-tight">Chunks</th>
              <th className="text-left px-6 py-3 font-semibold tracking-tight">Created</th>
              <th className="text-right px-6 py-3 font-semibold tracking-tight">Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc, index) => (
              <tr
                key={doc.id}
                className={index % 2 === 0 ? 'bg-white' : 'bg-[#F3F4F6]'}
              >
                <td className="px-6 py-4 font-medium text-[#111827]">
                  {truncate(doc.file_name, 40)}
                </td>
                <td className="px-6 py-4 text-gray-500">
                  {doc.document_title ? truncate(doc.document_title, 30) : '—'}
                </td>
                <td className="px-6 py-4">
                  <JobStatusBadge status={doc.status} />
                </td>
                <td className="px-6 py-4 text-gray-500">{doc.chunk_count ?? '—'}</td>
                <td className="px-6 py-4 text-gray-500">{formatDate(doc.created_at)}</td>
                <td className="px-6 py-4 text-right">
                  <button
                    onClick={() => handleDeleteClick(doc)}
                    disabled={deletingId === doc.id}
                    className="p-2 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors duration-150 disabled:opacity-50"
                    aria-label="Delete document"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete Document"
        description={`Are you sure you want to delete "${targetDoc?.file_name}"? This action cannot be undone.`}
        onConfirm={handleConfirmDelete}
        confirmLabel="Delete"
        isDestructive
      />
    </>
  );
}
