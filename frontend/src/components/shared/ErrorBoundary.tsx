'use client';

import { Component, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  /** Optional custom fallback renderer. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /** Label shown in the default fallback. */
  label?: string;
  /** Called once when the boundary catches. */
  onError?: (error: Error, info: { componentStack: string }) => void;
}

interface State {
  error: Error | null;
}

/**
 * Client-side error boundary for widget-level isolation. Use when a single
 * broken panel (e.g. chat, PDF viewer) shouldn't take down the whole route.
 * For route-level errors rely on Next.js App Router `error.tsx` files.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error('[ErrorBoundary]', error, info);
    this.props.onError?.(error, info);
  }

  private reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return (
      <div
        role="alert"
        aria-live="assertive"
        className="bg-white rounded-lg p-6 text-center border-2 border-[#F59E0B]"
      >
        <div className="inline-flex items-center justify-center h-12 w-12 bg-[#F59E0B] text-white rounded-md mb-4">
          <AlertTriangle className="h-6 w-6" strokeWidth={2.5} />
        </div>
        <h3 className="text-lg font-bold text-[#111827] mb-1">
          {this.props.label ?? 'This section failed to load'}
        </h3>
        {process.env.NODE_ENV !== 'production' && (
          <p className="text-xs font-mono text-gray-500 mb-4 break-words">
            {error.message}
          </p>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={this.reset}
          className="inline-flex items-center gap-2"
        >
          <RotateCcw className="h-4 w-4" />
          Retry
        </Button>
      </div>
    );
  }
}
