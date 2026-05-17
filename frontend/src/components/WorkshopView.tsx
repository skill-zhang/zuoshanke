/** 🛠 工坊 — 管理自己创作的场景（草稿 + 已发布） */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';
import { Scene, updateScene, renameCategory } from '../api/client';

const CATEGORY_META: Record<string, { icon: string; label: string }> = {
  life: { icon: '🌿', label: '生活' },
  ecommerce: { icon: '🛒', label: '电商' },
  work: { icon: '💼', label: '工作' },
  learn: { icon: '📚', label: '学习' },
  create: { icon: '🎨', label: '创作' },
  finance: { icon: '📈', label: '金融' },
  media: { icon: '💬', label: '自媒体' },
  other: { icon: '📦', label: '其他' },
};

const CATEGORY_ORDER = ['life', 'ecommerce', 'work', 'learn', 'create', 'finance', 'media', 'other'];

interface WorkshopViewProps {
  filterCat?: string | null;
  onEnterScene: (scene: Scene) => void;
  onCreateScene: () => void;
}

export function WorkshopView({ filterCat, onEnterScene, onCreateScene }: WorkshopViewProps) {
  const { workshopScenes, loadWorkshopScenes, loadingWorkshop, publishSceneVersion } = useStore();
  const [publishModal, setPublishModal] = useState<Scene | null>(null);
  const [publishVersion, setPublishVersion] = useState('');
  const [publishChangelog, setPublishChangelog] = useState('');
  const [publishing, setPublishing] = useState(false);
  const [editModal, setEditModal] = useState<Scene | null>(null);
  const [editForm, setEditForm] = useState({ name: '', icon: '', description: '', category: '', guide_text: '' });
  const [editing, setEditing] = useState(false);
  const [catManageOpen, setCatManageOpen] = useState(false);

  useEffect(() => {
    loadWorkshopScenes(filterCat ? { category: filterCat } : undefined);
  }, [filterCat]);

  const grouped = CATEGORY_ORDER
    .map(k => ({
      key: k,
      ...CATEGORY_META[k],
      items: workshopScenes.filter(s => s.category === k),
    }))
    .filter(g => g.items.length > 0);

  const handlePublish = async () => {
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

  const openPublishModal = (scene: Scene) => {
    const curVer = scene.version === '0.0' ? '0.0' : scene.version;
    const parts = curVer.split('.').map(Number);
    const sugg = parts.length === 2 ? `${parts[0]}.${parts[1] + 1}` : '1.0';
    setPublishVersion(sugg);
    setPublishChangelog('');
    setPublishModal(scene);
  };

  const openEditModal = (scene: Scene) => {
    setEditForm({
      name: scene.name,
      icon: scene.icon || '📦',
      description: scene.description || '',
      category: scene.category || 'other',
      guide_text: scene.guide_text || '',
    });
    setEditModal(scene);
  };

  const handleEditSave = async () => {
    if (!editModal || !editForm.name.trim()) return;
    setEditing(true);
    try {
      await updateScene(editModal.id, {
        name: editForm.name.trim(),
        icon: editForm.icon.trim() || '📦',
        description: editForm.description.trim(),
        category: editForm.category,
        guide_text: editForm.guide_text.trim() || null,
      });
      setEditModal(null);
      loadWorkshopScenes();
    } catch (e: any) {
      alert('保存失败: ' + (e.message || ''));
    } finally {
      setEditing(false);
    }
  };

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

  return (
    <div className="workshop">
      <div className="ws-header">
        <div className="ws-header-title">
          🛠 工坊
          <span style={{ fontSize: 13, color: '#6e7681', fontWeight: 400 }}>
            · {filterCat ? CATEGORY_META[filterCat]?.label || filterCat : '全部类别'}
          </span>
        </div>
        <div className="ws-header-actions">
          <button className="btn" onClick={onCreateScene}>✨ 新建场景</button>
          <button className="btn" onClick={() => setCatManageOpen(true)}>📁 管理类别</button>
        </div>
      </div>

      <div className="ws-list">
        {loadingWorkshop ? (
          <div className="empty-state">
            <div className="empty-state-text">加载中...</div>
          </div>
        ) : grouped.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📭</div>
            <div className="empty-state-text">暂无场景</div>
            <div className="empty-state-desc">创建一个新场景吧</div>
          </div>
        ) : grouped.map(g => (
          <div key={g.key} className="category-group">
            <div className="cat-group-header">
              <span>{g.icon} {g.label}</span>
              <span className="cat-count">{g.items.length} 个场景</span>
            </div>
            {g.items.map(s => {
              const isPublished = s.version !== '0.0';
              return (
                <div key={s.id} className="ws-scene-item" onClick={() => onEnterScene(s)}>
                  <div className="ws-scene-icon">{s.icon || '📦'}</div>
                  <div className="ws-scene-info">
                    <div className="ws-scene-name">
                      {s.name}
                      <span className="scene-card-version">v{s.version}</span>
                      <span className={`status-badge ${isPublished ? 'status-published' : 'status-draft'}`}>
                        {isPublished ? '已发布' : '草稿'}
                      </span>
                    </div>
                    <div className="ws-scene-desc">
                      {s.description || '暂无简介'} · {formatDate(s.updated_at)}
                    </div>
                  </div>
                  <div className="ws-scene-meta">
                    {isPublished ? (
                      <span style={{ fontSize: 11, color: '#6e7681' }}>
                        {s.changelog ? s.changelog.substring(0, 20) + (s.changelog.length > 20 ? '…' : '') : ''}
                      </span>
                    ) : null}
                  </div>
                  <div className="ws-scene-actions">
                    <button className="btn-sm" onClick={e => { e.stopPropagation(); openEditModal(s); }}>✏️</button>
                    <button className="btn-sm" onClick={e => { e.stopPropagation(); openPublishModal(s); }}>
                      {isPublished ? '🔄' : '📦'}
                    </button>
                    <button className="btn-sm" onClick={e => { e.stopPropagation(); handleExport(s); }}>📤</button>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* ═══ 场景编辑弹窗 ═══ */}
      <div className={`modal-overlay${editModal ? ' show' : ''}`} onClick={() => !editing && setEditModal(null)}>
        <div className="modal" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            ✏️ 编辑场景
            <button className="modal-close" onClick={() => !editing && setEditModal(null)}>✕</button>
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
                  {CATEGORY_ORDER.map(k => (
                    <option key={k} value={k}>{CATEGORY_META[k]?.icon} {CATEGORY_META[k]?.label}</option>
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
              <div className="modal-actions">
                <button className="btn" onClick={() => setEditModal(null)} disabled={editing}>取消</button>
                <button className="btn btn-primary" onClick={handleEditSave} disabled={editing || !editForm.name.trim()}>
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
                <button className="btn btn-primary" onClick={handlePublish} disabled={publishing || !publishVersion.trim()}>
                  {publishing ? '发布中...' : '确认发布'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ═══ 类别管理弹窗 ═══ */}
      <div className={`modal-overlay${catManageOpen ? ' show' : ''}`} onClick={() => setCatManageOpen(false)}>
        <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            📁 类别管理
            <button className="modal-close" onClick={() => setCatManageOpen(false)}>✕</button>
          </div>
          {(() => {
            const catCounts: Record<string, number> = {};
            workshopScenes.forEach(s => { catCounts[s.category] = (catCounts[s.category] || 0) + 1; });
            return Object.entries(catCounts).length === 0 ? (
              <div style={{ padding: 20, textAlign: 'center', color: '#6e7681' }}>暂无类别</div>
            ) : (
              <>
                {Object.entries(catCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([catKey, count]) => {
                  const meta = CATEGORY_META[catKey];
                  return (
                    <div key={catKey} style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '8px 0', borderBottom: '1px solid #21262d',
                    }}>
                      <span style={{ fontSize: 20 }}>{meta?.icon || '📁'}</span>
                      <span style={{ flex: 1, fontSize: 14 }}>{meta?.label || catKey}</span>
                      <span style={{ fontSize: 12, color: '#6e7681' }}>{count} 个场景</span>
                      <span className="sidebar-menu-btn" style={{ fontSize: 13 }}
                        onClick={async () => {
                          const name = prompt('新类别名称：', meta?.label || catKey);
                          if (!name || name === (meta?.label || catKey)) return;
                          try {
                            await renameCategory(catKey, name);
                            setCatManageOpen(false);
                            loadWorkshopScenes();
                          } catch (e: any) {
                            alert('重命名失败: ' + (e.message || ''));
                          }
                        }}
                        title="重命名"
                      >✏️</span>
                    </div>
                  );
                })}
            <div style={{ borderTop: '1px solid #21262d', paddingTop: 8, marginTop: 4 }}>
              <span className="sidebar-menu-btn" style={{ fontSize: 13, color: '#58a6ff' }}
                onClick={() => {
                  setCatManageOpen(false);
                  useStore.getState().setCreateSceneModalOpen(true);
                }}
              >➕ 新建类别</span>
            </div>
            </>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
