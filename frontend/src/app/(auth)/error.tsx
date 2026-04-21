'use client';

import { useEffect } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function AuthError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[AuthError]', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-white p-6">
      <div
        role="alert"
        aria-live="assertive"
        className="w-full max-w-md bg-[#F3F4F6] rounded-lg p-8 text-center"
      >
        <div className="inline-flex items-center justify-center h-14 w-14 bg-[#F59E0B] text-white rounded-md mb-5">
          <AlertTriangle className="h-7 w-7" strokeWidth={2.5} />
        </div>
        <h2 className="text-xl font-extrabold text-[#111827] tracking-tight mb-2">
          Unable to sign you in
        </h2>
        <p className="text-sm text-gray-500 font-medium mb-6">
          An unexpected error occurred. Please try again.
        </p>
        <Button
          variant="primary"
          onClick={reset}
          className="w-full flex items-center justify-center gap-2"
        >
          <RotateCcw className="h-4 w-4" />
          Retry
        </Button>
      </div>
    </div>
  );
}
