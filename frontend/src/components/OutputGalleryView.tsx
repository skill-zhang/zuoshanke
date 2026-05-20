/** 📦 产出成果视图 — 分身生成的独立 HTML/入口卡片网格 */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';

interface Output {
  id: string;
  scene_id: string;
  title: string;
  description: string;
  type: string;
  file_path: string | null;
  url: string | null;
  created_at: string;
}

const TYPE_META: Record<string, { icon: string; label: string }> = {
  html: { icon: '📄', label: 'HTML 页面' },
  link: { icon: '🔗', label: '外部链接' },
};

function getTypeMeta(type: string) {
  return TYPE_META[type] || { icon: '📦', label: type };
}

export function OutputGalleryView() {
  const setView = useStore(s => s.setView);
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [loading, setLoading] = useState(true);

  const loadOutputs = async () => {
    setLoading(true);
    try {
      const resp = await fetch('/api/outputs');
      const data = await resp.json();
      setOutputs(data || []);
    } catch {
      setOutputs([]);
    }
    setLoading(false);
  };

  useEffect(() => { loadOutputs(); }, []);

  return (
    <div className="tools-view">
      <div className="view-header">
        <div style={{ fontSize: 16, fontWeight: 600 }}>📦 产出成果</div>
      </div>

      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#8b949e' }}>加载中...</div>
      ) : outputs.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#8b949e' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
          <div style={{ fontSize: 15, marginBottom: 8 }}>暂无产出成果</div>
          <div style={{ fontSize: 13 }}>分身创建 HTML 或注册入口后，会出现在这里</div>
        </div>
      ) : (
        <div className="card-grid">
          {outputs.map(out => {
            const meta = getTypeMeta(out.type);
            let href = out.url || '';
            if (out.file_path && !href) {
              href = `/outputs/${out.file_path}`;
            }
            // 前端 5173 端口 → 后端 8000 端口
            const fullHref = href ? `http://localhost:8000${href}` : '';
            return (
              <div
                key={out.id}
                className="output-card"
                onClick={() => { if (fullHref) window.open(fullHref, '_blank'); }}
                style={{ cursor: fullHref ? 'pointer' : 'default' }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
                  <span style={{ fontSize: 28, flexShrink: 0 }}>{meta.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: '#e6edf3', marginBottom: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {out.title}
                    </div>
                    <div style={{ fontSize: 12, color: '#8b949e', marginBottom: 6 }}>
                      {meta.label}
                    </div>
                    {out.description && (
                      <div style={{ fontSize: 12, color: '#6e7681', lineHeight: 1.4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {out.description}
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ fontSize: 11, color: '#484f58' }}>
                  {new Date(out.created_at).toLocaleString('zh-CN')}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
