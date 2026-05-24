/** 高危命令审批弹窗状态 */
import { create } from 'zustand';

const API_BASE = '/api';

interface ApprovalInfo {
  command: string;
  reason: string;
  category: string;
  description: string;
}

interface ApprovalState {
  visible: boolean;
  info: ApprovalInfo | null;
  submitting: boolean;
  showApproval: (info: ApprovalInfo) => void;
  approve: () => Promise<void>;
  reject: () => void;
  dismiss: () => void;
}

export const approvalStore = create<ApprovalState>((set, get) => ({
  visible: false,
  info: null,
  submitting: false,

  showApproval: (info) => {
    set({ visible: true, info, submitting: false });
  },

  approve: async () => {
    const { info } = get();
    if (!info) return;
    set({ submitting: true });

    try {
      await fetch(`${API_BASE}/agent-loop/command-approval`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: info.command,
          approved: true,
        }),
      });
    } catch {
      // 静默失败
    }
    set({ visible: false, info: null, submitting: false });
  },

  reject: () => {
    const { info } = get();
    if (!info) return;

    fetch(`${API_BASE}/agent-loop/command-approval`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: info.command,
        approved: false,
      }),
    }).catch(() => {});

    set({ visible: false, info: null, submitting: false });
  },

  dismiss: () => {
    set({ visible: false, info: null, submitting: false });
  },
}));
