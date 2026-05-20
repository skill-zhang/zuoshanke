import { useStore } from '../stores/appStore';
import { LogoSvg } from './Logo';

interface TopbarProps {
  extraTitle?: string;
}

export function Topbar({ extraTitle }: TopbarProps) {
  const { view, setView, currentScene } = useStore();

  const showBreadcrumb = view === 'chat' || view === 'dashboard';

  return (
    <div className="topbar">
      <div className="logo-group" onClick={() => setView('chat')}>
        <LogoSvg />
        <span className="logo-text">坐山客</span>
      </div>

      {showBreadcrumb ? (
        <div className="breadcrumb">
          <span className="arrow">›</span>
          {view === 'dashboard' && currentScene ? (
            <>
              <span style={{ color: '#8b949e' }}>{currentScene.icon || '📦'} {currentScene.name}</span>
              <span style={{ color: '#666', marginLeft: 6 }}>| 📊 仪表盘</span>
            </>
          ) : currentScene ? (
            <>
              <span style={{ color: '#8b949e' }}>{currentScene.icon || '📦'} {currentScene.name}</span>
            </>
          ) : (
            <span style={{ color: '#484f58' }}>闲聊模式</span>
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
