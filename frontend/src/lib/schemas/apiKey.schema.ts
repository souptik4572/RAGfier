import { z } from 'zod';

export const SCOPE_OPTIONS = [
  { value: 'query:read', label: 'Query (read)' },
  { value: 'documents:read', label: 'Documents (read)' },
  { value: 'documents:write', label: 'Documents (write)' },
  { value: 'analytics:read', label: 'Analytics (read)' },
] as const;

export const createApiKeySchema = z.object({
  name: z.string().min(1, 'Key name is required'),
  integration_id: z.string().uuid('Select an integration'),
  scopes: z
    .array(
      z.enum([
        'query:read',
        'documents:read',
        'documents:write',
        'analytics:read',
      ])
    )
    .min(1, 'Select at least one scope'),
  // HTML date inputs return '' when empty — treat that as undefined and convert to ISO
  expires_at: z
    .string()
    .optional()
    .transform((val) => {
      if (!val || val.trim() === '') return null;
      const parsed = new Date(val);
      return isNaN(parsed.getTime()) ? null : parsed.toISOString();
    }),
});

export type CreateApiKeyFormValues = z.infer<typeof createApiKeySchema>;
