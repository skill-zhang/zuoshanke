/** AgentLoopDashboard — 6 面板仪表盘
 *
 * 布局：
 *   ① 阶段循环图 (Loop Diagram)
 *   ② 可折叠思维导图 (Collapsible Mind Map)
 *   ③ 2×2 网格: TM收敛结果 / Priority Queue / Action Map / Reflect Timeline
 *   ④ Status Bar
 */
import { useMemo, useRef, useState } from 'react';
import { useStore } from '../stores/appStore';
import type { DashboardQueueItem, DashboardReflectItem, ThinkNode } from '../api/client';
import { CustomMindMap, type ThinkNodeData } from './CustomMindMap';

// ═══ 阶段循环图 ═══
const PHASES = [
  { key: 'diverge', icon: '🧠', label: '发散', desc: '头脑风暴\n拆解子问题' },
  { key: 'converge', icon: '🔀', label: '收敛', desc: '聚类去重\n合并相似项' },
  { key: 'sort', icon: '📊', label: '排序', desc: '依赖分析\n优先级队列' },
  { key: 'focus', icon: '🎯', label: '聚焦执行', desc: 'WIP 限制\n一次一件事' },
  { key: 'reflect', icon: '🔄', label: '反馈调整', desc: '结果反哺\n重新循环' },
];

function LoopDiagram() {
  const phase = useStore(s => s.dashboardPhase);
  const idx = PHASES.findIndex(p => p.key === phase);
  const highlightArrow = (i: number) => i < idx ? '#a78bfa' : '#3a3a4a';

  return (
    <div className="loop-diagram">
      <h2>阶段循环</h2>
      <div className="loop-flow">
        {PHASES.map((p, i) => (
          <span key={p.key} style={{ display: 'flex', alignItems: 'center' }}>
            <div className="loop-step">
              <div className={`icon ${p.key}`} style={{
                background: i <= idx ? `rgba(139,92,246,0.2)` : `rgba(60,60,80,0.2)`,
                border: i === idx ? `2px solid #a78bfa` : i < idx ? `2px solid #555` : `2px solid #333`,
                opacity: i > idx ? 0.5 : 1,
              }}>
                {p.icon}
              </div>
              <div className="label" style={{ color: i === idx ? '#c084fc' : i < idx ? '#999' : '#666' }}>{p.label}</div>
              <div className="desc">{p.desc}</div>
            </div>
            {i < PHASES.length - 1 && (
              <div className="loop-arrow" style={{
                background: highlightArrow(i),
                width: 56, height: 2, margin: '0 6px', flexShrink: 0,
                position: 'relative',
              }}>
                <span style={{
                  position: 'absolute', right: -4, top: -7,
                  color: highlightArrow(i), fontSize: 15,
                }}>›</span>
              </div>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

// ═══ 思维导图（可收起 + 自适应高度） ═══
function CollapsibleMindMap() {
  const [expanded, setExpanded] = useState(true);
  const mmRef = useRef<HTMLDivElement>(null);
  const thinkingMap = useStore(s => s.thinkingMap);
  const nodesRef = useRef<any[]>([]);
  nodesRef.current = thinkingMap?.nodes || nodesRef.current;
  const nodes = nodesRef.current;

  const mindMapNodes = useMemo(() => {
    if (!nodes || nodes.length === 0) return [];
    return nodes.map((n: any) => ({
        id: n.id,
        parent_id: n.parent_id || null,
        label: n.label,
        status: n.status,
        created_by: n.created_by || 'brainstorm',
        action_status: n.action_status || null,
        converged_from: n.converged_from || [],
      }));
  }, [nodes]);

  return (
    <div className="dashboard-mindmap">
      <div className="mm-title-row" style={{ cursor: 'pointer', userSelect: 'none' }}
        onClick={() => setExpanded(v => !v)}>
        <span className="collapse-arrow">{expanded ? '▼' : '▶'}</span>
        <h3>🧠 发散阶段 — Thinking Map 思维导图</h3>
        <span className="badge badge-blue">头脑风暴</span>
        <span className="badge badge-orange">收敛标记</span>
        <span className="badge badge-pink">反馈注入</span>
      </div>
      {expanded && (
        <>
          <div className="mm-legend">
            <span><span className="dot blue"></span> 活跃节点</span>
            <span><span className="dot green"></span> 已收敛→队列</span>
            <span><span className="dot orange"></span> 已收敛未分配</span>
            <span><span className="dot gray"></span> 头脑风暴中</span>
            <span><span className="dot pink"></span> 反馈新增</span>
            <span><span className="dot red"></span> 已废弃</span>
            <span className="mm-count">{nodes.length} 节点</span>
          </div>
          <div className="mm-body" ref={mmRef}>
            {nodes.length > 0 ? (
              <CustomMindMap nodes={mindMapNodes} />
            ) : (
              <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>
                发送消息后自动生成思维节点
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ═══ TM 收敛结果卡片 ═══
function TMResultsCard() {
  const thinkingMap = useStore(s => s.thinkingMap);
  const nodes: any[] = thinkingMap?.nodes || [];

  const convergedNodes = nodes.filter((n: any) => n.status === 'confirmed' && n.converged_from?.length > 0);
  const queuedNodes = nodes.filter((n: any) => n.status === 'confirmed' && !n.converged_from?.length);
  const brainstormNodes = nodes.filter((n: any) => n.status !== 'confirmed' && n.status !== 'discarded' && n.type !== 'root');
  const discardedNodes = nodes.filter((n: any) => n.status === 'discarded');
  const feedbackNodes = nodes.filter((n: any) => n.created_by === 'reflect');

  return (
    <div className="card">
      <h3>🧠 Thinking Map <span className="badge badge-orange">收敛结果</span></h3>
      <div className="tm-nodes">
        {convergedNodes.map((n: any) => (
          <div key={n.id} className="tm-node converged">
            <span className="dot orange"></span>
            <span className="text">{n.label} <span className="s">— 合入: {(n.converged_from || []).join(', ')}</span></span>
            {n.converged_from?.length > 0 && <span className="merged-count">🔀×{n.converged_from.length}</span>}
            <span className="status-tag" style={{ background: 'rgba(249,115,22,0.1)', color: '#fb923c' }}>已收敛</span>
          </div>
        ))}
        {queuedNodes.filter((n: any) => n.priority).map((n: any) => (
          <div key={n.id} className="tm-node" style={{ borderColor: 'rgba(34,197,94,0.3)' }}>
            <span className="dot green"></span>
            <span className="text">{n.label}</span>
            <span className="status-tag" style={{ background: 'rgba(34,197,94,0.1)', color: '#4ade80' }}>→队列 P{n.priority}</span>
          </div>
        ))}
        {brainstormNodes.map((n: any) => (
          <div key={n.id} className="tm-node" style={{ borderColor: 'rgba(59,130,246,0.3)' }}>
            <span className="dot blue"></span>
            <span className="text">{n.label}</span>
            <span className="status-tag" style={{ background: 'rgba(59,130,246,0.1)', color: '#60a5fa' }}>头脑风暴中</span>
          </div>
        ))}
        {feedbackNodes.map((n: any) => (
          <div key={n.id} className="tm-node" style={{ borderColor: 'rgba(236,72,153,0.3)' }}>
            <span className="dot pink"></span>
            <span className="text">{n.label}</span>
            <span className="status-tag" style={{ background: 'rgba(236,72,153,0.1)', color: '#f472b6' }}>反馈注入</span>
          </div>
        ))}
        {discardedNodes.map((n: any) => (
          <div key={n.id} className="tm-node strikethrough">
            <span className="dot red"></span>
            <span className="text">{n.label}</span>
            <span className="status-tag" style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}>已废弃</span>
          </div>
        ))}
        {nodes.filter((n: any) => n.type !== 'root').length === 0 && (
          <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
            发送消息后自动生成
          </div>
        )}
      </div>
    </div>
  );
}

// ═══ Priority Queue 卡片 ═══
function PriorityQueueCard() {
  const pq = useStore(s => s.priorityQueue);
  const running = pq.filter(i => i.status === 'running');
  const pending = pq.filter(i => i.status === 'pending');
  const completed = pq.filter(i => i.status === 'completed');
  const blocked = pq.filter(i => i.status === 'blocked');

  const priorityColor = (p: number) => {
    const map: Record<number, string> = { 1: '#f87171', 2: '#fb923c', 3: '#60a5fa', 4: '#888' };
    return map[p] || '#888';
  };
  const priorityBg = (p: number) => {
    const map: Record<number, string> = { 1: 'rgba(239,68,68,0.2)', 2: 'rgba(249,115,22,0.2)', 3: 'rgba(59,130,246,0.2)', 4: 'rgba(100,100,120,0.2)' };
    return map[p] || 'rgba(100,100,120,0.2)';
  };

  const all = [...running, ...pending, ...blocked, ...completed];

  return (
    <div className="card">
      <h3>📊 Priority Queue <span className="badge badge-purple">DAG + 拓扑排序</span></h3>
      {all.length === 0 ? (
        <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
          收敛后自动生成优先级队列
        </div>
      ) : (
        all.map((item) => (
          <div key={item.id} className={`pq-item ${item.status === 'running' ? 'active' : ''} ${item.status === 'completed' ? 'completed' : ''}`}>
            <span className={`prio p${item.priority}`} style={{
              background: priorityBg(item.priority), color: priorityColor(item.priority),
            }}>P{item.priority}</span>
            <span className="pq-text">
              {item.title}
              {item.deps && item.deps.length > 0 && (
                <span className="dep">依赖: {item.deps.join(', ')} · {item.status === 'running' ? '执行中' : item.status === 'blocked' ? '阻塞' : ''}</span>
              )}
            </span>
          </div>
        ))
      )}
      {all.length > 0 && (
        <div className="pq-status">
          <span>📋 队列中: <strong>{pending.length + running.length}</strong></span>
          {blocked.length > 0 && <span>🔴 阻塞: <strong>{blocked.length}</strong></span>}
          <span>✅ 已完成: <strong>{completed.length}</strong></span>
        </div>
      )}
    </div>
  );
}

// ═══ Action Map 聚焦卡片 ═══
function ActionMapCard() {
  const pq = useStore(s => s.priorityQueue);
  const running = pq.filter(i => i.status === 'running');
  const pending = pq.filter(i => i.status === 'pending');
  const completed = pq.filter(i => i.status === 'completed');
  const activeTask = running[0] || null;
  const nextUp = pending.slice(0, 3);

  return (
    <div className="card">
      <h3>🎯 Action Map <span className="badge badge-green">聚焦执行</span></h3>
      <div className="am-focus">
        {activeTask ? (
          <div className="am-active-card">
            <div className="am-label">▶ 当前执行</div>
            <h4>{activeTask.title}</h4>
            <div className="am-progress">
              <div className="am-progress-bar" style={{ width: '45%' }}></div>
            </div>
          </div>
        ) : (
          <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
            {completed.length > 0 ? '✅ 所有任务已完成' : '等待执行任务...'}
          </div>
        )}
        {nextUp.length > 0 && (
          <div className="am-queue-preview">
            <div className="am-queue-item">
              <span className="q-dot" style={{ background: '#fb923c' }}></span>
              <span className="q-text">⬆ 下一步: {nextUp[0].title}</span>
            </div>
            {nextUp.slice(1).map((item, i) => (
              <div key={item.id} className="am-queue-item">
                <span className="q-dot"></span>
                <span className="q-text">{i + 2}. {item.title}</span>
              </div>
            ))}
          </div>
        )}
        {completed.length > 0 && (
          <div className="am-completed">
            <div className="am-c-label">▼ 已完成 ({completed.length})</div>
            <div className="am-completed-item">✅ {completed[completed.length - 1].title}</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══ Reflect Timeline 卡片 ═══
function ReflectCard() {
  const reflectTimeline = useStore(s => s.reflectTimeline);

  return (
    <div className="card">
      <h3>🔄 Reflect Timeline <span className="badge badge-pink">反馈调整</span></h3>
      {reflectTimeline.length === 0 ? (
        <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
          工具执行后将在此记录
        </div>
      ) : (
        reflectTimeline.slice(-10).reverse().map((item: DashboardReflectItem) => (
          <div key={item.id} className="reflect-item">
            <div className={`r-icon ${item.type === 'success' ? 'success' : item.type === 'fail' ? 'fail' : 'new'}`}>
              {item.icon || (item.type === 'success' ? '✅' : item.type === 'fail' ? '🔴' : '💡')}
            </div>
            <div className="r-content">
              <div className="r-title">{item.title}</div>
              {item.detail && <div className="r-detail">{item.detail.slice(0, 120)}</div>}
              {item.tag === 'inject' && <span className="r-tag inject">↪ {item.tag_text || '注入TM'}</span>}
              {item.tag === 'blocked' && <span className="r-tag blocked">🚫 {item.tag_text || '阻塞'}</span>}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

// ═══ Status Bar ═══
const PHASE_LABELS: Record<string, string> = {
  diverge: '🧠 发散', converge: '🔀 收敛', sort: '📊 排序',
  focus: '🎯 聚焦', reflect: '🔄 反馈',
};

function DashboardStatusBar() {
  const { dashboardPhase, dashboardLoopCount, dashboardStepCount, contextUsage, currentModelName } = useStore();

  return (
    <div className="dashboard-status-bar">
      <span className="dot-active"></span>
      <span>Agent Loop 运行中</span>
      <span>|</span>
      <span>当前阶段: <strong>{PHASE_LABELS[dashboardPhase] || dashboardPhase}</strong></span>
      <span>|</span>
      <span>循环: {dashboardLoopCount}</span>
      <span>|</span>
      <span>步: {dashboardStepCount}</span>
      {contextUsage && (
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#888' }}>
          ⚡ Token: {contextUsage.usageStr} · {contextUsage.progressBar}
        </span>
      )}
    </div>
  );
}

// ═══ 仪表盘根组件 ═══
export default function AgentLoopDashboard() {
  return (
    <div className="agent-loop-dashboard">
      <LoopDiagram />
      <CollapsibleMindMap />
      <div className="grid dashboard-grid">
        <TMResultsCard />
        <PriorityQueueCard />
        <ActionMapCard />
        <ReflectCard />
      </div>
      <DashboardStatusBar />
    </div>
  );
}
