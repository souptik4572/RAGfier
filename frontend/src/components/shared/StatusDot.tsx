import { cn } from '@/lib/utils';

interface StatusDotProps {
  status: 'up' | 'down' | 'unknown';
  className?: string;
}

const statusColors: Record<StatusDotProps['status'], string> = {
  up: 'bg-[#10B981]',
  down: 'bg-red-500',
  unknown: 'bg-gray-400',
};

export function StatusDot({ status, className }: StatusDotProps) {
  return (
    <span
      className={cn(
        'inline-block w-3 h-3 rounded-full flex-shrink-0',
        statusColors[status],
        className
      )}
      aria-label={`Status: ${status}`}
    />
  );
}
