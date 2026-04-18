import { z } from 'zod';

export const startEvalRunSchema = z.object({
  dataset_version: z
    .string()
    .optional()
    .transform((val) => (val && val.trim() !== '' ? val.trim() : undefined)),
  trigger: z
    .string()
    .min(1, 'Trigger label is required')
    .max(40, 'Trigger must be 40 characters or fewer'),
});

export type StartEvalRunFormInput = z.input<typeof startEvalRunSchema>;
export type StartEvalRunFormOutput = z.output<typeof startEvalRunSchema>;
