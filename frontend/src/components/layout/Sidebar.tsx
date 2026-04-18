'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Layers,
  Key,
  FlaskConical,
  ScrollText,
  BarChart3,
  FileText,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { label: 'Integrations', href: '/integrations', icon: Layers },
  { label: 'API Keys', href: '/api-keys', icon: Key },
  { label: 'Eval Runs', href: '/eval', icon: FlaskConical },
  { label: 'Audit Logs', href: '/audit-logs', icon: ScrollText },
  { label: 'Usage', href: '/usage', icon: BarChart3 },
  { label: 'Prompts', href: '/prompts', icon: FileText },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 flex-shrink-0 bg-[#111827] flex flex-col h-full">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-white/10">
        <Link href="/dashboard" className="flex items-center gap-1">
          <span className="text-xl font-extrabold text-white tracking-tight">
            RAGfier
          </span>
          <span className="w-2 h-2 rounded-full bg-[#3B82F6] ml-0.5 mt-0.5" />
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map(({ label, href, icon: Icon }) => {
          const isActive = pathname === href || pathname.startsWith(href + '/');
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-md transition-colors duration-150',
                isActive
                  ? 'bg-[#3B82F6] text-white'
                  : 'text-gray-300 hover:bg-white/10'
              )}
            >
              <Icon className="h-4 w-4 flex-shrink-0" />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-white/10">
        <p className="text-xs text-gray-500">RAGfier v0.1.0</p>
      </div>
    </aside>
  );
}
