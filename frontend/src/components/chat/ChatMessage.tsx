'use client';

import { memo, useMemo } from 'react';
import { Check, Copy, Lock, Sparkles } from 'lucide-react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { PluggableList } from 'unified';
import { cn } from '@/lib/utils';
import {
  type ChatMessage as ChatMessageType,
  type BackendCitation,
  useChatStore,
} from '@/lib/store/chatStore';
import { remarkCitations } from '@/lib/markdown/remarkCitations';
import { useCopyToClipboard } from '@/lib/hooks/useCopyToClipboard';
import { CitationInline } from './CitationInline';
import { StreamingCursor } from './StreamingCursor';

interface ChatMessageProps {
  message: ChatMessageType;
}

interface MarkdownBodyProps {
  content: string;
  citations: BackendCitation[];
  isStreaming: boolean;
  onCitationClick: (sourceId: string) => void;
}

const MarkdownBody = memo(function MarkdownBody({
  content,
  citations,
  isStreaming,
  onCitationClick,
}: MarkdownBodyProps) {
  const remarkPlugins = useMemo<PluggableList>(
    () => [remarkGfm, [remarkCitations, { isStreaming }]],
    [isStreaming]
  );

  const components = useMemo<Components>(() => {
    return {
      p: ({ children }) => (
        <p className="my-2.5 leading-7 first:mt-0 last:mb-0">{children}</p>
      ),
      h1: ({ children }) => (
        <h1 className="text-xl font-semibold text-[#111827] mt-4 mb-2 first:mt-0">
          {children}
        </h1>
      ),
      h2: ({ children }) => (
        <h2 className="text-lg font-semibold text-[#111827] mt-4 mb-2 first:mt-0">
          {children}
        </h2>
      ),
      h3: ({ children }) => (
        <h3 className="text-base font-semibold text-[#111827] mt-3 mb-1.5 first:mt-0">
          {children}
        </h3>
      ),
      ul: ({ children }) => (
        <ul className="list-disc pl-6 my-2.5 space-y-1.5 marker:text-gray-400">
          {children}
        </ul>
      ),
      ol: ({ children }) => (
        <ol className="list-decimal pl-6 my-2.5 space-y-1.5 marker:text-gray-400">
          {children}
        </ol>
      ),
      li: ({ children }) => <li className="leading-7 pl-1">{children}</li>,
      blockquote: ({ children }) => (
        <blockquote className="border-l-4 border-[#E5E7EB] pl-4 my-3 text-gray-600 italic">
          {children}
        </blockquote>
      ),
      a: ({ children, href }) => (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#3B82F6] underline underline-offset-2 hover:text-[#2563EB]"
        >
          {children}
        </a>
      ),
      strong: ({ children }) => (
        <strong className="font-semibold text-[#111827]">{children}</strong>
      ),
      em: ({ children }) => <em className="italic">{children}</em>,
      hr: () => <hr className="my-4 border-[#E5E7EB]" />,
      code: ({ className, children, ...props }) => {
        const hasLang = /language-/.test(className ?? '');
        const text = Array.isArray(children)
          ? children.join('')
          : typeof children === 'string'
          ? children
          : '';
        const isBlock = hasLang || text.includes('\n');
        if (isBlock) {
          return (
            <code
              className={cn('font-mono text-[0.85em] whitespace-pre', className)}
              {...props}
            >
              {children}
            </code>
          );
        }
        return (
          <code className="bg-[#F3F4F6] text-[#111827] rounded px-1.5 py-0.5 text-[0.85em] font-mono wrap-break-word">
            {children}
          </code>
        );
      },
      pre: ({ children }) => (
        <pre className="bg-[#0F172A] text-[#E5E7EB] rounded-lg p-4 my-3 overflow-x-auto text-[13px] font-mono leading-relaxed border border-[#1F2937]">
          {children}
        </pre>
      ),
      table: ({ children }) => (
        <div className="overflow-x-auto my-3 rounded-md border border-[#E5E7EB]">
          <table className="w-full text-sm border-collapse">{children}</table>
        </div>
      ),
      thead: ({ children }) => (
        <thead className="bg-[#F9FAFB]">{children}</thead>
      ),
      th: ({ children }) => (
        <th className="border-b border-[#E5E7EB] px-3 py-2 text-left font-semibold text-[#111827]">
          {children}
        </th>
      ),
      td: ({ children }) => (
        <td className="border-b border-[#E5E7EB] px-3 py-2 last:border-b-0">
          {children}
        </td>
      ),
      // Custom: rendered from the `citation` mdast node injected by remarkCitations.
      cite: ({ node, children }) => {
        const props = (node?.properties ?? {}) as Record<string, unknown>;
        const raw = props.dataSourceN ?? props['data-source-n'];
        const n = typeof raw === 'string' ? raw : Array.isArray(raw) ? raw[0] : undefined;
        if (typeof n !== 'string') {
          return <>{children}</>;
        }
        const idx = parseInt(n, 10) - 1;
        const citation = citations[idx];
        const sourceId = citation?.source_id ?? `[SOURCE_${n}]`;
        return (
          <CitationInline
            sourceId={sourceId}
            onClick={() => onCitationClick(sourceId)}
          />
        );
      },
    };
  }, [citations, onCitationClick]);

  return (
    <ReactMarkdown remarkPlugins={remarkPlugins} components={components}>
      {content}
    </ReactMarkdown>
  );
});

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1.5">
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" />
    </span>
  );
}

export const ChatMessage = memo(function ChatMessage({ message }: ChatMessageProps) {
  const focusCitation = useChatStore((s) => s.focusCitation);
  const [isCopied, copy] = useCopyToClipboard();
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end mb-6">
        <div className="bg-[#F3F4F6] text-[#111827] rounded-2xl rounded-tr-md px-4 py-2.5 max-w-[80%] text-sm leading-relaxed whitespace-pre-wrap wrap-break-word">
          {message.content}
        </div>
      </div>
    );
  }

  const isThinking = message.isStreaming && message.content === '';
  const showActions = !message.isStreaming && message.content.length > 0;

  return (
    <div className="group flex gap-3 mb-6">
      {/* Assistant avatar */}
      <div
        aria-hidden="true"
        className="shrink-0 w-8 h-8 rounded-full bg-linear-to-br from-[#3B82F6] to-[#1E40AF] flex items-center justify-center shadow-sm"
      >
        <Sparkles className="h-4 w-4 text-white" />
      </div>

      {/* Message body */}
      <div className="flex-1 min-w-0 pt-0.5">
        {message.declined && (
          <div className="flex items-center gap-1.5 mb-2 px-3 py-1.5 rounded-md bg-[#FEF3C7] border border-[#F59E0B] text-[#B45309] font-semibold text-xs uppercase tracking-wide w-fit">
            <Lock className="h-3.5 w-3.5" />
            <span>Response declined</span>
          </div>
        )}

        <div className="text-[#111827] text-[15px] leading-7 wrap-break-word">
          {isThinking ? (
            <ThinkingDots />
          ) : (
            <>
              <MarkdownBody
                content={message.content}
                citations={message.citations}
                isStreaming={message.isStreaming}
                onCitationClick={focusCitation}
              />
              {message.isStreaming && <StreamingCursor />}
            </>
          )}
        </div>

        {showActions && (
          <div className="mt-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-150">
            <button
              onClick={() => copy(message.content)}
              aria-label={isCopied ? 'Copied to clipboard' : 'Copy message'}
              className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-[#111827] hover:bg-[#F3F4F6] rounded-md px-2 py-1 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6]"
            >
              {isCopied ? (
                <>
                  <Check className="h-3.5 w-3.5 text-emerald-600" />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
});
