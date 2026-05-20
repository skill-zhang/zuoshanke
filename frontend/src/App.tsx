import { useEffect, useState, useRef, useCallback } from 'react';
import { useStore, AgentStatus } from './stores/appStore';
import { Topbar } from './components/Topbar';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';
import { PlazaView } from './components/PlazaView';
import { WorkshopView } from './components/WorkshopView';
import { ToolsView } from './components/ToolsView';
import { SettingsDrawer } from './components/SettingsDrawer';
import { MemoryView } from './components/MemoryView';
import { SkillsView } from './components/SkillsView';
import { CapabilityVerify } from './components/CapabilityVerify';
import { OutputGalleryView } from './components/OutputGalleryView';
import { SecretGarden } from './components/SecretGarden';
import { AgentCharacter } from './components/AgentCharacter';
import AgentLoopDashboard from './components/AgentLoopDashboard';
import { Scene, createScene } from './api/client';

// ═══ 稳定选择器（避免 useSyncExternalStore getSnapshot 引用变化）═══
const selectAgentStatus = (s: any) => s.agentStatus;
const selectAgentMessage = (s: any) => s.agentMessage;
const selectAgentHidden = (s: any) => s.agentHidden;
const selectSetAgentStatus = (s: any) => s.setAgentStatus;
const selectSetAgentMessage = (s: any) => s.setAgentMessage;
const selectSetAgentHidden = (s: any) => s.setAgentHidden;
const selectIsGenerating = (s: any) => s.isGenerating;

export default function App() {
  const {
    view, setView,
    currentScene, setCurrentScene,
    loadThinkingMap, loadSceneMessages,
    channels, setCurrentChannel,
    loadWorkshopScenes,
    createSceneModalOpen, setCreateSceneModalOpen,
  } = useStore();

  const [createName, setCreateName] = useState('');
  const [createCategory, setCreateCategory] = useState('other');
  const [createNewCategory, setCreateNewCategory] = useState('');
  const [createUseNewCategory, setCreateUseNewCategory] = useState(false);
  const [createDescription, setCreateDescription] = useState('');
  const [creating, setCreating] = useState(false);

  // ═══ 角色动画联动 — AI原生自洽（稳定选择器防 getSnapshot 警告） ═══
  const agentStatus = useStore(selectAgentStatus);
  const agentMessage = useStore(selectAgentMessage);
  const agentHidden = useStore(selectAgentHidden);
  const setAgentStatus = useStore(selectSetAgentStatus);
  const setAgentMessage = useStore(selectSetAgentMessage);
  const setAgentHidden = useStore(selectSetAgentHidden);
  const isGenerating = useStore(selectIsGenerating);

  // 工作状态自动检测
  const prevGenRef = useRef(isGenerating);
  useEffect(() => {
    const prev = prevGenRef.current;
    if (!prev && isGenerating) {
      setAgentStatus('working');
      setAgentMessage('拼命处理中💦');
      recordActivity();
    } else if (prev && !isGenerating) {
      setAgentStatus('done');
      setAgentMessage('搞定！✅');
      const t = setTimeout(() => {
        if (!isIdle) {
          setAgentStatus('idle');
          setAgentMessage('在线待命');
        }
      }, 2500);
      return () => clearTimeout(t);
    }
    prevGenRef.current = isGenerating;
  }, [isGenerating]);

  // ═══ 空闲自娱自乐 🎭 ═══
  const entertainments = [
    { status: 'laugh' as AgentStatus, msg: '哈哈，自己讲个笑话给自己听...' },
    { status: 'thinking' as AgentStatus, msg: '🎵 天青色等烟雨～而我在等你～🎵' },
    { status: 'laugh' as AgentStatus, msg: '为什么AI不怕冷？因为它有C:\\驱动器 ❄️' },
    { status: 'notify' as AgentStatus, msg: '🎶 没人聊天时就自己唱歌' },
    { status: 'angry' as AgentStatus, msg: '哼，这么久不理我' },
    { status: 'sad' as AgentStatus, msg: '清泉是不是把我忘了...😢' },
    { status: 'laugh' as AgentStatus, msg: '想到一个段子，先笑为敬🤣' },
    { status: 'thinking' as AgentStatus, msg: '🎵 无敌是多么～多么寂寞～🎵' },
    { status: 'notify' as AgentStatus, msg: '刚偷偷优化了一行没人让你干的代码' },
    { status: 'laugh' as AgentStatus, msg: '🤣 刚刚自己把自己逗笑了' },
  ];
  const lastActivityRef = useRef(Date.now());
  const [isIdle, setIsIdle] = useState(false);
  const idleCheckRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const entertainRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const recordActivity = useCallback(() => {
    lastActivityRef.current = Date.now();
    if (isIdle) {
      setIsIdle(false);
      setAgentHidden(false);
    }
  }, [isIdle]);

  // 全局监听用户操作
  useEffect(() => {
    const handler = () => recordActivity();
    window.addEventListener('mousedown', handler);
    window.addEventListener('keydown', handler);
    window.addEventListener('touchstart', handler);
    return () => {
      window.removeEventListener('mousedown', handler);
      window.removeEventListener('keydown', handler);
      window.removeEventListener('touchstart', handler);
    };
  }, [recordActivity]);

  // 空闲检测循环
  useEffect(() => {
    idleCheckRef.current = setInterval(() => {
      if (isGenerating) return;
      const elapsed = Date.now() - lastActivityRef.current;
      if (elapsed > 25000 && !isIdle) {
        setIsIdle(true);
      } else if (elapsed > 180000) {
        // 3分钟无操作 → 去睡觉
        setAgentHidden(true);
      } else if (elapsed < 25000 && isIdle) {
        setIsIdle(false);
        setAgentHidden(false);
      }
    }, 3000);
    return () => { if (idleCheckRef.current) clearInterval(idleCheckRef.current); };
  }, [isGenerating, isIdle]);

  // 空闲时自娱自乐
  useEffect(() => {
    if (!isIdle) {
      if (entertainRef.current) { clearInterval(entertainRef.current); entertainRef.current = null; }
      return;
    }
    // 初始随机延迟后开始娱乐
    const startDelay = setTimeout(() => {
      entertainRef.current = setInterval(() => {
        const pick = entertainments[Math.floor(Math.random() * entertainments.length)];
        setAgentStatus(pick.status);
        setAgentMessage(pick.msg);
      }, 5000 + Math.random() * 7000);
    }, 3000 + Math.random() * 5000);
    return () => { clearTimeout(startDelay); if (entertainRef.current) clearInterval(entertainRef.current); };
  }, [isIdle]);

  // ═══ 页面关闭时提取最后一个场景的记忆 ═══
  const prevSceneRef = useRef(currentScene);
  useEffect(() => {
    prevSceneRef.current = currentScene;
  }, [currentScene]);
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'hidden') {
        const scene = prevSceneRef.current;
        if (scene) {
          fetch(`/api/scenes/${scene.id}/extract-memory`, { method: 'POST' }).catch(() => {});
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, []);

  const handleEnterScene = async (scene: Scene) => {
    setCurrentScene(scene);
    setCurrentChannel(channels[0] || null);
    setView('chat');
    await loadThinkingMap(scene.id);
    await loadSceneMessages(scene.id);
    // 进入场景 → 角色打招呼
    setAgentStatus('greeting');
    setAgentMessage(`${scene.icon || '📦'} ${scene.name}，来了！`);
    setTimeout(() => {
      setAgentStatus('idle');
      setAgentMessage('在线待命');
    }, 3000);
  };

  const handleCreateScene = () => {
    setCreateName('');
    setCreateCategory('other');
    setCreateNewCategory('');
    setCreateUseNewCategory(false);
    setCreateDescription('');
    setCreateSceneModalOpen(true);
  };

  const handleCloseCreate = () => {
    if (creating) return;
    setCreateSceneModalOpen(false);
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
        const { importScene } = await import('./api/client');
        await importScene('none', data);
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
      const category = createUseNewCategory ? createNewCategory.trim() : createCategory;
      const scene = await createScene(createName.trim(), {
        description: createDescription.trim() || undefined,
        category: category || 'other',
      });
      setCreateSceneModalOpen(false);
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
      case 'secret-garden': return '🌸 秘密花园';
      case 'dashboard': return '📊 仪表盘';
      case 'chat':
        if (currentScene) return `${currentScene.icon || '📦'} ${currentScene.name}`;
        return '💬 聊天';
      default: return '坐山客';
    }
  };

  return (
    <>
      <Topbar extraTitle={getTitle()} />
      <AgentCharacter
        hidden={agentHidden}
      />

      <div className="main">
        <Sidebar />

        {view === 'plaza' ? (
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
         ) :
         view === 'tools' ? (
          <ToolsView />
        ) :        view === 'capability-verify' ? (
          <CapabilityVerify />
        ) : view === 'skills' ? (
          <SkillsView />
        ) : view === 'dashboard' ? (
          <AgentLoopDashboard />
        ) : view === 'memory' ? (
          <MemoryView />
        ) : view === 'outputs' ? (
          <OutputGalleryView />
        ) : view === 'secret-garden' ? (
          <SecretGarden />
        ) : (
          <ChatView />
        )}
      </div>

      <div className="statusbar">
        <span className="dot green" /> 坐山客 v0.2
        <span>|</span> API: http://localhost:8000
      </div>

      <SettingsDrawer />

      {/* ═══ 创建场景弹窗 ═══ */}
      <div className={`modal-overlay${createSceneModalOpen ? ' show' : ''}`} onClick={handleCloseCreate}>
        <div className="modal" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            创建新场景
            <button className="modal-close" onClick={handleCloseCreate}>✕</button>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">场景名称</label>
              <input className="form-input" value={createName} onChange={e => setCreateName(e.target.value)} placeholder="例：天气查询" />
            </div>
            <div className="form-group">
              <label className="form-label">类别</label>
              {createUseNewCategory ? (
                <input className="form-input" value={createNewCategory} onChange={e => setCreateNewCategory(e.target.value)} placeholder="输入新类别名称" />
              ) : (
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
              )}
              <div className="form-hint">
                <span style={{ cursor: 'pointer', color: '#58a6ff' }} onClick={() => {
                  setCreateUseNewCategory(!createUseNewCategory);
                  setCreateNewCategory('');
                }}>
                  {createUseNewCategory ? '← 选择已有类别' : '➕ 新建类别'}
                </span>
              </div>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">简介</label>
            <input className="form-input" value={createDescription} onChange={e => setCreateDescription(e.target.value)} placeholder="场景的简短描述" />
          </div>
          <div className="modal-actions">
            <button className="btn" onClick={handleCloseCreate} disabled={creating}>取消</button>
            <button className="btn btn-primary" onClick={doCreateScene} disabled={creating || !createName.trim()}>
              {creating ? '创建中...' : '创建'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
