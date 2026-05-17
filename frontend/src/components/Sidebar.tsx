/** 📋 侧边栏 — 频道列表 + 场景广场 + 工坊（分类折叠） */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';
import { listScenes, updateScene, deleteScene, Scene, listProjects, createScene, listMemories } from '../api/client';
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

  useEffect(() => { loadChannels(); }, []);
  // 侧边栏需要工坊数据来展示场景列表和计数，不管当前在哪个视图
  useEffect(() => { loadWorkshopScenes(); }, []);

  useEffect(() => {
    if (view === 'workshop') {
      loadWorkshopScenes();
    }
  }, [view]);

  // 加载记忆数量（用于 badge）
  useEffect(() => {
    listMemories().then(res => setMemories(res.data)).catch(() => {});
  }, []);

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

        {/* 分类折叠列表 */}
        {CATEGORIES.map(cat => {
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
        })}

        <div className="sidebar-action" onClick={async () => {
          const name = prompt('场景名称：');
          if (!name) return;
          try {
            const projects = await listProjects();
            if (projects.length === 0) {
              alert('请先创建一个项目');
              return;
            }
            await createScene(projects[0].id, name, { icon: '📦', category: 'other' });
            loadWorkshopScenes();
          } catch (e: any) {
            alert('创建失败: ' + (e.message || ''));
          }
        }}>
          <span className="sidebar-item-icon">+</span>
          新建场景
        </div>

        {/* ═══ 记忆 & 技能（底部工具） ═══ */}
        <div className="sidebar-section" style={{ marginTop: 12 }}>
          <div className="sidebar-label">🧰 系统工具</div>
        </div>

        <div className="sidebar-nav" onClick={() => useStore.getState().openMemoryDrawer()}>
          <span className="nav-icon">🧠</span>
          <span>记忆管理</span>
          <span className="badge">{memories.length}</span>
        </div>

        <div className="sidebar-nav" onClick={() => useStore.getState().openSkillsDrawer()}>
          <span className="nav-icon">📘</span>
          <span>技能管理</span>
        </div>
      </div>

      <div className="sidebar-footer">
        <span style={{ fontSize: 13, color: '#8b949e' }}>坐山客 · {currentProject?.name || '本地'}</span>
      </div>
    </div>
  );
}
