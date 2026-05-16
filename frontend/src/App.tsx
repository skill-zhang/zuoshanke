import { useEffect } from 'react';
import { useStore } from './stores/appStore';
import { Topbar } from './components/Topbar';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';
import { ProjectList } from './components/ProjectList';
import { ThinkingMapDrawer } from './components/ThinkingMapDrawer';
import { ActionMapDrawer } from './components/ActionMapDrawer';

export default function App() {
  const { view, loadProjects, currentProject } = useStore();

  useEffect(() => {
    loadProjects();
  }, []);

  return (
    <>
      <Topbar />

      <div className="main">
        {/* 侧边栏始终可见 */}
        <Sidebar />

        {view === 'projects' ? <ProjectList /> : <ChatView />}
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
    </>
  );
}
