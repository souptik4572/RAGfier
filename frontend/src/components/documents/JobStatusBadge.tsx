import { cn } from '@/lib/utils';
import type { Document } from '@/lib/api/documents';

interface JobStatusBadgeProps {
  status: Document['status'];
}

const statusConfig: Record<
  Document['status'],
  { className: string; label: string }
> = {
  pending: {
    className: 'bg-[#F3F4F6] text-[#111827]',
    label: 'Pending',
  },
  parsing: {
    className: 'bg-[#F59E0B] text-white',
    label: 'Parsing',
  },
  chunking: {
    className: 'bg-[#F59E0B] text-white',
    label: 'Chunking',
  },
  embedding: {
    className: 'bg-[#F59E0B] text-white',
    label: 'Embedding',
  },
  completed: {
    className: 'bg-[#10B981] text-white',
    label: 'Completed',
  },
  failed: {
    className: 'bg-red-500 text-white',
    label: 'Failed',
  },
};

export function JobStatusBadge({ status }: JobStatusBadgeProps) {
  const config = statusConfig[status] ?? statusConfig.pending;
  return (
    <span
      className={cn(
        'rounded-md text-xs font-semibold uppercase tracking-wider px-2 py-1',
        config.className
      )}
    >
      {config.label}
    </span>
  );
}
