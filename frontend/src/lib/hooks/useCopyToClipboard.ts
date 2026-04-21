'use client';

import { useState, useCallback } from 'react';

export function useCopyToClipboard(): [boolean, (text: string) => Promise<void>] {
  const [isCopied, setIsCopied] = useState(false);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy text:', err);
    }
  }, []);

  return [isCopied, copy];
}
