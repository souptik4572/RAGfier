'use client';

import { useCallback, useRef, useState } from 'react';
import { Upload, FileUp } from 'lucide-react';
import { toast } from 'sonner';
import { useJobPoller } from '@/lib/hooks/useJobPoller';
import { cn } from '@/lib/utils';

interface UploadDropzoneProps {
  onUpload: (file: File, title?: string) => Promise<void>;
  pendingJobId: string | null;
  integrationId: string;
}

export function UploadDropzone({
  onUpload,
  pendingJobId,
  integrationId,
}: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: jobStatus } = useJobPoller(pendingJobId, integrationId);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];

      const allowed = ['.pdf', '.md', '.markdown'];
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!allowed.includes(ext)) {
        toast.error('Only PDF and Markdown files are supported');
        return;
      }

      setIsUploading(true);
      try {
        await onUpload(file);
        toast.success(`${file.name} uploaded successfully`);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Upload failed';
        toast.error(message);
      } finally {
        setIsUploading(false);
        if (inputRef.current) {
          inputRef.current.value = '';
        }
      }
    },
    [onUpload]
  );

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = () => setIsDragging(false);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const onClick = () => inputRef.current?.click();

  const isProcessing =
    pendingJobId &&
    jobStatus?.status &&
    !['completed', 'failed'].includes(jobStatus.status);

  return (
    <div
      onClick={onClick}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn(
        'border-4 border-dashed rounded-lg p-12 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200',
        isDragging
          ? 'border-[#3B82F6] bg-blue-50'
          : 'border-[#3B82F6] bg-white hover:bg-[#F3F4F6]',
        (isUploading || isProcessing) && 'opacity-70 cursor-not-allowed'
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.md,.markdown"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
        disabled={isUploading || !!isProcessing}
      />

      <div className="w-16 h-16 rounded-full bg-[#F3F4F6] flex items-center justify-center mb-4">
        {isUploading || isProcessing ? (
          <Upload className="h-8 w-8 text-[#3B82F6] animate-bounce" />
        ) : (
          <FileUp className="h-8 w-8 text-[#3B82F6]" />
        )}
      </div>

      <p className="text-lg font-bold text-[#111827]">
        {isUploading
          ? 'Uploading…'
          : isProcessing
          ? `Processing: ${jobStatus?.status}…`
          : 'Drop files here or click to upload'}
      </p>
      <p className="mt-1 text-sm text-gray-500">
        Supports PDF and Markdown files
      </p>
    </div>
  );
}
