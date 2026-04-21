'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FlaskConical, Play } from 'lucide-react';
import { listEvalRuns } from '@/lib/api/eval';
import { getErrorMessage } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/shared/EmptyState';
import { LoadingBlock } from '@/components/shared/LoadingBlock';
import { Button } from '@/components/ui/button';
import { EvalRunCard } from '@/components/eval/EvalRunCard';
import { StartEvalRunDialog } from '@/components/eval/StartEvalRunDialog';

export default function EvalRunsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data: runs, isLoading, error } = useQuery({
    queryKey: ['eval-runs'],
    queryFn: listEvalRuns,
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasRunning = data?.some((r) => r.status === 'running');
      return hasRunning ? 5000 : false;
    },
  });

  return (
    <div>
      <PageHeader
        title="Eval Runs"
        subtitle="Evaluation results across datasets and releases"
        action={
          <Button
            variant="primary"
            size="sm"
            onClick={() => setDialogOpen(true)}
            className="gap-2"
          >
            <Play className="h-4 w-4" />
            Run Evaluation
          </Button>
        }
      />

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-48 w-full bg-white rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <EmptyState
          icon={<FlaskConical className="h-16 w-16 text-gray-400" />}
          title="Could not load eval runs"
          subtitle={getErrorMessage(error, 'Please try again.')}
        />
      ) : runs && runs.length > 0 ? (
        <div className="space-y-4">
          {runs.map((run) => (
            <EvalRunCard key={run.id} run={run} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<FlaskConical className="h-16 w-16 text-gray-400" />}
          title="No eval runs yet"
          subtitle="Trigger an evaluation to see results here."
          action={
            <Button
              variant="primary"
              onClick={() => setDialogOpen(true)}
              className="gap-2"
            >
              <Play className="h-4 w-4" />
              Run Evaluation
            </Button>
          }
        />
      )}

      <StartEvalRunDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
