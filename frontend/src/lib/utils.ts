import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(date));
}

export function truncate(str: string, n: number): string {
  if (str.length <= n) return str;
  return str.slice(0, n - 1) + '…';
}

function readString(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

export const DEFAULT_ERROR_MESSAGE = 'Something went wrong. Please try again.';

export function getErrorMessage(
  error: unknown,
  fallback: string = DEFAULT_ERROR_MESSAGE
): string {
  if (error instanceof Error) {
    const fromError = readString(error.message);
    if (fromError) return fromError;
  }

  const asString = readString(error);
  if (asString) return asString;

  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>;

    const detailValue = record.detail;
    if (Array.isArray(detailValue) && detailValue.length > 0) {
      const first = detailValue[0];
      if (first && typeof first === 'object') {
        const firstRecord = first as Record<string, unknown>;
        const msg = readString(firstRecord.msg) || readString(firstRecord.message);
        if (msg) return msg;
      }
      const firstAsString = readString(first);
      if (firstAsString) return firstAsString;
    }

    const detail = readString(detailValue);
    if (detail) return detail;

    const message = readString(record.message);
    if (message) return message;

    const errorMessage = readString(record.error);
    if (errorMessage) return errorMessage;
  }

  return fallback;
}
