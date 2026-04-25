'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { ArrowDown, ArrowUp, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/lib/store/chatStore';
import { useStreamQuery } from '@/lib/hooks/useStreamQuery';
import { ChatMessage } from './ChatMessage';
import { CitationCard } from './CitationCard';

interface ChatWindowProps {
  integrationId: string;
}

const SCROLL_BOTTOM_THRESHOLD = 80;

const EXAMPLE_PROMPTS = [
  'Summarize the key points in plain language.',
  'What are the main findings?',
  'Compare the perspectives discussed.',
  'List the most important takeaways.',
];

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
  const [stickToBottom, setStickToBottom] = useState(true);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const citationRefs = useRef<Map<string, HTMLDivElement | null>>(new Map());

  const isAnyStreaming = messages.some((m) => m.isStreaming);
  const messageCount = messages.length;
  const lastMessage = messages[messageCount - 1];
  const lastContent = lastMessage?.content ?? '';

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setStickToBottom(distanceFromBottom < SCROLL_BOTTOM_THRESHOLD);
  }, []);

  // Auto-scroll only while user is anchored near the bottom.
  // Smooth scroll on new messages; instant during token streams to avoid jitter.
  useEffect(() => {
    if (!stickToBottom) return;
    const behavior = isAnyStreaming ? 'auto' : 'smooth';
    messagesEndRef.current?.scrollIntoView({ behavior, block: 'end' });
  }, [messageCount, lastContent, isAnyStreaming, stickToBottom]);

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
      <div className="flex-1 lg:basis-2/3 bg-white rounded-lg flex flex-col overflow-hidden min-h-0 relative">
        {/* Messages */}
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-4 sm:p-6"
        >
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center px-4">
              <div className="w-12 h-12 rounded-2xl bg-linear-to-br from-[#3B82F6] to-[#1E40AF] flex items-center justify-center shadow-sm mb-4">
                <Sparkles className="h-6 w-6 text-white" />
              </div>
              <p className="text-xl font-semibold text-[#111827] mb-1">
                How can I help today?
              </p>
              <p className="text-sm text-gray-500 mb-6">
                Ask a question about your documents to get started.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
                {EXAMPLE_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => {
                      setInput(prompt);
                      textareaRef.current?.focus();
                    }}
                    className="text-left text-sm text-[#374151] bg-white hover:bg-[#F9FAFB] border border-[#E5E7EB] hover:border-[#3B82F6] rounded-xl px-4 py-3 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {!stickToBottom && messages.length > 0 && (
          <button
            onClick={() => {
              setStickToBottom(true);
              messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }}
            aria-label="Jump to latest message"
            className="absolute bottom-28 right-4 sm:right-6 bg-white shadow-md border border-[#E5E7EB] hover:border-[#3B82F6] hover:text-[#3B82F6] text-[#111827] rounded-full h-9 w-9 flex items-center justify-center transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]"
          >
            <ArrowDown className="h-4 w-4" />
          </button>
        )}

        {/* Input bar */}
        <div className="border-t border-[#E5E7EB] bg-white p-3 sm:p-4">
          {/* Pill input */}
          <div
            className={cn(
              'flex items-end gap-2 bg-[#F9FAFB] rounded-2xl border-2 border-transparent px-3 py-2 transition-colors duration-150',
              'focus-within:border-[#3B82F6] focus-within:bg-white'
            )}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your documents…"
              rows={1}
              disabled={isAnyStreaming}
              className={cn(
                'flex-1 resize-none bg-transparent border-0 outline-hidden px-1 py-1.5 text-sm text-[#111827] placeholder:text-gray-400',
                'disabled:opacity-60 disabled:cursor-not-allowed'
              )}
              aria-label="Query input"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isAnyStreaming}
              aria-label="Send message"
              className={cn(
                'bg-[#111827] text-white h-8 w-8 rounded-full flex items-center justify-center shrink-0 transition-all duration-150',
                'hover:bg-[#3B82F6]',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]',
                'disabled:bg-[#E5E7EB] disabled:text-gray-400 disabled:cursor-not-allowed disabled:hover:bg-[#E5E7EB]'
              )}
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>

          {/* Controls chip row */}
          <div className="flex items-center gap-2 mt-2.5 px-1 flex-wrap">
            <label className="inline-flex items-center gap-1.5 text-xs text-gray-500 bg-[#F3F4F6] hover:bg-[#E5E7EB] rounded-full px-2.5 py-1 cursor-pointer transition-colors duration-150">
              <span>Results</span>
              <select
                value={matchCount}
                onChange={(e) => setMatchCount(Number(e.target.value))}
                className="bg-transparent border-0 outline-hidden text-xs font-semibold text-[#111827] cursor-pointer focus:outline-none"
                aria-label="Number of results to retrieve"
              >
                {[3, 5, 10, 20].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>

            <label className="inline-flex items-center gap-1.5 text-xs text-gray-500 bg-[#F3F4F6] hover:bg-[#E5E7EB] rounded-full px-2.5 py-1 cursor-pointer select-none transition-colors duration-150">
              <input
                type="checkbox"
                checked={rerank}
                onChange={(e) => setRerank(e.target.checked)}
                className="accent-[#3B82F6] w-3 h-3"
              />
              <span className="font-semibold text-[#111827]">Rerank</span>
            </label>

            {messages.length > 0 && (
              <button
                onClick={clearChat}
                className="ml-auto text-xs text-gray-400 hover:text-[#111827] hover:bg-[#F3F4F6] rounded-full px-2.5 py-1 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B82F6]"
              >
                Clear chat
              </button>
            )}
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
