'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { AlertTriangle, RotateCcw, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[DashboardError]', error);
  }, [error]);

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div
        role="alert"
        aria-live="assertive"
        className="w-full max-w-xl bg-white rounded-lg p-8 sm:p-10 text-center"
      >
        <div className="inline-flex items-center justify-center h-14 w-14 bg-[#F59E0B] text-white rounded-md mb-5">
          <AlertTriangle className="h-7 w-7" strokeWidth={2.5} />
        </div>

        <h2 className="text-xl sm:text-2xl font-extrabold text-[#111827] tracking-tight mb-2">
          We couldn&apos;t load this page
        </h2>
        <p className="text-sm sm:text-base text-gray-500 font-medium mb-2">
          Something went wrong while rendering. You can retry, or head back to
          the dashboard.
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
              Dashboard
            </Link>
          </Button>
        </div>

        {process.env.NODE_ENV !== 'production' && error.message && (
          <pre className="mt-6 text-left bg-[#F3F4F6] text-[#111827] rounded-md p-4 overflow-x-auto text-xs font-mono whitespace-pre-wrap break-words">
            {error.message}
          </pre>
        )}
      </div>
    </div>
  );
}
