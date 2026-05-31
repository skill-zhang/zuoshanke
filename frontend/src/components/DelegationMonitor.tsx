/** 子 Agent 进度监视组件 — 在场景聊天中显示并行子任务状态 */
import React, { useEffect, useState } from 'react';

interface ChildTask {
  goal: string;
  status: 'running' | 'success' | 'error' | 'timeout';
  summary?: string;
  steps?: number;
  error?: string;
}

// 模块级状态（不引入额外 store，SSE 事件直接更新）
let _runningTasks: ChildTask[] = [];
let _completedTasks: ChildTask[] = [];
let _listeners: Array<() => void> = [];

function notifyListeners() {
  for (const fn of _listeners) fn();
}

export function setDelegateTasks(tasks: { goal: string }[]) {
  _runningTasks = tasks.map((t) => ({ goal: t.goal, status: 'running' as const }));
  _completedTasks = [];
  notifyListeners();
}

export function setDelegateResults(children: any[]) {
  _runningTasks = [];
  _completedTasks = (children || []).map((c: any) => ({
    goal: c.task || c.goal || '?',
    status: (c.status === 'success'
      ? 'success'
      : c.status === 'timeout'
        ? 'timeout'
        : 'error') as ChildTask['status'],
    summary: c.summary || '',
    steps: c.steps || 0,
    error: c.error,
  }));
  notifyListeners();
}

export function subscribeDelegateChanges(fn: () => void) {
  _listeners.push(fn);
  return () => {
    _listeners = _listeners.filter((f) => f !== fn);
  };
}

export function getDelegateState() {
  return { running: _runningTasks, completed: _completedTasks };
}

export function DelegationMonitor() {
  const [, forceUpdate] = useState(0);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const unsub = subscribeDelegateChanges(() => {
      forceUpdate((n) => n + 1);
      // 有新任务开始时，重新打开面板
      if (getDelegateState().running.length > 0) {
        setDismissed(false);
      }
    });
    return unsub;
  }, []);

  const { running, completed } = getDelegateState();

  if (running.length === 0 && completed.length === 0) return null;
  if (dismissed) return null;

  return (
    <div
      style={{
        margin: '8px 0',
        padding: '10px 14px',
        background: 'rgba(30, 30, 50, 0.6)',
        borderRadius: 8,
        border: '1px solid rgba(255,255,255,0.06)',
        fontSize: 13,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 6,
        }}
      >
        <div style={{ color: '#8b949e', fontWeight: 500 }}>⚡ 并行子任务</div>
        <span
          onClick={() => setDismissed(true)}
          style={{
            cursor: 'pointer',
            color: '#6e7681',
            fontSize: 16,
            lineHeight: 1,
            userSelect: 'none',
          }}
          title="收起"
        >
          ✕
        </span>
      </div>

      {/* 执行中的任务 */}
      {running.map((t, i) => (
        <div
          key={`run-${i}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '4px 0',
            color: '#c9d1d9',
          }}
        >
          <span
            className="spinner"
            style={{
              display: 'inline-block',
              width: 12,
              height: 12,
              border: '2px solid rgba(88,166,255,0.3)',
              borderTopColor: '#58a6ff',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }}
          />
          <span style={{ flex: 1 }}>{t.goal}</span>
          <span style={{ color: '#58a6ff', fontSize: 11 }}>执行中...</span>
        </div>
      ))}

      {/* 已完成的任务 */}
      {completed.map((t, i) => (
        <div
          key={`done-${i}`}
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            padding: '4px 0',
            color:
              t.status === 'success' ? '#7ee787' : t.status === 'timeout' ? '#d29922' : '#ff7b72',
          }}
        >
          <span>{t.status === 'success' ? '✅' : t.status === 'timeout' ? '⏱️' : '❌'}</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#c9d1d9' }}>{t.goal}</div>
            {t.summary && (
              <div style={{ color: '#8b949e', fontSize: 12, marginTop: 2 }}>
                {t.summary.length > 200 ? t.summary.slice(0, 200) + '...' : t.summary}
              </div>
            )}
            {t.error && (
              <div style={{ color: '#ff7b72', fontSize: 12, marginTop: 2 }}>{t.error}</div>
            )}
            <div style={{ color: '#6e7681', fontSize: 11, marginTop: 1 }}>{t.steps} 步</div>
          </div>
        </div>
      ))}
    </div>
  );
}
