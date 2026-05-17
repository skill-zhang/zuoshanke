/** 📘 技能管理抽屉 — 查看/创建/编辑/删除技能 */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';
import {
  listSkills, getSkill, createSkill, updateSkill, deleteSkill,
  type SkillMeta,
} from '../api/client';

export function SkillsDrawer() {
  const { skillsDrawerOpen, closeSkillsDrawer } = useStore();
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 新建/编辑
  const [editing, setEditing] = useState<string | null>(null); // null = new, name = editing
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editTriggers, setEditTriggers] = useState('');
  const [editCategory, setEditCategory] = useState('general');
  const [saving, setSaving] = useState(false);

  // 查看详情
  const [viewing, setViewing] = useState<{ name: string; description: string; content: string; triggers: string[] } | null>(null);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await listSkills();
      setSkills(res.data);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (skillsDrawerOpen) load();
  }, [skillsDrawerOpen]);

  const resetForm = () => {
    setEditing(null);
    setEditName('');
    setEditDesc('');
    setEditContent('');
    setEditTriggers('');
    setEditCategory('general');
  };

  const startEdit = (s?: SkillMeta) => {
    if (s) {
      setEditing(s.name);
      setEditName(s.name);
      setEditDesc(s.description);
      setEditContent('');
      setEditTriggers((s.triggers || []).join(', '));
      setEditCategory(s.category);
    } else {
      resetForm();
      setEditing('__new__');
    }
  };

  const handleSave = async () => {
    if (!editName.trim() || !editDesc.trim() || !editContent.trim()) return;
    setSaving(true);
    setError('');
    try {
      const triggers = editTriggers.split(/[,，]/).map(s => s.trim()).filter(Boolean);
      if (editing === '__new__') {
        await createSkill({
          name: editName.trim(),
          description: editDesc.trim(),
          content: editContent.trim(),
          triggers,
          category: editCategory,
        });
      } else if (editing) {
        await updateSkill(editing, {
          description: editDesc.trim(),
          content: editContent.trim(),
          triggers,
          category: editCategory,
        });
      }
      resetForm();
      await load();
    } catch (e: any) {
      setError(e.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`确定删除技能「${name}」？`)) return;
    try {
      await deleteSkill(name);
      if (viewing?.name === name) setViewing(null);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleView = async (name: string) => {
    try {
      const res = await getSkill(name);
      setViewing(res.data);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <>
      <div className={`drawer-overlay${skillsDrawerOpen ? ' open' : ''}`} onClick={closeSkillsDrawer} />
      <div className={`drawer skills-drawer${skillsDrawerOpen ? ' open' : ''}`}>
        <div className="drawer-header">
          <span style={{ fontSize: 16, fontWeight: 600, color: '#c9d1d9' }}>📘 技能管理</span>
          <span className="close" onClick={closeSkillsDrawer}>✕</span>
        </div>

        <div className="drawer-body">
          {error && <div className="mem-error">{error}</div>}

          <div className="mem-toolbar">
            <button className="btn-sm" onClick={load} disabled={loading}>
              {loading ? '🔄 加载中…' : '🔄 刷新'}
            </button>
            <button className="btn-primary" onClick={() => startEdit()}>
              + 新建技能
            </button>
          </div>

          {/* 编辑/新建表单 */}
          {editing && (
            <div className="mem-form" style={{ border: '1px solid #30363d', padding: 10, borderRadius: 6, marginBottom: 8 }}>
              <input className="form-input" value={editName} onChange={e => setEditName(e.target.value)}
                placeholder="技能名（小写英文/数字/下划线）" disabled={editing !== '__new__'} style={{ marginBottom: 6 }} />
              <input className="form-input" value={editDesc} onChange={e => setEditDesc(e.target.value)}
                placeholder="简短的说明" style={{ marginBottom: 6 }} />
              <textarea className="form-textarea" value={editContent} onChange={e => setEditContent(e.target.value)}
                placeholder="技能正文（Markdown）" rows={4} style={{ marginBottom: 6 }} />
              <input className="form-input" value={editTriggers} onChange={e => setEditTriggers(e.target.value)}
                placeholder="触发关键词（逗号分隔）" style={{ marginBottom: 6 }} />
              <select className="form-select" value={editCategory} onChange={e => setEditCategory(e.target.value)} style={{ marginBottom: 6 }}>
                <option value="general">通用</option>
                <option value="formatting">格式化</option>
                <option value="workflow">流程</option>
                <option value="reference">参考</option>
              </select>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn-primary" onClick={handleSave} disabled={saving}>
                  {saving ? '保存中…' : '💾 保存'}
                </button>
                <button className="btn-sm" onClick={resetForm}>取消</button>
              </div>
            </div>
          )}

          {/* 详情查看 */}
          {viewing && (
            <div className="mem-form" style={{ border: '1px solid #30363d', padding: 10, borderRadius: 6, marginBottom: 8, position: 'relative' }}>
              <span className="close" style={{ position: 'absolute', top: 6, right: 8, fontSize: 11 }}
                onClick={() => setViewing(null)}>✕</span>
              <div style={{ fontWeight: 600, color: '#58a6ff', marginBottom: 4 }}>{viewing.name}</div>
              <div style={{ color: '#8b949e', fontSize: 12, marginBottom: 4 }}>{viewing.description}</div>
              <div style={{ color: '#8b949e', fontSize: 11, marginBottom: 4 }}>
                触发词: {viewing.triggers.join(', ')}
              </div>
              <pre className="skill-preview">{viewing.content.slice(0, 1000)}</pre>
              <button className="btn-tiny" onClick={() => { startEdit({ name: viewing.name, description: viewing.description, category: 'general', triggers: viewing.triggers, version: '1.0' }); setViewing(null); }}>✏️ 编辑</button>
            </div>
          )}

          {skills.length === 0 && !loading && (
            <div className="mem-empty">暂无技能</div>
          )}

          <div className="mem-list">
            {skills.map(s => (
              <div key={s.name} className="mem-item" style={{ cursor: 'pointer' }} onClick={() => handleView(s.name)}>
                <div className="mem-item-header">
                  <span className="mem-key">{s.name}</span>
                  <span className="badge" style={{ background: '#23863633', color: '#3fb950', fontSize: 10 }}>{s.category}</span>
                </div>
                <div className="mem-content" style={{ fontSize: 12, color: '#8b949e' }}>{s.description}</div>
                {s.triggers && s.triggers.length > 0 && (
                  <div className="mem-tags" style={{ marginTop: 4 }}>
                    {s.triggers.map((t, i) => <span key={i} className="mem-tag">{t}</span>)}
                  </div>
                )}
                <div className="mem-actions" onClick={e => e.stopPropagation()}>
                  <button className="btn-tiny danger" onClick={() => handleDelete(s.name)}>🗑 删除</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
