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
// Persona types
// ---------------------------------------------------------------------------

export interface PersonaDef {
  id: string;
  name: string;
  desc: string;
  prompt: string;
}

export const PRESET_PERSONAS: PersonaDef[] = [
  { id: 'default',   name: 'myTrader 助手', desc: '默认模式，全能量化投资助手', prompt: '' },
  { id: 'buffett',   name: '巴菲特',        desc: '价值投资之父，护城河理论，长期持有', prompt: '__server__' },
  { id: 'munger',    name: '查理·芒格',     desc: '多元思维模型，逆向思考，避免愚蠢', prompt: '__server__' },
  { id: 'graham',    name: '本杰明·格雷厄姆', desc: '价值投资鼻祖，安全边际，防御型投资', prompt: '__server__' },
  { id: 'lynch',     name: '彼得·林奇',     desc: '成长股猎手，十倍股，从生活中发现机会', prompt: '__server__' },
  { id: 'livermore', name: '杰西·利弗莫尔', desc: '趋势交易先驱，顺势而为，严格止损', prompt: '__server__' },
  { id: 'dalio',     name: '瑞·达利欧',     desc: '全天候策略，债务周期，原则驱动', prompt: '__server__' },
  { id: 'custom',    name: '自定义',        desc: '用户自定义投资风格', prompt: '' },
];

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
  // Persona
  personaId: string;
  customPersonaPrompt: string;

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
  setPersona: (personaId: string, customPrompt?: string) => void;
}

let _msgCounter = 0;
function nextMsgId(): string {
  _msgCounter += 1;
  return `msg_${Date.now()}_${_msgCounter}`;
}

function _ls(key: string): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(key);
}
function _lsSet(key: string, val: string) {
  if (typeof window !== 'undefined') localStorage.setItem(key, val);
}
function _lsDel(key: string) {
  if (typeof window !== 'undefined') localStorage.removeItem(key);
}

export const useAgentStore = create<AgentState>((set, get) => ({
  isOpen: false,
  mode: 'floating',
  conversationId: _ls('agent_conversation_id'),
  messages: [],
  isStreaming: false,
  activeSkill: null,
  pageContext: {},
  personaId: _ls('agent_persona_id') || 'default',
  customPersonaPrompt: _ls('agent_persona_custom') || '',

  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
  setOpen: (open) => set({ isOpen: open }),

  setMode: (mode) => set({ mode }),

  setConversationId: (id) => {
    if (id) { _lsSet('agent_conversation_id', id); } else { _lsDel('agent_conversation_id'); }
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
    _lsDel('agent_conversation_id');
    set({ conversationId: null, messages: [], activeSkill: null });
  },

  setPersona: (personaId, customPrompt) => {
    _lsSet('agent_persona_id', personaId);
    if (customPrompt !== undefined) {
      _lsSet('agent_persona_custom', customPrompt);
      set({ personaId, customPersonaPrompt: customPrompt });
    } else {
      set({ personaId });
    }
  },
}));

export { nextMsgId };
