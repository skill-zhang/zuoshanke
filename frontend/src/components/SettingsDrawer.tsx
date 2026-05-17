/** ⚙ 系统设置抽屉 — 三层展示 */
import { useEffect, useState, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import type { RouteConfig } from '../api/client';

type EditingRoute = { key: string } & Pick<RouteConfig, 'temperature' | 'max_tokens' | 'repeat_penalty'>;

const ROUTE_LABELS: Record<string, string> = {
  channel: '频道闲聊',
  scene: '场景分析',
  extraction: '约束提取',
  medium: 'Medium 任务',
  heavy: 'Heavy 任务',
};

const ROUTE_ORDER = ['channel', 'scene', 'extraction', 'medium', 'heavy'];

export function SettingsDrawer() {
  const {
    settingsDrawerOpen, closeSettingsDrawer,
    settingsData, serviceStatus, settingsLoading,
    loadSettings, refreshServiceStatus, updateSettingsPartial,
  } = useStore();

  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editedRoutes, setEditedRoutes] = useState<Record<string, EditingRoute>>({});
  const [statusTimer, setStatusTimer] = useState<ReturnType<typeof setInterval> | null>(null);

  // 打开时加载数据
  useEffect(() => {
    if (settingsDrawerOpen) {
      loadSettings();
      // 每 10 秒刷新服务状态
      const timer = setInterval(refreshServiceStatus, 10000);
      setStatusTimer(timer);
    } else {
      // 关闭时清空编辑状态
      setDirty(false);
      setEditedRoutes({});
    }
    return () => {
      if (statusTimer) clearInterval(statusTimer);
    };
  }, [settingsDrawerOpen]);

  // 编辑值变化
  const handleEdit = useCallback((key: string, field: string, value: number) => {
    setEditedRoutes(prev => ({
      ...prev,
      [key]: { ...(prev[key] || { key }), [field]: value },
    }));
    setDirty(true);
  }, []);

  // 保存
  const handleSave = async () => {
    setSaving(true);
    // 只推送有编辑的路由
    const routing: Record<string, any> = {};
    for (const [key, edit] of Object.entries(editedRoutes)) {
      const patch: Record<string, any> = {};
      if (edit.temperature !== undefined) patch.temperature = edit.temperature;
      if (edit.max_tokens !== undefined) patch.max_tokens = edit.max_tokens;
      if (edit.repeat_penalty !== undefined) patch.repeat_penalty = edit.repeat_penalty;
      if (Object.keys(patch).length > 0) routing[key] = patch;
    }
    const ok = await updateSettingsPartial({ routing });
    setSaving(false);
    if (ok) {
      setDirty(false);
      setEditedRoutes({});
    }
  };

  // 重置
  const handleReset = () => {
    setEditedRoutes({});
    setDirty(false);
  };

  const status = serviceStatus;
  const routing = settingsData?.routing || {};

  return (
    <>
      <div
        className={`drawer-overlay${settingsDrawerOpen ? ' open' : ''}`}
        onClick={closeSettingsDrawer}
      />
      <div className={`drawer settings-drawer${settingsDrawerOpen ? ' open' : ''}`}>
        <div className="drawer-header">
          <span style={{ fontSize: 16, fontWeight: 600, color: '#c9d1d9' }}>⚙ 系统设置</span>
          <span className="close" onClick={closeSettingsDrawer}>✕</span>
        </div>

        <div className="settings-body">
          {settingsLoading ? (
            <div className="settings-loading">正在加载…</div>
          ) : (
            <>
              {/* ── ① 服务运维层 ── */}
              <section className="settings-section">
                <h3 className="settings-section-title">① 服务状态</h3>
                <div className="settings-service-grid">
                  <div className="service-item">
                    <span className="service-label">llama-server</span>
                    <span className={`service-value status-${status?.llama_server === 'running' ? 'ok' : 'err'}`}>
                      {status?.llama_server === 'running' ? '✅ 运行中' : status?.llama_server === 'error' ? '⚠ 异常' : '⛔ 已停止'}
                    </span>
                  </div>
                  <div className="service-item">
                    <span className="service-label">端口</span>
                    <span className="service-value">{status?.port || 8083}</span>
                  </div>
                  <div className="service-item">
                    <span className="service-label">模型</span>
                    <span className="service-value">{status?.model_name || '-'}</span>
                  </div>
                  <div className="service-item">
                    <span className="service-label">上下文</span>
                    <span className="service-value">{status?.context_size || '-'} ctx</span>
                  </div>
                  <div className="service-item">
                    <span className="service-label">Flash Attention</span>
                    <span className="service-value">{status?.flash_attention || 'auto'}</span>
                  </div>
                  <div className="service-item">
                    <span className="service-label">插槽</span>
                    <span className="service-value">{status?.slots || 0} 个{status?.processing ? ' · 处理中' : ''}</span>
                  </div>
                  {status?.vram_used_mb && (
                    <div className="service-item">
                      <span className="service-label">显存</span>
                      <span className="service-value">
                        {Math.round(status.vram_used_mb / 1024)}/{Math.round((status.vram_total_mb || 12226) / 1024)} GB
                      </span>
                    </div>
                  )}
                </div>
                <div className="settings-service-actions">
                  <button className="btn-sm" onClick={refreshServiceStatus}>🔄 刷新</button>
                </div>
              </section>

              {/* ── ② 模型路由层 ── */}
              <section className="settings-section">
                <h3 className="settings-section-title">② 模型路由参数</h3>
                <p className="settings-section-desc">每个路由独立设置 Temperature / Max Tokens / Repeat Penalty，变更即刻生效</p>

                <div className="settings-routing-table">
                  <div className="routing-header">
                    <span className="rth-route">路由</span>
                    <span className="rth-model">模型</span>
                    <span className="rth-temp">温度</span>
                    <span className="rth-tokens">最大 Token</span>
                    <span className="rth-penalty">重复惩罚</span>
                  </div>
                  {ROUTE_ORDER.map(key => {
                    const cfg = routing[key];
                    if (!cfg) return null;
                    const edit = editedRoutes[key];
                    return (
                      <div key={key} className="routing-row">
                        <span className="rth-route rv-label">{ROUTE_LABELS[key] || key}</span>
                        <span className="rth-model rv-model">{cfg.provider === 'local' ? '💻' : '☁️'} {cfg.model}</span>
                        <span className="rth-temp">
                          <input
                            type="number"
                            className="setting-input"
                            step="0.05"
                            min="0"
                            max="2"
                            value={edit?.temperature ?? cfg.temperature}
                            onChange={e => handleEdit(key, 'temperature', parseFloat(e.target.value) || 0)}
                          />
                        </span>
                        <span className="rth-tokens">
                          <input
                            type="number"
                            className="setting-input"
                            step="128"
                            min="128"
                            max="32768"
                            value={edit?.max_tokens ?? cfg.max_tokens}
                            onChange={e => handleEdit(key, 'max_tokens', parseInt(e.target.value) || 4096)}
                          />
                        </span>
                        <span className="rth-penalty">
                          <input
                            type="number"
                            className="setting-input"
                            step="0.05"
                            min="1.0"
                            max="2.0"
                            value={edit?.repeat_penalty ?? cfg.repeat_penalty}
                            onChange={e => handleEdit(key, 'repeat_penalty', parseFloat(e.target.value) || 1.0)}
                          />
                        </span>
                      </div>
                    );
                  })}
                </div>

                {dirty && (
                  <div className="settings-actions">
                    <button className="btn-primary" onClick={handleSave} disabled={saving}>
                      {saving ? '💾 保存中…' : '💾 保存更改'}
                    </button>
                    <button className="btn-sm" onClick={handleReset}>↩ 撤销</button>
                  </div>
                )}
              </section>

              {/* ── ③ 人设/能力层 ── */}
              <section className="settings-section">
                <h3 className="settings-section-title">③ 系统人设 <span className="badge-locked">🔒 预览</span></h3>
                <div className="settings-prompts">
                  <div className="prompt-card">
                    <div className="prompt-card-header">
                      <span className="prompt-route-label">频道人设</span>
                      <span className="badge-locked">暂不可编辑</span>
                    </div>
                    <pre className="prompt-content">{settingsData?.system_prompts?.channel || '-'}</pre>
                  </div>
                  <div className="prompt-card">
                    <div className="prompt-card-header">
                      <span className="prompt-route-label">场景人设</span>
                      <span className="badge-locked">暂不可编辑</span>
                    </div>
                    <pre className="prompt-content">{settingsData?.system_prompts?.scene || '-'}</pre>
                  </div>
                </div>
              </section>

              {/* ── 特性开关 ── */}
              <section className="settings-section">
                <h3 className="settings-section-title">④ 特性开关 <span className="badge-locked">🔒 预留</span></h3>
                <div className="settings-features">
                  <div className="feature-item disabled">
                    <span>PDF as Image</span>
                    <span className="feature-toggle off">OFF</span>
                  </div>
                  <div className="feature-item disabled">
                    <span>Vision（多模态）</span>
                    <span className="feature-toggle off">OFF</span>
                  </div>
                </div>
                <p className="settings-hint">功能开发中，未来版本解锁</p>
              </section>
            </>
          )}
        </div>
      </div>
    </>
  );
}
