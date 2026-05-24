/** 高危命令审批弹窗 — Agent 执行的命令被扫描器阻断时显示 */
import { useEffect } from 'react';
import { useStore } from 'zustand';
import { approvalStore } from '../stores/approvalStore';

export function CommandApprovalDialog() {
  const { visible, info, submitting, approve, reject, dismiss } = useStore(approvalStore);

  const categoryIcons: Record<string, string> = {
    filesystem: '🗂',
    disk: '💿',
    git: '🔀',
    database: '🗄',
    network: '🌐',
    docker: '🐳',
    package: '📦',
    config: '🔐',
  };

  const categoryLabels: Record<string, string> = {
    filesystem: '文件系统',
    disk: '磁盘操作',
    git: 'Git 操作',
    database: '数据库',
    network: '网络',
    docker: 'Docker',
    package: '包管理',
    config: '系统配置',
  };

  // 可见时按 Esc 关闭 = 拒绝
  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') reject();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [visible, reject]);

  if (!visible || !info) return null;

  const icon = categoryIcons[info.category] || '⚠️';
  const label = categoryLabels[info.category] || info.category;

  return (
    <div className="modal-overlay show" onClick={reject}>
      <div className="modal" onClick={e => e.stopPropagation()}
           style={{ maxWidth: 520 }}>
        <div className="modal-title" style={{ color: '#f85149' }}>
          <span>{icon} 高危操作被阻断</span>
          <button className="modal-close" onClick={reject}>✕</button>
        </div>

        <div style={{ margin: '12px 0' }}>
          <div style={{
            background: 'rgba(248,81,73,0.1)',
            border: '1px solid rgba(248,81,73,0.3)',
            borderRadius: 8,
            padding: '10px 14px',
            marginBottom: 12,
            fontSize: 13,
            color: '#f85149',
          }}>
            <span style={{ fontWeight: 600 }}>{label}</span> · {info.description}
          </div>

          <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 6 }}>
            被阻断的命令：
          </div>
          <pre style={{
            background: '#0d1117',
            border: '1px solid #21262d',
            borderRadius: 6,
            padding: '10px 14px',
            fontSize: 13,
            fontFamily: "'SF Mono','Fira Code','Cascadia Code',monospace",
            color: '#e6edf3',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            maxHeight: 120,
            overflow: 'auto',
            margin: 0,
          }}>{info.command}</pre>

          <p style={{ margin: '12px 0 0 0', color: '#c9d1d9', fontSize: 13, lineHeight: 1.6 }}>
            {info.reason}
          </p>
        </div>

        <div className="modal-actions" style={{ borderTop: '1px solid #21262d', paddingTop: 12 }}>
          <button
            className="btn"
            onClick={reject}
            disabled={submitting}
            style={{ color: '#f85149', borderColor: 'rgba(248,81,73,0.4)' }}
          >
            拒绝
          </button>
          <button
            className="btn btn-primary"
            onClick={approve}
            disabled={submitting}
            style={{ background: '#f85149', borderColor: '#f85149' }}
          >
            {submitting ? '处理中...' : '⚠ 仍要执行'}
          </button>
        </div>
      </div>
    </div>
  );
}
