import { useState } from 'react';
import { useStore } from '../stores/appStore';
import { Project, deleteProject } from '../api/client';
import { FolderSvg } from './Logo';

export function ProjectList() {
  const { projects, loadProjects, setCurrentProject, setView, createProjectAndReload } = useStore();
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    const name = prompt('项目名称：');
    if (!name) return;
    setCreating(true);
    try {
      await createProjectAndReload(name);
    } finally {
      setCreating(false);
    }
  };

  const handleEnter = (proj: Project) => {
    setCurrentProject(proj);
    setView('chat');
  };

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除此项目及其所有场景？')) return;
    await deleteProject(id);
    await loadProjects();
  };

  return (
    <div className="page active">
      <h2><FolderSvg />项目管理</h2>
      <p className="subtitle">每个项目包含多个场景，场景下有独立讨论频道和 Thinking Map</p>

      <table>
        <thead>
          <tr><th>项目名称</th><th>最后活跃</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          {projects.length === 0 && (
            <tr>
              <td colSpan={4} style={{ textAlign: 'center', color: '#484f58', padding: 40 }}>
                还没有项目，点击下方按钮创建
              </td>
            </tr>
          )}
          {projects.map((p) => (
            <tr key={p.id}>
              <td>
                <span className="project-name" onClick={() => handleEnter(p)}>{p.name}</span>
              </td>
              <td style={{ color: '#8b949e' }}>
                {new Date(p.updated_at).toLocaleString('zh-CN')}
              </td>
              <td>
                <span className={`status-dot ${p.status === 'active' ? 'green' : 'gray'}`} />
                {p.status === 'active' ? '活跃' : p.status === 'idle' ? '闲置' : '归档'}
              </td>
              <td>
                <button style={{ fontSize: 13, padding: '4px 10px' }} onClick={() => handleDelete(p.id)}>
                  删除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="actions">
        <button className="primary" onClick={handleCreate} disabled={creating}>
          {creating ? '创建中...' : '+ 新建项目'}
        </button>
      </div>
    </div>
  );
}
