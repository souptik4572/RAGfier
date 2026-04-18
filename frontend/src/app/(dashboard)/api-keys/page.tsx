import { PageHeader } from '@/components/layout/PageHeader';
import { Key } from 'lucide-react';

export default function ApiKeysPage() {
  return (
    <div>
      <PageHeader title="API Keys" subtitle="Manage your API keys" />
      <div className="bg-white rounded-lg p-16 flex flex-col items-center justify-center text-center">
        <Key className="h-16 w-16 text-gray-400 mb-6" />
        <h2 className="text-xl font-bold text-[#111827] mb-2">
          API Keys Coming Soon
        </h2>
        <p className="text-gray-500 max-w-sm">
          API key management will be available in a future milestone.
        </p>
      </div>
    </div>
  );
}
