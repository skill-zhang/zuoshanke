/**
 * Agent Loop 执行追踪状态管理 — Zustand
 *
 * Schema v1.6: 独立于 appStore，只存 trace 事件不存对话。
 * 场景隔离：key=sceneId 的 Map。
 * 过期：前端缓存最近一次 Agent Loop 的 traces，切场景/新会话时自动清空。
 */
import { create } from 'zustand';

/** 单条 trace 事件（与 agent.log JSONL 格式对齐） */
export interface TraceEvent {
  id: string;
  step: number;
  eventType: 'tool_start' | 'tool_done' | 'tool_error' | 'thinking' | 'status' | 'done';
  tool?: string;
  args?: any;
  result?: any;
  error?: string;
  text?: string;
  toolCallId?: string;
  /** 工具执行耗时（ms） */
  durationMs?: number;
  /** 前端收到时间戳（用于步级别展示，非精确日志时间） */
  receivedAt: string;
}

/** 按 step 分组的 trace */
export interface TraceStep {
  step: number;
  events: TraceEvent[];
  /** 第一步事件的时间戳 */
  startedAt: string;
  /** 状态 */
  status: 'running' | 'done' | 'error';
}

interface TraceState {
  /** 按 sceneId 隔离的 traces */
  tracesByScene: Record<string, TraceEvent[]>;

  /** UI 状态 */
  isPanelOpen: boolean;
  floatingBtnTop: number;  // 悬浮按钮 top 位置（px）

  /** 内部版本号，每次 mutation 递增 — 用于 useEffect 监听任何内容变化 */
  _updateVersion: number;

  /** 当前场景的步骤列表（派生自 traces） */
  getSteps: (sceneId: string) => TraceStep[];

  /** 追加一条 trace */
  appendTrace: (sceneId: string, event: TraceEvent) => void;

  /** 清空某场景的 traces */
  clearTraces: (sceneId: string) => void;

  /** 面板开关 */
  setPanelOpen: (open: boolean) => void;
  togglePanel: () => void;

  /** 设置悬浮按钮位置 */
  setFloatingBtnTop: (top: number) => void;

  /** 更新 tool_done 事件（补充耗时） */
  updateToolDone: (sceneId: string, toolCallId: string, result: any, durationMs: number) => void;

  /** 更新 tool_error 事件 */
  updateToolError: (sceneId: string, toolCallId: string, error: string) => void;
}

export const useTraceStore = create<TraceState>((set, get) => ({
  tracesByScene: {},
  isPanelOpen: false,
  floatingBtnTop: window.innerHeight / 2,
  _updateVersion: 0,

  getSteps: (sceneId: string): TraceStep[] => {
    const traces = get().tracesByScene[sceneId] || [];
    if (traces.length === 0) return [];

    const stepMap = new Map<number, TraceEvent[]>();
    for (const t of traces) {
      const list = stepMap.get(t.step) || [];
      list.push(t);
      stepMap.set(t.step, list);
    }

    const steps: TraceStep[] = [];
    for (const [step, events] of stepMap) {
      const hasError = events.some(e => e.eventType === 'tool_error');
      const hasDone = events.some(e => e.eventType === 'done');
      const isRunning = !hasDone && !hasError && events.some(e => e.eventType === 'tool_start');

      steps.push({
        step,
        events,
        startedAt: events[0]?.receivedAt || '',
        status: hasError ? 'error' : hasDone ? 'done' : isRunning ? 'running' : 'done',
      });
    }

    return steps.sort((a, b) => a.step - b.step);
  },

  appendTrace: (sceneId, event) => {
    set(state => {
      const existing = state.tracesByScene[sceneId] || [];
      // 避免重复
      if (event.eventType === 'tool_start' && existing.some(e =>
        e.eventType === 'tool_start' && e.tool === event.tool && e.step === event.step && e.toolCallId === event.toolCallId
      )) {
        return state;
      }
      return {
        tracesByScene: {
          ...state.tracesByScene,
          [sceneId]: [...existing, event],
        },
        _updateVersion: state._updateVersion + 1,
      };
    });
  },

  clearTraces: (sceneId) => {
    set(state => {
      const { [sceneId]: _, ...rest } = state.tracesByScene;
      return { tracesByScene: rest, _updateVersion: state._updateVersion + 1 };
    });
  },

  setPanelOpen: (open) => set({ isPanelOpen: open }),
  togglePanel: () => set(state => ({ isPanelOpen: !state.isPanelOpen })),

  setFloatingBtnTop: (top) => set({ floatingBtnTop: top }),

  updateToolDone: (sceneId, toolCallId, result, durationMs) => {
    set(state => {
      const traces = state.tracesByScene[sceneId] || [];
      return {
        tracesByScene: {
          ...state.tracesByScene,
          [sceneId]: traces.map(t =>
            t.toolCallId === toolCallId && t.eventType === 'tool_start'
              ? { ...t, eventType: 'tool_done' as const, result, durationMs }
              : t
          ),
        },
        _updateVersion: state._updateVersion + 1,
      };
    });
  },

  updateToolError: (sceneId, toolCallId, error) => {
    set(state => {
      const traces = state.tracesByScene[sceneId] || [];
      return {
        tracesByScene: {
          ...state.tracesByScene,
          [sceneId]: traces.map(t =>
            t.toolCallId === toolCallId && t.eventType === 'tool_start'
              ? { ...t, eventType: 'tool_error' as const, error }
              : t
          ),
        },
        _updateVersion: state._updateVersion + 1,
      };
    });
  },
}));
