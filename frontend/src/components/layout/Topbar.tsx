'use client';

import { useRouter } from 'next/navigation';
import { LogOut, Menu } from 'lucide-react';
import { useAuthStore } from '@/lib/store/authStore';
import { useUiStore } from '@/lib/store/uiStore';
import { Button } from '@/components/ui/button';

interface TopbarProps {
  title?: string;
}

export function Topbar({ title }: TopbarProps) {
  const router = useRouter();
  const { email, clearAuth } = useAuthStore();
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);

  const handleLogout = () => {
    clearAuth();
    document.cookie = 'ragfier-token=; Max-Age=0; path=/';
    router.push('/login');
  };

  return (
    <header className="h-16 shrink-0 bg-white border-b-2 border-[#F3F4F6] flex items-center justify-between px-4 sm:px-6 lg:px-8 gap-3">
      <div className="flex items-center gap-2 min-w-0">
        <button
          onClick={toggleSidebar}
          className="lg:hidden p-2 -ml-2 rounded-md text-[#111827] hover:bg-[#F3F4F6] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]"
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </button>
        {title && (
          <h1 className="text-base sm:text-lg font-bold text-[#111827] tracking-tight truncate">
            {title}
          </h1>
        )}
      </div>
      <div className="flex items-center gap-2 sm:gap-4 shrink-0">
        {email && (
          <span className="hidden md:inline text-sm font-medium text-gray-500 truncate max-w-[200px]">
            {email}
          </span>
        )}
        <Button
          variant="outline"
          onClick={handleLogout}
          className="flex items-center gap-2 h-9 px-3 sm:px-4 text-sm"
          aria-label="Logout"
        >
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Logout</span>
        </Button>
      </div>
    </header>
  );
}
