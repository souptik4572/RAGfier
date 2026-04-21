'use client';

import Link from 'next/link';
import { CheckCircle2, XCircle, Clock, GitBranch } from 'lucide-react';
import type { EvalRunSummary } from '@/lib/api/eval';
import { ScoreBar } from '@/components/shared/ScoreBar';
import { formatDate, cn } from '@/lib/utils';

interface EvalRunCardProps {
  run: EvalRunSummary;
}

export function EvalRunCard({ run }: EvalRunCardProps) {
  const isFailed = run.passed === false;
  const isPassed = run.passed === true;
  const isRunning = run.status === 'running' || run.status === 'pending';

  const headerStyle = isPassed
    ? 'bg-[#10B981] text-white'
    : isFailed
    ? 'bg-red-500 text-white'
    : 'bg-[#F3F4F6] text-[#111827]';

  const headerIcon = isPassed ? (
    <CheckCircle2 className="h-5 w-5" />
  ) : isFailed ? (
    <XCircle className="h-5 w-5" />
  ) : (
    <Clock className="h-5 w-5" />
  );

  return (
    <Link
      href={`/eval/${run.id}`}
      className="block bg-white rounded-lg overflow-hidden transition-all duration-200 hover:scale-[1.01]"
    >
      <div className={cn('px-4 sm:px-5 py-4 flex items-center justify-between gap-3', headerStyle)}>
        <div className="flex items-center gap-3 min-w-0">
          <span className="shrink-0">{headerIcon}</span>
          <div className="min-w-0">
            <p className="font-mono text-sm font-bold truncate">
              {run.id.slice(0, 8)}
            </p>
            <p className="text-xs opacity-90 mt-0.5 truncate">
              {run.dataset_version || 'unversioned'} · {run.trigger}
            </p>
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs font-semibold uppercase tracking-wider">
            {run.status}
          </p>
          {run.created_at && (
            <p className="hidden sm:block text-xs opacity-80 mt-0.5">
              {formatDate(run.created_at)}
            </p>
          )}
        </div>
      </div>

      <div className="p-4 sm:p-5 space-y-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
          <span>
            <span className="font-semibold text-[#111827]">
              {run.total_samples}
            </span>{' '}
            samples
          </span>
          {run.failed_samples > 0 && (
            <span>
              <span className="font-semibold text-red-600">
                {run.failed_samples}
              </span>{' '}
              failed
            </span>
          )}
          {run.git_branch && (
            <span className="flex items-center gap-1">
              <GitBranch className="h-3 w-3" />
              {run.git_branch}
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
          <ScoreBar label="Faithfulness" value={run.scores.faithfulness_avg} />
          <ScoreBar label="Answer Relevancy" value={run.scores.answer_relevancy_avg} />
          <ScoreBar label="Context Precision" value={run.scores.context_precision_avg} />
          <ScoreBar label="Context Recall" value={run.scores.context_recall_avg} />
          <ScoreBar label="Citation Coverage" value={run.scores.citation_coverage_avg} />
          <ScoreBar label="Decline Accuracy" value={run.scores.decline_accuracy_avg} />
        </div>

        {isRunning && (
          <p className="text-xs italic text-gray-400">
            Run still in progress — scores will appear when complete.
          </p>
        )}
      </div>
    </Link>
  );
}
