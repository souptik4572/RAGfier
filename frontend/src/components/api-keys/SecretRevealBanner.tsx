'use client';

import { X, AlertTriangle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogClose,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { CopyButton } from '@/components/shared/CopyButton';

interface SecretRevealBannerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  secret: string;
  prefix: string;
}

export function SecretRevealBanner({
  open,
  onOpenChange,
  secret,
  prefix,
}: SecretRevealBannerProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-xl p-0"
        hideDefaultClose
      >
        <div className="bg-[#F59E0B] text-white p-5 sm:p-6 relative pr-14">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center shrink-0">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <DialogTitle className="text-white font-bold text-lg tracking-tight">
                Copy your API key now
              </DialogTitle>
              <DialogDescription className="text-white/90 text-sm mt-1">
                The full secret will never be shown again. Store it somewhere
                safe before closing this dialog.
              </DialogDescription>
            </div>
          </div>

          <DialogClose
            className="absolute right-4 top-4 p-2 rounded-md text-white/80 hover:text-white hover:bg-white/20 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-white/40"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </DialogClose>
        </div>

        <div className="p-5 sm:p-6 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">
              Key prefix
            </p>
            <p className="font-mono text-sm text-[#111827]">{prefix}</p>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
              Secret
            </p>
            <div className="flex items-center gap-2 bg-[#111827] text-white rounded-md px-3 py-3">
              <code className="flex-1 font-mono text-sm break-all select-all">
                {secret}
              </code>
              <div className="shrink-0">
                <CopyButton
                  text={secret}
                  className="text-gray-300 hover:bg-white/10 hover:text-white"
                />
              </div>
            </div>
          </div>

          <div className="pt-2">
            <Button
              variant="primary"
              onClick={() => onOpenChange(false)}
              className="w-full h-11"
            >
              I&apos;ve copied my key
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
