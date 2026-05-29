/**
 * 🏠 WorkbenchView — 坐山客工作台（Schema v1.8）
 *
 * 个人工作台已从主系统剥离为独立沙箱进程。
 * 此组件变为跳转入口，打开独立工作台页面。
 *
 * 独立工作台在单独的 Vite dev server（:5174）和
 * 独立后端（:8001）中运行，崩了不影响核心系统。
 */
import { useEffect } from 'react';

export function WorkbenchView() {
  useEffect(() => {
    window.location.href = 'http://localhost:5174/wb/';
  }, []);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      background: '#0d1117',
      color: '#8b949e',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      <div style={{ fontSize: 48, marginBottom: 16 }}>🏠</div>
      <div style={{ fontSize: 16, marginBottom: 8 }}>正在进入个人工作台…</div>
      <div style={{ fontSize: 13, color: '#484f58' }}>
        如果页面没有自动跳转，<a href="http://localhost:5174/wb/"
          style={{ color: '#58a6ff' }}>点击这里</a>
      </div>
    </div>
  );
}
