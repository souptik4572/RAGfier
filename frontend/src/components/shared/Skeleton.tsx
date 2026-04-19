import { cn } from '@/lib/utils';

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

/**
 * Rectangular placeholder for loading states. Uses `animate-pulse`
 * with a muted background; pass `bg-white` to invert on muted surfaces.
 */
export function Skeleton({ className, ...props }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn('animate-pulse bg-[#F3F4F6] rounded-md', className)}
      {...props}
    />
  );
}

interface TextSkeletonProps {
  lines?: number;
  className?: string;
}

/** Multi-line text skeleton — last line is shorter for a natural shape. */
export function TextSkeleton({ lines = 3, className }: TextSkeletonProps) {
  return (
    <div className={cn('space-y-2', className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn('h-4', i === lines - 1 ? 'w-2/3' : 'w-full')}
        />
      ))}
    </div>
  );
}

interface TableSkeletonProps {
  rows?: number;
  columns?: number;
  className?: string;
}

/** Compact table skeleton for data-heavy pages (audit, eval, usage). */
export function TableSkeleton({
  rows = 5,
  columns = 4,
  className,
}: TableSkeletonProps) {
  return (
    <div
      className={cn('bg-white rounded-lg overflow-hidden', className)}
      aria-hidden="true"
    >
      <div className="bg-[#111827] h-11" />
      <div className="divide-y divide-[#F3F4F6]">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-4 px-6 py-4">
            {Array.from({ length: columns }).map((_, c) => (
              <Skeleton
                key={c}
                className={cn(
                  'h-4 flex-1',
                  c === columns - 1 && 'max-w-[80px]'
                )}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
