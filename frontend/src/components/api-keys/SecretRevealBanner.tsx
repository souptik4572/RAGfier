'use client';

import { X, AlertTriangle } from 'lucide-react';
import { CopyButton } from '@/components/shared/CopyButton';

interface SecretRevealBannerProps {
  secret: string;
  prefix: string;
  onDismiss: () => void;
}

export function SecretRevealBanner({
  secret,
  prefix,
  onDismiss,
}: SecretRevealBannerProps) {
  return (
    <div className="bg-[#F59E0B] text-white p-5 rounded-lg mb-6 flex items-start gap-4">
      <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center shrink-0">
        <AlertTriangle className="h-5 w-5" />
      </div>

      <div className="flex-1 min-w-0">
        <h3 className="font-bold text-base tracking-tight">
          Copy your API key now — it will never be shown again.
        </h3>
        <p className="text-sm text-white/90 mt-0.5">
          Key prefix{' '}
          <span className="font-mono font-semibold">{prefix}</span> — the full
          secret is only displayed this one time.
        </p>

        <div className="mt-3 flex items-center gap-2 bg-white/20 rounded-md px-3 py-2">
          <code className="flex-1 font-mono text-sm break-all select-all">
            {secret}
          </code>
          <div className="shrink-0">
            <CopyButton
              text={secret}
              className="text-white hover:bg-white/20 hover:text-white"
            />
          </div>
        </div>
      </div>

      <button
        onClick={onDismiss}
        className="p-1.5 rounded-md hover:bg-white/20 transition-colors duration-150 shrink-0"
        aria-label="Dismiss"
      >
        <X className="h-5 w-5" />
      </button>
    </div>
  );
}
