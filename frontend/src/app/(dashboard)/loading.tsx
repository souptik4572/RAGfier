import { Skeleton } from '@/components/shared/Skeleton';

export default function DashboardLoading() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Loading"
      className="animate-in fade-in duration-150"
    >
      <div className="flex items-center justify-between gap-4 mb-6 sm:mb-8">
        <Skeleton className="h-9 w-48 bg-white" />
        <Skeleton className="h-11 w-36 bg-white hidden sm:block" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 sm:gap-6 mb-8">
        <Skeleton className="h-28 bg-white" />
        <Skeleton className="h-28 bg-white" />
        <Skeleton className="h-28 bg-white" />
        <Skeleton className="h-28 bg-white" />
      </div>

      <Skeleton className="h-64 w-full bg-white" />
      <span className="sr-only">Loading page content…</span>
    </div>
  );
}
