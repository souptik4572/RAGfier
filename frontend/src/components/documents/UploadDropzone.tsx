'use client';

import { useCallback, useRef, useState } from 'react';
import { Upload, FileUp, FileText, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useJobPoller } from '@/lib/hooks/useJobPoller';
import { cn, getErrorMessage } from '@/lib/utils';

interface UploadDropzoneProps {
  onUpload: (file: File, title?: string) => Promise<void>;
  pendingJobId: string | null;
  integrationId: string;
}

const ALLOWED_EXTENSIONS = ['.pdf', '.md', '.markdown'];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadDropzone({
  onUpload,
  pendingJobId,
  integrationId,
}: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [stagedFile, setStagedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: jobStatus } = useJobPoller(pendingJobId, integrationId);

  const isProcessing =
    !!pendingJobId &&
    !!jobStatus?.status &&
    !['completed', 'failed'].includes(jobStatus.status);

  const isBusy = isSubmitting || isProcessing;

  const stageFiles = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];

    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      toast.error('Only PDF and Markdown files are supported');
      return;
    }

    setStagedFile(file);
  }, []);

  const handleSubmit = async () => {
    if (!stagedFile) return;
    setIsSubmitting(true);
    try {
      await onUpload(stagedFile);
      toast.success(`${stagedFile.name} uploaded — processing started`);
      setStagedFile(null);
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    } catch (err) {
      toast.error(getErrorMessage(err, 'Upload failed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRemoveStaged = () => {
    setStagedFile(null);
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!isBusy) setIsDragging(true);
  };

  const onDragLeave = () => setIsDragging(false);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (isBusy) return;
    stageFiles(e.dataTransfer.files);
  };

  const onDropzoneClick = () => {
    if (!isBusy && !stagedFile) {
      inputRef.current?.click();
    }
  };

  const progressPercent =
    isProcessing && jobStatus?.total_chunks && jobStatus.total_chunks > 0
      ? Math.round((jobStatus.processed_chunks / jobStatus.total_chunks) * 100)
      : null;

  return (
    <div className="space-y-4">
      <div
        onClick={onDropzoneClick}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={cn(
          'border-4 border-dashed rounded-lg p-6 sm:p-12 flex flex-col items-center justify-center text-center transition-all duration-200',
          stagedFile
            ? 'border-[#10B981] bg-[#F0FDF4]'
            : 'border-[#3B82F6]',
          !stagedFile && (isDragging ? 'bg-blue-50' : 'bg-white'),
          isBusy
            ? 'opacity-70 cursor-not-allowed'
            : stagedFile
            ? 'cursor-default'
            : 'cursor-pointer hover:bg-[#F3F4F6]'
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.md,.markdown"
          className="hidden"
          onChange={(e) => stageFiles(e.target.files)}
          disabled={isBusy}
        />

        {stagedFile ? (
          <div className="w-full max-w-md flex items-center gap-4 bg-white rounded-lg p-4">
            <div className="w-12 h-12 rounded-md bg-[#10B981] flex items-center justify-center shrink-0">
              <FileText className="h-6 w-6 text-white" />
            </div>
            <div className="flex-1 min-w-0 text-left">
              <p className="font-semibold text-[#111827] truncate">
                {stagedFile.name}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                {formatBytes(stagedFile.size)} · Ready to submit
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleRemoveStaged();
              }}
              disabled={isBusy}
              className="p-2 rounded-md text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors duration-150 disabled:opacity-50 shrink-0"
              aria-label="Remove file"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <>
            <div className="w-16 h-16 rounded-full bg-[#F3F4F6] flex items-center justify-center mb-4">
              {isProcessing ? (
                <Upload className="h-8 w-8 text-[#3B82F6] animate-bounce" />
              ) : (
                <FileUp className="h-8 w-8 text-[#3B82F6]" />
              )}
            </div>

            <p className="text-lg font-bold text-[#111827]">
              {isProcessing
                ? `Processing: ${jobStatus?.status}…`
                : 'Drop files here or click to select'}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              Supports PDF and Markdown files
            </p>

            {isProcessing && progressPercent !== null && (
              <div className="mt-4 w-48">
                <div className="bg-[#F3F4F6] h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-[#3B82F6] h-full rounded-full transition-all duration-300"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  {progressPercent}% chunks processed
                </p>
              </div>
            )}

            {pendingJobId && jobStatus?.status === 'failed' && (
              <p className="mt-3 text-sm text-red-500 font-semibold">
                Processing failed
                {jobStatus.error_message ? `: ${jobStatus.error_message}` : ''}
              </p>
            )}

            {pendingJobId && jobStatus?.status === 'completed' && (
              <p className="mt-3 text-sm text-[#10B981] font-semibold">
                Processing complete
              </p>
            )}
          </>
        )}
      </div>

      {stagedFile && (
        <div className="flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={handleRemoveStaged}
            disabled={isBusy}
            className="h-11 px-6"
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={handleSubmit}
            disabled={isBusy}
            className="h-11 px-6 flex items-center gap-2"
          >
            <Upload className="h-4 w-4" />
            {isSubmitting ? 'Submitting…' : 'Submit for ingestion'}
          </Button>
        </div>
      )}
    </div>
  );
}
