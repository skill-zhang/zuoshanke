/** 📋 侧边栏 — 频道列表 + 场景列表 */
import { useEffect, useState } from 'react';
import { useStore } from '../stores/appStore';
import { listScenes, createScene, updateScene, deleteScene, Scene } from '../api/client';
import { ChannelSvg, ProjectFolderSvg } from './Logo';

export function Sidebar() {
  const {
    setView, currentProject, setCurrentScene,
    currentScene, loadThinkingMap, loadSceneMessages,
    channels, currentChannel, setCurrentChannel,
    loadChannels, loadChannelMessages,
    createChannelAndReload, updateChannelAndReload,
    deleteChannelAndReload, clearChannelHistory,
  } = useStore();

  const [scenes, setScenes] = useState<Scene[]>([]);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);

  useEffect(() => { loadChannels(); }, []);

  useEffect(() => {
    if (currentProject) {
      listScenes(currentProject.id).then(s => {
        setScenes(s.filter(sc => !sc.name.startsWith('_')));
      }).catch(console.error);
    } else {
      setScenes([]);
    }
  }, [currentProject]);

  const refreshScenes = async () => {
    if (!currentProject) return;
    try {
      const s = await listScenes(currentProject.id);
      setScenes(s.filter(sc => !sc.name.startsWith('_')));
    } catch { /* skip */ }
  };

  const closeMenu = () => setMenuOpen(null);

  // 频道操作
  const handleCreateChannel = async () => {
    const name = prompt('频道名称：');
    if (!name) return;
    try { await createChannelAndReload(name); } catch (e) { console.error(e); }
  };

  const handleEnterChannel = async (channelId: string) => {
    const ch = channels.find(c => c.id === channelId);
    if (!ch) return;
    setCurrentChannel(ch);
    setCurrentScene(null);
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
    !currentScene && currentChannel?.id === chId;

  // 场景操作
  const handleCreateScene = async () => {
    if (!currentProject) return;
    const name = prompt('场景名称：');
    if (!name) return;
    try { await createScene(currentProject.id, name); await refreshScenes(); }
    catch (e) { console.error(e); }
  };

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
    await refreshScenes();
    closeMenu();
  };

  const handlePin = async (scene: Scene) => {
    await updateScene(scene.id, { pinned: !scene.pinned });
    await refreshScenes();
    closeMenu();
  };

  const handleDelete = async (scene: Scene) => {
    if (!confirm(`确定删除场景「${scene.name}」？\n该场景下的所有数据将被永久删除。`)) return;
    await deleteScene(scene.id);
    if (currentScene?.id === scene.id) setCurrentScene(null);
    await refreshScenes();
    closeMenu();
  };

  const toggleMenu = (id: string) => {
    setMenuOpen(menuOpen === id ? null : id);
  };

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

        {/* ═══ 当前项目 · 场景 ═══ */}
        <div className="sidebar-section section-gap">
          <div className="sidebar-label">
            <ProjectFolderSvg />
            {currentProject ? `当前项目 · ${currentProject.name}` : '当前项目 · 未选择'}
          </div>
        </div>

        {!currentProject ? (
          <div className="sidebar-placeholder" onClick={() => setView('projects')}>
            选择一个项目开始工作 →
          </div>
        ) : (
          <>
            {scenes.map((s) => (
              <div
                key={s.id}
                className={`sidebar-item indent${currentScene?.id === s.id ? ' active' : ''}`}
                onClick={() => handleEnterScene(s)}
              >
                <span className="sidebar-item-icon">#</span>
                <span className="sidebar-item-name">{s.pinned ? '📌 ' : ''}{s.name}</span>
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
            ))}

            <div className="sidebar-action" onClick={handleCreateScene}>
              <span className="sidebar-item-icon">+</span>
              新建场景
            </div>

            <div className="sidebar-action" onClick={() => setView('projects')}>
              <ProjectFolderSvg />
              管理项目
            </div>
          </>
        )}
      </div>

      <div className="sidebar-footer">
        <span className="link" onClick={() => setView('projects')}>
          <ProjectFolderSvg /> 切换项目
        </span>
      </div>
    </div>
  );
}
