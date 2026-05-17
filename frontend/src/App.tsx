import { useEffect, useState } from 'react';
import { useStore } from './stores/appStore';
import { Topbar } from './components/Topbar';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';
import { PlazaView } from './components/PlazaView';
import { WorkshopView } from './components/WorkshopView';
import { ProjectList } from './components/ProjectList';
import { ThinkingMapDrawer } from './components/ThinkingMapDrawer';
import { ActionMapDrawer } from './components/ActionMapDrawer';
import { SettingsDrawer } from './components/SettingsDrawer';
import { Scene, createScene, listProjects } from './api/client';

export default function App() {
  const {
    view, setView, loadProjects, currentProject,
    currentScene, setCurrentScene,
    loadThinkingMap, loadSceneMessages,
    channels, setCurrentChannel,
    loadWorkshopScenes,
  } = useStore();

  const [createModal, setCreateModal] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createIcon, setCreateIcon] = useState('📦');
  const [createCategory, setCreateCategory] = useState('other');
  const [createDescription, setCreateDescription] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadProjects();
  }, []);

  const handleEnterScene = async (scene: Scene) => {
    setCurrentScene(scene);
    setCurrentChannel(channels[0] || null);
    setView('chat');
    await loadThinkingMap(scene.id);
    await loadSceneMessages(scene.id);
  };

  const handleCreateScene = () => {
    setCreateName('');
    setCreateIcon('📦');
    setCreateCategory('other');
    setCreateDescription('');
    setCreateModal(true);
  };

  const handleImportScene = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const projects = await listProjects();
        if (projects.length === 0) {
          alert('请先创建一个项目');
          return;
        }
        const { importScene } = await import('./api/client');
        await importScene(projects[0].id, data);
        if (view === 'plaza') {
          const { loadPlazaScenes } = useStore.getState();
          loadPlazaScenes();
        }
        loadWorkshopScenes();
        alert('场景导入成功！');
      } catch (err: any) {
        alert('导入失败: ' + (err.message || '文件格式错误'));
      }
    };
    input.click();
  };

  const doCreateScene = async () => {
    if (!createName.trim()) return;
    setCreating(true);
    try {
      const projects = await listProjects();
      if (projects.length === 0) {
        alert('请先创建一个项目');
        return;
      }
      const scene = await createScene(projects[0].id, createName.trim(), {
        icon: createIcon || undefined,
        description: createDescription.trim() || undefined,
        category: createCategory,
      });
      setCreateModal(false);
      loadWorkshopScenes();
      // 自动进入新创建的场景
      handleEnterScene(scene);
    } catch (err: any) {
      alert('创建失败: ' + (err.message || '未知错误'));
    } finally {
      setCreating(false);
    }
  };

  const getTitle = () => {
    switch (view) {
      case 'plaza': return '🏪 场景广场';
      case 'workshop': return '🛠 工坊';
      case 'projects': return '📁 项目管理';
      case 'chat':
        if (currentScene) return `${currentScene.icon || '📦'} ${currentScene.name}`;
        return '💬 聊天';
      default: return '坐山客';
    }
  };

  return (
    <>
      <Topbar extraTitle={getTitle()} />

      <div className="main">
        <Sidebar />

        {view === 'projects' ? <ProjectList /> :
         view === 'plaza' ? (
           <PlazaView
             onEnterScene={handleEnterScene}
             onCreateScene={handleCreateScene}
             onImportScene={handleImportScene}
           />
         ) :
         view === 'workshop' ? (
           <WorkshopView
             onEnterScene={handleEnterScene}
             onCreateScene={handleCreateScene}
           />
         ) : (
           <ChatView />
         )}
      </div>

      <div className="statusbar">
        <span className="dot green" /> 坐山客 v0.2
        <span>|</span> API: http://localhost:8000
        {currentProject && (
          <>
            <span>|</span>
            项目: {currentProject.name}
          </>
        )}
      </div>

      <ThinkingMapDrawer />
      <ActionMapDrawer />
      <SettingsDrawer />

      {/* ═══ 创建场景弹窗 ═══ */}
      <div className={`modal-overlay${createModal ? ' show' : ''}`} onClick={() => !creating && setCreateModal(false)}>
        <div className="modal" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            创建新场景
            <button className="modal-close" onClick={() => !creating && setCreateModal(false)}>✕</button>
          </div>
          <div className="form-group">
            <label className="form-label">图标</label>
            <input className="form-input" value={createIcon} onChange={e => setCreateIcon(e.target.value)} placeholder="输入 emoji 图标" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">场景名称</label>
              <input className="form-input" value={createName} onChange={e => setCreateName(e.target.value)} placeholder="例：天气查询" />
            </div>
            <div className="form-group">
              <label className="form-label">类别</label>
              <select className="form-select" value={createCategory} onChange={e => setCreateCategory(e.target.value)}>
                <option value="life">🌿 生活</option>
                <option value="ecommerce">🛒 电商</option>
                <option value="work">💼 工作</option>
                <option value="learn">📚 学习</option>
                <option value="create">🎨 创作</option>
                <option value="finance">📈 金融</option>
                <option value="media">💬 自媒体</option>
                <option value="other">📦 其他</option>
              </select>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">简介</label>
            <input className="form-input" value={createDescription} onChange={e => setCreateDescription(e.target.value)} placeholder="场景的简短描述" />
          </div>
          <div className="modal-actions">
            <button className="btn" onClick={() => setCreateModal(false)} disabled={creating}>取消</button>
            <button className="btn btn-primary" onClick={doCreateScene} disabled={creating || !createName.trim()}>
              {creating ? '创建中...' : '创建'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
