import { useStore } from '../stores/appStore';
import { LogoSvg } from './Logo';

interface TopbarProps {
  extraTitle?: string;
}

export function Topbar({ extraTitle }: TopbarProps) {
  const { view, setView, currentProject, currentScene } = useStore();

  const showBreadcrumb = view === 'chat' || view === 'projects' || view === 'dashboard';

  return (
    <div className="topbar">
      <div className="logo-group" onClick={() => setView('projects')}>
        <LogoSvg />
        <span className="logo-text">坐山客</span>
      </div>

      {showBreadcrumb ? (
        <div className="breadcrumb">
          <span className="arrow">›</span>
          {view === 'projects' ? (
            <span style={{ color: '#c9d1d9' }}>项目管理</span>
          ) : view === 'dashboard' && currentScene ? (
            <>
              <span style={{ color: '#8b949e' }}>{currentScene.icon || '📦'} {currentScene.name}</span>
              <span style={{ color: '#666', marginLeft: 6 }}>| 📊 仪表盘</span>
            </>
          ) : currentProject ? (
            <>
              <span style={{ color: '#8b949e' }}>项目</span>
              <span className="clickable" onClick={() => setView('projects')}>
                {currentProject.name}
              </span>
              {currentScene && (
                <>
                  <span className="sep">|</span>
                  <span style={{ color: '#8b949e' }}>场景</span>
                  <span style={{ color: '#c9d1d9' }}>{currentScene.name}</span>
                </>
              )}
            </>
          ) : (
            <span style={{ color: '#484f58' }}>未选择项目 — 闲聊模式</span>
          )}
        </div>
      ) : (
        <div className="breadcrumb">
          <span className="arrow">›</span>
          <span style={{ color: '#c9d1d9' }}>{extraTitle || ''}</span>
        </div>
      )}

      <span className="spacer" />

      {view === 'dashboard' && currentScene && (
        <button className="btn back-chat-btn" onClick={() => setView('chat')}>
          💬 回到对话
        </button>
      )}

      {view === 'chat' && currentScene && (
        <button className="btn dash-btn" onClick={async () => {
          const store = useStore.getState();
          const sid = store.currentScene!.id;
          await store.loadThinkingMap(sid);
          await Promise.all([
            store.loadDashboardQueue(sid),
            store.loadDashboardReflect(sid),
            store.loadDashboardStatus(sid),
          ]);
          store.setView('dashboard');
        }}>
          🧠 思考 <span className="dash-btn-arrow">⏩</span> ⚡ 行动
        </button>
      )}

      <button className="btn settings-btn" title="系统设置" onClick={() => {
        useStore.getState().openSettingsDrawer();
      }}>
        ⚙
      </button>
    </div>
  );
}
