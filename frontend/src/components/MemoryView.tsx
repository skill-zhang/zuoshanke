/** 🧠 记忆管理全页视图 — 卡片网格 + CRUD + 强化/固定 */
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

const LEVEL_TITLES: Record<string, string> = {
  P0: '永不过期', P1: '重要', P2: '普通', P3: '待清理',
};

export function MemoryView() {
  const { setView } = useStore();
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 筛选
  const [filterLevel, setFilterLevel] = useState<string>('all');

  // 新建表单
  const [showForm, setShowForm] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newTags, setNewTags] = useState('');
  const [creating, setCreating] = useState(false);

  // 详情 modal
  const [detailMem, setDetailMem] = useState<AgentMemory | null>(null);

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

  useEffect(() => { load(); }, []);

  // ── 筛选逻辑 ──
  const filtered = filterLevel === 'all'
    ? memories
    : memories.filter(m => (m.priority_level || 'P2') === filterLevel);

  // 分类计数
  const counts = {
    all: memories.length,
    P0: memories.filter(m => m.priority_level === 'P0').length,
    P1: memories.filter(m => m.priority_level === 'P1').length,
    P2: memories.filter(m => m.priority_level === 'P2').length,
    P3: memories.filter(m => m.priority_level === 'P3').length,
  };

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    setCreating(true);
    setError('');
    try {
      // 自动生成 key：取前 4 个中文字
      const key = newContent.trim().replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_').slice(0, 20).toLowerCase() || `mem_${Date.now()}`;
      await createMemory({
        key: `manual_${key}`,
        content: newContent.trim(),
        tags: newTags.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        base_weight: 2,
      });
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
    if (!confirm(`确定删除记忆「${key}」？`)) return;
    try {
      await deleteMemory(key);
      setDetailMem(null);
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
    <div className="view-page memory-view">
      {/* ── 顶栏 ── */}
      <div className="view-header">
        <span style={{ fontSize: 18, fontWeight: 600, color: '#e6edf3' }}>🧠 记忆管理</span>
        <div className="view-header-actions">
          <button className="btn-sm" onClick={load} disabled={loading}>
            {loading ? '🔄' : '🔄 刷新'}
          </button>
          <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
            {showForm ? '✕ 取消' : '+ 新建记忆'}
          </button>
          <button className="btn-sm" onClick={() => setView('chat')}>← 返回</button>
        </div>
      </div>

      {error && <div className="toast toast-error">{error}</div>}

      {/* ── 新建表单 ── */}
      {showForm && (
        <div className="mem-form-card">
          <textarea className="form-textarea" value={newContent} onChange={e => setNewContent(e.target.value)}
            placeholder="记忆内容" rows={2} style={{ marginBottom: 6, width: '100%' }} />
          <input className="form-input" value={newTags} onChange={e => setNewTags(e.target.value)}
            placeholder="标签（逗号分隔）" style={{ marginBottom: 6, width: '100%' }} />
          <button className="btn-primary" onClick={handleCreate} disabled={creating || !newContent.trim()}>
            {creating ? '创建中…' : '创建'}
          </button>
        </div>
      )}

      {/* ── 分类 Tabs ── */}
      <div className="view-tabs">
        {[
          { key: 'all', icon: '🔍', label: `全部 (${counts.all})` },
          { key: 'P0', icon: '🔒', label: `P0 (${counts.P0})` },
          { key: 'P1', icon: '⭐', label: `P1 (${counts.P1})` },
          { key: 'P2', icon: '📝', label: `P2 (${counts.P2})` },
          { key: 'P3', icon: '💤', label: `P3 (${counts.P3})` },
        ].map(t => (
          <div key={t.key}
            className={`view-tab${filterLevel === t.key ? ' active' : ''}`}
            onClick={() => setFilterLevel(t.key)}>
            {t.icon} {t.label}
          </div>
        ))}
      </div>

      {/* ── 卡片网格 ── */}
      {filtered.length === 0 && !loading && (
        <div className="empty-state">
          {filterLevel === 'all' ? '暂无记忆，聊天时 LLM 会通过 memory 工具自动创建' : '该等级暂无记忆'}
        </div>
      )}

      <div className="card-grid">
        {filtered.map(m => (
          <div key={m.id}
            className={`memory-card level-${(m.priority_level || 'p2').toLowerCase()}`}
            onClick={() => setDetailMem(m)}>
            <div className="memory-card-header">
              <span className="memory-level-icon">{LEVEL_ICONS[m.priority_level] || '📝'}</span>
              <span className="memory-key">{m.key}</span>
              <span className={`memory-weight${(m.weight ?? 0) >= 8 ? ' w-p0' : (m.weight ?? 0) >= 4 ? ' w-p1' : (m.weight ?? 0) >= 2 ? ' w-p2' : ' w-p3'}`}>
                {(m.weight ?? 0).toFixed(1)}
              </span>
            </div>
            <div className="memory-card-content">{m.content}</div>
            <div className="memory-card-tags">
              {(m.tags || []).map((t, i) => <span key={i} className="mem-tag">{t}</span>)}
            </div>
            <div className="memory-card-footer">
              <span className="memory-source">{m.source || ''}</span>
              <span className="memory-level-title">{LEVEL_TITLES[m.priority_level] || ''}</span>
            </div>
          </div>
        ))}
      </div>

      {/* ── 详情 Modal ── */}
      {detailMem && (
        <>
          <div className="modal-overlay" onClick={() => setDetailMem(null)} />
          <div className="modal mem-detail-modal">
            <div className="modal-header">
              <span>
                {LEVEL_ICONS[detailMem.priority_level] || '📝'} {detailMem.key}
              </span>
              <span className="modal-close" onClick={() => setDetailMem(null)}>✕</span>
            </div>
            <div className="modal-body">
              <div className="mem-detail-field">
                <label>内容</label>
                <div className="mem-detail-content">{detailMem.content}</div>
              </div>
              <div className="mem-detail-field">
                <label>等级 / 权重</label>
                <div>{detailMem.priority_level} · {(detailMem.weight ?? 0).toFixed(2)}</div>
              </div>
              <div className="mem-detail-field">
                <label>标签</label>
                <div className="memory-card-tags">
                  {(detailMem.tags || []).map((t, i) => <span key={i} className="mem-tag">{t}</span>)}
                </div>
              </div>
              <div className="mem-detail-field">
                <label>来源</label>
                <div>{detailMem.source || '—'}</div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-tiny" onClick={() => { handleReinforce(detailMem.key); }}>
                ⬆ 强化
              </button>
              {detailMem.priority_level !== 'P0' && (
                <button className="btn-tiny" onClick={() => { handlePin(detailMem.key); }}>
                  🔒 固定 P0
                </button>
              )}
              <button className="btn-tiny danger" onClick={() => handleDelete(detailMem.key)}>
                🗑 删除
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
