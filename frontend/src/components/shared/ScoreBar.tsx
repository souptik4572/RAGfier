import { cn } from '@/lib/utils';

interface ScoreBarProps {
  label: string;
  value: number | null | undefined;
  max?: number;
  threshold?: number;
}

export function ScoreBar({
  label,
  value,
  max = 1,
  threshold = 0.7,
}: ScoreBarProps) {
  const hasValue = typeof value === 'number';
  const ratio = hasValue ? Math.max(0, Math.min(value / max, 1)) : 0;
  const percent = Math.round(ratio * 100);

  const fillColor = !hasValue
    ? 'bg-[#E5E7EB]'
    : value >= threshold
    ? 'bg-[#10B981]'
    : value >= threshold * 0.6
    ? 'bg-[#F59E0B]'
    : 'bg-red-400';

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-[#111827]">{label}</span>
        <span className="text-xs font-mono text-gray-500">
          {hasValue ? value.toFixed(2) : '—'}
        </span>
      </div>
      <div className="bg-[#F3F4F6] h-1.5 rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-300', fillColor)}
          style={{ width: hasValue ? `${percent}%` : '0%' }}
        />
      </div>
    </div>
  );
}
