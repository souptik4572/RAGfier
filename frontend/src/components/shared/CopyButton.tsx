'use client';

import { Copy, Check } from 'lucide-react';
import { useCopyToClipboard } from '@/lib/hooks/useCopyToClipboard';
import { cn } from '@/lib/utils';

interface CopyButtonProps {
  text: string;
  className?: string;
}

export function CopyButton({ text, className }: CopyButtonProps) {
  const [isCopied, copy] = useCopyToClipboard();

  return (
    <button
      onClick={() => copy(text)}
      className={cn(
        'p-2 rounded-md text-gray-400 hover:text-[#3B82F6] hover:bg-[#F3F4F6] transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]',
        className
      )}
      aria-live="polite"
      aria-label={isCopied ? 'Copied!' : 'Copy to clipboard'}
      title={isCopied ? 'Copied!' : 'Copy'}
    >
      {isCopied ? (
        <Check className="h-4 w-4 text-[#10B981]" />
      ) : (
        <Copy className="h-4 w-4" />
      )}
    </button>
  );
}
