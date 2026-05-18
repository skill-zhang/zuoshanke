/** ActionMapDrawer — Action Map 列表 + React Flow 详情视图 + Hermes 日志面板 + 执行记录 + 工具查看 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { useStore } from '../stores/appStore';
import { generateActionMapStream, executeActionMapStream, getActionMapLogs, getToolSkill, type ExecuteStreamEvent, type ActionExecutionLog } from '../api/client';
import ActionMapView from './ActionMapView';

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  draft:    { label: '📝 草稿', cls: 'card-status paused' },
  ready:    { label: '▶ 就绪', cls: 'card-status completed' },
  running:  { label: '⏳ 执行中', cls: 'card-status running' },
  paused:   { label: '⏸ 暂停', cls: 'card-status paused' },
  completed:{ label: '✅ 完成', cls: 'card-status completed' },
  failed:   { label: '❌ 失败', cls: 'card-status failed' },
};

export function ActionMapDrawer() {
  const {
    actionMapDrawerOpen,
    closeActionMapDrawer,
    actionMaps,
    currentActionMap,
    setCurrentActionMap,
    updateActionMapStatusAndReload,
    deleteActionMapAndReload,
    thinkingMap,
  } = useStore();

  // ═══ Hermes 生成状态 ═══
  const [generatingNodeId, setGeneratingNodeId] = useState<string | null>(null);
  const [hermesLogs, setHermesLogs] = useState<string[]>([]);
  const [genError, setGenError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  const handleGenerate = useCallback(async (thinkNodeId: string) => {
    setGeneratingNodeId(thinkNodeId);
    setHermesLogs([]);
    setGenError(null);

    try {
      const generator = generateActionMapStream(thinkNodeId);
      for await (const event of generator) {
        if (event.type === 'hermes_log' || event.type === 'status') {
          setHermesLogs(prev => [...prev, event.line]);
        } else if (event.type === 'result') {
          const store = useStore.getState();
          if (store.thinkingMap) {
            await store.loadActionMaps(store.thinkingMap.id);
            const sceneId = store.currentScene?.id;
            if (sceneId) await store.loadThinkingMap(sceneId);
          }
          useStore.setState({ actionMapDrawerOpen: true });
          setGeneratingNodeId(null);
        } else if (event.type === 'error') {
          setGenError(event.message);
          setGeneratingNodeId(null);
        } else if (event.type === 'done') {
          setGeneratingNodeId(null);
        }
      }
    } catch (err: any) {
      setGenError(err.message || '网络错误');
      setGeneratingNodeId(null);
    }
  }, []);

  // ═══ Action Map 执行状态 ═══
  const [executingMapId, setExecutingMapId] = useState<string | null>(null);
  const [execLogs, setExecLogs] = useState<Array<{nodeId: string; line: string}>>([]);
  const [execNodeStatus, setExecNodeStatus] = useState<Record<string, string>>({});
  const [execError, setExecError] = useState<string | null>(null);
  const [newTools, setNewTools] = useState<Array<{ name: string; description: string }>>([]);

  const handleExecute = useCallback(async () => {
    if (!currentActionMap) return;
    const mapId = currentActionMap.id;
    setExecutingMapId(mapId);
    setExecLogs([]);
    setExecNodeStatus({});
    setExecError(null);
    setNewTools([]);

    try {
      const generator = executeActionMapStream(mapId);
      for await (const event of generator) {
        if (event.type === 'node_start') {
          setExecNodeStatus(prev => ({ ...prev, [event.node_id]: 'running' }));
          setExecLogs(prev => [...prev, { nodeId: event.node_id, line: `▶ ${event.label}` }]);
        } else if (event.type === 'node_done') {
          setExecNodeStatus(prev => ({ ...prev, [event.node_id]: event.status }));
          const icon = event.status === 'completed' ? '✅' : '❌';
          setExecLogs(prev => [...prev, { nodeId: event.node_id, line: `${icon} ${event.label} (${event.status})` }]);
        } else if (event.type === 'hermes_log') {
          setExecLogs(prev => [...prev, { nodeId: event.node_id, line: event.line }]);
        } else if (event.type === 'tools_documented') {
          setNewTools(event.tools);
          setExecLogs(prev => [...prev, {
            nodeId: '', line: `🔧 新增 ${event.count} 个工具: ${event.tools.map(t => t.name).join(', ')}`
          }]);
        } else if (event.type === 'map_done') {
          const store = useStore.getState();
          if (store.thinkingMap) {
            await store.loadActionMaps(store.thinkingMap.id);
            const sceneId = store.currentScene?.id;
            if (sceneId) {
              await store.loadThinkingMap(sceneId);
              await store.loadSceneMessages(sceneId);  // 刷新聊天消息
            }
          }
          const refreshed = useStore.getState().actionMaps.find(m => m.id === mapId);
          if (refreshed) useStore.setState({ currentActionMap: refreshed });
          setExecutingMapId(null);
        } else if (event.type === 'error') {
          setExecError(event.message);
          setExecutingMapId(null);
        }
      }
    } catch (err: any) {
      setExecError(err.message || '网络错误');
      setExecutingMapId(null);
    }
  }, [currentActionMap]);

  // 自动滚动日志到底部
  useEffect(() => {
    if (generatingNodeId && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [hermesLogs, generatingNodeId]);

  // ═══ 可拖拽调整宽度 ═══
  const [drawerWidth, setDrawerWidth] = useState(840);
  const resizing = useRef(false);
  const startX = useRef(0);
  const startW = useRef(840);

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizing.current = true;
    startX.current = e.clientX;
    startW.current = drawerWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [drawerWidth]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!resizing.current) return;
      const dx = startX.current - e.clientX;
      const newW = Math.max(500, Math.min(1400, startW.current + dx));
      setDrawerWidth(newW);
    };
    const onUp = () => {
      resizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  // ═══ 执行记录面板 ═══
  const [showExecHistory, setShowExecHistory] = useState(false);
  const [execHistoryLogs, setExecHistoryLogs] = useState<ActionExecutionLog[]>([]);
  const [execHistoryLoading, setExecHistoryLoading] = useState(false);

  const loadExecHistory = useCallback(async () => {
    if (!currentActionMap) return;
    setExecHistoryLoading(true);
    try {
      const logs = await getActionMapLogs(currentActionMap.id);
      setExecHistoryLogs(logs);
      setShowExecHistory(true);
    } catch (e) {
      console.error('loadExecHistory:', e);
    } finally {
      setExecHistoryLoading(false);
    }
  }, [currentActionMap]);

  // ═══ 工具查看 ═══
  const [expandedTool, setExpandedTool] = useState<string | null>(null);
  const [toolSkillContent, setToolSkillContent] = useState<string>('');
  const [toolSkillLoading, setToolSkillLoading] = useState(false);

  const toggleToolInspector = useCallback(async (toolName: string) => {
    if (expandedTool === toolName) {
      setExpandedTool(null);
      return;
    }
    setExpandedTool(toolName);
    setToolSkillLoading(true);
    try {
      const res = await getToolSkill(toolName);
      setToolSkillContent(res.data?.content || '');
    } catch (e) {
      setToolSkillContent(`❌ 加载失败: ${e}`);
    } finally {
      setToolSkillLoading(false);
    }
  }, [expandedTool]);

  // 切换 Action Map 时重置执行状态
  useEffect(() => {
    setShowExecHistory(false);
    setExecHistoryLogs([]);
    setExpandedTool(null);
    setNewTools([]);
    // 如果当前执行的不是这个 map，清执行状态
    if (executingMapId && executingMapId !== currentActionMap?.id) {
      setExecLogs([]);
      setExecNodeStatus({});
      setExecError(null);
    }
  }, [currentActionMap?.id]);

  if (!actionMapDrawerOpen) return null;

  const completedNodes = (m: any) =>
    m.nodes?.filter((n: any) => n.status === 'completed').length || 0;
  const totalNodes = (m: any) => m.nodes?.length || 0;

  // ═══ 可执行节点（按 think_node_id 分组统计版本） ═══
  const actionableNodes = thinkingMap?.nodes?.filter(
    (n: any) => n.actionable
  ) || [];
  const nodeVersionCount: Record<string, number> = {};
  const nodeLatestMap: Record<string, any> = {};
  actionMaps.forEach(m => {
    nodeVersionCount[m.think_node_id] = (nodeVersionCount[m.think_node_id] || 0) + 1;
    if (!nodeLatestMap[m.think_node_id] || new Date(m.updated_at) > new Date(nodeLatestMap[m.think_node_id].updated_at)) {
      nodeLatestMap[m.think_node_id] = m;
    }
  });

  return (
    <>
      <div className="drawer-overlay open" onClick={closeActionMapDrawer} />
      <div className="drawer open" style={{ width: drawerWidth, right: 0 }}>
        {/* 左边缘拖拽把手 */}
        <div
          onMouseDown={onResizeStart}
          style={{
            position: 'absolute', left: -2, top: 0, bottom: 0, width: 8,
            cursor: 'col-resize', zIndex: 10, background: 'transparent',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onMouseEnter={(e) => {
            (e.target as HTMLElement).style.background = 'rgba(88,166,255,0.08)';
            const grip = (e.target as HTMLElement).querySelector('.resize-grip') as HTMLElement;
            if (grip) grip.style.opacity = '1';
          }}
          onMouseLeave={(e) => {
            (e.target as HTMLElement).style.background = 'transparent';
            const grip = (e.target as HTMLElement).querySelector('.resize-grip') as HTMLElement;
            if (grip) grip.style.opacity = '0.3';
          }}
        >
          <span className="resize-grip" style={{
            display: 'inline-block', width: '18px', height: '32px',
            border: '3px solid #484f58', borderRadius: '5px',
            background: 'rgba(72,79,88,0.1)', opacity: 0.3,
            transition: 'opacity 0.15s, border-color 0.15s',
            userSelect: 'none', pointerEvents: 'none',
          }} />
        </div>
        <div className="drawer-header">
          <span className="tab active">
            ⚡ Action Maps {!currentActionMap && `(${actionMaps.length})`}
          </span>
          {currentActionMap && (
            <span className="tab" style={{ cursor: 'pointer' }} onClick={() => setCurrentActionMap(null)}>
              ← 列表
            </span>
          )}
          <span className="close" onClick={closeActionMapDrawer}>✕</span>
        </div>

        <div className="drawer-body" style={{ background: '#0d1117', display: 'flex', flexDirection: 'column' }}>
          {!currentActionMap ? (
            /* ═══ 列表视图 ═══ */
            <div className="action-list">
              <h3 style={{ margin: '0 0 4px' }}>⚡ Action Maps</h3>

              {generatingNodeId && (
                <div className="hermes-log-panel">
                  <div className="hermes-log-header">
                    <span>🧠 Hermes 正在生成…</span>
                    <button className="btn" style={{ fontSize: '11px', padding: '2px 10px', background: 'rgba(248,81,73,0.1)', borderColor: '#f85149', color: '#f85149' }}
                      onClick={() => setGeneratingNodeId(null)}>停止</button>
                  </div>
                  <div className="hermes-log-body">
                    {hermesLogs.map((line, i) => (
                      <div key={i} className="hermes-log-line">{line}</div>
                    ))}
                    <div ref={logEndRef} />
                  </div>
                </div>
              )}

              {genError && (
                <div className="hermes-error" onClick={() => setGenError(null)}>
                  ❌ {genError} <span style={{ fontSize: '11px', opacity: 0.7 }}>(点击关闭)</span>
                </div>
              )}

              {/* ═══ 可执行节点 ═══ */}
              {actionableNodes.length > 0 && (
                <div style={{ marginBottom: '16px' }}>
                  <p className="subtitle" style={{ marginBottom: '10px' }}>
                    🔧 可执行节点 — 点击生成 Action Map
                  </p>
                  {actionableNodes.map((n: any) => {
                    const count = nodeVersionCount[n.id] || 0;
                    const latest = nodeLatestMap[n.id];
                    return (
                      <div key={n.id} className="action-card" style={{ borderColor: '#58a6ff33', marginBottom: '8px' }}>
                        <div className="card-header">
                          <span className="card-title">🔧 {n.label}</span>
                          {count > 0 && latest && (
                            <span className={`card-status ${(STATUS_BADGE[latest.status]?.cls.split(' ')[1]) || 'paused'}`}>
                              已有 {count} 个版本 · {STATUS_BADGE[latest.status]?.label}
                            </span>
                          )}
                          {count === 0 && <span className="card-status paused">尚未生成</span>}
                        </div>
                        <button className="btn" disabled={generatingNodeId !== null}
                          style={{ marginTop: '8px', fontSize: '13px', padding: '5px 16px',
                            background: '#1f3a5f', borderColor: '#58a6ff', color: '#58a6ff',
                            opacity: generatingNodeId ? 0.5 : 1 }}
                          onClick={(e) => { e.stopPropagation(); handleGenerate(n.id); }}>
                          {count > 0 ? '⚡ 生成新版本' : '⚡ 生成 Action Map'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* ═══ 已有 Action Map 卡片 ═══ */}
              {actionMaps.length > 0 && (
                <>
                  {actionableNodes.length > 0 && (
                    <p className="subtitle" style={{ marginBottom: '8px' }}>─── 已有 Action Map ───</p>
                  )}
                  {actionMaps.map((m) => {
                    const badge = STATUS_BADGE[m.status] || STATUS_BADGE.draft;
                    return (
                      <div key={m.id} className="action-card" onClick={() => setCurrentActionMap(m)}>
                        <div className="card-header">
                          <span className="card-title">{m.title}</span>
                          <span className={`card-status ${badge.cls.split(' ')[1] || 'paused'}`}>{badge.label}</span>
                        </div>
                        <div className="card-meta">
                          <span>📊 节点: {completedNodes(m)}/{totalNodes(m)}</span>
                          <span>🕐 {new Date(m.updated_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
                          {m.replan_count > 0 && <span style={{ color: '#d29922' }}>🔄 重规划 {m.replan_count} 次</span>}
                        </div>
                        <div style={{ display: 'flex', gap: '8px', marginTop: '8px', flexWrap: 'wrap' }}
                             onClick={(e) => e.stopPropagation()}>
                          {m.status === 'draft' && (
                            <button className="btn" style={{ fontSize: '12px', padding: '3px 10px', background: '#1f3a5f', borderColor: '#58a6ff', color: '#58a6ff' }}
                              onClick={() => updateActionMapStatusAndReload(m.id, 'ready')}>▶ 就绪</button>
                          )}
                          {(m.status === 'ready' || m.status === 'paused') && (
                            <button className="btn" style={{ fontSize: '12px', padding: '3px 10px', background: 'rgba(63,185,80,0.1)', borderColor: '#3fb950', color: '#3fb950' }}
                              onClick={() => updateActionMapStatusAndReload(m.id, 'running')}>▶ 开始</button>
                          )}
                          {m.status === 'running' && (
                            <button className="btn" style={{ fontSize: '12px', padding: '3px 10px', background: 'rgba(210,153,34,0.1)', borderColor: '#d29922', color: '#d29922' }}
                              onClick={() => updateActionMapStatusAndReload(m.id, 'paused')}>⏸ 暂停</button>
                          )}
                          <button className="btn" disabled={generatingNodeId !== null}
                            style={{ fontSize: '12px', padding: '3px 10px', background: 'rgba(88,166,255,0.08)', borderColor: '#58a6ff', color: '#58a6ff', opacity: generatingNodeId ? 0.5 : 1 }}
                            onClick={() => handleGenerate(m.think_node_id)}>🔄 重新生成</button>
                          <button className="btn" style={{ fontSize: '12px', padding: '3px 10px', background: 'rgba(248,81,73,0.08)', borderColor: '#f85149', color: '#f85149' }}
                            onClick={() => { if (confirm(`删除 "${m.title}"？`)) deleteActionMapAndReload(m.id); }}>🗑 删除</button>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}

              {actionableNodes.length === 0 && actionMaps.length === 0 && (
                <div style={{ color: '#8b949e', padding: '30px 0', textAlign: 'center', fontSize: '14px' }}>
                  暂无 Action Map<br />
                  <span style={{ fontSize: '12px' }}>在 Thinking Map 中将叶子节点标记为「可执行」后生成</span>
                </div>
              )}
            </div>
          ) : (
            /* ═══ 详情视图（React Flow + 执行记录 + 工具查看） ═══ */
            <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '12px', borderBottom: '1px solid #21262d' }}>
                <span style={{ fontSize: '15px', color: '#e6edf3', fontWeight: 500 }}>{currentActionMap.title}</span>
                <span className={`card-status ${(STATUS_BADGE[currentActionMap.status]?.cls.split(' ')[1]) || 'paused'}`}
                      style={{ fontSize: '11px' }}>{STATUS_BADGE[currentActionMap.status]?.label || currentActionMap.status}</span>
                <div style={{ flex: 1 }} />
                {executingMapId ? (
                  <button className="btn" style={{ fontSize: '12px', padding: '3px 12px', background: 'rgba(248,81,73,0.1)', borderColor: '#f85149', color: '#f85149' }}
                    onClick={() => setExecutingMapId(null)}>⏹ 停止</button>
                ) : (
                  (currentActionMap.status === 'ready' || currentActionMap.status === 'running') && (
                    <button className="btn" style={{ fontSize: '12px', padding: '3px 12px', background: 'rgba(63,185,80,0.1)', borderColor: '#3fb950', color: '#3fb950' }}
                      onClick={handleExecute}>▶ 执行</button>
                  )
                )}
                <div style={{ display: 'flex', gap: '6px', fontSize: '11px', color: '#8b949e' }}>
                  <span>🟢 完成</span><span>🔴 失败</span><span>🔵 执行中</span><span>⚪ 待执行</span>
                </div>
              </div>
              <div style={{ flex: 1, minHeight: 0 }}>
                <ActionMapView
                  nodes={currentActionMap.nodes}
                  edges={currentActionMap.edges}
                  nodeStatusOverrides={execNodeStatus}
                />
              </div>

              {/* ═══ Hermes 实时执行日志面板 ═══ */}
              {(executingMapId && executingMapId === currentActionMap?.id) && (
                <div className="hermes-log-panel" style={{ margin: 0, borderTop: '1px solid #21262d' }}>
                  <div className="hermes-log-header"><span>⚡ Hermes 正在执行...</span></div>
                  <div className="hermes-log-body" style={{ maxHeight: '160px' }}>
                    {execLogs.map((entry, i) => (
                      <div key={i} className="hermes-log-line">{entry.line}</div>
                    ))}
                    <div ref={logEndRef} />
                  </div>
                </div>
              )}

              {/* 执行错误 */}
              {execError && (
                <div className="hermes-error" onClick={() => setExecError(null)}>
                  ❌ {execError} <span style={{ fontSize: '11px', opacity: 0.7 }}>(点击关闭)</span>
                </div>
              )}

              {/* ═══ 执行记录 & 工具（执行完成后可见） ═══ */}
              {!executingMapId && (currentActionMap.status === 'completed' || currentActionMap.status === 'failed') && (
                <div style={{ borderTop: '1px solid #21262d', background: '#0d1117' }}>
                  {/* 工具列表 */}
                  {newTools.length > 0 && (
                    <div style={{ padding: '10px 16px', borderBottom: '1px solid #21262d20' }}>
                      <span style={{ color: '#58a6ff', fontSize: '13px', fontWeight: 500 }}>🔧 新增工具: </span>
                      {newTools.map((t, i) => (
                        <span key={t.name}>
                          <span
                            onClick={() => toggleToolInspector(t.name)}
                            style={{
                              color: '#58a6ff', cursor: 'pointer', textDecoration: 'underline',
                              fontSize: '13px', fontFamily: 'monospace',
                            }}
                          >{t.name}</span>
                          {i < newTools.length - 1 && <span style={{ color: '#484f58' }}> · </span>}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* 工具详情 — 内联展开 */}
                  {expandedTool && (
                    <div style={{ padding: '12px 16px', borderBottom: '1px solid #21262d20', background: '#161b22' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <span style={{ color: '#e6edf3', fontSize: '14px', fontWeight: 500 }}>
                          📄 {expandedTool} — 使用说明
                        </span>
                        <button className="btn" style={{ fontSize: '11px', padding: '2px 8px', background: 'transparent', borderColor: '#484f58', color: '#8b949e' }}
                          onClick={() => setExpandedTool(null)}>✕ 收起</button>
                      </div>
                      {toolSkillLoading ? (
                        <div style={{ color: '#8b949e', fontSize: '13px' }}>⏳ 加载中...</div>
                      ) : (
                        <div style={{
                          color: '#c9d1d9', fontSize: '13px', lineHeight: 1.6,
                          whiteSpace: 'pre-wrap', fontFamily: 'monospace',
                          maxHeight: '400px', overflowY: 'auto',
                          background: '#0d1117', padding: '12px', borderRadius: '6px',
                        }}>
                          {toolSkillContent}
                        </div>
                      )}
                    </div>
                  )}

                  {/* 📋 执行记录按钮 */}
                  <div style={{ padding: '8px 16px' }}>
                    <button className="btn"
                      style={{ fontSize: '12px', padding: '3px 12px', background: 'transparent', borderColor: '#484f58', color: '#8b949e' }}
                      onClick={() => showExecHistory ? setShowExecHistory(false) : loadExecHistory()}>
                      {showExecHistory ? '📋 收起执行记录' : '📋 查看执行记录'}
                    </button>
                  </div>

                  {/* 执行记录面板 */}
                  {showExecHistory && (
                    <div className="hermes-log-panel" style={{ margin: '0 16px 12px', borderTop: '1px solid #21262d' }}>
                      <div className="hermes-log-header"><span>📋 执行记录</span></div>
                      <div className="hermes-log-body" style={{ maxHeight: '300px' }}>
                        {execHistoryLoading ? (
                          <div className="hermes-log-line">⏳ 加载中...</div>
                        ) : execHistoryLogs.length === 0 ? (
                          <div className="hermes-log-line" style={{ color: '#8b949e' }}>暂无执行记录</div>
                        ) : (
                          execHistoryLogs.map((log, i) => {
                            const prefix = log.event_type === 'node_start' ? '▶' :
                                           log.event_type === 'node_done' ? (log.status === 'completed' ? '✅' : '❌') :
                                           log.event_type === 'tools_documented' ? '🔧' : '  ';
                            const label = log.node_label ? `[${log.node_label}] ` : '';
                            return (
                              <div key={log.id || i} className="hermes-log-line">
                                {prefix} {label}{log.line || ''}
                                {log.result && (
                                  <div style={{ fontSize: '11px', color: '#8b949e', paddingLeft: '24px', marginTop: '2px' }}>
                                    {log.result.slice(0, 200)}
                                  </div>
                                )}
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
