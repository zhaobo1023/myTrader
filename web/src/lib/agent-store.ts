'use client';

import { create } from 'zustand';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AgentToolCall {
  callId: string;
  name: string;
  params: Record<string, unknown>;
  result?: Record<string, unknown>;
  durationMs?: number;
  success?: boolean;
  loading?: boolean;
}

export interface AgentAction {
  action: string;
  payload: Record<string, unknown>;
  confirmed?: boolean;   // true = user confirmed, false = user cancelled
  executed?: boolean;     // true = action was carried out
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  toolCalls?: AgentToolCall[];
  action?: AgentAction;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface AgentState {
  isOpen: boolean;
  mode: 'floating' | 'fullscreen';
  conversationId: string | null;
  messages: AgentMessage[];
  isStreaming: boolean;
  activeSkill: string | null;
  pageContext: Record<string, unknown>;

  // Actions
  toggle: () => void;
  setOpen: (open: boolean) => void;
  setMode: (mode: 'floating' | 'fullscreen') => void;
  setConversationId: (id: string | null) => void;
  addMessage: (msg: AgentMessage) => void;
  updateLastAssistantContent: (content: string) => void;
  addToolCallToLastAssistant: (tc: AgentToolCall) => void;
  updateToolCallResult: (callId: string, result: Record<string, unknown>, durationMs: number, success: boolean) => void;
  addActionToLastAssistant: (action: AgentAction) => void;
  setStreaming: (streaming: boolean) => void;
  setActiveSkill: (skillId: string | null) => void;
  updatePageContext: (ctx: Record<string, unknown>) => void;
  clearMessages: () => void;
  newConversation: () => void;
}

let _msgCounter = 0;
function nextMsgId(): string {
  _msgCounter += 1;
  return `msg_${Date.now()}_${_msgCounter}`;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  isOpen: false,
  mode: 'floating',
  conversationId: typeof window !== 'undefined'
    ? localStorage.getItem('agent_conversation_id') || null
    : null,
  messages: [],
  isStreaming: false,
  activeSkill: null,
  pageContext: {},

  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
  setOpen: (open) => set({ isOpen: open }),

  setMode: (mode) => set({ mode }),

  setConversationId: (id) => {
    if (typeof window !== 'undefined') {
      if (id) {
        localStorage.setItem('agent_conversation_id', id);
      } else {
        localStorage.removeItem('agent_conversation_id');
      }
    }
    set({ conversationId: id });
  },

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  updateLastAssistantContent: (content) =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'assistant') {
          msgs[i] = { ...msgs[i], content: msgs[i].content + content };
          break;
        }
      }
      return { messages: msgs };
    }),

  addToolCallToLastAssistant: (tc) =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'assistant') {
          const existing = msgs[i].toolCalls || [];
          msgs[i] = { ...msgs[i], toolCalls: [...existing, tc] };
          break;
        }
      }
      return { messages: msgs };
    }),

  updateToolCallResult: (callId, result, durationMs, success) =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].toolCalls) {
          const toolCalls = msgs[i].toolCalls!.map((tc) =>
            tc.callId === callId
              ? { ...tc, result, durationMs, success, loading: false }
              : tc,
          );
          msgs[i] = { ...msgs[i], toolCalls };
          break;
        }
      }
      return { messages: msgs };
    }),

  addActionToLastAssistant: (action) =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'assistant') {
          msgs[i] = { ...msgs[i], action };
          break;
        }
      }
      return { messages: msgs };
    }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  setActiveSkill: (skillId) => set({ activeSkill: skillId }),

  updatePageContext: (ctx) => set({ pageContext: ctx }),

  clearMessages: () => set({ messages: [] }),

  newConversation: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('agent_conversation_id');
    }
    set({ conversationId: null, messages: [], activeSkill: null });
  },
}));

export { nextMsgId };
