import { create } from 'zustand';

export interface BackendCitation {
  source_id: string;
  chunk_id: string;
  content: string;
  metadata: {
    source: string;
    page_number?: number;
    bounding_boxes?: number[][];
    section_heading?: string;
    document_title?: string;
  };
  rerank_score?: number;
  rrf_score?: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: BackendCitation[];
  declined: boolean;
  isStreaming: boolean;
  retrieval_metadata?: unknown;
  createdAt: Date;
}

interface FinalizeMessagePayload {
  declined: boolean;
  retrieval_metadata: unknown;
}

interface ChatState {
  messages: ChatMessage[];
  activeCitationSourceId: string | null;
  citationFocusNonce: number;
  addUserMessage: (content: string) => string;
  startAssistantMessage: () => string;
  appendToken: (id: string, token: string) => void;
  finalizeCitation: (id: string, citations: BackendCitation[]) => void;
  finalizeMessage: (id: string, payload: FinalizeMessagePayload) => void;
  setActiveCitation: (sourceId: string | null) => void;
  focusCitation: (sourceId: string) => void;
  clearChat: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  activeCitationSourceId: null,
  citationFocusNonce: 0,

  addUserMessage: (content: string) => {
    const id = crypto.randomUUID();
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id,
          role: 'user',
          content,
          citations: [],
          declined: false,
          isStreaming: false,
          createdAt: new Date(),
        },
      ],
    }));
    return id;
  },

  startAssistantMessage: () => {
    const id = crypto.randomUUID();
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id,
          role: 'assistant',
          content: '',
          citations: [],
          declined: false,
          isStreaming: true,
          createdAt: new Date(),
        },
      ],
    }));
    return id;
  },

  appendToken: (id: string, token: string) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, content: msg.content + token } : msg
      ),
    }));
  },

  finalizeCitation: (id: string, citations: BackendCitation[]) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, citations } : msg
      ),
    }));
  },

  finalizeMessage: (id: string, payload: FinalizeMessagePayload) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id
          ? {
              ...msg,
              isStreaming: false,
              declined: payload.declined,
              retrieval_metadata: payload.retrieval_metadata,
            }
          : msg
      ),
    }));
  },

  setActiveCitation: (sourceId: string | null) => {
    set({ activeCitationSourceId: sourceId });
  },

  focusCitation: (sourceId: string) => {
    set((state) => ({
      activeCitationSourceId: sourceId,
      citationFocusNonce: state.citationFocusNonce + 1,
    }));
  },

  clearChat: () => {
    set({ messages: [], activeCitationSourceId: null, citationFocusNonce: 0 });
  },
}));
