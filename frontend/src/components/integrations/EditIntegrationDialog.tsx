'use client';

import { useEffect } from 'react';
import { useForm, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { z } from 'zod';
import {
  updateIntegration,
  type Integration,
} from '@/lib/api/integrations';
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
import { Select } from '@/components/ui/select';

const editIntegrationSchema = z.object({
  name: z.string().min(1, 'Integration name is required'),
  environment: z.enum(['production', 'staging', 'development'], {
    required_error: 'Please select an environment',
  }),
  metadata: z
    .string()
    .optional()
    .transform((val) => {
      if (!val || val.trim() === '') return {};
      try {
        return JSON.parse(val) as Record<string, unknown>;
      } catch {
        return {};
      }
    }),
});

type FormInput = z.input<typeof editIntegrationSchema>;
type FormOutput = z.output<typeof editIntegrationSchema>;

interface EditIntegrationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  integration: Integration;
}

export function EditIntegrationDialog({
  open,
  onOpenChange,
  integration,
}: EditIntegrationDialogProps) {
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(editIntegrationSchema) as unknown as Resolver<
      FormInput,
      unknown,
      FormOutput
    >,
    defaultValues: {
      name: integration.name,
      environment: integration.environment,
      metadata:
        integration.metadata && Object.keys(integration.metadata).length > 0
          ? JSON.stringify(integration.metadata, null, 2)
          : '',
    },
  });

  useEffect(() => {
    if (open) {
      reset({
        name: integration.name,
        environment: integration.environment,
        metadata:
          integration.metadata &&
          Object.keys(integration.metadata).length > 0
            ? JSON.stringify(integration.metadata, null, 2)
            : '',
      });
    }
  }, [open, integration, reset]);

  const onSubmit = async (data: FormOutput) => {
    try {
      await updateIntegration(integration.id, data);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['integrations'] }),
        queryClient.invalidateQueries({
          queryKey: ['integration', integration.id],
        }),
      ]);
      toast.success('Integration updated');
      onOpenChange(false);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to update integration'));
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
          <DialogTitle>Edit Integration</DialogTitle>
          <DialogDescription>
            Update the integration&apos;s name, environment, or metadata.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 p-6 pt-0">
          <div>
            <Label htmlFor="name" required>
              Integration name
            </Label>
            <Input id="name" {...register('name')} />
            {errors.name && (
              <p className="mt-1 text-sm text-red-500">{errors.name.message}</p>
            )}
          </div>

          <div>
            <Label htmlFor="environment" required>
              Environment
            </Label>
            <Select
              defaultValue={integration.environment}
              onValueChange={(val) =>
                setValue(
                  'environment',
                  val as 'production' | 'staging' | 'development'
                )
              }
              options={[
                { value: 'development', label: 'Development' },
                { value: 'staging', label: 'Staging' },
                { value: 'production', label: 'Production' },
              ]}
              placeholder="Select environment"
            />
            {errors.environment && (
              <p className="mt-1 text-sm text-red-500">
                {errors.environment.message}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="metadata">Metadata (JSON)</Label>
            <textarea
              id="metadata"
              rows={4}
              className="bg-[#F3F4F6] border-0 text-[#111827] rounded-md px-4 py-3 w-full focus:bg-white focus:border-2 focus:border-[#3B82F6] focus:outline-none transition-all duration-200 resize-none font-mono text-sm"
              placeholder='{"owner": "team-name"}'
              {...register('metadata')}
            />
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
              {isSubmitting ? 'Saving…' : 'Save Changes'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
