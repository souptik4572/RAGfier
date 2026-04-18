'use client';

import { useEffect } from 'react';
import { useForm, Controller, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  createApiKeySchema,
  SCOPE_OPTIONS,
} from '@/lib/schemas/apiKey.schema';
import {
  createApiKey,
  type ApiKeyScope,
  type ApiKeyWithSecret,
} from '@/lib/api/api-keys';
import type { Integration } from '@/lib/api/integrations';
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
import { cn } from '@/lib/utils';

type FormInput = z.input<typeof createApiKeySchema>;
type FormOutput = z.output<typeof createApiKeySchema>;

interface CreateApiKeyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  integrations: Integration[];
  onCreated: (key: ApiKeyWithSecret) => void;
}

export function CreateApiKeyDialog({
  open,
  onOpenChange,
  integrations,
  onCreated,
}: CreateApiKeyDialogProps) {
  const queryClient = useQueryClient();
  const defaultIntegrationId = integrations[0]?.id ?? '';

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors, isSubmitting },
  } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(createApiKeySchema) as unknown as Resolver<
      FormInput,
      unknown,
      FormOutput
    >,
    defaultValues: {
      name: '',
      integration_id: defaultIntegrationId,
      scopes: ['query:read'],
      expires_at: '',
    },
  });

  useEffect(() => {
    if (open) {
      reset({
        name: '',
        integration_id: defaultIntegrationId,
        scopes: ['query:read'],
        expires_at: '',
      });
    }
  }, [open, defaultIntegrationId, reset]);

  const onSubmit = async (data: FormOutput) => {
    try {
      const created = await createApiKey({
        name: data.name,
        integration_id: data.integration_id,
        scopes: data.scopes,
        expires_at: data.expires_at,
      });
      await queryClient.invalidateQueries({ queryKey: ['api-keys'] });
      toast.success('API key created');
      reset();
      onOpenChange(false);
      onCreated(created);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create API key';
      toast.error(message);
    }
  };

  const handleClose = () => {
    reset();
    onOpenChange(false);
  };

  const integrationOptions = integrations.map((i) => ({
    value: i.id,
    label: `${i.name} (${i.environment})`,
  }));

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New API Key</DialogTitle>
          <DialogDescription>
            API keys authenticate external applications calling the RAGfier API.
            The secret is shown only once on creation.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 p-6 pt-0">
          {/* Name */}
          <div>
            <Label htmlFor="name">Key name</Label>
            <Input
              id="name"
              placeholder="Production Server"
              {...register('name')}
            />
            {errors.name && (
              <p className="mt-1 text-sm text-red-500">{errors.name.message}</p>
            )}
          </div>

          {/* Integration select */}
          <div>
            <Label htmlFor="integration_id">Integration</Label>
            {integrations.length === 0 ? (
              <p className="text-sm text-red-500 mt-1">
                Create an integration first before adding API keys.
              </p>
            ) : (
              <Controller
                name="integration_id"
                control={control}
                render={({ field }) => (
                  <Select
                    value={field.value}
                    onValueChange={field.onChange}
                    options={integrationOptions}
                    placeholder="Select an integration"
                  />
                )}
              />
            )}
            {errors.integration_id && (
              <p className="mt-1 text-sm text-red-500">
                {errors.integration_id.message}
              </p>
            )}
          </div>

          {/* Scopes */}
          <div>
            <Label>Scopes</Label>
            <Controller
              name="scopes"
              control={control}
              render={({ field }) => (
                <div className="grid grid-cols-2 gap-2 mt-1">
                  {SCOPE_OPTIONS.map((option) => {
                    const checked = field.value?.includes(option.value);
                    return (
                      <label
                        key={option.value}
                        className={cn(
                          'flex items-center gap-2 px-3 py-2.5 rounded-md cursor-pointer transition-all duration-150 select-none',
                          checked
                            ? 'bg-[#3B82F6] text-white'
                            : 'bg-[#F3F4F6] text-[#111827] hover:bg-[#E5E7EB]'
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              field.onChange([
                                ...(field.value ?? []),
                                option.value,
                              ]);
                            } else {
                              field.onChange(
                                (field.value ?? []).filter(
                                  (s: ApiKeyScope) => s !== option.value
                                )
                              );
                            }
                          }}
                          className={cn(
                            'w-4 h-4 shrink-0',
                            checked ? 'accent-white' : 'accent-[#3B82F6]'
                          )}
                        />
                        <span className="text-sm font-medium">{option.label}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            />
            {errors.scopes && (
              <p className="mt-1 text-sm text-red-500">
                {errors.scopes.message}
              </p>
            )}
          </div>

          {/* Expires at */}
          <div>
            <Label htmlFor="expires_at">Expires at (optional)</Label>
            <Input id="expires_at" type="date" {...register('expires_at')} />
          </div>

          {/* Actions */}
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
              disabled={isSubmitting || integrations.length === 0}
              className="flex-1 h-11"
            >
              {isSubmitting ? 'Creating…' : 'Create API Key'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
