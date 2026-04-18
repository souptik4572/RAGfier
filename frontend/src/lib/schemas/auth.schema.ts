import { z } from 'zod';

export const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

export type LoginFormValues = z.infer<typeof loginSchema>;

export const signupSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  tenant_name: z.string().min(2, 'Tenant name must be at least 2 characters'),
  tenant_slug: z
    .string()
    .min(2, 'Tenant slug must be at least 2 characters')
    .regex(
      /^[a-z0-9-]+$/,
      'Tenant slug must only contain lowercase letters, numbers, and hyphens'
    ),
});

export type SignupFormValues = z.infer<typeof signupSchema>;
