import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center font-semibold px-6 rounded-md transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]',
  {
    variants: {
      variant: {
        primary:
          'bg-[#3B82F6] text-white h-14 hover:bg-[#2563EB] hover:scale-105',
        secondary:
          'bg-[#F3F4F6] text-[#111827] hover:bg-[#E5E7EB] hover:scale-105',
        outline:
          'border-4 border-[#3B82F6] text-[#3B82F6] hover:bg-[#3B82F6] hover:text-white hover:scale-105',
        destructive:
          'bg-red-500 text-white hover:bg-red-600 hover:scale-105',
        ghost:
          'text-[#111827] hover:bg-[#F3F4F6]',
      },
      size: {
        default: '',
        sm: 'h-9 px-4 text-sm',
        lg: 'h-14 px-8',
        icon: 'h-10 w-10 p-0',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
