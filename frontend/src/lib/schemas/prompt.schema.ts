import { z } from 'zod';

export const createPromptSchema = z.object({
  name: z
    .string()
    .min(1, 'Prompt name is required')
    .max(120, 'Name must be 120 characters or fewer'),
  system_prompt: z
    .string()
    .min(1, 'System prompt is required'),
  user_prompt_template: z
    .string()
    .min(1, 'User prompt template is required')
    .refine((val) => val.includes('{context}'), {
      message: 'Template must include the {context} placeholder',
    })
    .refine((val) => val.includes('{query}'), {
      message: 'Template must include the {query} placeholder',
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
  global: z.boolean().optional().default(false),
});

export type CreatePromptFormInput = z.input<typeof createPromptSchema>;
export type CreatePromptFormOutput = z.output<typeof createPromptSchema>;
