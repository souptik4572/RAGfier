import { PageHeader } from '@/components/layout/PageHeader';
import { BarChart3 } from 'lucide-react';

export default function UsagePage() {
  return (
    <div>
      <PageHeader title="Usage" subtitle="Monitor your platform usage and quotas" />
      <div className="bg-white rounded-lg p-16 flex flex-col items-center justify-center text-center">
        <BarChart3 className="h-16 w-16 text-gray-400 mb-6" />
        <h2 className="text-xl font-bold text-[#111827] mb-2">
          Usage Analytics Coming Soon
        </h2>
        <p className="text-gray-500 max-w-sm">
          Detailed usage metrics and billing information will be available in a future milestone.
        </p>
      </div>
    </div>
  );
}
