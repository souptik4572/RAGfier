'use client';

import { useState, useCallback } from 'react';
import { toast } from 'sonner';

export function useCopyToClipboard(): [boolean, (text: string) => Promise<void>] {
  const [isCopied, setIsCopied] = useState(false);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch {
      toast.error('Failed to copy to clipboard');
    }
  }, []);

  return [isCopied, copy];
}
