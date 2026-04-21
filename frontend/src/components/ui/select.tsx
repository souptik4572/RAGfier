'use client';

import * as React from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  options: SelectOption[];
  placeholder?: string;
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
  className?: string;
}

function Select({
  options,
  placeholder = 'Select an option',
  defaultValue,
  value,
  onValueChange,
  disabled,
  className,
}: SelectProps) {
  return (
    <SelectPrimitive.Root
      defaultValue={defaultValue}
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger
        className={cn(
          'flex items-center justify-between',
          'bg-[#F3F4F6] border-0 text-[#111827] rounded-md px-4 py-3 w-full',
          'focus:bg-white focus:border-2 focus:border-[#3B82F6] focus:outline-none',
          'focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]',
          'transition-all duration-200',
          'data-[placeholder]:text-gray-400',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          className
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown className="h-4 w-4 text-gray-400" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>

      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className={cn(
            'relative z-50 min-w-(--radix-select-trigger-width) max-h-(--radix-select-content-available-height) overflow-hidden',
            'bg-white rounded-lg border-2 border-[#E5E7EB]',
            'data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
            'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95'
          )}
          position="popper"
          sideOffset={4}
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className={cn(
                  'relative flex w-full cursor-pointer select-none items-center rounded-md pl-4 pr-10 py-2 text-sm font-medium',
                  'text-[#111827] hover:bg-[#F3F4F6]',
                  'focus:bg-[#F3F4F6] focus:outline-none',
                  'data-[disabled]:pointer-events-none data-[disabled]:opacity-50'
                )}
              >
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator className="absolute right-3 inline-flex items-center">
                  <Check className="h-4 w-4 text-[#3B82F6]" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

export { Select };
