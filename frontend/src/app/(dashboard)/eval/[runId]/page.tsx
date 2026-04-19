'use client';

import { use } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, FlaskConical } from 'lucide-react';
import {
  listEvalRuns,
  listEvalSamples,
  type EvalRunSummary,
} from '@/lib/api/eval';
import { getErrorMessage } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { EmptyState } from '@/components/shared/EmptyState';
import { ScoreBar } from '@/components/shared/ScoreBar';
import { EvalSampleTable } from '@/components/eval/EvalSampleTable';
import { cn } from '@/lib/utils';

interface EvalRunDetailPageProps {
  params: Promise<{ runId: string }>;
}

export default function EvalRunDetailPage({ params }: EvalRunDetailPageProps) {
  const { runId } = use(params);

  const { data: runs } = useQuery({
    queryKey: ['eval-runs'],
    queryFn: listEvalRuns,
  });

  const { data: samples, isLoading, error } = useQuery({
    queryKey: ['eval-samples', runId],
    queryFn: () => listEvalSamples(runId),
  });

  const run: EvalRunSummary | undefined = runs?.find((r) => r.id === runId);

  return (
    <div>
      <Link
        href="/eval"
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-[#111827] transition-colors duration-150 mb-3"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to runs
      </Link>

      <PageHeader
        title={run ? `Run ${run.id.slice(0, 8)}` : 'Run detail'}
        subtitle={run ? `${run.dataset_version} · ${run.trigger}` : ''}
      />

      {run && (
        <div className="bg-white rounded-lg p-4 sm:p-6 mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                Status
              </p>
              <p
                className={cn(
                  'text-lg font-bold mt-1',
                  run.passed === true
                    ? 'text-[#10B981]'
                    : run.passed === false
                    ? 'text-red-500'
                    : 'text-[#111827]'
                )}
              >
                {run.status}
                {run.passed !== null && run.passed !== undefined && (
                  <span className="ml-2 text-sm font-semibold">
                    ({run.passed ? 'Passed' : 'Failed'})
                  </span>
                )}
              </p>
            </div>
            <div className="sm:text-right">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                Samples
              </p>
              <p className="text-lg font-bold text-[#111827] mt-1">
                {run.total_samples}
                {run.failed_samples > 0 && (
                  <span className="text-sm text-red-500 ml-2">
                    · {run.failed_samples} failed
                  </span>
                )}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 sm:gap-x-6 gap-y-4">
            <ScoreBar label="Faithfulness" value={run.scores.faithfulness_avg} />
            <ScoreBar label="Answer Relevancy" value={run.scores.answer_relevancy_avg} />
            <ScoreBar label="Context Precision" value={run.scores.context_precision_avg} />
            <ScoreBar label="Context Recall" value={run.scores.context_recall_avg} />
            <ScoreBar label="Citation Coverage" value={run.scores.citation_coverage_avg} />
            <ScoreBar label="Decline Accuracy" value={run.scores.decline_accuracy_avg} />
            <ScoreBar label="Latency Compliance" value={run.scores.latency_compliance_avg} />
          </div>
        </div>
      )}

      <h2 className="text-lg font-bold text-[#111827] mb-3">Samples</h2>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4].map((i) => (
            <LoadingBlock key={i} className="h-12 w-full bg-white rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <EmptyState
          icon={<FlaskConical className="h-16 w-16 text-gray-400" />}
          title="Could not load samples"
          subtitle={getErrorMessage(error, 'Please try again.')}
        />
      ) : samples && samples.length > 0 ? (
        <EvalSampleTable samples={samples} />
      ) : (
        <EmptyState
          icon={<FlaskConical className="h-16 w-16 text-gray-400" />}
          title="No samples for this run"
          subtitle="Samples appear after the run processes individual eval items."
        />
      )}
    </div>
  );
}
