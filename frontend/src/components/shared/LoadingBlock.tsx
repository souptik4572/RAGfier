import { cn } from '@/lib/utils';

interface LoadingBlockProps {
  className?: string;
}

export function LoadingBlock({ className }: LoadingBlockProps) {
  return (
    <div
      className={cn('animate-pulse bg-[#F3F4F6] rounded-lg', className)}
      aria-hidden="true"
    />
  );
}
