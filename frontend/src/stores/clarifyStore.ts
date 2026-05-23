/** Clarify 对话状态 — 自开发场景的 LLM 追问弹窗 */
import { create } from 'zustand';

const API_BASE = '/api';

interface ClarifyInfo {
  event_id: string;
  question: string;
  choices: string[] | null;
}

interface ClarifyState {
  visible: boolean;
  info: ClarifyInfo | null;
  loading: boolean;
  submitting: boolean;
  customInput: string;
  setCustomInput: (v: string) => void;
  checkPending: () => Promise<void>;
  submitResponse: (response: string) => Promise<void>;
  dismiss: () => void;
}

export const clarifyStore = create<ClarifyState>((set, get) => ({
  visible: false,
  info: null,
  loading: false,
  submitting: false,
  customInput: '',

  setCustomInput: (v) => set({ customInput: v }),

  checkPending: async () => {
    if (get().visible) return;

    set({ loading: true });
    try {
      const res = await fetch(`${API_BASE}/agent-loop/clarify-pending`);
      const data = await res.json();
      if (data.pending && data.info) {
        set({
          visible: true,
          info: data.info,
          loading: false,
          customInput: '',
        });
      } else {
        set({ loading: false });
      }
    } catch {
      set({ loading: false });
    }
  },

  submitResponse: async (response) => {
    const { info } = get();
    if (!info) return;

    set({ submitting: true });
    try {
      await fetch(`${API_BASE}/agent-loop/clarify-response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: info.event_id, response }),
      });
    } catch {
      // 静默失败
    }
    set({ visible: false, info: null, submitting: false, customInput: '' });
  },

  dismiss: () => {
    set({ visible: false, info: null, customInput: '' });
  },
}));
