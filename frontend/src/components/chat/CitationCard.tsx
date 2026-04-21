'use client';

import { forwardRef } from 'react';
import { cn } from '@/lib/utils';
import type { BackendCitation } from '@/lib/store/chatStore';

interface CitationCardProps {
  citation: BackendCitation;
  isActive: boolean;
  isPulsing?: boolean;
  onClick: () => void;
}

export const CitationCard = forwardRef<HTMLDivElement, CitationCardProps>(
  function CitationCard(
    { citation, isActive, isPulsing = false, onClick },
    ref
  ) {
    const { metadata, content, source_id, rerank_score } = citation;

    const displayTitle =
      metadata.document_title ??
      metadata.source.split('/').pop() ??
      metadata.source;

    const snippet = content.length > 150 ? content.slice(0, 150) + '…' : content;

    return (
      <div
        ref={ref}
        onClick={onClick}
        className={cn(
          'rounded-lg p-4 cursor-pointer transition-all duration-300 hover:scale-[1.02] border-2',
          isPulsing
            ? 'bg-blue-50 border-[#3B82F6]'
            : isActive
            ? 'bg-white border-[#3B82F6]'
            : 'bg-white border-transparent'
        )}
      >
        {/* Source ID badge */}
        <div className="mb-2">
          <span className="bg-[#3B82F6] text-white text-xs font-semibold rounded-md px-2 py-0.5">
            {source_id}
          </span>
        </div>

        {/* Document title */}
        <p className="text-sm font-semibold text-[#111827] leading-snug">
          {displayTitle}
        </p>

        {/* Page number */}
        {metadata.page_number !== undefined && (
          <p className="text-xs text-gray-400 mt-0.5">
            Page {metadata.page_number}
          </p>
        )}

        {/* Section heading */}
        {metadata.section_heading && (
          <p className="text-xs text-gray-500 mt-1 italic">
            {metadata.section_heading}
          </p>
        )}

        {/* Content snippet */}
        <p className="text-sm text-[#111827] mt-2 leading-relaxed">{snippet}</p>

        {/* Rerank score bar */}
        {rerank_score !== undefined && (
          <div className="mt-3">
            <p className="text-xs text-gray-400 mb-1">Relevance</p>
            <div className="bg-[#F3F4F6] h-1 rounded-full overflow-hidden">
              <div
                className="bg-[#3B82F6] h-full rounded-full transition-all duration-300"
                style={{ width: `${Math.min(rerank_score * 100, 100)}%` }}
              />
            </div>
          </div>
        )}
      </div>
    );
  }
);
