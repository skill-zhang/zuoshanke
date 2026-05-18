/** 📘 技能管理视图 — 卡片网格 + 详/编Modal + 导出/导入 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { useStore } from '../stores/appStore';
import {
  listSkills, getSkill, createSkill, updateSkill, deleteSkill,
  type SkillMeta,
} from '../api/client';

// ── 默认分类图标映射（识别不了的fallback到📘） ──
const CATEGORY_ICONS: Record<string, string> = {
  development: '🛠', reference: '📖', formatting: '🎨',
  workflow: '⚡', general: '📦',
};
function getCatIcon(cat: string) { return CATEGORY_ICONS[cat] || '📘'; }
function getCatLabel(cat: string) {
  const m: Record<string, string> = {
    development: '开发', reference: '参考', formatting: '格式化',
    workflow: '流程', general: '通用',
  };
  return m[cat] || cat;
}

export function SkillsView() {
  const { setView } = useStore();

  const [skills, setSkills] = useState<(SkillMeta & { content?: string })[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');

  // ── 动态分类列表 = '全部' + 数据中出现的分类（去重保序） ──
  const categories = (() => {
    const keys = new Set(skills.map(s => s.category).filter(Boolean));
    const known = ['development', 'reference', 'formatting', 'workflow', 'general'];
    // 已知分类按固定顺序，未知分类追加在后面
    const ordered = known.filter(k => keys.has(k));
    const extra = [...keys].filter(k => !known.includes(k));
    return [
      { key: 'all', icon: '🔍', label: `全部 (${skills.length})` },
      ...ordered.map(k => ({ key: k, icon: getCatIcon(k), label: getCatLabel(k) })),
      ...extra.map(k => ({ key: k, icon: getCatIcon(k), label: getCatLabel(k) })),
    ];
  })();

  // 详情弹窗
  const [detailSkill, setDetailSkill] = useState<(SkillMeta & { content: string }) | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // 新建/编辑弹窗
  const [editOpen, setEditOpen] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editTriggers, setEditTriggers] = useState('');
  const [editCategory, setEditCategory] = useState('general');
  const [saving, setSaving] = useState(false);

  // 删除确认
  const [deleteName, setDeleteName] = useState<string | null>(null);

  // 导入文件 input ref
  const importInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);

  // ── 加载 ──
  const load = useCallback(async () => {
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
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── 筛选 ──
  const filtered = skills.filter(s => {
    if (category !== 'all' && s.category !== category) return false;
    if (search) {
      const q = search.toLowerCase();
      return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q);
    }
    return true;
  });

  // ── 详情 ──
  const openDetail = async (name: string) => {
    try {
      const res = await getSkill(name);
      setDetailSkill(res.data);
      setDetailOpen(true);
    } catch (e: any) { setError(e.message || '加载详情失败'); }
  };
  const closeDetail = () => { setDetailOpen(false); setDetailSkill(null); };

  // ── 新建/编辑 ──
  const openCreate = () => {
    setEditingName(null); setEditName(''); setEditDesc('');
    setEditContent(''); setEditTriggers(''); setEditCategory('general');
    setEditOpen(true);
  };
  const openEdit = async (name: string) => {
    try {
      const res = await getSkill(name);
      setEditingName(name); setEditName(name);
      setEditDesc(res.data.description); setEditContent(res.data.content);
      setEditTriggers((res.data.triggers || []).join(', '));
      setEditCategory(res.data.category);
      setEditOpen(true); setDetailOpen(false);
    } catch (e: any) { setError(e.message || '加载失败'); }
  };
  const resetEdit = () => { setEditOpen(false); setEditingName(null); };
  const handleSave = async () => {
    if (!editName.trim() || !editDesc.trim() || !editContent.trim()) return;
    setSaving(true); setError('');
    try {
      const triggers = editTriggers.split(/[,，]/).map(s => s.trim()).filter(Boolean);
      if (editingName === null) {
        await createSkill({ name: editName.trim(), description: editDesc.trim(), content: editContent.trim(), triggers, category: editCategory });
      } else {
        await updateSkill(editingName, { description: editDesc.trim(), content: editContent.trim(), triggers, category: editCategory });
      }
      resetEdit();
      await load();
    } catch (e: any) { setError(e.message || '保存失败'); } finally { setSaving(false); }
  };

  // ── 删除 ──
  const handleDelete = async () => {
    if (!deleteName) return;
    try {
      await deleteSkill(deleteName);
      setDeleteName(null);
      if (detailSkill?.name === deleteName) setDetailOpen(false);
      await load();
    } catch (e: any) { setError(e.message); }
  };

  // ── 导出 ──
  const downloadBlob = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  /** 组装 SKILL.md 文件内容 */
  const buildSkillMd = (s: SkillMeta & { content: string }) => {
    const triggers = s.triggers?.length ? JSON.stringify(s.triggers) : '[]';
    return `---\nname: ${s.name}\ndescription: ${s.description}\nversion: ${s.version || '1.0'}\ncategory: ${s.category}\ntriggers: ${triggers}\n---\n\n${s.content}`;
  };

  const exportSingle = (s: SkillMeta & { content: string }) => {
    downloadBlob(buildSkillMd(s), `${s.name}.skill.md`);
  };

  const exportAll = async () => {
    // 逐个获取完整内容，合并到一个文件中用 --- 分隔
    let combined = '';
    for (const s of skills) {
      try {
        const res = await getSkill(s.name);
        combined += buildSkillMd(res.data) + '\n\n═══════════════════════════════════\n\n';
      } catch { /* skip failed */ }
    }
    if (combined) downloadBlob(combined, `skills-all-${new Date().toISOString().slice(0, 10)}.md`);
  };

  // ── 导入 ──
  /** 解析 SKILL.md 前注和正文 */
  const parseSkillMd = (text: string): { name: string; description: string; content: string; triggers: string[]; category: string } | null => {
    const match = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/);
    if (!match) return null;
    const metaStr = match[1];
    const content = match[2].trim();
    const meta: Record<string, any> = {};
    for (const line of metaStr.split('\n')) {
      const idx = line.indexOf(':');
      if (idx === -1) continue;
      const k = line.slice(0, idx).trim();
      let v: any = line.slice(idx + 1).trim();
      if (v.startsWith('[') && v.endsWith(']')) {
        try { v = JSON.parse(v); } catch { v = v.slice(1, -1).split(',').map((x: string) => x.trim().replace(/"/g, '')); }
      }
      meta[k] = v;
    }
    if (!meta.name || !meta.description || !content) return null;
    return {
      name: meta.name,
      description: meta.description,
      content,
      triggers: Array.isArray(meta.triggers) ? meta.triggers : [],
      category: meta.category || 'general',
    };
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;
    setImporting(true); setError('');
    let imported = 0; let failed = 0;
    for (let i = 0; i < files.length; i++) {
      const text = await files[i].text();
      const parsed = parseSkillMd(text);
      if (!parsed) { failed++; continue; }
      try {
        await createSkill(parsed);
        imported++;
      } catch { failed++; }
    }
    setImporting(false);
    await load();
    if (e.target) e.target.value = '';
    if (imported > 0) {
      setError(`✅ 成功导入 ${imported} 个技能${failed > 0 ? `，${failed} 个失败（可能已存在）` : ''}`);
    } else {
      setError(`❌ 导入失败，请检查文件格式（需为 SKILL.md 格式）`);
    }
  };

  // ── Shared style helpers ──
  const btn = (extra: Record<string, any> = {}) => ({
    padding: '6px 16px', borderRadius: 6, border: '1px solid #30363d',
    background: 'transparent', color: '#e6edf3', cursor: 'pointer', fontSize: 13,
    display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
    ...extra,
  });

  const modalOverlay: React.CSSProperties = {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,.6)', zIndex: 100,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  };
  const modalBox: React.CSSProperties = {
    background: '#161b22', border: '1px solid #30363d', borderRadius: 12,
    maxHeight: '85vh', overflowY: 'auto', padding: 24,
  };

  // ── 渲染 ──
  return (
    <div className="tools-view" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* ═══ 动态分类 Tabs ═══ */}
      <div style={{ display: 'flex', gap: 6, padding: '16px 24px 0', overflowX: 'auto', flexShrink: 0 }}>
        {categories.map(c => (
          <div key={c.key}
            className={`category-tab${category === c.key ? ' active' : ''}`}
            onClick={() => setCategory(c.key)}
            style={{
              padding: '6px 16px', borderRadius: 20,
              background: category === c.key ? '#1f6feb33' : 'transparent',
              color: category === c.key ? '#58a6ff' : '#8b949e',
              cursor: 'pointer', whiteSpace: 'nowrap',
              fontSize: 13,
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
        <div style={{ display: 'flex', alignItems: 'center', background: '#161b22', border: '1px solid #30363d', borderRadius: 6, padding: '6px 12px', width: 260, gap: 8 }}>
          <span>🔍</span>
          <input type="text" placeholder="搜索技能..." value={search} onChange={e => setSearch(e.target.value)}
            style={{ background: 'none', border: 'none', color: '#e6edf3', fontSize: 13, outline: 'none', flex: 1, fontFamily: 'inherit' }} />
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => importInputRef.current?.click()} disabled={importing} style={btn()}>
            {importing ? '⏳' : '📥'} 导入
          </button>
          <input ref={importInputRef} type="file" accept=".md" multiple
            onChange={handleImport} style={{ display: 'none' }} />
          <button onClick={exportAll} style={btn()}>📤 导出全部</button>
          <button onClick={openCreate} style={btn({ background: '#238636', borderColor: '#2ea043', color: '#fff' })}>➕ 新建技能</button>
        </div>
      </div>

      {/* ═══ 提示条 ═══ */}
      {error && (
        <div style={{
          margin: '0 24px 8px', padding: '8px 14px', borderRadius: 6, fontSize: 13,
          background: error.startsWith('✅') ? '#23863622' : '#f8514915',
          color: error.startsWith('✅') ? '#3fb950' : '#f85149',
        }}>{error}</div>
      )}

      {/* ═══ 技能卡片网格 ═══ */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16, alignContent: 'start' }}>
        {loading && <div className="empty-state" style={{ gridColumn: '1/-1', textAlign: 'center', padding: 60, color: '#6e7681' }}>🔄 加载中...</div>}
        {!loading && !error && filtered.length === 0 && (
          <div className="empty-state" style={{ gridColumn: '1/-1', textAlign: 'center', padding: 60, color: '#6e7681' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📘</div>
            <div style={{ fontSize: 15, marginBottom: 8 }}>没有匹配的技能</div>
            <div style={{ fontSize: 13, color: '#8b949e' }}>试试其他搜索词或分类，或导入/新建一个技能</div>
          </div>
        )}
        {filtered.map(s => (
          <div key={s.name} className="tool-card"
            onClick={() => openDetail(s.name)}
            style={{
              background: '#161b22', border: '1px solid #30363d', borderRadius: 10, padding: 20, cursor: 'pointer',
              transition: 'all .15s', display: 'flex', flexDirection: 'column',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = '#6e7681'; e.currentTarget.style.background = '#1c2128'; e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,.3)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = '#30363d'; e.currentTarget.style.background = '#161b22'; e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
          >
            <div style={{ fontSize: 32, lineHeight: 1, marginBottom: 10 }}>{getCatIcon(s.category)}</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 3, display: 'flex', alignItems: 'center', gap: 8 }}>
              <code style={{ fontFamily: "'SF Mono','Fira Code',monospace" }}>{s.name}</code>
              <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 4, background: '#23863633', color: '#3fb950' }}>v{s.version}</span>
            </div>
            <div style={{ fontSize: 12, color: '#8b949e', lineHeight: 1.5, flex: 1, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{s.description}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 10, paddingTop: 8, borderTop: '1px solid #21262d', fontSize: 11, color: '#6e7681' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, background: '#21262d', padding: '2px 6px', borderRadius: 4, fontSize: 11 }}>
                {getCatIcon(s.category)} {getCatLabel(s.category)}
              </span>
              {s.triggers && s.triggers.length > 0 && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, background: '#1f6feb22', padding: '2px 6px', borderRadius: 4, fontSize: 11, color: '#58a6ff' }}>
                  🎯 {s.triggers.slice(0, 2).join(', ')}{s.triggers.length > 2 ? ` +${s.triggers.length - 2}` : ''}
                </span>
              )}
              <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 2, cursor: 'pointer', padding: '2px 5px', borderRadius: 4, fontSize: 12, color: '#8b949e' }}
                title="下载 .skill.md"
                onClick={async (e) => {
                  e.stopPropagation();
                  try {
                    const res = await getSkill(s.name);
                    const triggers = res.data.triggers?.length ? JSON.stringify(res.data.triggers) : '[]';
                    const md = `---\nname: ${res.data.name}\ndescription: ${res.data.description}\nversion: ${res.data.version || '1.0'}\ncategory: ${res.data.category}\ntriggers: ${triggers}\n---\n\n${res.data.content}`;
                    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a'); a.href = url; a.download = `${s.name}.skill.md`;
                    document.body.appendChild(a); a.click(); document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                  } catch {}
                }}
              >⬇️</span>
            </div>
          </div>
        ))}
      </div>

      {/* ═══ 详情 Modal ═══ */}
      {detailOpen && detailSkill && (
        <div className="modal-overlay show" style={modalOverlay} onClick={e => { if (e.target === e.currentTarget) closeDetail(); }}>
          <div style={{ ...modalBox, width: 680 }}>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>{getCatIcon(detailSkill.category)} {detailSkill.name} <span style={{ fontSize: 12, fontWeight: 400, color: '#6e7681' }}>v{detailSkill.version}</span></span>
              <button className="modal-close" onClick={closeDetail} style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 4 }}>📝 说明</div>
              <div style={{ fontSize: 14, color: '#e6edf3' }}>{detailSkill.description}</div>
            </div>

            <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
              <div style={{ flex: 1, background: '#0d1117', borderRadius: 8, padding: 12 }}>
                <div style={{ fontSize: 11, color: '#6e7681', marginBottom: 4, textTransform: 'uppercase', letterSpacing: .5 }}>分类</div>
                <div style={{ fontSize: 13, color: '#58a6ff' }}>{getCatIcon(detailSkill.category)} {getCatLabel(detailSkill.category)}</div>
              </div>
              <div style={{ flex: 2, background: '#0d1117', borderRadius: 8, padding: 12 }}>
                <div style={{ fontSize: 11, color: '#6e7681', marginBottom: 4, textTransform: 'uppercase', letterSpacing: .5 }}>触发词</div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {detailSkill.triggers?.length ? detailSkill.triggers.map((t, i) => (
                    <span key={i} style={{ background: '#1f6feb22', color: '#58a6ff', padding: '2px 8px', borderRadius: 10, fontSize: 12 }}>{t}</span>
                  )) : <span style={{ color: '#6e7681', fontSize: 13 }}>无触发词</span>}
                </div>
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 6 }}>📄 正文</div>
              <div style={{ background: '#0d1117', border: '1px solid #30363d', borderRadius: 8, padding: 14, maxHeight: 300, overflowY: 'auto' }}>
                <pre style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: '#c9d1d9', whiteSpace: 'pre-wrap', fontFamily: "'SF Mono','Fira Code',monospace" }}>{detailSkill.content}</pre>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, paddingTop: 14, borderTop: '1px solid #21262d' }}>
              <button onClick={() => exportSingle(detailSkill)} style={btn()}>📤 导出</button>
              <button onClick={() => openEdit(detailSkill.name)} style={btn()}>✏️ 编辑</button>
              <button onClick={() => { setDeleteName(detailSkill.name); setDetailOpen(false); }}
                style={btn({ borderColor: '#f85149', color: '#f85149' })}>🗑 删除</button>
            </div>
          </div>
        </div>
      )}

      {/* ═══ 新建/编辑 Modal ═══ */}
      {editOpen && (
        <div className="modal-overlay show" style={modalOverlay} onClick={e => { if (e.target === e.currentTarget) resetEdit(); }}>
          <div style={{ ...modalBox, width: 600 }}>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              {editingName ? `✏️ ${editingName}` : '📘 新建技能'}
              <button className="modal-close" onClick={resetEdit} style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>

            {error && <div style={{ color: '#f85149', fontSize: 13, marginBottom: 12, padding: 8, background: '#f8514915', borderRadius: 6 }}>{error}</div>}

            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>技能名 *</label>
              <input value={editName} onChange={e => setEditName(e.target.value)}
                placeholder="小写英文/数字/下划线" disabled={editingName !== null}
                style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>说明 *</label>
              <input value={editDesc} onChange={e => setEditDesc(e.target.value)} placeholder="简短说明"
                style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>正文 * (Markdown)</label>
              <textarea value={editContent} onChange={e => setEditContent(e.target.value)} placeholder="## 标题\n\n正文..." rows={8}
                style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit', resize: 'vertical' }} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>触发词（逗号分隔）</label>
              <input value={editTriggers} onChange={e => setEditTriggers(e.target.value)} placeholder="调试, bug, 错误, 根因"
                style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>分类</label>
              <select value={editCategory} onChange={e => setEditCategory(e.target.value)}
                style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }}>
                {categories.filter(c => c.key !== 'all').map(c => (
                  <option key={c.key} value={c.key}>{c.icon} {c.label}</option>
                ))}
              </select>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, paddingTop: 14, borderTop: '1px solid #21262d' }}>
              <button onClick={resetEdit} style={btn()}>取消</button>
              <button onClick={handleSave} disabled={saving}
                style={btn({ background: '#238636', borderColor: '#2ea043', color: '#fff' })}>
                {saving ? '⏳ 保存中...' : '💾 保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══ 删除确认 Modal ═══ */}
      {deleteName && (
        <div className="modal-overlay show" style={modalOverlay} onClick={e => { if (e.target === e.currentTarget) setDeleteName(null); }}>
          <div style={{ ...modalBox, width: 420 }}>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              ⚠️ 确认删除
              <button className="modal-close" onClick={() => setDeleteName(null)} style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>
            <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', padding: '4px 0 16px' }}>
              <span style={{ fontSize: 40, lineHeight: 1 }}>🗑️</span>
              <div>
                <div style={{ fontSize: 15, fontWeight: 500, color: '#e6edf3', marginBottom: 6 }}>「{deleteName}」</div>
                <div style={{ fontSize: 13, color: '#8b949e', lineHeight: 1.6 }}>删除后 Agent Loop 将无法匹配到该技能的知识。</div>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, paddingTop: 14, borderTop: '1px solid #21262d' }}>
              <button onClick={() => setDeleteName(null)} style={btn()}>取消</button>
              <button onClick={handleDelete} style={btn({ borderColor: '#f85149', background: '#f85149', color: '#fff' })}>确认删除</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
