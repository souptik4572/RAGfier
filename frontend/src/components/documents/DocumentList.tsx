'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { type Document, deleteDocument } from '@/lib/api/documents';
import { JobStatusBadge } from './JobStatusBadge';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatDate, truncate } from '@/lib/utils';

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
      await deleteDocument(targetDoc.id);
      await queryClient.invalidateQueries({ queryKey: ['documents', integrationId] });
      toast.success('Document deleted');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Delete failed';
      toast.error(message);
    } finally {
      setDeletingId(null);
      setTargetDoc(null);
      setConfirmOpen(false);
    }
  };

  return (
    <>
      <div className="bg-white rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File Name</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Chunks</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((doc) => (
              <TableRow key={doc.id}>
                <TableCell className="font-medium">
                  {truncate(doc.file_name, 40)}
                </TableCell>
                <TableCell className="text-gray-500">
                  {doc.title ? truncate(doc.title, 30) : '—'}
                </TableCell>
                <TableCell>
                  <JobStatusBadge status={doc.status} />
                </TableCell>
                <TableCell className="text-gray-500">
                  {doc.chunk_count ?? '—'}
                </TableCell>
                <TableCell className="text-gray-500">
                  {formatDate(doc.created_at)}
                </TableCell>
                <TableCell className="text-right">
                  <button
                    onClick={() => handleDeleteClick(doc)}
                    disabled={deletingId === doc.id}
                    className="p-2 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors duration-150 disabled:opacity-50"
                    aria-label="Delete document"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
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
