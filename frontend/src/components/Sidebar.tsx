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

  // 加载频道
  useEffect(() => {
    loadChannels();
  }, []);

  // 加载场景
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
    } catch {}
  };

  // ═══ 频道操作 ═══
  const handleCreateChannel = async () => {
    const name = prompt('频道名称：');
    if (!name) return;
    try { await createChannelAndReload(name); } catch (e) { console.error(e); }
  };

  const handleEnterChannel = async (channelId: string) => {
    const ch = channels.find(c => c.id === channelId);
    if (!ch) return;
    setCurrentChannel(ch);
    setCurrentScene(null);  // 退出场景
    await loadChannelMessages(channelId);
  };

  const handleRenameChannel = async (channelId: string, currentName: string) => {
    const name = prompt('新名称：', currentName);
    if (!name) return;
    await updateChannelAndReload(channelId, { name });
    setMenuOpen(null);
  };

  const handlePinChannel = async (channelId: string, pinned: boolean) => {
    await updateChannelAndReload(channelId, { pinned: !pinned });
    setMenuOpen(null);
  };

  const handleDeleteChannel = async (channelId: string, name: string) => {
    if (!confirm(`确定删除频道「${name}」？`)) return;
    await deleteChannelAndReload(channelId);
    setMenuOpen(null);
  };

  const handleClearChannel = async (channelId: string) => {
    if (!confirm('确定清空该频道所有聊天记录？')) return;
    await clearChannelHistory(channelId);
    setMenuOpen(null);
  };

  // ═══ 场景操作 ═══
  const handleCreateScene = async () => {
    if (!currentProject) return;
    const name = prompt('场景名称：');
    if (!name) return;
    try { await createScene(currentProject.id, name); await refreshScenes(); }
    catch (e) { console.error(e); }
  };

  const handleEnterScene = async (scene: Scene) => {
    setCurrentScene(scene);
    setCurrentChannel(channels[0] || null);  // 保持当前频道但不激活场景频道
    setView('chat');
    await loadThinkingMap(scene.id);
    await loadSceneMessages(scene.id);
  };

  const handleRename = async (scene: Scene) => {
    const name = prompt('新名称：', scene.name);
    if (!name) return;
    await updateScene(scene.id, { name });
    await refreshScenes();
    setMenuOpen(null);
  };

  const handlePin = async (scene: Scene) => {
    await updateScene(scene.id, { pinned: !scene.pinned });
    await refreshScenes();
    setMenuOpen(null);
  };

  const handleDelete = async (scene: Scene) => {
    if (!confirm(`确定删除场景「${scene.name}」？\n该场景下的所有数据将被永久删除。`)) return;
    await deleteScene(scene.id);
    if (currentScene?.id === scene.id) setCurrentScene(null);
    await refreshScenes();
    setMenuOpen(null);
  };

  const isChannelActive = (chId: string) =>
    !currentScene && currentChannel?.id === chId;

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
            className={`sidebar-item${isChannelActive(ch.id) ? ' active' : ''}`}
            style={{ paddingLeft: 30, position: 'relative' }}
            onClick={() => handleEnterChannel(ch.id)}
          >
            <span style={{ width: 22, textAlign: 'center', fontSize: 16 }}>
              {ch.is_default ? '💬' : '#'}
            </span>
            <span style={{ flex: 1 }}>
              {ch.pinned && !ch.is_default ? '📌 ' : ''}{ch.name}
            </span>
            <span
              style={{ cursor: 'pointer', padding: '0 4px', fontSize: 16, flexShrink: 0 }}
              onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === ch.id ? null : ch.id); }}
            >···</span>

            {menuOpen === ch.id && (
              <div style={{
                position: 'absolute', right: 8, top: 36, background: '#21262d',
                border: '1px solid #30363d', borderRadius: 6, zIndex: 10,
                minWidth: 140, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              }}>
                {ch.is_default ? (
                  <div className="sidebar-menu-item"
                    onClick={(e) => { e.stopPropagation(); handleClearChannel(ch.id); }}
                  >🗑 清空聊天记录</div>
                ) : (
                  <>
                    <div className="sidebar-menu-item"
                      onClick={(e) => { e.stopPropagation(); handlePinChannel(ch.id, ch.pinned); }}
                    >📌 {ch.pinned ? '取消置顶' : '置顶'}</div>
                    <div className="sidebar-menu-item"
                      onClick={(e) => { e.stopPropagation(); handleRenameChannel(ch.id, ch.name); }}
                    >✏️ 重命名</div>
                    <div className="sidebar-menu-item" style={{ color: '#f85149' }}
                      onClick={(e) => { e.stopPropagation(); handleDeleteChannel(ch.id, ch.name); }}
                    >🗑 删除</div>
                  </>
                )}
              </div>
            )}
          </div>
        ))}

        <div
          className="sidebar-item"
          style={{ paddingLeft: 30, color: '#8b949e' }}
          onClick={handleCreateChannel}
        >
          <span style={{ width: 22, textAlign: 'center', fontSize: 16 }}>+</span>
          新建频道
        </div>

        {/* ═══ 当前项目 · 场景 ═══ */}
        <div className="sidebar-section" style={{ marginTop: 8 }}>
          <div className="sidebar-label">
            <ProjectFolderSvg />
            {currentProject ? `当前项目 · ${currentProject.name}` : '当前项目 · 未选择'}
          </div>
        </div>

        {!currentProject && (
          <div
            className="sidebar-item"
            style={{ paddingLeft: 30, color: '#8b949e', fontSize: 13, fontStyle: 'italic' }}
            onClick={() => setView('projects')}
          >
            选择一个项目开始工作 →
          </div>
        )}

        {scenes.map((s) => (
          <div
            key={s.id}
            className={`sidebar-item${currentScene?.id === s.id ? ' active' : ''}`}
            style={{ paddingLeft: 30, position: 'relative' }}
            onClick={() => handleEnterScene(s)}
          >
            <span style={{ width: 22, textAlign: 'center', fontSize: 16, flexShrink: 0 }}>#</span>
            <span style={{ flex: 1 }}>{s.pinned ? '📌 ' : ''}{s.name}</span>
            <span
              style={{ cursor: 'pointer', padding: '0 4px', fontSize: 16, flexShrink: 0 }}
              onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === s.id ? null : s.id); }}
            >···</span>

            {menuOpen === s.id && (
              <div style={{
                position: 'absolute', right: 8, top: 36, background: '#21262d',
                border: '1px solid #30363d', borderRadius: 6, zIndex: 10,
                minWidth: 120, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              }}>
                <div className="sidebar-menu-item"
                  onClick={(e) => { e.stopPropagation(); handlePin(s); }}
                >📌 {s.pinned ? '取消置顶' : '置顶'}</div>
                <div className="sidebar-menu-item"
                  onClick={(e) => { e.stopPropagation(); handleRename(s); }}
                >✏️ 重命名</div>
                <div className="sidebar-menu-item" style={{ color: '#f85149' }}
                  onClick={(e) => { e.stopPropagation(); handleDelete(s); }}
                >🗑 删除</div>
              </div>
            )}
          </div>
        ))}

        {currentProject && (
          <div
            className="sidebar-item"
            style={{ paddingLeft: 30, color: '#8b949e' }}
            onClick={handleCreateScene}
          >
            <span style={{ width: 22, textAlign: 'center', fontSize: 16 }}>+</span>
            新建场景
          </div>
        )}

        <div
          className="sidebar-item"
          style={{ paddingLeft: 30, color: '#8b949e' }}
          onClick={() => { setView('projects'); }}
        >
          <span style={{ width: 22, textAlign: 'center', fontSize: 16 }}>📁</span>
          管理项目
        </div>
      </div>

      <div className="sidebar-footer">
        <span className="link" onClick={() => setView('projects')}>
          <ProjectFolderSvg /> 切换项目
        </span>
      </div>
    </div>
  );
}
