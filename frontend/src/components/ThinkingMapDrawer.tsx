import { useEffect, useRef, useState } from 'react';
import { useStore } from '../stores/appStore';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';

/** 扁平节点 → markdown */
function nodesToMarkdown(nodes: any[]): string {
  if (!nodes || nodes.length === 0) return '# 暂无数据';
  const root = nodes.find((n: any) => n.type === 'root' && !n.parent_id);
  if (!root) return '# 无根节点';
  const childrenMap: Record<string, any[]> = {};
  nodes.forEach(n => {
    const pid = n.parent_id || '__orphan__';
    if (!childrenMap[pid]) childrenMap[pid] = [];
    childrenMap[pid].push(n);
  });
  const walk = (nodeId: string, level: number): string => {
    const node = nodes.find((n: any) => n.id === nodeId);
    if (!node) return '';
    const prefix = '#'.repeat(Math.min(level + 1, 6));
    let icon = '';
    if (node.status === 'confirmed') icon = ' ✓';
    else if (node.status === 'discussing') icon = ' ❓';
    if (node.actionable) icon += ' 🔧';
    let md = `${prefix} ${node.label}${icon}\n`;
    const kids = childrenMap[node.id] || [];
    for (const kid of kids) kids.sort((a: any, b: any) => a.label.localeCompare(b.label));
    for (const kid of kids) md += walk(kid.id, level + 1);
    return md;
  };
  return walk(root.id, 0);
}

export function ThinkingMapDrawer() {
  const { drawerOpen, closeDrawer, thinkingMap, toggleNodeActionable } = useStore();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [showNodeSettings, setShowNodeSettings] = useState(false);

  useEffect(() => {
    if (!drawerOpen || !thinkingMap) return;

    if (!wrapRef.current) return;
    setStatus('loading');

    const el = wrapRef.current;
    el.innerHTML = '';

    try {
      const markdown = nodesToMarkdown(thinkingMap.nodes);

      const transformer = new Transformer();
      const result = transformer.transform(markdown);

      if (!result?.root) {
        throw new Error('Transformer 返回了空数据');
      }

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      el.appendChild(svg);
      el.classList.add('markmap-dark');
      const mm = Markmap.create(svg, { duration: 0 }, result.root);
      mm.fit();
      setStatus('ready');
    } catch (e: any) {
      console.error('[ThinkingMap] render error:', e);
      setStatus('error');
      el.innerHTML = `<pre style="color:#f85149;padding:20px;font-size:12px">渲染失败: ${e.message}\n\n${nodesToMarkdown(thinkingMap.nodes)}</pre>`;
    }
  }, [drawerOpen, thinkingMap]);

  if (!drawerOpen) return null;

  // 找所有叶子节点
  const leafNodes = (thinkingMap?.nodes || []).filter(
    (n: any) => n.type === 'leaf' && !(thinkingMap?.nodes || []).some((c: any) => c.parent_id === n.id)
  );

  return (
    <>
      <div className="drawer-overlay open" onClick={closeDrawer} />
      <div className="drawer open">
        <div className="drawer-header">
          <span className="tab active">🧠 Thinking Map</span>
          <button
            className={`tab ${showNodeSettings ? 'active' : ''}`}
            style={{ cursor: 'pointer', border: 'none', background: 'none', color: showNodeSettings ? '#58a6ff' : '#8b949e', fontSize: '14px', padding: '4px 12px' }}
            onClick={() => setShowNodeSettings(!showNodeSettings)}
          >
            🔧 节点设置
          </button>
          <span className="close" onClick={closeDrawer}>✕</span>
        </div>
        <div className="drawer-body" style={{ background: '#0d1117', display: 'flex', flexDirection: 'column' }}>
          {status === 'loading' && (
            <div style={{ color: '#8b949e', padding: 40, textAlign: 'center' }}>加载中...</div>
          )}
          <div id="mindmap-wrap" ref={wrapRef} style={{ flex: 1, minHeight: 0 }} />

          {/* ═══ 节点设置面板 ═══ */}
          {showNodeSettings && (
            <div className="node-settings-panel">
              <h4 style={{ margin: '0 0 8px', fontSize: '14px', color: '#e6edf3' }}>
                🔧 叶子节点设置
              </h4>
              <p style={{ fontSize: '12px', color: '#8b949e', margin: '0 0 12px' }}>
                标记「可执行」后，可在 ⚡ Action Map 抽屉中生成行动计划
              </p>
              {leafNodes.length === 0 ? (
                <div style={{ color: '#8b949e', fontSize: '13px', padding: '12px 0', textAlign: 'center' }}>
                  暂无叶子节点
                </div>
              ) : (
                <div className="node-settings-list">
                  {leafNodes.map((n: any) => (
                    <div key={n.id} className="node-settings-row">
                      <div className="node-settings-info">
                        <span className="node-settings-label">
                          {n.actionable && '🔧 '}
                          {n.label}
                        </span>
                        <span className="node-settings-status">
                          {n.status === 'confirmed' ? '✅' : n.status === 'discussing' ? '❓' : ''}
                        </span>
                      </div>
                      <button
                        className={`toggle-actionable ${n.actionable ? 'on' : 'off'}`}
                        onClick={() => toggleNodeActionable(n.id, !n.actionable)}
                      >
                        {n.actionable ? '🔧 可执行' : '○ 设为可执行'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
