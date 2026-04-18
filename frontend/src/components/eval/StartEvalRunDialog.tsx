'use client';

import { useForm, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  startEvalRunSchema,
  type StartEvalRunFormInput,
  type StartEvalRunFormOutput,
} from '@/lib/schemas/eval.schema';
import { startEvalRun } from '@/lib/api/eval';
import { getErrorMessage } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

interface StartEvalRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function StartEvalRunDialog({
  open,
  onOpenChange,
}: StartEvalRunDialogProps) {
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<StartEvalRunFormInput, unknown, StartEvalRunFormOutput>({
    resolver: zodResolver(startEvalRunSchema) as unknown as Resolver<
      StartEvalRunFormInput,
      unknown,
      StartEvalRunFormOutput
    >,
    defaultValues: {
      dataset_version: '',
      trigger: 'manual',
    },
  });

  const onSubmit = async (data: StartEvalRunFormOutput) => {
    try {
      const result = await startEvalRun({
        dataset_version: data.dataset_version,
        trigger: data.trigger,
      });
      await queryClient.invalidateQueries({ queryKey: ['eval-runs'] });
      toast.success(`Evaluation queued (${result.eval_run_id.slice(0, 8)}…)`);
      reset();
      onOpenChange(false);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to start evaluation'));
    }
  };

  const handleClose = () => {
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Run Evaluation</DialogTitle>
          <DialogDescription>
            Kick off an evaluation against the golden dataset. The run executes
            in the background — refresh to see progress.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 p-6 pt-0">
          <div>
            <Label htmlFor="dataset_version">Dataset version (optional)</Label>
            <Input
              id="dataset_version"
              placeholder="golden_v1"
              {...register('dataset_version')}
            />
            <p className="mt-1 text-xs text-gray-500">
              Leave blank to use the default dataset configured on the backend.
            </p>
          </div>

          <div>
            <Label htmlFor="trigger" required>
              Trigger label
            </Label>
            <Input
              id="trigger"
              placeholder="manual"
              {...register('trigger')}
            />
            <p className="mt-1 text-xs text-gray-500">
              Shown on the run card — use &quot;manual&quot;, &quot;ci&quot;, or
              a release tag.
            </p>
            {errors.trigger && (
              <p className="mt-1 text-sm text-red-500">{errors.trigger.message}</p>
            )}
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={handleClose}
              className="flex-1 h-11"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={isSubmitting}
              className="flex-1 h-11"
            >
              {isSubmitting ? 'Queuing…' : 'Start Run'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
