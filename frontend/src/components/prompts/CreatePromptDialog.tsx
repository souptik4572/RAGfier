'use client';

import { useForm, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  createPromptSchema,
  type CreatePromptFormInput,
  type CreatePromptFormOutput,
} from '@/lib/schemas/prompt.schema';
import { createPrompt } from '@/lib/api/prompts';
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

interface CreatePromptDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultName?: string;
}

const DEFAULT_USER_TEMPLATE = `Context:\n{context}\n\nQuestion: {query}\n\nAnswer:`;

export function CreatePromptDialog({
  open,
  onOpenChange,
  defaultName = '',
}: CreatePromptDialogProps) {
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreatePromptFormInput, unknown, CreatePromptFormOutput>({
    resolver: zodResolver(createPromptSchema) as unknown as Resolver<
      CreatePromptFormInput,
      unknown,
      CreatePromptFormOutput
    >,
    defaultValues: {
      name: defaultName,
      system_prompt: '',
      user_prompt_template: DEFAULT_USER_TEMPLATE,
      metadata: '',
      global: false,
    },
  });

  const onSubmit = async (data: CreatePromptFormOutput) => {
    try {
      await createPrompt({
        name: data.name,
        system_prompt: data.system_prompt,
        user_prompt_template: data.user_prompt_template,
        metadata: data.metadata,
        global: data.global,
      });
      await queryClient.invalidateQueries({ queryKey: ['prompts'] });
      toast.success('Prompt version created');
      reset();
      onOpenChange(false);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to create prompt'));
    }
  };

  const handleClose = () => {
    reset();
    onOpenChange(false);
  };

  const textareaClass =
    'bg-[#F3F4F6] border-0 text-[#111827] rounded-md px-4 py-3 w-full focus:bg-white focus:border-2 focus:border-[#3B82F6] focus:outline-none transition-all duration-200 resize-none font-mono text-xs';

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Prompt Version</DialogTitle>
          <DialogDescription>
            Create a new version of a prompt. Templates must include the{' '}
            <code className="font-mono text-xs bg-[#F3F4F6] px-1 py-0.5 rounded">
              {'{context}'}
            </code>{' '}
            and{' '}
            <code className="font-mono text-xs bg-[#F3F4F6] px-1 py-0.5 rounded">
              {'{query}'}
            </code>{' '}
            placeholders.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 p-5 sm:p-6 pt-0">
          <div>
            <Label htmlFor="name" required>
              Prompt name
            </Label>
            <Input
              id="name"
              placeholder="rag_generation_v1"
              {...register('name')}
            />
            <p className="mt-1 text-xs text-gray-500">
              Use an existing name to add a new version, or a new name to start a
              prompt.
            </p>
            {errors.name && (
              <p className="mt-1 text-sm text-red-500">{errors.name.message}</p>
            )}
          </div>

          <div>
            <Label htmlFor="system_prompt" required>
              System prompt
            </Label>
            <textarea
              id="system_prompt"
              rows={5}
              className={textareaClass}
              placeholder="You are a careful, citation-first assistant..."
              {...register('system_prompt')}
            />
            {errors.system_prompt && (
              <p className="mt-1 text-sm text-red-500">
                {errors.system_prompt.message}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="user_prompt_template" required>
              User prompt template
            </Label>
            <textarea
              id="user_prompt_template"
              rows={7}
              className={textareaClass}
              {...register('user_prompt_template')}
            />
            {errors.user_prompt_template && (
              <p className="mt-1 text-sm text-red-500">
                {errors.user_prompt_template.message}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="metadata">Metadata (JSON, optional)</Label>
            <textarea
              id="metadata"
              rows={4}
              className={textareaClass}
              placeholder='{"model": "claude-sonnet-4-6", "temperature": 0.2, "max_tokens": 1024}'
              {...register('metadata')}
            />
            <p className="mt-1 text-xs text-gray-500">
              Invalid JSON is ignored silently.
            </p>
          </div>

          <div className="flex items-center gap-2 bg-[#F3F4F6] rounded-md px-3 py-2">
            <input
              id="global"
              type="checkbox"
              className="h-4 w-4 rounded accent-[#3B82F6]"
              {...register('global')}
            />
            <Label htmlFor="global" className="mb-0 cursor-pointer">
              Publish as global (shared across all tenants)
            </Label>
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
              {isSubmitting ? 'Creating…' : 'Create Version'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
