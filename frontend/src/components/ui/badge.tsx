import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-md text-xs font-semibold px-2 py-1',
  {
    variants: {
      variant: {
        default: 'bg-[#F3F4F6] text-[#111827]',
        primary: 'bg-[#3B82F6] text-white',
        secondary: 'bg-[#10B981] text-white',
        accent: 'bg-[#F59E0B] text-[#111827]',
        destructive: 'bg-red-500 text-white',
        outline: 'border-2 border-[#E5E7EB] text-[#111827]',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
