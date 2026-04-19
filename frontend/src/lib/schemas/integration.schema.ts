import { z } from 'zod';

export const createIntegrationSchema = z.object({
  name: z.string().min(1, 'Integration name is required'),
  environment: z.enum(['production', 'staging', 'development'], {
    required_error: 'Please select an environment',
  }),
  prompt_name: z.string().min(1, 'Please select a prompt'),
  // textarea accepts a JSON string; we parse it to a dict on the way out
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

export type CreateIntegrationFormValues = z.infer<typeof createIntegrationSchema>;
