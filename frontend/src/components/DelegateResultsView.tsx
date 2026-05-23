/** 🧩 子 Agent 成果展示页 — 持久化的 delegate 结果卡片网格 */
import { useEffect, useState } from 'react';

interface DelegateResult {
  id: string;
  scene_id: string;
  session_id: string | null;
  parent_message_id: string | null;
  task: string;
  status: string;     // success / error / timeout
  summary: string;
  steps: number;
  error: string | null;
  created_at: string;
}

const STATUS_META: Record<string, { icon: string; label: string; color: string }> = {
  success: { icon: '✅', label: '成功', color: '#3fb950' },
  error:   { icon: '❌', label: '失败', color: '#ff7b72' },
  timeout: { icon: '⏱️', label: '超时', color: '#d29922' },
};

function getStatusMeta(status: string) {
  return STATUS_META[status] || { icon: '❓', label: status, color: '#8b949e' };
}

export function DelegateResultsView() {
  const [results, setResults] = useState<DelegateResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadResults = async () => {
    setLoading(true);
    try {
      const resp = await fetch('/api/delegate-results');
      const data = await resp.json();
      setResults(data || []);
    } catch {
      setResults([]);
    }
    setLoading(false);
  };

  useEffect(() => { loadResults(); }, []);

  const toggleExpanded = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="tools-view">
      <div className="view-header">
        <div style={{ fontSize: 16, fontWeight: 600 }}>🧩 子 Agent 成果</div>
        <button
          className="btn-icon"
          onClick={loadResults}
          title="刷新"
          style={{
            marginLeft: 8, background: 'none', border: '1px solid #30363d',
            borderRadius: 6, padding: '4px 10px', color: '#8b949e', cursor: 'pointer', fontSize: 13,
          }}
        >
          🔄
        </button>
      </div>

      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#8b949e' }}>加载中...</div>
      ) : results.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#8b949e' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🤖</div>
          <div style={{ fontSize: 15, marginBottom: 8 }}>暂无子 Agent 执行记录</div>
          <div style={{ fontSize: 13 }}>场景中使用 delegate_task 派发子任务后，结果会出现在这里</div>
        </div>
      ) : (
        <div className="output-gallery-grid">
          {results.map(r => {
            const meta = getStatusMeta(r.status);
            const isExpanded = expandedId === r.id;
            return (
              <div
                key={r.id}
                className="output-card"
                onClick={() => toggleExpanded(r.id)}
                style={{ cursor: 'pointer' }}
              >
                {/* 头部：状态图标 + 任务目标 */}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
                  <span style={{ fontSize: 24, flexShrink: 0 }}>{meta.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 14, fontWeight: 600, color: '#e6edf3', marginBottom: 4,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>
                      {r.task}
                    </div>
                    <div style={{ fontSize: 12, color: meta.color, marginBottom: 4 }}>
                      {meta.label} · {r.steps} 步
                    </div>
                    {/* 摘要（折叠/展开） */}
                    {isExpanded ? (
                      <div style={{ fontSize: 12, color: '#c9d1d9', lineHeight: 1.5, marginTop: 6, whiteSpace: 'pre-wrap' }}>
                        {r.summary}
                        {r.error && (
                          <div style={{ color: '#ff7b72', marginTop: 6, padding: '6px 8px', background: 'rgba(255,123,114,0.08)', borderRadius: 4 }}>
                            ❌ {r.error}
                          </div>
                        )}
                      </div>
                    ) : (
                      r.summary && (
                        <div style={{
                          fontSize: 12, color: '#6e7681', lineHeight: 1.4,
                          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                        }}>
                          {r.summary}
                        </div>
                      )
                    )}
                  </div>
                </div>
                {/* 底部：时间 */}
                <div style={{ fontSize: 11, color: '#484f58' }}>
                  {new Date(r.created_at).toLocaleString('zh-CN')}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
