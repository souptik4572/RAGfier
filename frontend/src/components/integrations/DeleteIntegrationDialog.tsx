'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle } from 'lucide-react';
import {
  deleteIntegration,
  type Integration,
} from '@/lib/api/integrations';
import { getErrorMessage } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

interface DeleteIntegrationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  integration: Integration;
}

export function DeleteIntegrationDialog({
  open,
  onOpenChange,
  integration,
}: DeleteIntegrationDialogProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirmation, setConfirmation] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    if (confirmation !== integration.name) return;
    setIsDeleting(true);
    try {
      const result = await deleteIntegration(integration.id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['integrations'] }),
        queryClient.invalidateQueries({ queryKey: ['api-keys'] }),
      ]);
      toast.success(
        `Integration deleted — removed ${result.deleted_documents} document(s), ${result.deleted_jobs} job(s), ${result.deleted_api_keys} API key(s).`
      );
      onOpenChange(false);
      router.push('/integrations');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to delete integration'));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleClose = () => {
    setConfirmation('');
    onOpenChange(false);
  };

  const canDelete = confirmation === integration.name && !isDeleting;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-red-500" />
            Delete Integration
          </DialogTitle>
          <DialogDescription>
            This action cannot be undone. It permanently removes the
            integration, all associated API keys, uploaded documents, ingestion
            jobs, and any stored files.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 p-6 pt-0">
          <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            <p className="font-semibold">You are about to delete:</p>
            <p className="mt-1 font-mono text-red-900">{integration.name}</p>
          </div>

          <div>
            <Label htmlFor="confirm" required>
              Type{' '}
              <span className="font-mono text-[#111827]">
                {integration.name}
              </span>{' '}
              to confirm
            </Label>
            <Input
              id="confirm"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
              placeholder={integration.name}
              autoComplete="off"
            />
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={handleClose}
              className="flex-1 h-11"
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="primary"
              disabled={!canDelete}
              onClick={handleDelete}
              className="flex-1 h-11 bg-red-600 hover:bg-red-700 disabled:bg-red-300"
            >
              {isDeleting ? 'Deleting…' : 'Delete Integration'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
