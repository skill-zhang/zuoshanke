/** ⚙ 系统设置 — 全屏页面（4 Tab：Provider/路由/人设/服务） */
import { useEffect, useState, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import {
  SettingsData, ServiceStatus, RouteConfig,
  listProviders, createProvider, updateProvider, deleteProvider,
  createModel, updateModel, deleteModel,
  getSettings, updateSettings, getServiceStatus,
  AiProviderData, AiModelData,
} from '../api/client';
import { showPrompt, showConfirm, showAlert } from '../stores/dialogStore';

const ROUTE_LABELS: Record<string, string> = {
  channel: '💬 频道闲聊',
  scene: '🔧 场景分析',
  extraction: '🔗 约束提取',
  medium: '⚖️ Medium',
  heavy: '🏋️ Heavy',
};
const ROUTE_ORDER = ['channel', 'scene', 'extraction', 'medium', 'heavy'];

const TABS = [
  { key: 'providers', label: '☁ Provider 管理' },
  { key: 'routing', label: '🔀 路由配置' },
  { key: 'prompts', label: '📝 系统人设' },
  { key: 'service', label: '💻 服务状态' },
];

function maskKey(key: string) {
  if (!key || key.length <= 8) return '********';
  return key.slice(0, 4) + '****' + key.slice(-4);
}

export function SettingsView() {
  const { setView, settingsLoading } = useStore();

  const [activeTab, setActiveTab] = useState('providers');

  // Provider state
  const [providers, setProviders] = useState<AiProviderData[]>([]);
  const [providersLoading, setProvidersLoading] = useState(false);

  // Settings state
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [settingsLoadingData, setSettingsLoadingData] = useState(false);

  // Service status
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);

  // Provider edit modal
  const [provModalOpen, setProvModalOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<AiProviderData | null>(null);
  const [provForm, setProvForm] = useState({ name: '', base_url: '', api_key: '', provider_type: 'openai-compatible' });
  const [provSaving, setProvSaving] = useState(false);

  // Model edit modal
  const [modelModalOpen, setModelModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<{ providerId: string; model: AiModelData | null }>({ providerId: '', model: null });
  const [modelForm, setModelForm] = useState({
    name: '', display_name: '', temperature: 0.7, max_tokens: 8192,
    context_length: 32768, repeat_penalty: 1.05, vision: false, function_calling: true,
  });
  const [modelSaving, setModelSaving] = useState(false);

  // Route editing
  const [editedRoutes, setEditedRoutes] = useState<Record<string, Partial<RouteConfig>>>({});
  const [routeSaving, setRouteSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Prompt editing
  const [editedCP, setEditedCP] = useState<string | undefined>();
  const [editedSP, setEditedSP] = useState<string | undefined>();
  const [promptSaving, setPromptSaving] = useState(false);

  // ── Load data ──
  const loadProviders = useCallback(async () => {
    setProvidersLoading(true);
    try {
      const r = await listProviders();
      setProviders(r.providers);
    } catch { /* ignore */ }
    setProvidersLoading(false);
  }, []);

  const loadSettingsData = useCallback(async () => {
    setSettingsLoadingData(true);
    try {
      const s = await getSettings();
      setSettings(s);
    } catch { /* ignore */ }
    setSettingsLoadingData(false);
  }, []);

  const loadServiceStatus = useCallback(async () => {
    try {
      setServiceStatus(await getServiceStatus());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (settingsLoading) return;
    if (activeTab === 'providers') loadProviders();
    else if (activeTab === 'routing' || activeTab === 'prompts') loadSettingsData();
    else if (activeTab === 'service') loadServiceStatus();
  }, [activeTab, settingsLoading]);

  // ── Provider CRUD ──
  const openCreateProvider = () => {
    setEditingProvider(null);
    setProvForm({ name: '', base_url: '', api_key: '', provider_type: 'openai-compatible' });
    setProvModalOpen(true);
  };
  const openEditProvider = (p: AiProviderData) => {
    setEditingProvider(p);
    setProvForm({ name: p.name, base_url: p.base_url, api_key: p.api_key || '', provider_type: p.provider_type });
    setProvModalOpen(true);
  };
  const handleSaveProvider = async () => {
    if (!provForm.name.trim() || !provForm.base_url.trim()) return;
    setProvSaving(true);
    try {
      if (editingProvider) {
        await updateProvider(editingProvider.id, provForm);
      } else {
        await createProvider(provForm);
      }
      setProvModalOpen(false);
      await loadProviders();
    } catch (e: any) { showAlert('操作失败: ' + (e.message || '')); }
    setProvSaving(false);
  };
  const handleDeleteProvider = async (p: AiProviderData) => {
    if (p.models.length > 0) {
      if (!await showConfirm(`「${p.name}」下有 ${p.models.length} 个模型，确认级联删除全部？`)) return;
    } else {
      if (!await showConfirm(`确认删除 Provider「${p.name}」？`)) return;
    }
    try {
      await deleteProvider(p.id);
      await loadProviders();
    } catch (e: any) { showAlert('删除失败: ' + (e.message || '')); }
  };

  // ── Model CRUD ──
  const openCreateModel = (providerId: string) => {
    setEditingModel({ providerId, model: null });
    setModelForm({ name: '', display_name: '', temperature: 0.7, max_tokens: 8192,
      context_length: 32768, repeat_penalty: 1.05, vision: false, function_calling: true });
    setModelModalOpen(true);
  };
  const openEditModel = (providerId: string, m: AiModelData) => {
    setEditingModel({ providerId, model: m });
    setModelForm({
      name: m.name, display_name: m.display_name || '', temperature: m.temperature,
      max_tokens: m.max_tokens, context_length: m.context_length, repeat_penalty: m.repeat_penalty,
      vision: m.vision, function_calling: m.function_calling,
    });
    setModelModalOpen(true);
  };
  const handleSaveModel = async () => {
    if (!modelForm.name.trim()) return;
    setModelSaving(true);
    try {
      if (editingModel.model) {
        await updateModel(editingModel.providerId, editingModel.model.id, modelForm);
      } else {
        await createModel(editingModel.providerId, modelForm);
      }
      setModelModalOpen(false);
      await loadProviders();
    } catch (e: any) { showAlert('操作失败: ' + (e.message || '')); }
    setModelSaving(false);
  };
  const handleDeleteModel = async (providerId: string, m: AiModelData) => {
    if (!await showConfirm(`确认删除模型「${m.name}」？`)) return;
    try {
      await deleteModel(providerId, m.id);
      await loadProviders();
    } catch (e: any) { showAlert('删除失败: ' + (e.message || '')); }
  };

  // ── Route editing ──
  const handleRouteEdit = (key: string, field: string, value: any) => {
    setEditedRoutes(prev => ({ ...prev, [key]: { ...(prev[key] || {}), [field]: value } }));
    setDirty(true);
  };
  const handleRouteSave = async () => {
    setRouteSaving(true);
    try {
      const routing: Record<string, any> = {};
      for (const [key, edit] of Object.entries(editedRoutes)) {
        if (Object.keys(edit).length > 0) routing[key] = edit;
      }
      if (Object.keys(routing).length > 0) {
        const updated = await updateSettings({ routing });
        setSettings(updated);
      }
      setEditedRoutes({});
      setDirty(false);
    } catch (e: any) { showAlert('保存失败: ' + (e.message || '')); }
    setRouteSaving(false);
  };
  const handleRouteReset = () => {
    setEditedRoutes({});
    setDirty(false);
  };

  // ── Prompt editing ──
  const handlePromptSave = async () => {
    setPromptSaving(true);
    try {
      const sp: Record<string, string> = {};
      if (editedCP !== undefined) sp.channel = editedCP.trim();
      if (editedSP !== undefined) sp.scene = editedSP.trim();
      if (Object.keys(sp).length > 0) {
        const updated = await updateSettings({ system_prompts: sp });
        setSettings(updated);
      }
      setEditedCP(undefined);
      setEditedSP(undefined);
    } catch (e: any) { showAlert('保存失败: ' + (e.message || '')); }
    setPromptSaving(false);
  };

  // ── Helpers ──
  const findProviderName = (pid?: string) =>
    providers.find(p => p.id === pid)?.name || pid || '-';
  const findModelName = (pid?: string, mid?: string) => {
    const p = providers.find(pp => pp.id === pid);
    return p?.models.find(m => m.id === mid)?.name || mid || '-';
  };

  return (
    <div className="settings-view">
      {/* ═══ Header ═══ */}
      <div className="sv-header">
        <span className="sv-title">⚙ 系统设置</span>
      </div>

      {/* ═══ Tabs ═══ */}
      <div className="sv-tabs">
        {TABS.map(t => (
          <div
            key={t.key}
            className={`sv-tab${activeTab === t.key ? ' active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >{t.label}</div>
        ))}
      </div>

      {/* ═══ Tab: Provider 管理 ═══ */}
      {activeTab === 'providers' && (
        <div className="sv-tab-content">
          <div className="sv-desc-row">
            <span className="sv-desc">管理 AI Provider 的连接信息和模型列表</span>
            <button className="btn-primary btn-sm" onClick={openCreateProvider}>+ 添加 Provider</button>
          </div>

          {providersLoading ? (
            <div className="sv-loading">加载中…</div>
          ) : providers.length === 0 ? (
            <div className="sv-empty">暂无 Provider，点击上方按钮添加</div>
          ) : (
            <div className="sv-providers-list">
              {providers.map(p => (
                <div key={p.id} className="sv-provider-card">
                  <div className="sv-provider-header">
                    <div className="sv-provider-info">
                      <span className="sv-provider-name">{p.name}</span>
                      <span className="sv-provider-type">{p.provider_type === 'local' ? '💻 本地' : '☁️ 云端'}</span>
                      {p.is_active ? <span className="badge-green">活跃</span> : <span className="badge-gray">禁用</span>}
                    </div>
                    <div className="sv-provider-actions">
                      <button className="btn-ghost btn-xs" onClick={() => openEditProvider(p)}>✏️</button>
                      <button className="btn-ghost btn-xs" onClick={() => handleDeleteProvider(p)}>🗑️</button>
                    </div>
                  </div>
                  <div className="sv-provider-detail">
                    <span className="sv-detail-item"><span className="sv-detail-label">Base URL</span> {p.base_url}</span>
                    <span className="sv-detail-item"><span className="sv-detail-label">API Key</span> {maskKey(p.api_key)}</span>
                  </div>

                  {/* Models under this provider */}
                  <div className="sv-models-section">
                    <div className="sv-models-header">
                      <span className="sv-models-count">模型 ({p.models.length})</span>
                      <button className="btn-ghost btn-xs" onClick={() => openCreateModel(p.id)}>+ 添加</button>
                    </div>
                    {p.models.length === 0 ? (
                      <div className="sv-models-empty">暂无模型</div>
                    ) : (
                      <div className="sv-models-list">
                        {p.models.map(m => (
                          <div key={m.id} className="sv-model-row">
                            <span className="sv-model-name">{m.display_name || m.name}</span>
                            <span className="sv-model-caps">
                              {m.vision && <span className="cap-tag">🖼️</span>}
                              {m.function_calling && <span className="cap-tag">🔧</span>}
                            </span>
                            <span className="sv-model-params">T={m.temperature} · ctx={m.context_length}</span>
                            <div className="sv-model-actions">
                              <button className="btn-ghost btn-xs" onClick={() => openEditModel(p.id, m)}>✏️</button>
                              <button className="btn-ghost btn-xs" onClick={() => handleDeleteModel(p.id, m)}>🗑️</button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ═══ Tab: 路由配置 ═══ */}
      {activeTab === 'routing' && (
        <div className="sv-tab-content">
          <div className="sv-desc-row">
            <span className="sv-desc">每个路由选择 Provider + 模型，可覆盖默认参数</span>
            {dirty && (
              <div className="sv-route-actions">
                <button className="btn-primary btn-sm" onClick={handleRouteSave} disabled={routeSaving}>
                  {routeSaving ? '保存中…' : '💾 保存'}
                </button>
                <button className="btn-ghost btn-sm" onClick={handleRouteReset}>↩ 撤销</button>
              </div>
            )}
          </div>

          {settingsLoadingData ? (
            <div className="sv-loading">加载中…</div>
          ) : !settings ? (
            <div className="sv-empty">无法加载设置</div>
          ) : (
            <div className="sv-routing-table">
              <div className="sv-rth">
                <span className="sv-rth-route">路由</span>
                <span className="sv-rth-provider">Provider</span>
                <span className="sv-rth-model">模型</span>
                <span className="sv-rth-temp">温度</span>
                <span className="sv-rth-tokens">Max Tokens</span>
                <span className="sv-rth-penalty">惩罚</span>
              </div>
              {ROUTE_ORDER.map(key => {
                const cfg = settings.routing[key];
                if (!cfg) return null;
                const edit = editedRoutes[key] || {};
                const selProvId = edit.provider_id ?? cfg.provider_id ?? '';
                const selProvider = providers.find(p => p.id === selProvId);
                const models = selProvider?.models || [];

                return (
                  <div key={key} className="sv-route-row">
                    <span className="sv-rth-route sv-rv-label">{ROUTE_LABELS[key] || key}</span>

                    <span className="sv-rth-provider">
                      <select
                        className="sv-select"
                        value={selProvId}
                        onChange={e => {
                          const pid = e.target.value;
                          handleRouteEdit(key, 'provider_id', pid);
                          handleRouteEdit(key, 'model_id', '');
                          const p = providers.find(pp => pp.id === pid);
                          handleRouteEdit(key, 'provider', p?.name || '');
                        }}
                      >
                        <option value="">-- 选择 Provider --</option>
                        {providers.filter(p => p.is_active).map(p => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </select>
                    </span>

                    <span className="sv-rth-model">
                      <select
                        className="sv-select"
                        value={edit.model_id ?? cfg.model_id ?? ''}
                        onChange={e => {
                          handleRouteEdit(key, 'model_id', e.target.value);
                          const m = models.find(mm => mm.id === e.target.value);
                          if (m) {
                            handleRouteEdit(key, 'model', m.name);
                          }
                        }}
                      >
                        <option value="">-- 选择模型 --</option>
                        {models.map(m => (
                          <option key={m.id} value={m.id}>
                            {m.display_name || m.name}
                          </option>
                        ))}
                      </select>
                    </span>

                    <span className="sv-rth-temp">
                      <input type="number" className="sv-input" step="0.05" min="0" max="2"
                        value={edit.temperature ?? cfg.temperature}
                        onChange={e => handleRouteEdit(key, 'temperature', parseFloat(e.target.value) || 0)} />
                    </span>

                    <span className="sv-rth-tokens">
                      <input type="number" className="sv-input" step="128" min="128" max="131072"
                        value={edit.max_tokens ?? cfg.max_tokens}
                        onChange={e => handleRouteEdit(key, 'max_tokens', parseInt(e.target.value) || 4096)} />
                    </span>

                    <span className="sv-rth-penalty">
                      <input type="number" className="sv-input" step="0.05" min="1.0" max="2.0"
                        value={edit.repeat_penalty ?? cfg.repeat_penalty}
                        onChange={e => handleRouteEdit(key, 'repeat_penalty', parseFloat(e.target.value) || 1.0)} />
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ═══ Tab: 系统人设 ═══ */}
      {activeTab === 'prompts' && (
        <div className="sv-tab-content">
          <div className="sv-desc-row">
            <span className="sv-desc">配置频道和场景的系统人设提示词</span>
          </div>

          {settingsLoadingData ? (
            <div className="sv-loading">加载中…</div>
          ) : !settings ? (
            <div className="sv-empty">无法加载设置</div>
          ) : (
            <div className="sv-prompts-area">
              <div className="sv-prompt-card">
                <div className="sv-prompt-header">
                  <span className="sv-prompt-label">💬 频道人设</span>
                </div>
                <textarea className="sv-prompt-textarea"
                  value={editedCP ?? settings.system_prompts.channel}
                  onChange={e => setEditedCP(e.target.value)}
                  rows={4} />
              </div>

              <div className="sv-prompt-card">
                <div className="sv-prompt-header">
                  <span className="sv-prompt-label">🔧 场景人设</span>
                </div>
                <textarea className="sv-prompt-textarea"
                  value={editedSP ?? settings.system_prompts.scene}
                  onChange={e => setEditedSP(e.target.value)}
                  rows={4} />
              </div>

              {(editedCP !== undefined || editedSP !== undefined) && (
                <div className="sv-route-actions" style={{ marginTop: 12 }}>
                  <button className="btn-primary btn-sm" onClick={handlePromptSave} disabled={promptSaving}>
                    {promptSaving ? '保存中…' : '💾 保存人设'}
                  </button>
                  <button className="btn-ghost btn-sm" onClick={() => { setEditedCP(undefined); setEditedSP(undefined); }}>
                    ↩ 撤销
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ═══ Tab: 服务状态 ═══ */}
      {activeTab === 'service' && (
        <div className="sv-tab-content">
          <div className="sv-desc-row">
            <span className="sv-desc">查看后端服务运行状态</span>
            <button className="btn-ghost btn-sm" onClick={loadServiceStatus}>🔄 刷新</button>
          </div>

          <div className="sv-service-grid">
            <div className="sv-service-card">
              <span className="sv-service-label">llama-server</span>
              <span className={`sv-service-value ${serviceStatus?.llama_server === 'running' ? 'status-ok' : 'status-err'}`}>
                {serviceStatus?.llama_server === 'running' ? '✅ 运行中' : serviceStatus?.llama_server === 'error' ? '⚠ 异常' : '⛔ 已停止'}
              </span>
            </div>
            <div className="sv-service-card">
              <span className="sv-service-label">端口</span>
              <span className="sv-service-value">{serviceStatus?.port || 8083}</span>
            </div>
            <div className="sv-service-card">
              <span className="sv-service-label">模型</span>
              <span className="sv-service-value">{serviceStatus?.model_name || '-'}</span>
            </div>
            <div className="sv-service-card">
              <span className="sv-service-label">上下文</span>
              <span className="sv-service-value">{serviceStatus?.context_size || '-'} ctx</span>
            </div>
            <div className="sv-service-card">
              <span className="sv-service-label">Flash Attention</span>
              <span className="sv-service-value">{serviceStatus?.flash_attention || 'auto'}</span>
            </div>
            <div className="sv-service-card">
              <span className="sv-service-label">插槽</span>
              <span className="sv-service-value">{serviceStatus?.slots || 0} 个{serviceStatus?.processing ? ' · 处理中' : ''}</span>
            </div>
            {serviceStatus?.vram_used_mb && (
              <div className="sv-service-card">
                <span className="sv-service-label">显存</span>
                <span className="sv-service-value">
                  {Math.round(serviceStatus.vram_used_mb / 1024)}/{Math.round((serviceStatus.vram_total_mb || 12226) / 1024)} GB
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ═══ Provider 编辑弹窗 ═══ */}
      <div className={`modal-overlay${provModalOpen ? ' show' : ''}`} onClick={() => !provSaving && setProvModalOpen(false)}>
        <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            {editingProvider ? '✏️ 编辑 Provider' : '➕ 添加 Provider'}
            <button className="modal-close" onClick={() => !provSaving && setProvModalOpen(false)}>✕</button>
          </div>
          <div className="form-group">
            <label className="form-label">名称</label>
            <input className="form-input" value={provForm.name}
              onChange={e => setProvForm(f => ({ ...f, name: e.target.value }))}
              placeholder="DeepSeek" autoFocus />
          </div>
          <div className="form-group">
            <label className="form-label">Base URL</label>
            <input className="form-input" value={provForm.base_url}
              onChange={e => setProvForm(f => ({ ...f, base_url: e.target.value }))}
              placeholder="https://api.deepseek.com" />
          </div>
          <div className="form-group">
            <label className="form-label">API Key</label>
            <input className="form-input" value={provForm.api_key}
              onChange={e => setProvForm(f => ({ ...f, api_key: e.target.value }))}
              placeholder="sk-..." type="password" />
          </div>
          <div className="form-group">
            <label className="form-label">类型</label>
            <select className="sv-select" value={provForm.provider_type}
              onChange={e => setProvForm(f => ({ ...f, provider_type: e.target.value }))}>
              <option value="openai-compatible">☁️ 云端 (OpenAI 兼容)</option>
              <option value="local">💻 本地 (llama-server)</option>
            </select>
          </div>
          <div className="modal-actions">
            <button className="btn" onClick={() => setProvModalOpen(false)} disabled={provSaving}>取消</button>
            <button className="btn-primary" onClick={handleSaveProvider} disabled={provSaving || !provForm.name.trim() || !provForm.base_url.trim()}>
              {provSaving ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      </div>

      {/* ═══ Model 编辑弹窗 ═══ */}
      <div className={`modal-overlay${modelModalOpen ? ' show' : ''}`} onClick={() => !modelSaving && setModelModalOpen(false)}>
        <div className="modal modal-md" onClick={e => e.stopPropagation()}>
          <div className="modal-title">
            {editingModel.model ? '✏️ 编辑模型' : '➕ 添加模型'}
            <button className="modal-close" onClick={() => !modelSaving && setModelModalOpen(false)}>✕</button>
          </div>
          <div className="sv-modal-grid">
            <div className="form-group">
              <label className="form-label">模型名称</label>
              <input className="form-input" value={modelForm.name}
                onChange={e => setModelForm(f => ({ ...f, name: e.target.value }))}
                placeholder="deepseek-v4-flash" />
            </div>
            <div className="form-group">
              <label className="form-label">显示名称</label>
              <input className="form-input" value={modelForm.display_name}
                onChange={e => setModelForm(f => ({ ...f, display_name: e.target.value }))}
                placeholder="DeepSeek v4 Flash" />
            </div>
            <div className="form-group">
              <label className="form-label">Temperature</label>
              <input className="form-input" type="number" step="0.05" min="0" max="2"
                value={modelForm.temperature}
                onChange={e => setModelForm(f => ({ ...f, temperature: parseFloat(e.target.value) || 0 }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Max Tokens</label>
              <input className="form-input" type="number" step="128" min="128" max="131072"
                value={modelForm.max_tokens}
                onChange={e => setModelForm(f => ({ ...f, max_tokens: parseInt(e.target.value) || 4096 }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Context Length</label>
              <input className="form-input" type="number" step="1024" min="1024" max="2097152"
                value={modelForm.context_length}
                onChange={e => setModelForm(f => ({ ...f, context_length: parseInt(e.target.value) || 32768 }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Repeat Penalty</label>
              <input className="form-input" type="number" step="0.05" min="1.0" max="2.0"
                value={modelForm.repeat_penalty}
                onChange={e => setModelForm(f => ({ ...f, repeat_penalty: parseFloat(e.target.value) || 1.0 }))} />
            </div>
            <div className="form-group form-check-row">
              <label className="form-label">Vision</label>
              <label className="sv-toggle">
                <input type="checkbox" checked={modelForm.vision}
                  onChange={e => setModelForm(f => ({ ...f, vision: e.target.checked }))} />
                <span className="sv-toggle-slider"></span>
              </label>
            </div>
            <div className="form-group form-check-row">
              <label className="form-label">Function Calling</label>
              <label className="sv-toggle">
                <input type="checkbox" checked={modelForm.function_calling}
                  onChange={e => setModelForm(f => ({ ...f, function_calling: e.target.checked }))} />
                <span className="sv-toggle-slider"></span>
              </label>
            </div>
          </div>
          <div className="modal-actions">
            <button className="btn" onClick={() => setModelModalOpen(false)} disabled={modelSaving}>取消</button>
            <button className="btn-primary" onClick={handleSaveModel} disabled={modelSaving || !modelForm.name.trim()}>
              {modelSaving ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
