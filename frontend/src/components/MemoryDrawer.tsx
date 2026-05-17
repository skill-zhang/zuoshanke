/** 🧠 记忆管理抽屉 — 查看/创建/强化/删除记忆 */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';
import {
  listMemories, createMemory, deleteMemory,
  reinforceMemory, pinMemory,
  type AgentMemory,
} from '../api/client';

const LEVEL_ICONS: Record<string, string> = {
  P0: '🔒', P1: '⭐', P2: '📝', P3: '💤',
};

export function MemoryDrawer() {
  const { memoryDrawerOpen, closeMemoryDrawer } = useStore();
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 新建表单
  const [showForm, setShowForm] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newTags, setNewTags] = useState('');
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await listMemories();
      setMemories(res.data);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (memoryDrawerOpen) load();
  }, [memoryDrawerOpen]);

  const handleCreate = async () => {
    if (!newKey.trim() || !newContent.trim()) return;
    setCreating(true);
    setError('');
    try {
      await createMemory({
        key: newKey.trim(),
        content: newContent.trim(),
        tags: newTags.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        base_weight: 2,
      });
      setNewKey('');
      setNewContent('');
      setNewTags('');
      setShowForm(false);
      await load();
    } catch (e: any) {
      setError(e.message || '创建失败');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (key: string) => {
    try {
      await deleteMemory(key);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleReinforce = async (key: string) => {
    try {
      await reinforceMemory(key);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handlePin = async (key: string) => {
    try {
      await pinMemory(key);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <>
      <div className={`drawer-overlay${memoryDrawerOpen ? ' open' : ''}`} onClick={closeMemoryDrawer} />
      <div className={`drawer memory-drawer${memoryDrawerOpen ? ' open' : ''}`}>
        <div className="drawer-header">
          <span style={{ fontSize: 16, fontWeight: 600, color: '#c9d1d9' }}>🧠 记忆管理</span>
          <span className="close" onClick={closeMemoryDrawer}>✕</span>
        </div>

        <div className="drawer-body">
          {error && <div className="mem-error">{error}</div>}

          <div className="mem-toolbar">
            <button className="btn-sm" onClick={load} disabled={loading}>
              {loading ? '🔄 加载中…' : '🔄 刷新'}
            </button>
            <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
              {showForm ? '✕ 取消' : '+ 新建记忆'}
            </button>
          </div>

          {showForm && (
            <div className="mem-form">
              <input className="form-input" value={newKey} onChange={e => setNewKey(e.target.value)}
                placeholder="唯一标识 key（如 name/preference_ui）" style={{ marginBottom: 6 }} />
              <textarea className="form-textarea" value={newContent} onChange={e => setNewContent(e.target.value)}
                placeholder="记忆内容" rows={2} style={{ marginBottom: 6 }} />
              <input className="form-input" value={newTags} onChange={e => setNewTags(e.target.value)}
                placeholder="标签（逗号分隔）" style={{ marginBottom: 6 }} />
              <button className="btn-primary" onClick={handleCreate} disabled={creating || !newKey.trim() || !newContent.trim()}>
                {creating ? '创建中…' : '创建'}
              </button>
            </div>
          )}

          {memories.length === 0 && !loading && (
            <div className="mem-empty">暂无记忆，聊天时会自动提取</div>
          )}

          <div className="mem-list">
            {memories.map(m => (
              <div key={m.id} className={`mem-item level-${m.priority_level?.toLowerCase() || 'p2'}`}>
                <div className="mem-item-header">
                  <span className="mem-level">{LEVEL_ICONS[m.priority_level] || '📝'}</span>
                  <span className="mem-key">{m.key}</span>
                  <span className="mem-weight">{m.weight?.toFixed(1)}</span>
                </div>
                <div className="mem-content">{m.content}</div>
                {m.tags && m.tags.length > 0 && (
                  <div className="mem-tags">
                    {m.tags.map((t, i) => <span key={i} className="mem-tag">{t}</span>)}
                  </div>
                )}
                <div className="mem-actions">
                  <button className="btn-tiny" onClick={() => handleReinforce(m.key)} title="强化（×2）">⬆ 强化</button>
                  {m.priority_level !== 'P0' && (
                    <button className="btn-tiny" onClick={() => handlePin(m.key)} title="标记 P0 永不过期">🔒 固定</button>
                  )}
                  <button className="btn-tiny danger" onClick={() => handleDelete(m.key)}>🗑 删除</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
