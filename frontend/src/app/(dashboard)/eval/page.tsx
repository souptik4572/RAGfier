import { PageHeader } from '@/components/layout/PageHeader';
import { FlaskConical } from 'lucide-react';

export default function EvalPage() {
  return (
    <div>
      <PageHeader title="Eval Runs" subtitle="Evaluate your RAG pipeline quality" />
      <div className="bg-white rounded-lg p-16 flex flex-col items-center justify-center text-center">
        <FlaskConical className="h-16 w-16 text-gray-400 mb-6" />
        <h2 className="text-xl font-bold text-[#111827] mb-2">
          Evaluation Runs Coming Soon
        </h2>
        <p className="text-gray-500 max-w-sm">
          Automated evaluation against golden samples will be available in a future milestone.
        </p>
      </div>
    </div>
  );
}
