import { useStore } from '../stores/appStore';
import { LogoSvg } from './Logo';

export function Topbar() {
  const { view, setView, currentProject, currentScene } = useStore();

  return (
    <div className="topbar">
      <div className="logo-group" onClick={() => setView('projects')}>
        <LogoSvg />
        <span className="logo-text">坐山客</span>
      </div>
      <div className="breadcrumb">
        <span className="arrow">›</span>
        {view === 'projects' ? (
          <span style={{ color: '#c9d1d9' }}>项目管理</span>
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
      <span className="spacer" />
      {view === 'chat' && currentScene && (
        <>
          <button className="btn tm-btn" onClick={async () => {
            const store = useStore.getState();
            await store.loadThinkingMap(store.currentScene!.id);
            store.openDrawer();
          }}>
            🧠 Thinking Map
          </button>
          <button className="btn am-btn" onClick={async () => {
            const store = useStore.getState();
            if (store.thinkingMap) {
              await store.loadActionMaps(store.thinkingMap.id);
            }
            store.openActionMapDrawer();
          }}>
            ⚡ Action Map
          </button>
        </>
      )}
    </div>
  );
}
