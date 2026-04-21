import Link from 'next/link';
import { Compass, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F3F4F6] p-6">
      <div className="w-full max-w-xl bg-white rounded-lg p-8 sm:p-12 text-center">
        <div className="inline-flex items-center justify-center h-16 w-16 bg-[#3B82F6] text-white rounded-md mb-6">
          <Compass className="h-8 w-8" strokeWidth={2.5} />
        </div>

        <p className="text-sm font-bold uppercase tracking-widest text-[#3B82F6] mb-2">
          404
        </p>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-[#111827] tracking-tight mb-2">
          Page not found
        </h1>
        <p className="text-sm sm:text-base text-gray-500 font-medium mb-8">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>

        <Button
          variant="primary"
          asChild
          className="inline-flex items-center justify-center gap-2"
        >
          <Link href="/dashboard">
            <Home className="h-4 w-4" />
            Return to dashboard
          </Link>
        </Button>
      </div>
    </div>
  );
}
