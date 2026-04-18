'use client';

import { useRouter } from 'next/navigation';
import { LogOut } from 'lucide-react';
import { useAuthStore } from '@/lib/store/authStore';
import { Button } from '@/components/ui/button';

interface TopbarProps {
  title?: string;
}

export function Topbar({ title }: TopbarProps) {
  const router = useRouter();
  const { email, clearAuth } = useAuthStore();

  const handleLogout = () => {
    clearAuth();
    document.cookie = 'ragfier-token=; Max-Age=0; path=/';
    router.push('/login');
  };

  return (
    <header className="h-16 flex-shrink-0 bg-white border-b-2 border-[#F3F4F6] flex items-center justify-between px-8">
      <div>
        {title && (
          <h1 className="text-lg font-bold text-[#111827] tracking-tight">
            {title}
          </h1>
        )}
      </div>
      <div className="flex items-center gap-4">
        {email && (
          <span className="text-sm font-medium text-gray-500">{email}</span>
        )}
        <Button
          variant="outline"
          onClick={handleLogout}
          className="flex items-center gap-2 h-9 px-4 text-sm"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
    </header>
  );
}
