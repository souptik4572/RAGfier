'use client';

import { useRef, useEffect, useState } from 'react';
import { Send } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/lib/store/chatStore';
import { useStreamQuery } from '@/lib/hooks/useStreamQuery';
import { ChatMessage } from './ChatMessage';
import { CitationCard } from './CitationCard';

interface ChatWindowProps {
  integrationId: string;
}

export function ChatWindow({ integrationId }: ChatWindowProps) {
  const {
    messages,
    activeCitationSourceId,
    citationFocusNonce,
    setActiveCitation,
    clearChat,
  } = useChatStore();
  const { streamQuery } = useStreamQuery();

  const [input, setInput] = useState('');
  const [matchCount, setMatchCount] = useState(3);
  const [rerank, setRerank] = useState(true);
  const [pulsingSourceId, setPulsingSourceId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const citationRefs = useRef<Map<string, HTMLDivElement | null>>(new Map());

  const isAnyStreaming = messages.some((m) => m.isStreaming);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Scroll the sidebar to the focused citation and pulse-highlight it
  useEffect(() => {
    if (citationFocusNonce === 0 || !activeCitationSourceId) return;
    const el = citationRefs.current.get(activeCitationSourceId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    setPulsingSourceId(activeCitationSourceId);
    const timer = setTimeout(() => setPulsingSourceId(null), 1400);
    return () => clearTimeout(timer);
  }, [citationFocusNonce, activeCitationSourceId]);

  // Auto-resize textarea
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isAnyStreaming) return;
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    await streamQuery(integrationId, trimmed, { matchCount, rerank });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Gather citations from the last assistant message that has them
  const activeCitations = (() => {
    const assistantMessages = messages.filter((m) => m.role === 'assistant' && m.citations.length > 0);
    return assistantMessages.length > 0
      ? assistantMessages[assistantMessages.length - 1].citations
      : [];
  })();

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-220px)] min-h-[500px]">
      {/* Chat area — left 2/3 on desktop, full on mobile */}
      <div className="flex-1 lg:basis-2/3 bg-white rounded-lg flex flex-col overflow-hidden min-h-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center text-gray-400">
              <p className="text-lg font-semibold text-[#111827] mb-1">Ask anything</p>
              <p className="text-sm">Send a query to start exploring your documents.</p>
            </div>
          )}
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div className="bg-[#F3F4F6] border-t-2 border-[#E5E7EB] p-3 sm:p-4">
          {/* Controls row */}
          <div className="flex items-center gap-4 mb-3">
            <label className="flex items-center gap-1.5 text-xs font-semibold text-[#111827]">
              Results
              <select
                value={matchCount}
                onChange={(e) => setMatchCount(Number(e.target.value))}
                className="ml-1 bg-white border-0 rounded-md text-xs px-2 py-1 text-[#111827] focus:outline-none focus:border-2 focus:border-[#3B82F6] focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]"
                aria-label="Number of results to retrieve"
              >
                {[3, 5, 10, 20].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-1.5 text-xs font-semibold text-[#111827] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rerank}
                onChange={(e) => setRerank(e.target.checked)}
                className="accent-[#3B82F6] w-3.5 h-3.5"
              />
              Rerank
            </label>

            {messages.length > 0 && (
              <button
                onClick={clearChat}
                className="ml-auto text-xs text-gray-400 hover:text-[#111827] transition-colors duration-150 rounded-md px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]"
              >
                Clear chat
              </button>
            )}
          </div>

          {/* Textarea + send */}
          <div className="flex items-end gap-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your documents…"
              rows={1}
              disabled={isAnyStreaming}
              className={cn(
                'flex-1 resize-none rounded-md bg-[#F3F4F6] border-0 px-4 py-3 text-sm text-[#111827] placeholder:text-gray-400 transition-all duration-150',
                'focus:outline-none focus:bg-white focus:border-2 focus:border-[#3B82F6]',
                'focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]',
                'disabled:opacity-60 disabled:cursor-not-allowed'
              )}
              aria-label="Query input"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isAnyStreaming}
              aria-label="Send message"
              className={cn(
                'bg-[#3B82F6] text-white h-12 sm:h-14 rounded-md hover:bg-[#2563EB] hover:scale-105 transition-all duration-200 font-semibold px-4 sm:px-6',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]',
                'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:bg-[#3B82F6]',
                'flex items-center gap-2 shrink-0'
              )}
            >
              <Send className="h-4 w-4" />
              <span className="hidden sm:inline">Send</span>
            </button>
          </div>
        </div>
      </div>

      {/* Citation sidebar — right 1/3 on desktop, below on mobile */}
      <div className="lg:basis-1/3 lg:max-h-none max-h-60 bg-[#F3F4F6] rounded-lg p-4 overflow-y-auto flex flex-col gap-3 shrink-0 lg:shrink">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">
          Sources
        </p>
        {activeCitations.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-center text-gray-400 text-sm py-8">
            Citations will appear here after your first query.
          </div>
        ) : (
          activeCitations.map((citation) => (
            <CitationCard
              key={citation.chunk_id}
              ref={(el) => {
                citationRefs.current.set(citation.source_id, el);
              }}
              citation={citation}
              isActive={activeCitationSourceId === citation.source_id}
              isPulsing={pulsingSourceId === citation.source_id}
              onClick={() =>
                setActiveCitation(
                  activeCitationSourceId === citation.source_id ? null : citation.source_id
                )
              }
            />
          ))
        )}
      </div>
    </div>
  );
}
