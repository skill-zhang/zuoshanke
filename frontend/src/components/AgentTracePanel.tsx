/**
 * Agent Loop 执行追踪面板 — Schema v1.6
 *
 * 右侧抽屉，min-width 640px，可拖拽调宽。
 * 悬浮按钮（场景专属），可上下拖动。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useStore } from '../stores/appStore';
import { useTraceStore, TraceEvent, TraceStep } from '../stores/traceStore';

// ── 工具图标映射 ──
const TOOL_ICONS: Record<string, string> = {
  run_code: '⚡',
  write_file: '📝',
  patch: '🔧',
  read_file: '📖',
  search_files: '🔍',
  think: '💭',
  clarify: '❓',
  delegate_task: '📤',
  web_search: '🌐',
  terminal: '💻',
  diverge: '🌱',
  converge: '🎯',
  self_map_declare: '🗺️',
  self_map_update: '🔄',
};
const DEFAULT_TOOL_ICON = '⚙️';

function getToolIcon(tool: string): string {
  return TOOL_ICONS[tool] || DEFAULT_TOOL_ICON;
}

// ── 格式化耗时 ──
function fmtDuration(ms: number | undefined): string {
  if (ms === undefined) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ── 格式化时间戳 ──
function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

// ══════════════════════════════════════
//  子组件
// ══════════════════════════════════════

/** LLM 思考卡片 */
const ThinkingCard: React.FC<{ text: string }> = ({ text }) => (
  <div className="trace-thinking-card">
    <div className="trace-thinking-label">💭 LLM 思考</div>
    <div className="trace-thinking-text">{text}</div>
  </div>
);

/** 工具调用卡片 */
const ToolCallCard: React.FC<{ event: TraceEvent }> = ({ event }) => {
  const [expanded, setExpanded] = useState(true);  // 默认展开
  const isError = event.eventType === 'tool_error';
  const isRunning = event.eventType === 'tool_start' && !event.durationMs;

  return (
    <div className={`trace-tool-card ${isError ? 'trace-tool-error' : ''} ${expanded ? 'expanded' : ''}`}>
      <div className="trace-tool-header" onClick={() => setExpanded(!expanded)}>
        <span className="trace-tool-arrow">{expanded ? '▼' : '▶'}</span>
        <span className={`trace-tool-dot ${isError ? 'fail' : isRunning ? 'running' : 'ok'}`} />
        <span className="trace-tool-icon">{getToolIcon(event.tool || '')}</span>
        <span className="trace-tool-name">{event.tool}</span>
        <span className="trace-tool-time">
          {isRunning ? '运行中...' : fmtDuration(event.durationMs)}
        </span>
      </div>
      {(expanded && (event.args || event.result || event.error)) && (
        <div className="trace-tool-detail">
          {event.args && (
            <div className="trace-detail-section">
              <div className="trace-detail-label">参数</div>
              <pre className="trace-detail-code">{formatArgs(event.args)}</pre>
            </div>
          )}
          {event.error && (
            <div className="trace-detail-section">
              <div className="trace-detail-label">错误</div>
              <pre className="trace-detail-output error">{event.error}</pre>
            </div>
          )}
          {event.result && (
            <div className="trace-detail-section">
              <div className="trace-detail-label">输出</div>
              <pre className="trace-detail-output success">{formatResult(event.result)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/** 格式化工具参数 */
function formatArgs(args: any): string {
  if (typeof args === 'string') return args;
  try {
    // code 或 code_b64 太长时截断
    const copy = { ...args };
    if (copy.code && copy.code.length > 500) {
      copy.code = copy.code.slice(0, 500) + '\n... [已截断]';
    }
    if (copy.code_b64) {
      copy.code_b64 = `[base64 ${copy.code_b64.length} 字符]`;
    }
    return JSON.stringify(copy, null, 2);
  } catch {
    return String(args);
  }
}

/** 格式化工具结果 */
function formatResult(result: any): string {
  if (typeof result === 'string') return result;
  if (typeof result === 'object' && result !== null) {
    // 如果是 {stdout, stderr, exit_code} 格式
    if ('stdout' in result) {
      let out = result.stdout || '';
      if (result.stderr) out += '\n--- stderr ---\n' + result.stderr;
      if (out.length > 2000) out = out.slice(0, 2000) + '\n... [已截断]';
      return out;
    }
    try {
      return JSON.stringify(result, null, 2);
    } catch {
      return String(result);
    }
  }
  return String(result);
}

/** 单步内容 */
const TraceStepView: React.FC<{ step: TraceStep }> = ({ step }) => {
  const [expanded, setExpanded] = useState(true);

  const statusIcon = step.status === 'error' ? '❌' : step.status === 'running' ? '🔄' : '✅';

  return (
    <div className={`trace-step-group ${expanded ? 'expanded' : ''}`}>
      <div className="trace-step-header" onClick={() => setExpanded(!expanded)}>
        <span className="trace-step-arrow">{expanded ? '▼' : '▶'}</span>
        <span className="trace-step-num">{step.step + 1}</span>
        <span className="trace-step-label">
          {step.events.find(e => e.eventType === 'thinking')?.text?.slice(0, 60) || `第 ${step.step + 1} 步`}
        </span>
        <span className="trace-step-time">{fmtTime(step.startedAt)}</span>
        <span className={`trace-step-status ${step.status}`} />
      </div>
      {expanded && (
        <div className="trace-step-content">
          {step.events.map((e, i) => {
            if (e.eventType === 'thinking') {
              return <ThinkingCard key={i} text={e.text || ''} />;
            }
            if (e.eventType === 'tool_start' || e.eventType === 'tool_done' || e.eventType === 'tool_error') {
              return <ToolCallCard key={`${e.tool}-${i}`} event={e} />;
            }
            return null;
          })}
        </div>
      )}
    </div>
  );
};

// ══════════════════════════════════════
//  主面板
// ══════════════════════════════════════

export const AgentTracePanel: React.FC = () => {
  const currentScene = useStore(s => s.currentScene);
  const traceStore = useTraceStore();
  const panelRef = useRef<HTMLDivElement>(null);
  const panelBodyRef = useRef<HTMLDivElement>(null);
  const [isResizing, setIsResizing] = useState(false);
  const [panelWidth, setPanelWidth] = useState(640);

  const sceneId = currentScene?.id || '';
  const steps = sceneId ? traceStore.getSteps(sceneId) : [];
  const hasTraces = steps.length > 0;

  // 自动滚动：面板打开时滚到底，已打开时底部附近跟随
  const prevOpenRef = useRef(false);
  useEffect(() => {
    // 面板关闭 → 重置标记，下次打开时再滚底
    if (!traceStore.isPanelOpen) {
      prevOpenRef.current = false;
      return;
    }

    const el = panelBodyRef.current;
    if (!el) return;

    // 面板刚打开 → 直接滚到底
    if (!prevOpenRef.current) {
      prevOpenRef.current = true;
      requestAnimationFrame(() => {
        if (panelBodyRef.current) {
          panelBodyRef.current.scrollTop = panelBodyRef.current.scrollHeight;
        }
      });
      return;
    }

    // 已打开：只在底部附近时自动跟随
    const threshold = 120;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    if (atBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [steps.length, steps[steps.length - 1]?.events.length, traceStore.isPanelOpen]);

  // 拖拽调宽
  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    if (!isResizing) return;
    const onMove = (e: MouseEvent) => {
      const newW = Math.max(640, window.innerWidth - e.clientX);
      setPanelWidth(newW);
    };
    const onUp = () => {
      setIsResizing(false);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [isResizing]);

  if (!traceStore.isPanelOpen) return null;

  const stepCount = steps.length;
  const toolCount = steps.reduce((s, st) => s + st.events.filter(e =>
    e.eventType === 'tool_start' || e.eventType === 'tool_done'
  ).length, 0);
  const llmCount = steps.reduce((s, st) => s + st.events.filter(e =>
    e.eventType === 'thinking' || e.eventType === 'tool_start'
  ).length, 0);
  const isRunning = steps.some(s => s.status === 'running');

  return (
    <div className="trace-panel" ref={panelRef} style={{ width: panelWidth, minWidth: 640 }}>
      {/* 拖拽把手 */}
      <div className="trace-resize-handle" onMouseDown={onResizeStart} />

      {/* 头部 */}
      <div className="trace-panel-header">
        <div className="trace-panel-title">
          ⚡ 执行追踪
          {isRunning && <span className="trace-badge">实时</span>}
        </div>
        <div className="trace-panel-actions">
          <button onClick={() => {
            document.querySelectorAll('.trace-step-group').forEach(el => el.classList.add('expanded'));
          }} title="全部展开">⊞</button>
          <button onClick={() => {
            document.querySelectorAll('.trace-step-group').forEach(el => el.classList.remove('expanded'));
          }} title="全部收起">⊟</button>
          <button onClick={() => traceStore.setPanelOpen(false)} title="关闭">✕</button>
        </div>
      </div>

      {/* 统计 */}
      {hasTraces && (
        <div className="trace-panel-stats">
          <span>步骤 <b>{stepCount}</b></span>
          <span>工具 <b>{toolCount}</b></span>
          <span>LLM 请求 <b>{llmCount}</b></span>
          <span style={{ color: isRunning ? 'var(--orange)' : 'var(--green)' }}>
            {isRunning ? '🔄 运行中' : '✅ 已完成'}
          </span>
        </div>
      )}

      {/* 内容 */}
      <div className="trace-panel-body" ref={panelBodyRef}>
        {!hasTraces ? (
          <div className="trace-empty">暂无执行记录</div>
        ) : (
          steps.map(s => <TraceStepView key={s.step} step={s} />)
        )}
      </div>

      {/* 底部 */}
      {hasTraces && (
        <div className="trace-panel-footer">
          <span>更新: {fmtTime(new Date().toISOString())}</span>
        </div>
      )}
    </div>
  );
};

// ══════════════════════════════════════
//  悬浮按钮
// ══════════════════════════════════════

export const FloatingTraceButton: React.FC = () => {
  const currentScene = useStore(s => s.currentScene);
  const traceStore = useTraceStore();
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef({ startY: 0, startTop: 0, moved: false });
  const btnRef = useRef<HTMLDivElement>(null);

  const hasTraces = !!currentScene?.id && (traceStore.tracesByScene[currentScene.id]?.length || 0) > 0;

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    setIsDragging(true);
    dragRef.current = {
      startY: e.clientY,
      startTop: traceStore.floatingBtnTop,
      moved: false,
    };
  }, [traceStore.floatingBtnTop]);

  useEffect(() => {
    if (!isDragging) return;
    const onMove = (e: MouseEvent) => {
      const dy = e.clientY - dragRef.current.startY;
      if (Math.abs(dy) > 5) dragRef.current.moved = true;
      const newTop = Math.max(80, Math.min(window.innerHeight - 120, dragRef.current.startTop + dy));
      if (btnRef.current) {
        btnRef.current.style.top = newTop + 'px';
        btnRef.current.style.transform = 'none';
      }
    };
    const onUp = () => {
      if (btnRef.current) {
        const top = parseFloat(btnRef.current.style.top || String(traceStore.floatingBtnTop));
        traceStore.setFloatingBtnTop(top);
      }
      setIsDragging(false);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [isDragging, traceStore.floatingBtnTop]);

  const onClick = useCallback(() => {
    if (dragRef.current.moved) return;
    traceStore.togglePanel();
  }, [traceStore]);

  // 只在场景页面显示（hooks 之后）
  if (!currentScene) return null;

  return (
    <div
      ref={btnRef}
      className={`floating-trace-btn ${traceStore.isPanelOpen ? 'open' : ''}`}
      style={{ top: traceStore.floatingBtnTop }}
      onMouseDown={onMouseDown}
      onClick={onClick}
    >
      <span className="ftb-icon">⚡</span>
      <span className="ftb-label">追踪</span>
      {hasTraces && <span className="ftb-dot" />}
    </div>
  );
};
