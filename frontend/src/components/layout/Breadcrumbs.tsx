'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight, Home } from 'lucide-react';
import { cn } from '@/lib/utils';

const SEGMENT_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  integrations: 'Integrations',
  'api-keys': 'API Keys',
  eval: 'Eval Runs',
  'audit-logs': 'Audit Logs',
  usage: 'Usage',
  prompts: 'Prompts',
  documents: 'Documents',
  playground: 'Playground',
};

const ID_PATTERN = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

function labelForSegment(segment: string): { label: string; isId: boolean } {
  const known = SEGMENT_LABELS[segment];
  if (known) return { label: known, isId: false };
  if (ID_PATTERN.test(segment)) {
    return { label: `${segment.slice(0, 8)}…`, isId: true };
  }
  const pretty = segment
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(' ');
  return { label: pretty, isId: false };
}

interface Crumb {
  label: string;
  href: string;
  isId: boolean;
  isCurrent: boolean;
}

function buildCrumbs(pathname: string): Crumb[] {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) return [];

  const crumbs: Crumb[] = [
    {
      label: 'Dashboard',
      href: '/dashboard',
      isId: false,
      isCurrent: pathname === '/dashboard',
    },
  ];

  if (segments[0] === 'dashboard') return crumbs;

  let accumulated = '';
  segments.forEach((segment, idx) => {
    accumulated += `/${segment}`;
    const { label, isId } = labelForSegment(segment);
    crumbs.push({
      label,
      href: accumulated,
      isId,
      isCurrent: idx === segments.length - 1,
    });
  });

  return crumbs;
}

export function Breadcrumbs() {
  const pathname = usePathname();
  const crumbs = buildCrumbs(pathname);

  if (crumbs.length <= 1) return null;

  return (
    <nav aria-label="Breadcrumb" className="mb-6">
      <ol className="flex flex-wrap items-center gap-1.5">
        {crumbs.map((crumb, idx) => {
          const isFirst = idx === 0;
          const content = (
            <span
              className={cn(
                'inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider transition-colors duration-150',
                crumb.isId && 'font-mono normal-case tracking-normal',
                crumb.isCurrent
                  ? 'text-[#111827]'
                  : 'text-gray-500'
              )}
            >
              {isFirst && <Home className="h-3.5 w-3.5" aria-hidden="true" />}
              {crumb.label}
            </span>
          );

          return (
            <li key={crumb.href} className="flex items-center gap-1.5">
              {crumb.isCurrent ? (
                <span aria-current="page">{content}</span>
              ) : (
                <Link
                  href={crumb.href}
                  className="rounded-md px-1.5 py-0.5 hover:bg-white hover:text-[#3B82F6] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6]"
                >
                  {content}
                </Link>
              )}
              {idx < crumbs.length - 1 && (
                <ChevronRight
                  className="h-3 w-3 text-gray-400 shrink-0"
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
