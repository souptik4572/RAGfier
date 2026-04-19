'use client';

import { useForm, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { z } from 'zod';
import {
  createIntegrationSchema,
} from '@/lib/schemas/integration.schema';
import { createIntegration } from '@/lib/api/integrations';
import { listPrompts } from '@/lib/api/prompts';
import { getErrorMessage } from '@/lib/utils';

const DEFAULT_PROMPT_NAME = 'rag_generation_v1';

// RHF works with raw input types (pre-transform); output goes to createIntegration
type FormInput = z.input<typeof createIntegrationSchema>;
type FormOutput = z.output<typeof createIntegrationSchema>;
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

interface CreateIntegrationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateIntegrationDialog({
  open,
  onOpenChange,
}: CreateIntegrationDialogProps) {
  const queryClient = useQueryClient();
  const { data: prompts = [] } = useQuery({
    queryKey: ['prompts'],
    queryFn: listPrompts,
    enabled: open,
  });

  const promptOptions = (() => {
    const seen = new Set<string>();
    const options: { value: string; label: string }[] = [];
    for (const p of prompts) {
      if (seen.has(p.name)) continue;
      seen.add(p.name);
      options.push({
        value: p.name,
        label: p.source === 'yaml' ? `${p.name} (default)` : p.name,
      });
    }
    if (!seen.has(DEFAULT_PROMPT_NAME)) {
      options.unshift({
        value: DEFAULT_PROMPT_NAME,
        label: `${DEFAULT_PROMPT_NAME} (default)`,
      });
    }
    return options;
  })();

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(createIntegrationSchema) as unknown as Resolver<
      FormInput,
      unknown,
      FormOutput
    >,
    defaultValues: {
      environment: 'development',
      prompt_name: DEFAULT_PROMPT_NAME,
      metadata: '',
    },
  });

  const onSubmit = async (data: FormOutput) => {
    try {
      await createIntegration(data);
      await queryClient.invalidateQueries({ queryKey: ['integrations'] });
      toast.success('Integration created successfully');
      reset();
      onOpenChange(false);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to create integration'));
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
          <DialogTitle>New Integration</DialogTitle>
          <DialogDescription>
            Create a new RAG integration to start ingesting documents.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 p-6 pt-0">
          <div>
            <Label htmlFor="name" required>Integration name</Label>
            <Input
              id="name"
              placeholder="My RAG Integration"
              {...register('name')}
            />
            {errors.name && (
              <p className="mt-1 text-sm text-red-500">{errors.name.message}</p>
            )}
          </div>

          <div>
            <Label htmlFor="environment" required>Environment</Label>
            <Select
              defaultValue="development"
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
            <Label htmlFor="prompt_name" required>Prompt</Label>
            <Select
              defaultValue={DEFAULT_PROMPT_NAME}
              onValueChange={(val) => setValue('prompt_name', val)}
              options={promptOptions}
              placeholder="Select prompt"
            />
            {errors.prompt_name && (
              <p className="mt-1 text-sm text-red-500">
                {errors.prompt_name.message}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="metadata">Metadata (optional)</Label>
            <textarea
              id="metadata"
              rows={3}
              className="bg-[#F3F4F6] border-0 text-[#111827] rounded-md px-4 py-3 w-full focus:bg-white focus:border-2 focus:border-[#3B82F6] focus:outline-none transition-all duration-200 resize-none font-sans text-sm"
              placeholder="Optional description or metadata..."
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
              {isSubmitting ? 'Creating…' : 'Create Integration'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
