/** 📋 侧边栏 — 频道列表 + 场景广场 + 工坊（分类折叠） */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';
import { listScenes, updateScene, deleteScene, Scene, listProjects, createScene, listMemories, renameCategory, createCategory, deleteCategory, listCategories, listTools, listSkills } from '../api/client';
import { ChannelSvg } from './Logo';

const CATEGORIES = [
  { key: 'life', icon: '🌿', label: '生活' },
  { key: 'ecommerce', icon: '🛒', label: '电商' },
  { key: 'work', icon: '💼', label: '工作' },
  { key: 'learn', icon: '📚', label: '学习' },
  { key: 'create', icon: '🎨', label: '创作' },
  { key: 'finance', icon: '📈', label: '金融' },
  { key: 'media', icon: '💬', label: '自媒体' },
  { key: 'other', icon: '📦', label: '其他' },
];

export function Sidebar() {
  const {
    setView, view,
    currentScene, setCurrentScene,
    currentProject,
    loadThinkingMap, loadSceneMessages,
    channels, currentChannel, setCurrentChannel,
    loadChannels, loadChannelMessages,
    createChannelAndReload, updateChannelAndReload,
    deleteChannelAndReload, clearChannelHistory,
    workshopScenes, loadWorkshopScenes,
  } = useStore();

  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [collapsedCats, setCollapsedCats] = useState<Set<string>>(new Set(['ecommerce', 'work', 'learn', 'create', 'finance', 'media', 'other']));
  const [memories, setMemories] = useState<{ key: string; priority_level: string }[]>([]);
  const [catManageOpen, setCatManageOpen] = useState(false);
  // ── 类别重命名状态 ──
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<{ name: string; label: string } | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renameSaving, setRenameSaving] = useState(false);
  // ── 新建类别状态 ──
  const [newCatOpen, setNewCatOpen] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatLabel, setNewCatLabel] = useState('');
  const [newCatIcon, setNewCatIcon] = useState('📁');
  const [newCatCreating, setNewCatCreating] = useState(false);
  // ── 动态类别列表 ──
  const [categories, setCategories] = useState<{ name: string; label: string; icon: string; count: number }[]>([]);

  // 加载类别元数据
  useEffect(() => {
    listCategories().then(setCategories).catch(() => {});
  }, [catManageOpen]);

  const [toolsCount, setToolsCount] = useState(0);
  const [skillsCount, setSkillsCount] = useState(0);

  useEffect(() => { loadChannels(); }, []);
  // 侧边栏需要工坊数据来展示场景列表和计数，不管当前在哪个视图
  useEffect(() => { loadWorkshopScenes(); }, []);

  // 加载工具和技能数量（每次 view 切换时也刷新）
  useEffect(() => {
    listTools().then(r => { if (r.success) setToolsCount(r.data.length); }).catch(() => {});
    listSkills().then(r => { if (r.success) setSkillsCount(r.data.length); }).catch(() => {});
  }, [view]);

  useEffect(() => {
    if (view === 'workshop') {
      loadWorkshopScenes();
    }
  }, [view]);

  // 加载记忆数量（用于 badge）
  useEffect(() => {
    listMemories().then(res => setMemories(res.data)).catch(() => {});
  }, [view]);  // 每次切视图刷新（记忆管理全页可增删改）

  const closeMenu = () => setMenuOpen(null);

  const toggleCategory = (key: string) => {
    setCollapsedCats(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleCreateChannel = async () => {
    const name = prompt('频道名称：');
    if (!name) return;
    try { await createChannelAndReload(name); } catch (e) { console.error(e); }
  };

  const handleEnterChannel = async (channelId: string) => {
    const ch = channels.find(c => c.id === channelId);
    if (!ch) return;
    setView('chat');
    setCurrentScene(null);
    setCurrentChannel(ch);
    await loadChannelMessages(channelId);
  };

  const handleRenameChannel = async (channelId: string, currentName: string) => {
    const name = prompt('新名称：', currentName);
    if (!name) return;
    await updateChannelAndReload(channelId, { name });
    closeMenu();
  };

  const handlePinChannel = async (channelId: string, pinned: boolean) => {
    await updateChannelAndReload(channelId, { pinned: !pinned });
    closeMenu();
  };

  const handleDeleteChannel = async (channelId: string, name: string) => {
    if (!confirm(`确定删除频道「${name}」？`)) return;
    await deleteChannelAndReload(channelId);
    closeMenu();
  };

  const handleClearChannel = async (channelId: string) => {
    if (!confirm('确定清空该频道所有聊天记录？')) return;
    await clearChannelHistory(channelId);
    closeMenu();
  };

  const isChannelActive = (chId: string) =>
    view === 'chat' && !currentScene && currentChannel?.id === chId;

  const handleEnterScene = async (scene: Scene) => {
    setCurrentScene(scene);
    setCurrentChannel(channels[0] || null);
    setView('chat');
    await loadThinkingMap(scene.id);
    await loadSceneMessages(scene.id);
  };

  const handleRename = async (scene: Scene) => {
    const name = prompt('新名称：', scene.name);
    if (!name) return;
    await updateScene(scene.id, { name });
    await loadWorkshopScenes();
    closeMenu();
  };

  const handleDelete = async (scene: Scene) => {
    if (!confirm(`确定删除场景「${scene.name}」？\n该场景下的所有数据将被永久删除。`)) return;
    await deleteScene(scene.id);
    if (currentScene?.id === scene.id) setCurrentScene(null);
    await loadWorkshopScenes();
    closeMenu();
  };

  const handlePin = async (scene: Scene) => {
    await updateScene(scene.id, { pinned: !scene.pinned });
    await loadWorkshopScenes();
    closeMenu();
  };

  const toggleMenu = (id: string) => {
    setMenuOpen(menuOpen === id ? null : id);
  };

  const handleRenameCategory = async (catKey: string, currentLabel: string) => {
    setRenameTarget({ name: catKey, label: currentLabel });
    setRenameValue(currentLabel);
    setRenameOpen(true);
  };

  // 按类别统计工坊场景
  const catCounts: Record<string, number> = {};
  workshopScenes.forEach(s => {
    catCounts[s.category] = (catCounts[s.category] || 0) + 1;
  });

  // 当前工坊过滤类别（若有）
  const activeCat = view === 'workshop' ? null : null;

  return (
    <div className="sidebar">
      <div className="sidebar-list">
        {/* ═══ 讨论 · 频道 ═══ */}
        <div className="sidebar-section">
          <div className="sidebar-label">
            <ChannelSvg />
            讨论 · 频道
          </div>
        </div>

        {channels.map((ch) => (
          <div
            key={ch.id}
            className={`sidebar-item indent${isChannelActive(ch.id) ? ' active' : ''}`}
            onClick={() => handleEnterChannel(ch.id)}
          >
            <span className="sidebar-item-icon">
              {ch.is_default ? '💬' : '#'}
            </span>
            <span className="sidebar-item-name">
              {ch.pinned && !ch.is_default ? '📌 ' : ''}{ch.name}
            </span>
            <span
              className="sidebar-menu-btn"
              onClick={(e) => { e.stopPropagation(); toggleMenu(ch.id); }}
            >···</span>

            {menuOpen === ch.id && (
              <div className="sidebar-dropdown">
                {ch.is_default ? (
                  <div className="sidebar-dropdown-item"
                    onClick={(e) => { e.stopPropagation(); handleClearChannel(ch.id); }}
                  >🗑 清空聊天记录</div>
                ) : (
                  <>
                    <div className="sidebar-dropdown-item"
                      onClick={(e) => { e.stopPropagation(); handlePinChannel(ch.id, ch.pinned); }}
                    >📌 {ch.pinned ? '取消置顶' : '置顶'}</div>
                    <div className="sidebar-dropdown-item"
                      onClick={(e) => { e.stopPropagation(); handleRenameChannel(ch.id, ch.name); }}
                    >✏️ 重命名</div>
                    <div className="sidebar-dropdown-item danger"
                      onClick={(e) => { e.stopPropagation(); handleDeleteChannel(ch.id, ch.name); }}
                    >🗑 删除</div>
                  </>
                )}
              </div>
            )}
          </div>
        ))}

        <div className="sidebar-action" onClick={handleCreateChannel}>
          <span className="sidebar-item-icon">+</span>
          新建频道
        </div>

        {/* ═══ 场景广场 ═══ */}
        <div
          className="sidebar-section"
          onClick={() => setView('plaza')}
          style={{ cursor: 'pointer', marginTop: 4, borderBottom: '1px solid #21262d' }}
        >
          <div className="sidebar-label">
            <svg viewBox="0 0 16 16" fill="#58a6ff" width="16" height="16">
              <path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h3A1.5 1.5 0 0 1 7 2.5v3A1.5 1.5 0 0 1 5.5 7h-3A1.5 1.5 0 0 1 1 5.5v-3ZM2.5 2a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3ZM1 10.5A1.5 1.5 0 0 1 2.5 9h3A1.5 1.5 0 0 1 7 10.5v3A1.5 1.5 0 0 1 5.5 15h-3A1.5 1.5 0 0 1 1 13.5v-3ZM2.5 9.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3ZM9 2.5A1.5 1.5 0 0 1 10.5 1h3A1.5 1.5 0 0 1 15 2.5v3A1.5 1.5 0 0 1 13.5 7h-3A1.5 1.5 0 0 1 9 5.5v-3ZM10.5 2a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3ZM9 10.5A1.5 1.5 0 0 1 10.5 9h3a1.5 1.5 0 0 1 1.5 1.5v3a1.5 1.5 0 0 1-1.5 1.5h-3A1.5 1.5 0 0 1 9 13.5v-3ZM10.5 9.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3Z"/>
            </svg>
            场景广场
          </div>
        </div>

        {/* ═══ 工坊 ═══ */}
        <div className="sidebar-section" style={{ marginTop: 4 }}>
          <div className="sidebar-label">
            <svg viewBox="0 0 16 16" fill="#58a6ff" width="16" height="16">
              <path d="M4.5 1.5A2.5 2.5 0 0 0 2 4v2.5c0 .69.56 1.25 1.25 1.25h7.5c.69 0 1.25-.56 1.25-1.25V4a2.5 2.5 0 0 0-2.5-2.5h-5Z"/>
              <path d="M1.5 9.5v3a2.5 2.5 0 0 0 2.5 2.5h4a.5.5 0 0 0 .5-.5v-7H5a.5.5 0 0 0-.5.5v1a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1-.5-.5Z"/>
              <path d="M11 9.5v.5h2.5a1.5 1.5 0 0 1 1.5 1.5v1a1.5 1.5 0 0 1-1.5 1.5H11a.5.5 0 0 1-.5-.5v-4a.5.5 0 0 1 .5-.5Z"/>
            </svg>
            工坊
          </div>
        </div>

        {/* 工坊入口 — 全部 */}
        <div
          className={`sidebar-nav${view === 'workshop' ? ' active' : ''}`}
          onClick={() => setView('workshop')}
        >
          <span className="nav-icon">
            <svg viewBox="0 0 16 16" fill="#58a6ff" width="16" height="16">
              <path d="M4.5 1.5A2.5 2.5 0 0 0 2 4v2.5c0 .69.56 1.25 1.25 1.25h7.5c.69 0 1.25-.56 1.25-1.25V4a2.5 2.5 0 0 0-2.5-2.5h-5Z"/>
              <path d="M1.5 9.5v3a2.5 2.5 0 0 0 2.5 2.5h4a.5.5 0 0 0 .5-.5v-7H5a.5.5 0 0 0-.5.5v1a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1-.5-.5Z"/>
              <path d="M11 9.5v.5h2.5a1.5 1.5 0 0 1 1.5 1.5v1a1.5 1.5 0 0 1-1.5 1.5H11a.5.5 0 0 1-.5-.5v-4a.5.5 0 0 1 .5-.5Z"/>
            </svg>
          </span>
          <span>创作空间</span>
          <span className="badge">{workshopScenes.length}</span>
        </div>

        {/* 分类折叠列表 — 预定义 + 自定义分类 */}
        {(() => {
          // 从实际数据中收集所有分类
          const allCatKeys = new Set(workshopScenes.map(s => s.category));
          // 构建显示列表：预定义分类（有场景的）+ 自定义分类（不在预定义中的）
          const displayCats: { key: string; icon: string; label: string }[] = [];
          const predefinedKeys = new Set(CATEGORIES.map(c => c.key));
          // 先加预定义的
          for (const cat of CATEGORIES) {
            if (allCatKeys.has(cat.key)) {
              displayCats.push(cat);
              allCatKeys.delete(cat.key);
            }
          }
          // 再加自定义的
          for (const key of allCatKeys) {
            displayCats.push({ key, icon: '📁', label: key });
          }
          return displayCats.map(cat => {
            const count = catCounts[cat.key] || 0;
            if (count === 0) return null;
            const isCollapsed = collapsedCats.has(cat.key);
            return (
              <div key={cat.key}>
                <div
                  className={`sidebar-category${isCollapsed ? ' collapsed' : ''}`}
                  onClick={() => toggleCategory(cat.key)}
                >
                  <span className="cat-arrow">▼</span>
                  <span className="cat-icon">{cat.icon}</span>
                  {cat.label}
                  <span className="cat-count">{count}</span>
                  <span className="sidebar-menu-btn" style={{ fontSize: 13, opacity: 0.5 }}
                    onClick={(e) => { e.stopPropagation(); handleRenameCategory(cat.key, cat.label); }}
                    title="重命名类别"
                  >✏️</span>
                </div>
                <div className={`sidebar-children${isCollapsed ? ' collapsed' : ''}`}>
                  {workshopScenes
                    .filter(s => s.category === cat.key)
                    .map(s => {
                      const isPublished = s.version !== '0.0';
                      return (
                        <div
                          key={s.id}
                          className={`sidebar-item indent${currentScene?.id === s.id && view === 'chat' ? ' active' : ''}`}
                          onClick={() => handleEnterScene(s)}
                          title={`${s.icon || '📦'} ${s.name} ${isPublished ? `v${s.version}` : '草稿'}`}
                        >
                          <span className="sidebar-item-icon">{s.icon || '📦'}</span>
                          <span className="sidebar-item-name" style={s.pinned ? { color: '#d29922' } : undefined}>{s.name}</span>
                          <span
                            className="badge"
                            style={isPublished ? { background: '#23863633', color: '#3fb950' } : { background: '#d2992233', color: '#d29922' }}
                          >
                            {isPublished ? `v${s.version}` : '草稿'}
                          </span>
                          <span
                            className="sidebar-menu-btn"
                            onClick={(e) => { e.stopPropagation(); toggleMenu(s.id); }}
                          >···</span>

                          {menuOpen === s.id && (
                            <div className="sidebar-dropdown">
                              <div className="sidebar-dropdown-item"
                                onClick={(e) => { e.stopPropagation(); handlePin(s); }}
                              >📌 {s.pinned ? '取消置顶' : '置顶'}</div>
                              <div className="sidebar-dropdown-item"
                                onClick={(e) => { e.stopPropagation(); handleRename(s); }}
                              >✏️ 重命名</div>
                              <div className="sidebar-dropdown-item danger"
                                onClick={(e) => { e.stopPropagation(); handleDelete(s); }}
                              >🗑 删除</div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                </div>
              </div>
            );
          });
        })()}

        <div className="sidebar-action" onClick={() => setCatManageOpen(true)}>
          <svg viewBox="0 0 16 16" fill="#58a6ff" width="16" height="16" style={{ flexShrink: 0 }}>
            <path d="M1.5 3h4a.5.5 0 0 1 .5.5v1a.5.5 0 0 0 .5.5h8a.5.5 0 0 1 .5.5V13a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 1 13V4.5A1.5 1.5 0 0 1 2.5 3Z"/>
          </svg>
          管理类别
        </div>

        <div className="sidebar-action" onClick={() => {
          useStore.getState().setCreateSceneModalOpen(true);
        }}>
          <span className="sidebar-item-icon">+</span>
          新建场景
        </div>

        {/* ═══ 记忆 & 技能（底部工具） ═══ */}
        <div className="sidebar-section" style={{ marginTop: 12 }}>
          <div className="sidebar-label">🧰 系统工具</div>
        </div>

        <div className="sidebar-nav" onClick={() => {
          setView('tools');
          useStore.getState().setCurrentScene(null);
        }}>
          <span className="nav-icon">🛠️</span>
          <span>工具管理</span>
          <span className="badge">{toolsCount}</span>
        </div>

        <div className="sidebar-nav" onClick={() => {
          setView('capability-verify');
          useStore.getState().setCurrentScene(null);
        }}>
          <span className="nav-icon">🧪</span>
          <span>能力验证</span>
        </div>

        <div className="sidebar-nav" onClick={() => { setView('memory'); useStore.getState().setCurrentScene(null); }}>
          <span className="nav-icon">🧠</span>
          <span>记忆管理</span>
          <span className="badge">{memories.length}</span>
        </div>

        <div className="sidebar-nav" onClick={() => { setView('skills'); useStore.getState().setCurrentScene(null); }}>
          <span className="nav-icon">📘</span>
          <span>技能管理</span>
          <span className="badge">{skillsCount}</span>
        </div>

        <div className="sidebar-nav" onClick={() => { setView('outputs'); useStore.getState().setCurrentScene(null); }}>
          <span className="nav-icon">📦</span>
          <span>产出成果</span>
        </div>
      </div>

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
                  <span className="sidebar-menu-btn" style={{ fontSize: 13 }}
                    onClick={() => handleRenameCategory(c.name, c.label)}
                    title="重命名"
                  >✏️</span>
                  {c.count === 0 && (
                    <span className="sidebar-menu-btn" style={{ fontSize: 13, color: '#f85149' }}
                      onClick={async () => {
                        if (!confirm(`确定删除类别「${c.label}」？`)) return;
                        try { await deleteCategory(c.name); setCatManageOpen(false); }
                        catch (e: any) { alert('删除失败: ' + (e.message || '')); }
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
                onKeyDown={e => { if (e.key === 'Enter') document.getElementById('sidebar-newcat-btn')?.click(); }} />
            </div>
          </div>
          <div className="modal-actions">
            <button className="btn" onClick={() => setNewCatOpen(false)} disabled={newCatCreating}>取消</button>
            <button id="sidebar-newcat-btn" onClick={async () => {
              if (!newCatName.trim()) return;
              setNewCatCreating(true);
              try {
                const catName = newCatName.trim();
                await createCategory({ name: catName, label: catName });
                listCategories().then(setCategories).catch(() => {});
                setNewCatOpen(false);
                setCatManageOpen(false);
              } catch (e: any) { alert('创建失败: ' + (e.message || '')); }
              finally { setNewCatCreating(false); }
            }} disabled={newCatCreating || !newCatName.trim()}
              style={{
                padding: '6px 16px', borderRadius: 6,
                background: newCatCreating || !newCatName.trim() ? '#23863666' : '#238636', color: '#fff',
                border: '1px solid #2ea043', cursor: newCatCreating || !newCatName.trim() ? 'not-allowed' : 'pointer', fontSize: 13,
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
                  placeholder="输入新的类别名称" autoFocus
                  onKeyDown={e => { if (e.key === 'Enter') document.getElementById('sidebar-rename-btn')?.click(); }} />
              </div>
            </div>
          )}
          <div className="modal-actions">
            <button className="btn" onClick={() => setRenameOpen(false)} disabled={renameSaving}>取消</button>
            <button id="sidebar-rename-btn" onClick={async () => {
              if (!renameTarget || !renameValue.trim() || renameSaving) return;
              setRenameSaving(true);
              try {
                await renameCategory(renameTarget.name, renameValue.trim());
                setRenameOpen(false);
                setCatManageOpen(false);
                loadWorkshopScenes();
              } catch (e: any) { alert('重命名失败: ' + (e.message || '')); }
              finally { setRenameSaving(false); }
            }} disabled={renameSaving || !renameValue.trim() || !renameTarget}
              style={{
                padding: '6px 16px', borderRadius: 6,
                background: renameSaving || !renameValue.trim() ? '#23863666' : '#238636', color: '#fff',
                border: '1px solid #2ea043', cursor: renameSaving || !renameValue.trim() ? 'not-allowed' : 'pointer', fontSize: 13,
              }}>
              {renameSaving ? '保存中...' : '✅ 确定'}
            </button>
          </div>
        </div>
      </div>

      <div className="sidebar-footer">
        <span style={{ fontSize: 13, color: '#8b949e' }}>坐山客 · {currentProject?.name || '本地'}</span>
      </div>
    </div>
  );
}
