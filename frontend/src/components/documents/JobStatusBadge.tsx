import { cn } from '@/lib/utils';
import type { Document } from '@/lib/api/documents';

interface JobStatusBadgeProps {
  status: Document['status'];
}

const statusConfig: Record<
  Document['status'],
  { className: string; dotClassName: string; label: string }
> = {
  pending: {
    className: 'bg-[#F3F4F6] text-[#111827]',
    dotClassName: 'bg-[#9CA3AF]',
    label: 'Pending',
  },
  parsing: {
    className: 'bg-[#F59E0B] text-white',
    dotClassName: 'bg-white',
    label: 'Parsing',
  },
  chunking: {
    className: 'bg-[#F59E0B] text-white',
    dotClassName: 'bg-white',
    label: 'Chunking',
  },
  embedding: {
    className: 'bg-[#F59E0B] text-white',
    dotClassName: 'bg-white',
    label: 'Embedding',
  },
  completed: {
    className: 'bg-[#10B981] text-white',
    dotClassName: 'bg-white',
    label: 'Completed',
  },
  failed: {
    className: 'bg-red-500 text-white',
    dotClassName: 'bg-white',
    label: 'Failed',
  },
};

export function JobStatusBadge({ status }: JobStatusBadgeProps) {
  const config = statusConfig[status] ?? statusConfig.pending;
  return (
    <span
      className={cn(
        'rounded-md text-xs font-semibold uppercase tracking-wider px-2 py-1 inline-flex items-center gap-1',
        config.className
      )}
    >
      <span
        className={cn('w-1.5 h-1.5 rounded-full inline-block shrink-0', config.dotClassName)}
      />
      {config.label}
    </span>
  );
}
