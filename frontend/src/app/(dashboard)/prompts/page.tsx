import { PageHeader } from '@/components/layout/PageHeader';
import { FileText } from 'lucide-react';

export default function PromptsPage() {
  return (
    <div>
      <PageHeader title="Prompts" subtitle="Manage and version your system prompts" />
      <div className="bg-white rounded-lg p-16 flex flex-col items-center justify-center text-center">
        <FileText className="h-16 w-16 text-gray-400 mb-6" />
        <h2 className="text-xl font-bold text-[#111827] mb-2">
          Prompt Management Coming Soon
        </h2>
        <p className="text-gray-500 max-w-sm">
          Versioned prompt management and A/B testing will be available in a future milestone.
        </p>
      </div>
    </div>
  );
}
