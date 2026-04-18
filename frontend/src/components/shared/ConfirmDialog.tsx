'use client';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  onConfirm: () => void | Promise<void>;
  confirmLabel?: string;
  cancelLabel?: string;
  isDestructive?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  isDestructive = false,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 overflow-hidden">
        <DialogHeader className="bg-[#111827] text-white p-6 rounded-t-lg">
          <DialogTitle className="text-white">{title}</DialogTitle>
          <DialogDescription className="text-gray-400 mt-1">
            {description}
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-3 p-6">
          <Button
            variant="secondary"
            onClick={() => onOpenChange(false)}
            className="flex-1 h-11"
          >
            {cancelLabel}
          </Button>
          <Button
            variant={isDestructive ? 'destructive' : 'primary'}
            onClick={onConfirm}
            className="flex-1 h-11"
          >
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
