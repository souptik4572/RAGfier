import * as React from 'react';
import { cn } from '@/lib/utils';

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          'bg-[#F3F4F6] border-0 text-[#111827] rounded-md px-4 py-3 w-full',
          'focus:bg-white focus:border-2 focus:border-[#3B82F6] focus:outline-none',
          'focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]',
          'transition-all duration-200',
          'placeholder:text-gray-400',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = 'Input';

export { Input };
