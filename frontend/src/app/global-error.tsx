'use client';

import { useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (typeof window !== 'undefined') {
      console.error('[GlobalError]', error);
    }
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          background: '#FFFFFF',
          color: '#111827',
          fontFamily: 'Outfit, sans-serif',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
        }}
      >
        <div
          style={{
            maxWidth: 480,
            width: '100%',
            background: '#F3F4F6',
            borderRadius: 8,
            padding: '2.5rem',
            textAlign: 'center',
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 64,
              height: 64,
              background: '#F59E0B',
              color: '#FFFFFF',
              borderRadius: 6,
              marginBottom: '1.5rem',
            }}
          >
            <AlertTriangle size={32} strokeWidth={2.5} />
          </div>
          <h1
            style={{
              fontSize: '1.875rem',
              fontWeight: 800,
              letterSpacing: '-0.02em',
              margin: 0,
              marginBottom: '0.5rem',
            }}
          >
            Something went wrong
          </h1>
          <p
            style={{
              color: '#6B7280',
              fontSize: '0.95rem',
              fontWeight: 500,
              margin: 0,
              marginBottom: '2rem',
            }}
          >
            An unexpected error occurred. Our team has been notified.
            {error.digest ? ` (ref: ${error.digest})` : ''}
          </p>
          <button
            onClick={reset}
            style={{
              background: '#3B82F6',
              color: '#FFFFFF',
              border: 'none',
              height: 48,
              padding: '0 1.5rem',
              borderRadius: 6,
              fontSize: '0.95rem',
              fontWeight: 600,
              fontFamily: 'inherit',
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
