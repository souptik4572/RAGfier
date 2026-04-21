'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { toast } from 'sonner';
import { signupSchema, type SignupFormValues } from '@/lib/schemas/auth.schema';
import { signup } from '@/lib/api/auth';
import { useAuthStore } from '@/lib/store/authStore';
import { getErrorMessage } from '@/lib/utils';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

export function SignupForm() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({
    resolver: zodResolver(signupSchema),
  });

  const onSubmit = async (data: SignupFormValues) => {
    try {
      const response = await signup(data);
      setAuth({
        accessToken: response.access_token,
        tenantId: response.tenant_id,
        userId: response.user_id,
        email: response.email,
      });
      document.cookie = 'ragfier-token=1; path=/; SameSite=Lax';
      router.push('/dashboard');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Signup failed'));
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      <div>
        <Label htmlFor="email" required>Email address</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          {...register('email')}
        />
        {errors.email && (
          <p className="mt-1 text-sm text-red-500">{errors.email.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="password" required>Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          placeholder="••••••••"
          {...register('password')}
        />
        {errors.password && (
          <p className="mt-1 text-sm text-red-500">{errors.password.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="tenant_name" required>Organization name</Label>
        <Input
          id="tenant_name"
          type="text"
          placeholder="Acme Corp"
          {...register('tenant_name')}
        />
        {errors.tenant_name && (
          <p className="mt-1 text-sm text-red-500">{errors.tenant_name.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="tenant_slug" required>Organization slug</Label>
        <Input
          id="tenant_slug"
          type="text"
          placeholder="acme-corp"
          {...register('tenant_slug')}
        />
        {errors.tenant_slug && (
          <p className="mt-1 text-sm text-red-500">{errors.tenant_slug.message}</p>
        )}
        <p className="mt-1 text-xs text-gray-400">
          Lowercase letters, numbers, and hyphens only
        </p>
      </div>

      <Button
        type="submit"
        variant="primary"
        className="w-full"
        disabled={isSubmitting}
      >
        {isSubmitting ? 'Creating account…' : 'Create account'}
      </Button>

      <p className="text-center text-sm text-gray-500">
        Already have an account?{' '}
        <Link
          href="/login"
          className="font-semibold text-[#3B82F6] hover:underline"
        >
          Sign in
        </Link>
      </p>
    </form>
  );
}
