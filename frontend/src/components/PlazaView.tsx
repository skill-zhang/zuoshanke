/** 🏪 场景广场 — 浏览已发布的场景 */
import { useEffect, useState, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import { Scene, updateScene } from '../api/client';

const CATEGORIES = [
  { key: 'all', icon: '🔍', label: '全部' },
  { key: 'life', icon: '🌿', label: '生活' },
  { key: 'ecommerce', icon: '🛒', label: '电商' },
  { key: 'work', icon: '💼', label: '工作' },
  { key: 'learn', icon: '📚', label: '学习' },
  { key: 'create', icon: '🎨', label: '创作' },
  { key: 'finance', icon: '📈', label: '金融' },
  { key: 'media', icon: '💬', label: '自媒体' },
];

const SOURCE_LABELS: Record<string, string> = {
  system: '坐山客系统',
  self: '你',
  imported: '导入',
};

interface PlazaViewProps {
  onEnterScene: (scene: Scene) => void;
  onCreateScene: () => void;
  onImportScene: () => void;
}

export function PlazaView({ onEnterScene, onCreateScene, onImportScene }: PlazaViewProps) {
  const { plazaScenes, loadPlazaScenes, loadingPlaza } = useStore();
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadPlazaScenes();
  }, []);

  useEffect(() => {
    const params: { category?: string; q?: string } = {};
    if (category !== 'all') params.category = category;
    if (search.trim()) params.q = search.trim();
    loadPlazaScenes(params);
  }, [category, search]);

  const filtered = plazaScenes;

  const formatDate = (d: string | null) => {
    if (!d) return '';
    try {
      const date = new Date(d);
      const now = new Date();
      const diff = now.getTime() - date.getTime();
      const days = Math.floor(diff / 86400000);
      if (days === 0) return '今天';
      if (days === 1) return '昨天';
      if (days < 7) return `${days}天前`;
      return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    } catch { return ''; }
  };

  const toggleWorkbenchPin = useCallback(async (scene: Scene, e: React.MouseEvent) => {
    e.stopPropagation();
    await updateScene(scene.id, { show_on_workbench: !scene.show_on_workbench });
    loadPlazaScenes();
  }, [loadPlazaScenes]);

  return (
    <div className="plaza">
      <div className="category-bar">
        {CATEGORIES.map(c => (
          <div
            key={c.key}
            className={`category-tab${category === c.key ? ' active' : ''}`}
            onClick={() => setCategory(c.key)}
          >
            {c.icon} {c.label}
          </div>
        ))}
      </div>

      <div className="plaza-toolbar">
        <div className="search-box">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            placeholder="搜索场景..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={onImportScene}>📥 导入场景</button>
          <button className="btn btn-accent" onClick={onCreateScene}>✨ 创建场景</button>
        </div>
      </div>

      <div className="plaza-grid">
        {loadingPlaza ? (
          <div className="empty-state">
            <div className="empty-state-text">加载中...</div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📭</div>
            <div className="empty-state-text">暂无已发布的场景</div>
            <div className="empty-state-desc">去工坊发布一个场景，或换个分类看看</div>
          </div>
        ) : filtered.map(s => (
          <div key={s.id} className="scene-card" onClick={() => onEnterScene(s)}>
            <div className="scene-card-icon">{s.icon || '📦'}</div>
            <div className="scene-card-name">
              {s.name}
              <span className="scene-card-version">v{s.version}</span>
            </div>
            <div className="scene-card-desc">{s.description || '暂无简介'}</div>
            <div className="scene-card-footer">
              <span className="scene-card-source">
                {SOURCE_LABELS[s.source] || s.source}
              </span>
              <span className="scene-card-updated">{formatDate(s.published_at || s.updated_at)}</span>
            </div>
            <button
              className={`plaza-pin-btn${s.show_on_workbench ? ' pinned' : ''}`}
              onClick={(e) => toggleWorkbenchPin(s, e)}
              title={s.show_on_workbench ? '从工作台移除' : '钉到工作台'}
            >
              {s.show_on_workbench ? '⭐ 已加入' : '☆ 加入工作台'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
