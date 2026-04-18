import { PageHeader } from '@/components/layout/PageHeader';
import { ScrollText } from 'lucide-react';

export default function AuditLogsPage() {
  return (
    <div>
      <PageHeader title="Audit Logs" subtitle="Track all platform activity" />
      <div className="bg-white rounded-lg p-16 flex flex-col items-center justify-center text-center">
        <ScrollText className="h-16 w-16 text-gray-400 mb-6" />
        <h2 className="text-xl font-bold text-[#111827] mb-2">
          Audit Logs Coming Soon
        </h2>
        <p className="text-gray-500 max-w-sm">
          Comprehensive audit logging will be available in a future milestone.
        </p>
      </div>
    </div>
  );
}
