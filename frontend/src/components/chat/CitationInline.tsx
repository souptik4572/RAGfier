'use client';

interface CitationInlineProps {
  sourceId: string;
  onClick: () => void;
}

export function CitationInline({ sourceId, onClick }: CitationInlineProps) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center bg-[#F3F4F6] border-2 border-[#3B82F6] text-[#3B82F6] text-xs font-semibold rounded-md px-1 cursor-pointer hover:bg-[#3B82F6] hover:text-white transition-all duration-200 mx-0.5 align-baseline"
      aria-label={`View source ${sourceId}`}
    >
      {sourceId}
    </button>
  );
}
