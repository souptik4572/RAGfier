'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { toast } from 'sonner';
import { loginSchema, type LoginFormValues } from '@/lib/schemas/auth.schema';
import { login } from '@/lib/api/auth';
import { useAuthStore } from '@/lib/store/authStore';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

export function LoginForm() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormValues) => {
    try {
      const response = await login(data);
      setAuth({
        accessToken: response.access_token,
        tenantId: response.tenant_id,
        userId: response.user_id,
        email: response.email,
      });
      document.cookie = 'ragfier-token=1; path=/; SameSite=Lax';
      router.push('/dashboard');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed';
      toast.error(message);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      <div>
        <Label htmlFor="email">Email address</Label>
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
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          {...register('password')}
        />
        {errors.password && (
          <p className="mt-1 text-sm text-red-500">{errors.password.message}</p>
        )}
      </div>

      <Button
        type="submit"
        variant="primary"
        className="w-full"
        disabled={isSubmitting}
      >
        {isSubmitting ? 'Signing in…' : 'Sign in'}
      </Button>

      <p className="text-center text-sm text-gray-500">
        Don&apos;t have an account?{' '}
        <Link
          href="/signup"
          className="font-semibold text-[#3B82F6] hover:underline"
        >
          Sign up
        </Link>
      </p>
    </form>
  );
}
