'use client';

import { Lock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { type ChatMessage as ChatMessageType, type BackendCitation, useChatStore } from '@/lib/store/chatStore';
import { CitationInline } from './CitationInline';
import { StreamingCursor } from './StreamingCursor';

interface ChatMessageProps {
  message: ChatMessageType;
}

function parseContentWithCitations(
  content: string,
  citations: BackendCitation[],
  onCitationClick: (sourceId: string) => void
): React.ReactNode[] {
  // Build a map from [SOURCE_N] index to citation source_id
  const parts = content.split(/(\[SOURCE_\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[SOURCE_(\d+)\]$/);
    if (match) {
      const idx = parseInt(match[1], 10) - 1;
      const citation = citations[idx];
      const sourceId = citation?.source_id ?? part;
      return (
        <CitationInline
          key={i}
          sourceId={sourceId}
          onClick={() => onCitationClick(sourceId)}
        />
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export function ChatMessage({ message }: ChatMessageProps) {
  const { setActiveCitation } = useChatStore();
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="bg-[#3B82F6] text-white rounded-lg px-4 py-3 max-w-[70%] text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  const isThinking = message.isStreaming && message.content === '';

  return (
    <div className="flex justify-start mb-4">
      <div
        className={cn(
          'rounded-lg px-4 py-3 max-w-[80%] text-sm text-[#111827] leading-relaxed',
          message.declined
            ? 'bg-[#FEF3C7] border-2 border-[#F59E0B]'
            : 'bg-white'
        )}
      >
        {message.declined && (
          <div className="flex items-center gap-1.5 mb-2 text-[#F59E0B] font-semibold text-xs uppercase tracking-wide">
            <Lock className="h-3.5 w-3.5" />
            <span>Response declined</span>
          </div>
        )}

        {isThinking ? (
          <span className="text-gray-400 italic">Thinking…</span>
        ) : (
          <>
            {parseContentWithCitations(message.content, message.citations, setActiveCitation)}
            {message.isStreaming && <StreamingCursor />}
          </>
        )}
      </div>
    </div>
  );
}
