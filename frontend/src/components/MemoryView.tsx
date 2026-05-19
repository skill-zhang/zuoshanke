/** 🧠 记忆管理全页视图 — 双层卡片：上层按来源聚合，下层按来源展示全部记忆 */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';
import {
  listMemories, createMemory, deleteMemory,
  reinforceMemory, pinMemory, listMemoryGroups,
  type AgentMemory, type MemoryGroup,
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
  const [groups, setGroups] = useState<MemoryGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // ── 双层导航 ──
  const [selectedGroup, setSelectedGroup] = useState<MemoryGroup | null>(null);

  // 筛选（下层用）
  const [filterLevel, setFilterLevel] = useState<string>('all');

  // 新建表单
  const [showForm, setShowForm] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newTags, setNewTags] = useState('');
  const [creating, setCreating] = useState(false);

  // 详情 modal
  const [detailMem, setDetailMem] = useState<AgentMemory | null>(null);

  // ── 加载上层（所有组） ──
  const loadGroups = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await listMemoryGroups();
      setGroups(res.data);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  // ── 加载下层（某个组的所有记忆） ──
  const loadMemories = async (group: MemoryGroup) => {
    setLoading(true);
    setError('');
    try {
      const res = await listMemories({
        scope: group.scope,
        context_id: group.context_id || undefined,
        scope_only: true,
      });
      setMemories(res.data);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  // 初始加载
  useEffect(() => { loadGroups(); }, []);

  // 选择组 → 加载下层
  const handleSelectGroup = (g: MemoryGroup) => {
    setSelectedGroup(g);
    setFilterLevel('all');
    setDetailMem(null);
    setShowForm(false);
    loadMemories(g);
  };

  // 返回上层
  const handleBack = () => {
    setSelectedGroup(null);
    setMemories([]);
    loadGroups();
  };

  // ── 筛选逻辑（下层） ──
  const filtered = filterLevel === 'all'
    ? memories
    : memories.filter(m => (m.priority_level || 'P2') === filterLevel);

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
      const key = newContent.trim().replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_').slice(0, 20).toLowerCase() || `mem_${Date.now()}`;
      await createMemory({
        key: `manual_${key}`,
        content: newContent.trim(),
        tags: newTags.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        base_weight: 2,
        scope: selectedGroup?.scope || 'zhu',
        context_id: selectedGroup?.context_id || undefined,
      });
      setNewContent('');
      setNewTags('');
      setShowForm(false);
      if (selectedGroup) await loadMemories(selectedGroup);
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
      if (selectedGroup) await loadMemories(selectedGroup);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleReinforce = async (key: string) => {
    try {
      await reinforceMemory(key);
      if (selectedGroup) await loadMemories(selectedGroup);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handlePin = async (key: string) => {
    try {
      await pinMemory(key);
      if (selectedGroup) await loadMemories(selectedGroup);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="view-page memory-view">
      {/* ── 顶栏 ── */}
      <div className="view-header">
        <span style={{ fontSize: 18, fontWeight: 600, color: '#e6edf3' }}>
          {selectedGroup
            ? `${selectedGroup.icon || '🧠'} ${selectedGroup.name} 的记忆`
            : '🧠 记忆管理'}
        </span>
        <div className="view-header-actions">
          <button className="btn-sm" onClick={selectedGroup ? handleBack : () => loadGroups()} disabled={loading}>
            {loading ? '🔄' : '🔄 刷新'}
          </button>
          {selectedGroup && (
            <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
              {showForm ? '✕ 取消' : '+ 新建记忆'}
            </button>
          )}
          <button className="btn-sm" onClick={() => setView('chat')}>← 返回</button>
        </div>
      </div>

      {error && <div className="toast toast-error">{error}</div>}

      {/* ═══ 上层：按来源聚合卡片 ═══ */}
      {!selectedGroup && (
        <>
          {groups.length === 0 && !loading && (
            <div className="empty-state">暂无记忆，会话结束后会自动提取</div>
          )}
          <div className="card-grid">
            {groups.map(g => (
              <div key={`${g.scope}:${g.context_id || ''}`}
                className="memory-group-card"
                onClick={() => handleSelectGroup(g)}>
                <div className="memory-group-card-icon">{g.icon || '🧠'}</div>
                <div className="memory-group-card-name">{g.name}</div>
                <div className="memory-group-card-count">{g.count} 条</div>
                {g.preview && (
                  <div className="memory-group-card-preview">{g.preview}</div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* ═══ 下层：某个组的全部记忆 ═══ */}
      {selectedGroup && (
        <>
          {/* 返回按钮 */}
          <div className="mem-back-row">
            <span className="mem-back-link" onClick={handleBack}>← 全部来源</span>
            <span className="mem-back-name">{selectedGroup.icon} {selectedGroup.name}</span>
          </div>

          {/* 新建表单 */}
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

          {/* 分类 Tabs */}
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

          {/* 卡片网格 */}
          {filtered.length === 0 && !loading && (
            <div className="empty-state">
              {filterLevel === 'all' ? '该来源暂无记忆' : '该等级暂无记忆'}
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

          {/* 详情 Modal */}
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
        </>
      )}
    </div>
  );
}
