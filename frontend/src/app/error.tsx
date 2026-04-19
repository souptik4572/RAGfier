'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { AlertTriangle, RotateCcw, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[AppError]', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F3F4F6] p-6">
      <div className="w-full max-w-xl bg-white rounded-lg p-8 sm:p-12 text-center">
        <div className="inline-flex items-center justify-center h-16 w-16 bg-[#F59E0B] text-white rounded-md mb-6">
          <AlertTriangle className="h-8 w-8" strokeWidth={2.5} />
        </div>

        <h1 className="text-2xl sm:text-3xl font-extrabold text-[#111827] tracking-tight mb-2">
          Something went wrong
        </h1>
        <p className="text-sm sm:text-base text-gray-500 font-medium mb-2">
          We hit an unexpected error while rendering this page.
        </p>
        {error.digest && (
          <p className="text-xs text-gray-400 font-mono mb-6">
            Reference: {error.digest}
          </p>
        )}

        <div className="flex flex-col sm:flex-row gap-3 justify-center mt-6">
          <Button
            variant="primary"
            onClick={reset}
            className="flex items-center justify-center gap-2"
          >
            <RotateCcw className="h-4 w-4" />
            Try again
          </Button>
          <Button
            variant="secondary"
            asChild
            className="flex items-center justify-center gap-2"
          >
            <Link href="/dashboard">
              <Home className="h-4 w-4" />
              Return to dashboard
            </Link>
          </Button>
        </div>

        {process.env.NODE_ENV !== 'production' && error.message && (
          <pre className="mt-8 text-left bg-[#F3F4F6] text-[#111827] rounded-md p-4 overflow-x-auto text-xs font-mono whitespace-pre-wrap break-words">
            {error.message}
          </pre>
        )}
      </div>
    </div>
  );
}
