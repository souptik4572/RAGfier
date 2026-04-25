const DEFAULT_ALLOWED_UPLOAD_EXTENSIONS = ['.pdf', '.md', '.markdown'];

function normalizeExtension(value: string): string | null {
  const trimmed = value.trim().toLowerCase();
  if (!trimmed) return null;
  return trimmed.startsWith('.') ? trimmed : `.${trimmed}`;
}

function parseAllowedUploadExtensions(rawValue: string | undefined): string[] {
  if (!rawValue) return DEFAULT_ALLOWED_UPLOAD_EXTENSIONS;

  const parsed = rawValue
    .split(',')
    .map(normalizeExtension)
    .filter((value): value is string => value !== null);

  const unique = Array.from(new Set(parsed));
  return unique.length > 0 ? unique : DEFAULT_ALLOWED_UPLOAD_EXTENSIONS;
}

export const allowedUploadExtensions = parseAllowedUploadExtensions(
  process.env.NEXT_PUBLIC_ALLOWED_FILE_EXTENSIONS
);

export const uploadAcceptAttribute = allowedUploadExtensions.join(',');
