/** 🛠 创作空间 — 全页卡片网格，管理所有场景（草稿 + 已发布） */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';
import { Scene, updateScene, deleteScene, renameCategory, createCategory, deleteCategory, listCategories } from '../api/client';

// ── 分类配置 ──
const CATEGORIES = [
  { key: 'all', icon: '🔍', label: '全部' },
  { key: 'life', icon: '🌿', label: '生活' },
  { key: 'ecommerce', icon: '🛒', label: '电商' },
  { key: 'work', icon: '💼', label: '工作' },
  { key: 'learn', icon: '📚', label: '学习' },
  { key: 'create', icon: '🎨', label: '创作' },
  { key: 'finance', icon: '📈', label: '金融' },
  { key: 'media', icon: '💬', label: '自媒体' },
  { key: 'other', icon: '📦', label: '其他' },
];
const CATEGORY_META: Record<string, { icon: string; label: string }> = {};
CATEGORIES.forEach(c => { if (c.key !== 'all') CATEGORY_META[c.key] = { icon: c.icon, label: c.label }; });

// 类别英文标识 → 中文名简单映射
const autoLabel = (name: string) => {
  const known: Record<string, string> = {
    life: '生活', ecommerce: '电商', work: '工作', learn: '学习',
    create: '创作', finance: '金融', media: '自媒体', other: '其他',
  };
  return known[name] || name;
};

const ICON_STYLE: React.CSSProperties = {
  width: 22, height: 22, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  background: '#21262d', borderRadius: 6, fontSize: 13, flexShrink: 0,
};

interface WorkshopViewProps {
  onEnterScene: (scene: Scene) => void;
  onCreateScene: () => void;
}

export function WorkshopView({ onEnterScene, onCreateScene }: WorkshopViewProps) {
  const { workshopScenes, loadWorkshopScenes, loadingWorkshop, publishSceneVersion } = useStore();

  // ── 筛选状态 ──
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');

  // ── 编辑弹窗 ──
  const [editModal, setEditModal] = useState<Scene | null>(null);
  const [editForm, setEditForm] = useState({ name: '', icon: '', description: '', category: '', guide_text: '', user_context: '' });
  const [editing, setEditing] = useState(false);
  const [bgEditMode, setBgEditMode] = useState(false);      // 背景设定是否正在编辑
  const [bgSaving, setBgSaving] = useState(false);            // 背景设定保存中

  // ── 发布弹窗 ──
  const [publishModal, setPublishModal] = useState<Scene | null>(null);
  const [publishVersion, setPublishVersion] = useState('');
  const [publishChangelog, setPublishChangelog] = useState('');
  const [publishing, setPublishing] = useState(false);

  // ── 删除确认 ──
  const [deleteTarget, setDeleteTarget] = useState<Scene | null>(null);
  const [deleting, setDeleting] = useState(false);

  // ── 类别管理 ──
  const [catManageOpen, setCatManageOpen] = useState(false);
  const [categories, setCategories] = useState<{ name: string; label: string; icon: string; count: number }[]>([]);
  // ── 新建类别弹窗 ──
  const [newCatOpen, setNewCatOpen] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatLabel, setNewCatLabel] = useState('');
  const [newCatIcon, setNewCatIcon] = useState('📁');
  const [newCatCreating, setNewCatCreating] = useState(false);
  // ── 重命名类别弹窗 ──
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<{ name: string; label: string } | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renameSaving, setRenameSaving] = useState(false);

  useEffect(() => { loadWorkshopScenes(); }, []);

  // 加载类别元数据
  useEffect(() => {
    listCategories().then(setCategories).catch(() => {});
  }, [catManageOpen]);

  // ── 过滤场景 ──
  const filtered = workshopScenes.filter(s => {
    if (category !== 'all' && s.category !== category) return false;
    if (search) {
      const q = search.toLowerCase();
      return s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q);
    }
    return true;
  });

  // ── 动态分类 tab ──
  const categoryTabs = (() => {
    const keys = new Set(categories.map(c => c.name));
    const allCount = workshopScenes.length;
    const tabs: { key: string; icon: string; label: string }[] = [
      { key: 'all', icon: '🔍', label: `全部 (${allCount})` },
    ];
    categories.forEach(c => {
      tabs.push({ key: c.name, icon: c.icon, label: `${c.label} (${c.count})` });
    });
    return tabs;
  })();

  // ── 日期格式化 ──
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

  // ── 编辑 ──
  const openEdit = (scene: Scene) => {
    setBgEditMode(false);
    setEditForm({
      name: scene.name,
      icon: scene.icon || '📦',
      description: scene.description || '',
      category: scene.category || 'other',
      guide_text: scene.guide_text || '',
      user_context: scene.user_context || '',
    });
    setEditModal(scene);
  };
  const saveEdit = async () => {
    if (!editModal || !editForm.name.trim()) return;
    setEditing(true);
    try {
      await updateScene(editModal.id, {
        name: editForm.name.trim(),
        icon: editForm.icon.trim() || '📦',
        description: editForm.description.trim(),
        category: editForm.category,
        guide_text: editForm.guide_text.trim() || null,
        user_context: editForm.user_context.trim() || null,
      });
      setEditModal(null);
      loadWorkshopScenes();
    } catch (e: any) {
      alert('保存失败: ' + (e.message || ''));
    } finally {
      setEditing(false);
    }
  };

  // ── 发布 ──
  const openPublish = (scene: Scene) => {
    const curVer = scene.version === '0.0' ? '0.0' : scene.version;
    const parts = curVer.split('.').map(Number);
    const sugg = parts.length === 2 ? `${parts[0]}.${parts[1] + 1}` : '1.0';
    setPublishVersion(sugg);
    setPublishChangelog('');
    setPublishModal(scene);
  };
  const doPublish = async () => {
    if (!publishModal || !publishVersion.trim()) return;
    setPublishing(true);
    try {
      const result = await publishSceneVersion(publishModal.id, publishVersion.trim(), publishChangelog.trim() || undefined);
      if (result) {
        setPublishModal(null);
        setPublishVersion('');
        setPublishChangelog('');
      } else {
        alert('发布失败，请检查版本号或重试');
      }
    } catch (e: any) {
      alert(e.message || '发布失败');
    } finally {
      setPublishing(false);
    }
  };

  // ── 导出 ──
  const handleExport = async (scene: Scene) => {
    try {
      const { exportScene } = await import('../api/client');
      const data = await exportScene(scene.id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${scene.name}.scene.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('导出失败:', e);
      alert('导出失败');
    }
  };

  // ── 删除 ──
  const doDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteScene(deleteTarget.id);
      setDeleteTarget(null);
      loadWorkshopScenes();
    } catch (e: any) {
      alert('删除失败: ' + (e.message || ''));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* ═══ 分类 Tabs ═══ */}
      <div style={{ display: 'flex', gap: 6, padding: '16px 24px 0', overflowX: 'auto', flexShrink: 0 }}>
        {categoryTabs.map(c => (
          <div key={c.key}
            onClick={() => setCategory(c.key)}
            style={{
              padding: '6px 16px', borderRadius: 20, whiteSpace: 'nowrap', cursor: 'pointer', fontSize: 13,
              background: category === c.key ? '#1f6feb33' : 'transparent',
              color: category === c.key ? '#58a6ff' : '#8b949e',
              border: category === c.key ? '1px solid #1f6feb66' : '1px solid transparent',
              transition: 'all .15s',
            }}
          >{c.icon} {c.label}</div>
        ))}
      </div>

      {/* ═══ 工具栏 ═══ */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 24px', flexShrink: 0, flexWrap: 'wrap', gap: 8,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', background: '#161b22',
          border: '1px solid #30363d', borderRadius: 6, padding: '6px 12px', width: 280, gap: 8,
        }}>
          <span>🔍</span>
          <input type="text" placeholder="搜索场景..." value={search} onChange={e => setSearch(e.target.value)}
            style={{ background: 'none', border: 'none', color: '#e6edf3', fontSize: 13, outline: 'none', flex: 1, fontFamily: 'inherit' }} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={() => setCatManageOpen(true)}
            style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #30363d', background: 'transparent', color: '#e6edf3', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
            📁 管理类别
          </button>
          <button className="btn btn-primary" onClick={onCreateScene}
            style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #2ea043', background: '#238636', color: '#fff', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
            ✨ 新建场景
          </button>
        </div>
      </div>

      {/* ═══ 场景卡片网格 ═══ */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '0 24px 24px',
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, alignContent: 'start',
      }}>
        {loadingWorkshop ? (
          <div className="empty-state" style={{ gridColumn: '1/-1', textAlign: 'center', padding: 60, color: '#6e7681' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
            <div style={{ fontSize: 15 }}>加载中...</div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty-state" style={{ gridColumn: '1/-1', textAlign: 'center', padding: 60, color: '#6e7681' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
            <div style={{ fontSize: 15, marginBottom: 8 }}>暂无场景</div>
            <div style={{ fontSize: 13, color: '#8b949e' }}>{search ? '试试其他搜索词' : '创建一个新场景吧'}</div>
          </div>
        ) : filtered.map(s => {
          const isPublished = s.version !== '0.0';
          const catMeta = categories.find(c => c.name === s.category);
          return (
            <div key={s.id}
              className="ws-card-wrapper"
              onClick={() => onEnterScene(s)}
              style={{
                background: '#161b22', border: '1px solid #30363d', borderRadius: 10, padding: 20, cursor: 'pointer',
                transition: 'all .15s', display: 'flex', flexDirection: 'column', position: 'relative',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = '#6e7681';
                e.currentTarget.style.background = '#1c2128';
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,.3)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = '#30363d';
                e.currentTarget.style.background = '#161b22';
                e.currentTarget.style.transform = 'none';
                e.currentTarget.style.boxShadow = 'none';
              }}
            >
              {/* 图标 */}
              <div style={{ fontSize: 32, lineHeight: 1, marginBottom: 10 }}>{s.icon || '📦'}</div>

              {/* 名称 + 版本 */}
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                {s.name}
                <span style={{
                  fontSize: 11, color: '#6e7681', background: '#21262d', borderRadius: 4,
                  padding: '1px 6px', fontWeight: 400, whiteSpace: 'nowrap',
                }}>
                  v{s.version}
                </span>
              </div>

              {/* 状态标签行 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <span style={{
                  fontSize: 11, padding: '2px 8px', borderRadius: 10, whiteSpace: 'nowrap',
                  background: isPublished ? '#23863633' : '#d2992233',
                  color: isPublished ? '#3fb950' : '#d29922',
                }}>
                  {isPublished ? '✅ 已发布' : '📝 草稿'}
                </span>
                {catMeta && (
                  <span style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 10, whiteSpace: 'nowrap',
                    background: '#21262d', color: '#8b949e',
                  }}>
                    {catMeta.icon} {catMeta.label}
                  </span>
                )}
              </div>

              {/* 描述 */}
              <div style={{
                fontSize: 13, color: '#8b949e', lineHeight: 1.5, flex: 1,
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
              }}>
                {s.description || '暂无简介'}
              </div>

              {/* 底部信息 */}
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginTop: 10, paddingTop: 8, borderTop: '1px solid #21262d',
                fontSize: 11, color: '#6e7681',
              }}>
                <span>{formatDate(s.updated_at)}</span>
              </div>

              {/* hover 操作按钮 */}
              <div className="ws-card-actions"
                style={{
                  position: 'absolute', top: 12, right: 12,
                  display: 'flex', gap: 2,
                }}
              >
                <ActionBtn icon="✏️" title="编辑" onClick={e => { e.stopPropagation(); openEdit(s); }} />
                <ActionBtn icon={isPublished ? '🔄' : '📦'} title={isPublished ? '发布新版本' : '发布'} onClick={e => { e.stopPropagation(); openPublish(s); }} />
                <ActionBtn icon="📤" title="导出" onClick={e => { e.stopPropagation(); handleExport(s); }} />
                <ActionBtn icon="🗑" title="删除" danger onClick={e => { e.stopPropagation(); setDeleteTarget(s); }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* ═══ 编辑弹窗 ═══ */}
      <div className={`modal-overlay${editModal ? ' show' : ''}`} onClick={() => !editing && setEditModal(null)}>
        <div className="modal" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            ✏️ 编辑场景
            <button className="modal-close" onClick={() => { setBgEditMode(false); !editing && setEditModal(null); }}>✕</button>
          </div>
          {editModal && (
            <>
              <div className="form-group">
                <label className="form-label">图标</label>
                <input className="form-input" value={editForm.icon} onChange={e => setEditForm(f => ({ ...f, icon: e.target.value }))} placeholder="输入 emoji" />
              </div>
              <div className="form-group">
                <label className="form-label">名称</label>
                <input className="form-input" value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} placeholder="场景名称" />
              </div>
              <div className="form-group">
                <label className="form-label">类别</label>
                <select className="form-select" value={editForm.category} onChange={e => setEditForm(f => ({ ...f, category: e.target.value }))}>
                  {categories.map(c => (
                    <option key={c.name} value={c.name}>{c.icon} {c.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">简介</label>
                <input className="form-input" value={editForm.description} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))} placeholder="场景简述" />
              </div>
              <div className="form-group">
                <label className="form-label">引导语</label>
                <textarea className="form-textarea" value={editForm.guide_text} onChange={e => setEditForm(f => ({ ...f, guide_text: e.target.value }))} placeholder="用户进入场景后的提示语" style={{ minHeight: 60 }} />
              </div>
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  背景设定
                  {!bgEditMode ? (
                    <button onClick={() => setBgEditMode(true)}
                      style={{ fontSize: 11, color: '#58a6ff', padding: '2px 8px', border: '1px solid #58a6ff44', borderRadius: 4, background: 'transparent', cursor: 'pointer' }}>
                      ✏️ 编辑
                    </button>
                  ) : (
                    <>
                      <span style={{ fontSize: 11, color: '#8b949e' }}>编辑模式</span>
                      <button onClick={async () => {
                        if (!editModal || bgSaving) return;
                        setBgSaving(true);
                        try {
                          const res = await updateScene(editModal.id, { user_context: editForm.user_context.trim() || null });
                          setEditForm(f => ({ ...f, user_context: res.user_context || '' }));
                        } catch {}
                        setBgSaving(false);
                        setBgEditMode(false);
                      }} disabled={bgSaving}
                        style={{ fontSize: 11, color: '#2ea043', padding: '2px 8px', border: '1px solid #2ea04344', borderRadius: 4, background: '#23863622', cursor: 'pointer' }}>
                        保存
                      </button>
                      <button onClick={() => setBgEditMode(false)}
                        style={{ fontSize: 11, color: '#8b949e', padding: '2px 8px', border: '1px solid #30363d', borderRadius: 4, background: 'transparent', cursor: 'pointer' }}>
                        取消
                      </button>
                    </>
                  )}
                  <button onClick={async () => {
                    if (!editModal) return;
                    try {
                      const res = await updateScene(editModal.id, { user_context: null });
                      setEditForm(f => ({ ...f, user_context: res.user_context || '' }));
                      setBgEditMode(false);
                    } catch {}
                  }} style={{ marginLeft: 'auto', fontSize: 11, color: '#6e7681', padding: 0, border: 'none', background: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                    恢复默认
                  </button>
                </label>
                {bgEditMode ? (
                  <textarea className="form-textarea" value={editForm.user_context} onChange={e => setEditForm(f => ({ ...f, user_context: e.target.value }))}
                    placeholder="定义这个场景中 AI 分身的行为规则、角色设定和工作方式…"
                    style={{ minHeight: 200, fontFamily: 'monospace', fontSize: 12, lineHeight: 1.5 }} />
                ) : (
                  <div style={{ background: '#0d1117', border: '1px solid #21262d', borderRadius: 6, padding: 12, minHeight: 100, maxHeight: 300, overflow: 'auto', fontFamily: 'monospace', fontSize: 12, lineHeight: 1.5, color: '#c9d1d9', whiteSpace: 'pre-wrap' }}>
                    {editForm.user_context || <span style={{ color: '#484f58', fontStyle: 'italic' }}>未设置背景设定</span>}
                  </div>
                )}
              </div>
              <div className="modal-actions">
                <button className="btn" onClick={() => setEditModal(null)} disabled={editing}>取消</button>
                <button className="btn btn-primary" onClick={saveEdit} disabled={editing || !editForm.name.trim()}>
                  {editing ? '保存中...' : '保存'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ═══ 发布弹窗 ═══ */}
      <div className={`modal-overlay${publishModal ? ' show' : ''}`} onClick={() => !publishing && setPublishModal(null)}>
        <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            {publishModal?.version === '0.0' ? '发布场景' : '发布新版本'}
            <button className="modal-close" onClick={() => !publishing && setPublishModal(null)}>✕</button>
          </div>
          {publishModal && (
            <>
              <div style={{ marginBottom: 16, fontSize: 14 }}>
                {publishModal.icon} {publishModal.name}
                <span style={{ marginLeft: 8, fontSize: 12, color: '#6e7681' }}>
                  当前版本 v{publishModal.version}
                </span>
              </div>
              <div className="form-group">
                <label className="form-label">新版本号</label>
                <input className="form-input" value={publishVersion} onChange={e => setPublishVersion(e.target.value)} placeholder="如 1.0 / 1.1 / 2.0" />
                <div className="form-hint">必须大于当前版本 v{publishModal.version}</div>
              </div>
              <div className="form-group">
                <label className="form-label">更新说明（可选）</label>
                <textarea className="form-textarea" value={publishChangelog} onChange={e => setPublishChangelog(e.target.value)} placeholder="描述本次更新的内容..." style={{ minHeight: 60 }} />
              </div>
              <div className="modal-actions">
                <button className="btn" onClick={() => setPublishModal(null)} disabled={publishing}>取消</button>
                <button className="btn btn-primary" onClick={doPublish} disabled={publishing || !publishVersion.trim()}>
                  {publishing ? '发布中...' : '确认发布'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ═══ 删除确认弹窗 ═══ */}
      {deleteTarget && (
        <div className="modal-overlay show"
          style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,.6)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={e => { if (e.target === e.currentTarget) setDeleteTarget(null); }}>
          <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12, width: 420, padding: 24 }}>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              ⚠️ 确认删除场景
              <button className="modal-close" onClick={() => setDeleteTarget(null)}
                style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>
            <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', padding: '4px 0 16px' }}>
              <span style={{ fontSize: 40, lineHeight: 1 }}>🗑️</span>
              <div>
                <div style={{ fontSize: 15, fontWeight: 500, color: '#e6edf3', marginBottom: 6 }}>
                  {deleteTarget.icon} {deleteTarget.name}
                </div>
                <div style={{ fontSize: 13, color: '#8b949e', lineHeight: 1.6 }}>
                  删除后，该场景及其所有聊天记录将被永久移除，<br />
                  无法恢复。
                </div>
                <div style={{ marginTop: 10, background: '#f8514915', border: '1px solid #f8514933', borderRadius: 6, padding: 10, fontSize: 13, color: '#f85149' }}>
                  ⚠️ 此操作不可撤销。场景中的所有数据和配置将会丢失。
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, paddingTop: 14, borderTop: '1px solid #21262d' }}>
              <button className="btn" onClick={() => setDeleteTarget(null)} disabled={deleting}
                style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #30363d', background: 'transparent', color: '#e6edf3', cursor: 'pointer', fontSize: 13 }}>取消</button>
              <button onClick={doDelete} disabled={deleting}
                style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #f85149', background: '#f85149', color: '#fff', cursor: 'pointer', fontSize: 13 }}>
                {deleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══ 类别管理弹窗 ═══ */}
      <div className={`modal-overlay${catManageOpen ? ' show' : ''}`} onClick={() => setCatManageOpen(false)}>
        <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            📁 类别管理
            <button className="modal-close" onClick={() => setCatManageOpen(false)}>✕</button>
          </div>
          {categories.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center', color: '#6e7681' }}>暂无类别</div>
          ) : (
            <>
              {categories.map(c => (
                <div key={c.name} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '8px 0', borderBottom: '1px solid #21262d',
                }}>
                  <span style={{ fontSize: 20 }}>{c.icon}</span>
                  <span style={{ flex: 1, fontSize: 14 }}>{c.label}</span>
                  <span style={{ fontSize: 12, color: '#6e7681' }}>{c.count} 个场景</span>
                  {/* 重命名 */}
                  <span style={{ fontSize: 13, cursor: 'pointer', color: '#8b949e', padding: 4 }}
                    onClick={() => {
                      setRenameTarget({ name: c.name, label: c.label });
                      setRenameValue(c.label);
                      setRenameOpen(true);
                    }}
                    title="重命名"
                  >✏️</span>
                  {/* 删除（仅当 count=0 时才可删） */}
                  {c.count === 0 && (
                    <span style={{ fontSize: 13, cursor: 'pointer', color: '#f85149', padding: 4 }}
                      onClick={async () => {
                        if (!confirm(`确定删除类别「${c.label}」？`)) return;
                        try {
                          await deleteCategory(c.name);
                          setCatManageOpen(false);
                        } catch (e: any) {
                          alert('删除失败: ' + (e.message || ''));
                        }
                      }}
                      title="删除"
                    >🗑️</span>
                  )}
                </div>
              ))}
              <div style={{ borderTop: '1px solid #21262d', paddingTop: 10, marginTop: 4 }}>
                <button onClick={() => {
                  setNewCatName('');
                  setNewCatOpen(true);
                }}
                  style={{
                    padding: '6px 16px', borderRadius: 6, border: '1px solid #2ea043',
                    background: '#238636', color: '#fff', cursor: 'pointer', fontSize: 13,
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >➕ 新建类别</button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ═══ 新建类别弹窗 ═══ */}
      <div className={`modal-overlay${newCatOpen ? ' show' : ''}`} onClick={() => !newCatCreating && setNewCatOpen(false)}>
        <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            ➕ 新建类别
            <button className="modal-close" onClick={() => !newCatCreating && setNewCatOpen(false)}>✕</button>
          </div>
          <div style={{ padding: '0 0 16px' }}>
            <div className="form-group">
              <label className="form-label">类别名称</label>
              <input className="form-input" value={newCatName}
                onChange={e => setNewCatName(e.target.value)}
                placeholder="输入类别名称，如 汽车、房产、美食"
                autoFocus
                onKeyDown={e => { if (e.key === 'Enter') document.getElementById('ws-newcat-btn')?.click(); }} />
            </div>
          </div>
          <div className="modal-actions">
            <button className="btn" onClick={() => setNewCatOpen(false)} disabled={newCatCreating}
              style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #30363d', background: 'transparent', color: '#e6edf3', cursor: 'pointer', fontSize: 13 }}>
              取消
            </button>
            <button onClick={async () => {
              if (!newCatName.trim()) return;
              setNewCatCreating(true);
              try {
                const catName = newCatName.trim();
                await createCategory({ name: catName, label: catName });
                listCategories().then(setCategories).catch(() => {});
                setNewCatOpen(false);
                setCatManageOpen(false);
              } catch (e: any) {
                alert('创建失败: ' + (e.message || ''));
              } finally {
                setNewCatCreating(false);
              }
            }} disabled={newCatCreating || !newCatName.trim()}
              style={{
                padding: '6px 16px', borderRadius: 6, border: '1px solid #2ea043',
                background: newCatCreating ? '#23863666' : '#238636', color: '#fff',
                cursor: newCatCreating || !newCatName.trim() ? 'not-allowed' : 'pointer', fontSize: 13,
              }}>
              {newCatCreating ? '创建中...' : '✅ 确定'}
            </button>
          </div>
        </div>
      </div>

      {/* ═══ 重命名类别弹窗 ═══ */}
      <div className={`modal-overlay${renameOpen ? ' show' : ''}`} onClick={() => !renameSaving && setRenameOpen(false)}>
        <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            ✏️ 重命名类别
            <button className="modal-close" onClick={() => !renameSaving && setRenameOpen(false)}>✕</button>
          </div>
          {renameTarget && (
            <div style={{ padding: '0 0 16px' }}>
              <div style={{ marginBottom: 12, fontSize: 14, color: '#8b949e', display: 'flex', alignItems: 'center', gap: 8 }}>
                原名：<span style={{ color: '#e6edf3', fontWeight: 500 }}>{renameTarget.label}</span>
              </div>
              <div className="form-group">
                <label className="form-label">新名称</label>
                <input className="form-input" value={renameValue}
                  onChange={e => setRenameValue(e.target.value)}
                  placeholder="输入新的类别名称"
                  autoFocus
                  onKeyDown={e => { if (e.key === 'Enter') document.getElementById('rename-confirm-btn')?.click(); }} />
              </div>
            </div>
          )}
          <div className="modal-actions">
            <button className="btn" onClick={() => setRenameOpen(false)} disabled={renameSaving}
              style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #30363d', background: 'transparent', color: '#e6edf3', cursor: 'pointer', fontSize: 13 }}>
              取消
            </button>
            <button id="rename-confirm-btn" onClick={async () => {
              if (!renameTarget || !renameValue.trim() || renameSaving) return;
              setRenameSaving(true);
              try {
                await renameCategory(renameTarget.name, renameValue.trim());
                setRenameOpen(false);
                setCatManageOpen(false);
                loadWorkshopScenes();
              } catch (e: any) {
                alert('重命名失败: ' + (e.message || ''));
              } finally {
                setRenameSaving(false);
              }
            }} disabled={renameSaving || !renameValue.trim() || !renameTarget}
              style={{
                padding: '6px 16px', borderRadius: 6, border: '1px solid #2ea043',
                background: renameSaving ? '#23863666' : '#238636', color: '#fff',
                cursor: renameSaving || !renameValue.trim() ? 'not-allowed' : 'pointer', fontSize: 13,
              }}>
              {renameSaving ? '保存中...' : '✅ 确定'}
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}

// ═══ 小型操作按钮 ═══
function ActionBtn({ icon, title, danger, onClick }: {
  icon: string; title: string; danger?: boolean; onClick: (e: React.MouseEvent) => void;
}) {
  return (
    <button onClick={onClick} title={title}
      style={{
        width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: 'none', borderRadius: 4, fontSize: 13, cursor: 'pointer',
        background: danger ? '#f8514915' : '#21262d',
        color: danger ? '#f85149' : '#8b949e',
        transition: 'background .12s',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = danger ? '#f8514933' : '#30363d'; }}
      onMouseLeave={e => { e.currentTarget.style.background = danger ? '#f8514915' : '#21262d'; }}
    >{icon}</button>
  );
}
