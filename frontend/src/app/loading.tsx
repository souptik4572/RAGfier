import { Skeleton } from '@/components/shared/Skeleton';

export default function RootLoading() {
  return (
    <div
      className="min-h-screen bg-[#F3F4F6] p-6 sm:p-8"
      role="status"
      aria-live="polite"
      aria-label="Loading page"
    >
      <Skeleton className="h-10 w-56 mb-8 bg-white" />
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 sm:gap-6 mb-8">
        <Skeleton className="h-28 bg-white" />
        <Skeleton className="h-28 bg-white" />
        <Skeleton className="h-28 bg-white" />
        <Skeleton className="h-28 bg-white" />
      </div>
      <Skeleton className="h-64 w-full bg-white" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
