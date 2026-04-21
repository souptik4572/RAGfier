import { type ReactNode } from 'react';

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, subtitle, action }: EmptyStateProps) {
  return (
    <div className="bg-[#F3F4F6] rounded-lg p-8 sm:p-16 flex flex-col items-center justify-center text-center">
      <div className="mb-4 sm:mb-6 text-gray-400">{icon}</div>
      <h3 className="text-lg sm:text-xl font-bold text-[#111827] mb-2">{title}</h3>
      {subtitle && (
        <p className="text-sm sm:text-base text-gray-500 max-w-sm mb-6">{subtitle}</p>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}
