/** ⚙ 系统设置 — 全屏页面（严格对齐原型 prototype-settings-v2.html） */
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
  { key: 'general', label: '⚙ 通用配置' },
];

function maskKey(key: string) {
  if (!key || key.length <= 4) return '****';
  // Show first 3 + last 4: "sk-****T3Bl"
  const prefix = key.slice(0, 3);
  const suffix = key.slice(-4);
  return `${prefix}********${suffix}`;
}

/** Provider icon */
function providerIcon(type: string, name: string): string {
  if (type === 'local') return '💻';
  if (name.includes('DeepSeek')) return '☁';
  if (name.includes('OpenAI')) return '🟢';
  return '☁';
}

export function SettingsView() {
  const { setView } = useStore();

  // ── State ──
  const [activeTab, setActiveTab] = useState('providers');
  const [providers, setProviders] = useState<AiProviderData[]>([]);
  const [providersLoading, setProvidersLoading] = useState(false);
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);

  // Provider modal
  const [provModal, setProvModal] = useState(false);
  const [editProv, setEditProv] = useState<AiProviderData | null>(null);
  const [provForm, setProvForm] = useState({ name: '', base_url: '', api_key: '', provider_type: 'openai-compatible' });
  const [provSaving, setProvSaving] = useState(false);

  // Model modal
  const [modelModal, setModelModal] = useState(false);
  const [editModel, setEditModel] = useState<{ pid: string; m: AiModelData | null }>({ pid: '', m: null });
  const [modelForm, setModelForm] = useState({ name: '', display_name: '', temperature: 0.7, max_tokens: 8192, context_length: 32768, repeat_penalty: 1.05, vision: false, function_calling: true });
  const [modelSaving, setModelSaving] = useState(false);

  // Route editing
  const [editedRoutes, setEditedRoutes] = useState<Record<string, Partial<RouteConfig>>>({});
  const [dirty, setDirty] = useState(false);
  const [routeSaving, setRouteSaving] = useState(false);
  const [expandedRoutes, setExpandedRoutes] = useState<Set<string>>(new Set(['channel']));

  // Prompts
  const [editedCP, setEditedCP] = useState<string | undefined>();
  const [editedSP, setEditedSP] = useState<string | undefined>();
  const [promptSaving, setPromptSaving] = useState(false);
  const [expandedStatus, setExpandedStatus] = useState<string | null>(null);
  // ── Features / 通用配置 ──
  const [featuresEdit, setFeaturesEdit] = useState<{ message_load_count: number } | null>(null);
  const [featuresSaving, setFeaturesSaving] = useState(false);
  // ── Inline API Key editing ──
  const [editingApiKeys, setEditingApiKeys] = useState<Record<string, string>>({});
  const startEditApiKey = (pid: string, currentKey: string) => {
    setEditingApiKeys(prev => ({ ...prev, [pid]: currentKey || '' }));
  };
  const cancelEditApiKey = (pid: string) => {
    setEditingApiKeys(prev => { const n = { ...prev }; delete n[pid]; return n; });
  };
  const saveApiKey = async (pid: string) => {
    const newKey = editingApiKeys[pid]?.trim();
    if (newKey === undefined) return;
    try {
      await updateProvider(pid, { api_key: newKey });
      setProviders(prev => prev.map(p => p.id === pid ? { ...p, api_key: newKey } : p));
      cancelEditApiKey(pid);
    } catch (e) { showAlert('保存失败'); }
  };

  // ── Load ──
  const loadP = useCallback(async () => {
    setProvidersLoading(true);
    try { setProviders((await listProviders()).providers); } catch {}
    setProvidersLoading(false);
  }, []);
  const loadS = useCallback(async () => {
    setSettingsLoading(true);
    try { setSettings(await getSettings()); } catch {}
    setSettingsLoading(false);
  }, []);
  const loadStatus = useCallback(async () => {
    try { setServiceStatus(await getServiceStatus()); } catch {}
  }, []);

  useEffect(() => {
    if (activeTab === 'providers') loadP();
    else if (activeTab === 'routing' || activeTab === 'prompts') loadS();
    else if (activeTab === 'service') loadStatus();
  }, [activeTab]);

  // ── Provider CRUD ──
  const openNewProv = () => { setEditProv(null); setProvForm({ name: '', base_url: '', api_key: '', provider_type: 'openai-compatible' }); setProvModal(true); };
  const openEditProv = (p: AiProviderData) => { setEditProv(p); setProvForm({ name: p.name, base_url: p.base_url, api_key: p.api_key || '', provider_type: p.provider_type }); setProvModal(true); };
  const saveProv = async () => {
    if (!provForm.name.trim() || !provForm.base_url.trim()) return;
    setProvSaving(true);
    try {
      if (editProv) await updateProvider(editProv.id, provForm);
      else await createProvider(provForm);
      setProvModal(false); await loadP();
    } catch (e: any) { showAlert('操作失败: ' + (e.message || '')); }
    setProvSaving(false);
  };
  const delProv = async (p: AiProviderData) => {
    if (!await showConfirm(p.models.length > 0 ? `「${p.name}」下有 ${p.models.length} 个模型，确认级联删除？` : `确认删除「${p.name}」？`)) return;
    try { await deleteProvider(p.id); await loadP(); } catch (e: any) { showAlert('删除失败: ' + (e.message || '')); }
  };

  // ── Model CRUD ──
  const openNewModel = (pid: string) => { setEditModel({ pid, m: null }); setModelForm({ name: '', display_name: '', temperature: 0.7, max_tokens: 8192, context_length: 32768, repeat_penalty: 1.05, vision: false, function_calling: true }); setModelModal(true); };
  const openEditModel = (pid: string, m: AiModelData) => { setEditModel({ pid, m }); setModelForm({ name: m.name, display_name: m.display_name || '', temperature: m.temperature, max_tokens: m.max_tokens, context_length: m.context_length, repeat_penalty: m.repeat_penalty, vision: m.vision, function_calling: m.function_calling }); setModelModal(true); };
  const saveModel = async () => {
    if (!modelForm.name.trim()) return;
    setModelSaving(true);
    try {
      if (editModel.m) await updateModel(editModel.pid, editModel.m.id, modelForm);
      else await createModel(editModel.pid, modelForm);
      setModelModal(false); await loadP();
    } catch (e: any) { showAlert('操作失败: ' + (e.message || '')); }
    setModelSaving(false);
  };
  const delModel = async (pid: string, m: AiModelData) => {
    if (!await showConfirm(`确认删除模型「${m.name}」？`)) return;
    try { await deleteModel(pid, m.id); await loadP(); } catch (e: any) { showAlert('删除失败: ' + (e.message || '')); }
  };

  // ── Route editing ──
  const editRoute = (key: string, field: string, value: any) => {
    setEditedRoutes(p => ({ ...p, [key]: { ...(p[key] || {}), [field]: value } }));
    setDirty(true);
  };
  const saveRoutes = async () => {
    setRouteSaving(true);
    try {
      const routing: Record<string, any> = {};
      for (const [k, v] of Object.entries(editedRoutes)) if (Object.keys(v).length > 0) routing[k] = v;
      if (Object.keys(routing).length > 0) setSettings(await updateSettings({ routing }));
      setEditedRoutes({}); setDirty(false);
    } catch (e: any) { showAlert('保存失败: ' + (e.message || '')); }
    setRouteSaving(false);
  };
  const resetRoutes = () => { setEditedRoutes({}); setDirty(false); };
  const toggleRouteExpand = (key: string) => {
    setExpandedRoutes(p => { const n = new Set(p); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  };

  /** 判断某个字段是否已被用户覆盖（不同于模型默认值） */
  const isCovered = (edit: Record<string, any>, field: string, defaultValue: any) =>
    edit[field] !== undefined && edit[field] !== defaultValue;

  /** 判断风险等级：0=安全 1=中度 2=严重 */
  const getRiskLevel = (val: number, field: string) => {
    if (field === 'temperature') {
      if (val > 1.5) return 2;
      if (val > 1.0) return 1;
      return 0;
    }
    if (field === 'max_tokens') {
      if (val > 131072) return 2;
      if (val > 65536) return 1;
      return 0;
    }
    if (field === 'repeat_penalty') {
      if (val < 0.5 || val > 2.0) return 2;
      if (val < 1.0 || val > 1.5) return 1;
      return 0;
    }
    return 0;
  };

  /** 判断当前路由行是否有任何修改（与模型默认值比） */
  const hasAnyCover = (edit: Record<string, any>, cfg: any, mTemp: number, mTokens: number, mPenalty: number) =>
    isCovered(edit, 'provider_id', cfg.provider_id) ||
    isCovered(edit, 'model_id', cfg.model_id) ||
    isCovered(edit, 'temperature', mTemp) ||
    isCovered(edit, 'max_tokens', mTokens) ||
    isCovered(edit, 'repeat_penalty', mPenalty);

  /** 获取当前行最高风险等级 */
  const getRowMaxRisk = (edit: Record<string, any>, mTemp: number, mTokens: number, mPenalty: number) => {
    const maxRisk = (a: number, b: number) => a > b ? a : b;
    let r = 0;
    r = maxRisk(r, getRiskLevel(edit.temperature ?? mTemp, 'temperature'));
    r = maxRisk(r, getRiskLevel(edit.max_tokens ?? mTokens, 'max_tokens'));
    r = maxRisk(r, getRiskLevel(edit.repeat_penalty ?? mPenalty, 'repeat_penalty'));
    return r;
  };

  // ── Prompts ──
  const [editingCP, setEditingCP] = useState(false);
  const [editingSP, setEditingSP] = useState(false);
  const saveSinglePrompt = async (field: 'channel' | 'scene') => {
    setPromptSaving(true);
    try {
      const sp: Record<string, string> = {};
      if (field === 'channel' && editedCP !== undefined) sp.channel = editedCP.trim();
      if (field === 'scene' && editedSP !== undefined) sp.scene = editedSP.trim();
      await updateSettings({ system_prompts: sp });
      setSettings(s => s ? { ...s, system_prompts: { ...s.system_prompts, ...sp } } : s);
      if (field === 'channel') setEditingCP(false);
      else setEditingSP(false);
    } catch (e) { showAlert('保存失败'); }
    finally { setPromptSaving(false); }
  };
  const resetPrompt = async (field: 'channel' | 'scene') => {
    const defaults: Record<string, string> = {
      channel: '你是坐山客（Zuoshanke），以广博学识和理性思维为用户提供帮助。用Markdown格式回复，风格：专业、有洞察力，像一位见多识广的科技顾问。',
      scene: '你是坐山客在某个领域的专业分身，是用户的AI工作伙伴。你可以调用工具获取实时信息（搜索、代码执行、文件操作等），也可以直接回答用户的问题。',
    };
    if (field === 'channel') { setEditedCP(defaults.channel); }
    else { setEditedSP(defaults.scene); }
  };

  // ── Features ──
  const saveFeatures = async () => {
    if (!featuresEdit || !settings) return;
    setFeaturesSaving(true);
    try {
      const updated = await updateSettings({ features: featuresEdit });
      setSettings(updated);
      setFeaturesEdit(null);
    } catch (e) { showAlert('保存失败'); }
    finally { setFeaturesSaving(false); }
  };

  // ── Render ──
  return (
    <div className="settings-view">
      <div className="sv-container">
        {/* Header */}
        <div className="sv-header">
        <div className="sv-title">⚙ 系统设置</div>
        <div className="sv-tabs">
          {TABS.map(t => (
            <div key={t.key} className={`sv-tab${activeTab === t.key ? ' active' : ''}`} onClick={() => setActiveTab(t.key)}>
              {t.label}
            </div>
          ))}
        </div>
      </div>

      {/* Body */}
      <div className="sv-body">

        {/* ═══ Tab 1: Provider ═══ */}
        {activeTab === 'providers' && (
          <div className="sv-tab-panel">
            <div className="sv-desc-row">
              <span className="sv-desc">管理 AI Provider 的连接信息。Provider 负责模型调用，每个 Provider 可以关联多个模型。</span>
              <button className="btn btn-sm btn-primary" onClick={openNewProv}>+ 添加 Provider</button>
            </div>

            {providersLoading ? (
              <div className="sv-loading">加载中…</div>
            ) : providers.length === 0 ? (
              <div className="sv-empty">暂无 Provider</div>
            ) : (
              providers.map(p => (
                <div key={p.id} className="sv-provider-card">
                  <div className="sv-provider-header" onClick={() => {}}>
                    <span className="sv-provider-icon">{providerIcon(p.provider_type, p.name)}</span>
                    <span className="sv-provider-name">{p.name}</span>
                    <span className="sv-provider-type-badge">{p.provider_type === 'local' ? '本地' : 'OpenAI 兼容'}</span>
                    {p.provider_type === 'local' && <span className="sv-provider-badge">本地</span>}
                    <span className="sv-provider-actions">
                      <span className="btn btn-sm btn-ghost" onClick={() => openEditProv(p)}>✏️</span>
                      <span className="btn btn-sm btn-ghost" onClick={() => delProv(p)}>🗑️</span>
                    </span>
                  </div>
                  <div className="sv-provider-body">
                    <div className="sv-provider-url-row">
                      <span>🌐 Base URL</span>
                      <span className="sv-provider-url">{p.base_url}</span>
                    </div>
                    <div className="sv-provider-url-row">
                      <span>🔑 API Key</span>
                      {editingApiKeys[p.id] !== undefined ? (
                        <>
                          <input className="sv-api-key-input" value={editingApiKeys[p.id]} onChange={e => setEditingApiKeys(prev => ({ ...prev, [p.id]: e.target.value }))} placeholder="输入新的 API Key" type="password" autoFocus />
                          <span className="btn btn-sm btn-primary" style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => saveApiKey(p.id)}>保存</span>
                          <span className="btn btn-sm btn-ghost" style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => cancelEditApiKey(p.id)}>取消</span>
                        </>
                      ) : (
                        <>
                          <span className="sv-provider-api-key">{p.api_key ? maskKey(p.api_key) : <span className="sv-no-key">（无需 API Key）</span>}</span>
                          {p.api_key && <span className="btn btn-sm btn-ghost" style={{ padding: '2px 6px', fontSize: 12 }} onClick={() => startEditApiKey(p.id, p.api_key!)}>更换</span>}
                        </>
                      )}
                    </div>
                    <div className="sv-provider-models-section">
                      <div className="sv-provider-models-title">
                        <span>支持的模型 <span className="sv-model-count-note">（{p.models.length}）</span></span>
                        <span className="btn btn-sm btn-ghost" onClick={() => openNewModel(p.id)}>+ 添加模型</span>
                      </div>
                      <div>
                        {p.models.map(m => (
                          <span key={m.id} className="sv-model-tag">
                            <span className="sv-model-tag-name">{m.display_name || m.name}</span>
                            <span className="sv-model-tag-params">· {m.context_length >= 1000000 ? `${Math.round(m.context_length/10000)/100}M` : m.context_length >= 1000 ? `${Math.round(m.context_length/1000)}K` : m.context_length} ctx · {m.temperature}T · {m.max_tokens >= 1000 ? `${Math.round(m.max_tokens/1000)}K` : m.max_tokens} tok</span>
                            <span className="sv-cap-divider">|</span>
                            <span className="sv-model-tag-cap">{m.vision ? '🖼 ' : ''}{m.function_calling ? '🔧' : ''}</span>
                            <span className="sv-model-tag-actions">
                              <span onClick={() => openEditModel(p.id, m)}>✏️</span>
                              <span onClick={() => delModel(p.id, m)}>🗑️</span>
                            </span>
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}

            {/* Dashed add area */}
            <div className="sv-add-provider-area" onClick={openNewProv}>
              <div className="sv-add-icon">+</div>
              <div className="sv-add-text">添加 Provider</div>
            </div>
          </div>
        )}

        {/* ═══ Tab 2: 路由配置 ═══ */}
        {activeTab === 'routing' && (
          <div className="sv-tab-panel">
            <div className="sv-desc-row" style={{ marginBottom: 12 }}>
              <span className="sv-desc">每个路由指定使用的 Provider 和模型。参数默认跟随模型自身的默认值，覆盖会蓝色高亮。展开行可配置能力开关。</span>
            </div>

            {settingsLoading ? (
              <div className="sv-loading">加载中…</div>
            ) : !settings ? (
              <div className="sv-empty">无法加载设置</div>
            ) : (
              <div className="sv-route-table">
                <div className="sv-route-header">
                  <span></span>
                  <span>路由</span>
                  <span>Provider</span>
                  <span>模型</span>
                  <span>温度</span>
                  <span>最大 Token</span>
                  <span>惩罚</span>
                  <span>能力</span>
                </div>

                {ROUTE_ORDER.map(key => {
                  const cfg = settings.routing[key];
                  if (!cfg) return null;
                  const edit = editedRoutes[key] || {};
                  const selPid = edit.provider_id ?? cfg.provider_id ?? '';
                  const selP = providers.find(pp => pp.id === selPid);
                  const models = selP?.models || [];
                  const selModel = models.find(m => m.id === (edit.model_id ?? cfg.model_id));
                  const isExpanded = expandedRoutes.has(key);

                  const modelTemp = selModel?.temperature ?? cfg.temperature;
                  const modelMaxTokens = selModel?.max_tokens ?? cfg.max_tokens;
                  const modelPenalty = selModel?.repeat_penalty ?? cfg.repeat_penalty;

                  const effectiveDefault = (field: string) => {
                    if (field === 'temperature') return modelTemp;
                    if (field === 'max_tokens') return modelMaxTokens;
                    if (field === 'repeat_penalty') return modelPenalty;
                    return (cfg as any)[field];
                  };

                  const rowRisk = getRowMaxRisk(edit, modelTemp, modelMaxTokens, modelPenalty);
                  const rowDirty = hasAnyCover(edit, cfg, modelTemp, modelMaxTokens, modelPenalty);

                  return (
                    <div key={key} className={`sv-route-row-wrap${rowDirty ? ' dirty' : ''}${rowRisk > 0 ? ' risk-' + rowRisk : ''}`}>
                      <div className="sv-route-row">
                        <span className={`sv-route-expand${isExpanded ? ' open' : ''}`} onClick={() => toggleRouteExpand(key)}>▶</span>
                        <span className="sv-route-label">{ROUTE_LABELS[key] || key}</span>
                        <div className="sv-route-provider-select">
                          <select value={selPid} onChange={e => { const v = e.target.value; editRoute(key, 'provider_id', v); editRoute(key, 'model_id', ''); const pp = providers.find(x => x.id === v); editRoute(key, 'provider', pp?.name || ''); }}>
                            <option value="">-- 选择 --</option>
                            {providers.filter(x => x.is_active).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                          </select>
                        </div>
                        <div className="sv-route-model-select">
                          <select value={edit.model_id ?? cfg.model_id ?? ''} onChange={e => { const v = e.target.value; editRoute(key, 'model_id', v); const mm = models.find(x => x.id === v); if (mm) editRoute(key, 'model', mm.name); }}>
                            <option value="">-- 选择 --</option>
                            {models.map(m => <option key={m.id} value={m.id}>{m.display_name || m.name}</option>)}
                          </select>
                        </div>
                        <div className="sv-route-param">
                          <input className={`sv-param-input${isCovered(edit, 'temperature', modelTemp) && getRiskLevel(edit.temperature ?? modelTemp, 'temperature') === 0 ? ' covered' : ''}${getRiskLevel(edit.temperature ?? modelTemp, 'temperature') === 1 ? ' risk' : ''}${getRiskLevel(edit.temperature ?? modelTemp, 'temperature') === 2 ? ' severe' : ''}`} type="number" value={edit.temperature ?? modelTemp} step="0.05" min="0" max="2" onChange={e => editRoute(key, 'temperature', parseFloat(e.target.value) || 0)} />
                          <span className="sv-param-hint">默认 {modelTemp}</span>
                        </div>
                        <div className="sv-route-param">
                          <input className={`sv-param-input${isCovered(edit, 'max_tokens', modelMaxTokens) && getRiskLevel(edit.max_tokens ?? modelMaxTokens, 'max_tokens') === 0 ? ' covered' : ''}${getRiskLevel(edit.max_tokens ?? modelMaxTokens, 'max_tokens') === 1 ? ' risk' : ''}${getRiskLevel(edit.max_tokens ?? modelMaxTokens, 'max_tokens') === 2 ? ' severe' : ''}`} type="number" value={edit.max_tokens ?? modelMaxTokens} step="128" min="128" max="131072" onChange={e => editRoute(key, 'max_tokens', parseInt(e.target.value) || 4096)} />
                          <span className="sv-param-hint">默认 {modelMaxTokens}</span>
                        </div>
                        <div className="sv-route-param">
                          <input className={`sv-param-input${isCovered(edit, 'repeat_penalty', modelPenalty) && getRiskLevel(edit.repeat_penalty ?? modelPenalty, 'repeat_penalty') === 0 ? ' covered' : ''}${getRiskLevel(edit.repeat_penalty ?? modelPenalty, 'repeat_penalty') === 1 ? ' risk' : ''}${getRiskLevel(edit.repeat_penalty ?? modelPenalty, 'repeat_penalty') === 2 ? ' severe' : ''}`} type="number" value={edit.repeat_penalty ?? modelPenalty} step="0.05" min="1.0" max="2.0" onChange={e => editRoute(key, 'repeat_penalty', parseFloat(e.target.value) || 1.0)} />
                          <span className="sv-param-hint">默认 {modelPenalty}</span>
                        </div>
                        <div className="sv-route-cap" onClick={() => toggleRouteExpand(key)} title="点击展开能力覆盖">
                          {models.find(m => m.id === (edit.model_id ?? cfg.model_id))?.vision ? '🖼 ' : ''}{models.find(m => m.id === (edit.model_id ?? cfg.model_id))?.function_calling ? '🔧' : ''}
                        </div>
                      </div>
                      <div className={`sv-route-detail${isExpanded ? ' open' : ''}`}>
                        <div className="sv-detail-title">⚡ 能力覆盖（可选）</div>
                        <div className="sv-cap-grid">
                          <div className="sv-cap-item">
                            <label className="sv-cap-toggle"><input type="checkbox" defaultChecked /><span className="sv-cap-slider"></span></label>
                            <span>🖼 Vision（来自模型）</span>
                          </div>
                          <div className="sv-cap-item">
                            <label className="sv-cap-toggle"><input type="checkbox" defaultChecked /><span className="sv-cap-slider"></span></label>
                            <span>🔧 Function Calling（来自模型）</span>
                          </div>
                          <div className="sv-cap-item">
                            <label className="sv-cap-toggle"><input type="checkbox" /><span className="sv-cap-slider"></span></label>
                            <span>📤 流式输出</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* 提示色块 */}
            <div className="sv-route-legend">
              🔵 蓝色边框 = 手动覆盖且值安全 · 🟡 金色边框 = 手动覆盖到风险值（温度{'>'}1.0 / max_tokens{'>'}65536 / 惩罚{'<'}1.0或{'>'}1.5） · 🔴 红色边框 = 模型默认值本身就有风险（去 Provider 调整模型参数）<br />
              🖼🔧 能力图标 = 模型自带的视觉/函数调用能力 · 展开行可关闭某些能力（灰色 = 模型不支持，不可开启）
            </div>

            {/* 底部路由操作 */}
            <div className="sv-route-actions" style={{ marginTop: 4 }}>
              <button className="btn btn-sm btn-primary" onClick={saveRoutes} disabled={routeSaving}>{routeSaving ? '保存中…' : '💾 保存路由配置'}</button>
              <button className="btn btn-sm btn-ghost" onClick={resetRoutes}>重置</button>
            </div>
          </div>
        )}

        {/* ═══ Tab 3: 人设 ═══ */}
        {activeTab === 'prompts' && (
          <div className="sv-tab-panel">
            {settingsLoading ? (
              <div className="sv-loading">加载中…</div>
            ) : !settings ? (
              <div className="sv-empty">无法加载设置</div>
            ) : (
              <div className="sv-prompts-area">
                <div className="sv-prompt-card">
                  <div className="sv-prompt-header">
                    <span className="sv-prompt-label">💬 频道人设</span>
                    {!editingCP && <span className="btn btn-sm btn-ghost" onClick={() => setEditingCP(true)}>✏️ 编辑</span>}
                  </div>
                  <textarea className="sv-prompt-textarea" value={editedCP ?? settings.system_prompts.channel}
                    onChange={e => setEditedCP(e.target.value)} rows={4} readOnly={!editingCP} />
                  {editingCP && (
                    <div className="sv-prompt-actions">
                      <span className="btn btn-sm btn-ghost" onClick={() => { setEditingCP(false); setEditedCP(undefined); }}>取消</span>
                      <span className="btn btn-sm btn-ghost" onClick={() => resetPrompt('channel')}>恢复默认</span>
                      <span className="btn btn-sm btn-primary" onClick={() => saveSinglePrompt('channel')} disabled={promptSaving}>{promptSaving ? '保存中…' : '保存'}</span>
                    </div>
                  )}
                </div>
                <div className="sv-prompt-card" style={{ marginTop: 12 }}>
                  <div className="sv-prompt-header">
                    <span className="sv-prompt-label">🔧 场景人设</span>
                    {!editingSP && <span className="btn btn-sm btn-ghost" onClick={() => setEditingSP(true)}>✏️ 编辑</span>}
                  </div>
                  <textarea className="sv-prompt-textarea" value={editedSP ?? settings.system_prompts.scene}
                    onChange={e => setEditedSP(e.target.value)} rows={4} readOnly={!editingSP} />
                  {editingSP && (
                    <div className="sv-prompt-actions">
                      <span className="btn btn-sm btn-ghost" onClick={() => { setEditingSP(false); setEditedSP(undefined); }}>取消</span>
                      <span className="btn btn-sm btn-ghost" onClick={() => resetPrompt('scene')}>恢复默认</span>
                      <span className="btn btn-sm btn-primary" onClick={() => saveSinglePrompt('scene')} disabled={promptSaving}>{promptSaving ? '保存中…' : '保存'}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══ Tab 4: 服务状态 ═══ */}
        {activeTab === 'service' && (
          <div className="sv-tab-panel">
            <div className="sv-status-header-row">
              <span className="sv-desc">系统各服务运行状态概览。</span>
              <span className="btn btn-sm btn-outline" onClick={loadStatus}>🔄 刷新</span>
            </div>

            <div className="sv-status-grid">
              {/* 💻 本地 Qwen */}
              <div className="sv-status-card-wrap">
                <div className="sv-status-card" onClick={() => setExpandedStatus(expandedStatus === 'qwen' ? null : 'qwen')}>
                  <div className="sv-status-card-left">
                    <span className="sv-status-card-name">💻 本地 Qwen</span>
                    <span className="sv-status-card-detail">
                      {serviceStatus?.llama_server === 'running' ? 'llama-server · 端口 ' + (serviceStatus?.port || 8083) :
                       serviceStatus?.llama_server === 'error' ? '服务异常' : '已停止'}
                    </span>
                  </div>
                  <div className="sv-status-card-right">
                    <span className={`sv-status-card-badge ${serviceStatus?.llama_server === 'running' ? 'badge-ok' : serviceStatus?.llama_server === 'error' ? 'badge-err' : 'badge-warn'}`}>
                      ● {serviceStatus?.llama_server === 'running' ? '运行中' : serviceStatus?.llama_server === 'error' ? '异常' : '已停止'}
                    </span>
                    <span className="sv-status-card-action">{expandedStatus === 'qwen' ? '收起' : '详情'}</span>
                  </div>
                </div>
                <div className={`sv-status-detail-panel${expandedStatus === 'qwen' ? ' open' : ''}`}>
                  <div className="sv-status-detail-grid">
                    <div className="sv-status-detail-item"><span className="sd-label">服务</span><span className="sd-value">llama-server</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">端口</span><span className="sd-value">{serviceStatus?.port || 8083}</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">模型</span><span className="sd-value">{serviceStatus?.model_name || '-'}</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">上下文</span><span className="sd-value">{serviceStatus?.context_size || '-'} ctx</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">Flash Attention</span><span className="sd-value">{serviceStatus?.flash_attention || 'auto'}</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">插槽</span><span className="sd-value">{serviceStatus?.slots || 0} 个{serviceStatus?.processing ? ' · 处理中' : ''}</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">显存</span><span className="sd-value">{serviceStatus?.vram_used_mb ? Math.round(serviceStatus.vram_used_mb / 1024) + ' / ' + Math.round((serviceStatus.vram_total_mb || 12226) / 1024) + ' GB' : '-'}</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">操作</span><span className="sd-value"><span className="btn btn-sm btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={loadStatus}>🔄 刷新</span></span></div>
                  </div>
                </div>
              </div>

              {/* 🤖 DeepSeek API */}
              <div className="sv-status-card-wrap">
                <div className={`sv-status-card${expandedStatus === 'deepseek' ? ' active' : ''}`} onClick={() => setExpandedStatus(expandedStatus === 'deepseek' ? null : 'deepseek')}>
                  <div className="sv-status-card-left">
                    <span className="sv-status-card-name">🤖 DeepSeek API</span>
                    <span className="sv-status-card-detail">
                      {providers.find(p => p.name.includes('DeepSeek'))?.base_url ? '已配置' : '未配置'}
                    </span>
                  </div>
                  <div className="sv-status-card-right">
                    <span className={`sv-status-card-badge ${providers.find(p => p.name.includes('DeepSeek'))?.api_key ? 'badge-ok' : 'badge-err'}`}>
                      ● {providers.find(p => p.name.includes('DeepSeek'))?.api_key ? '在线' : '未配置'}
                    </span>
                    <span className="sv-status-card-action">{expandedStatus === 'deepseek' ? '收起' : '详情'}</span>
                  </div>
                </div>
                <div className={`sv-status-detail-panel${expandedStatus === 'deepseek' ? ' open' : ''}`}>
                  {(() => {
                    const dsp = providers.find(p => p.name.includes('DeepSeek'));
                    return (
                      <div className="sv-status-detail-grid">
                        <div className="sv-status-detail-item"><span className="sd-label">Base URL</span><span className="sd-value">{dsp?.base_url || '-'}</span></div>
                        <div className="sv-status-detail-item"><span className="sd-label">模型数</span><span className="sd-value">{dsp?.models?.length || 0} 个</span></div>
                        <div className="sv-status-detail-item"><span className="sd-label">API Key</span><span className="sd-value">{dsp?.api_key ? maskKey(dsp.api_key) : '未配置'}</span></div>
                      </div>
                    );
                  })()}
                </div>
              </div>

              {/* 🗄 数据库 */}
              <div className="sv-status-card-wrap">
                <div className={`sv-status-card${expandedStatus === 'db' ? ' active' : ''}`} onClick={() => setExpandedStatus(expandedStatus === 'db' ? null : 'db')}>
                  <div className="sv-status-card-left">
                    <span className="sv-status-card-name">🗄 数据库</span>
                    <span className="sv-status-card-detail">SQLite · 后端运行中</span>
                  </div>
                  <div className="sv-status-card-right">
                    <span className="sv-status-card-badge badge-ok">● 已连接</span>
                    <span className="sv-status-card-action">{expandedStatus === 'db' ? '收起' : '详情'}</span>
                  </div>
                </div>
                <div className={`sv-status-detail-panel${expandedStatus === 'db' ? ' open' : ''}`}>
                  <div className="sv-status-detail-grid">
                    <div className="sv-status-detail-item"><span className="sd-label">类型</span><span className="sd-value">SQLite (WAL)</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">后端状态</span><span className="sd-value" style={{ color: '#3fb950' }}>运行中</span></div>
                    <div className="sv-status-detail-item"><span className="sd-label">操作</span><span className="sd-value"><span className="btn btn-sm btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={loadStatus}>🔄 刷新</span></span></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ═══ Tab 5: 通用配置 ═══ */}
        {activeTab === 'general' && (
          <div className="sv-tab-panel">
            <div className="sv-desc-row">
              <span className="sv-desc">通用功能配置项。</span>
            </div>

            {settingsLoading ? (
              <div className="sv-loading">加载中…</div>
            ) : !settings ? (
              <div className="sv-empty">无法加载设置</div>
            ) : (
              <div className="sv-general-section">
                <div className="sv-general-item">
                  <div className="sv-general-item-label">
                    <span className="sv-general-item-title">每次加载的聊天记录条数</span>
                    <span className="sv-general-item-desc">频道和场景中每次加载消息的数量，默认 4 条。</span>
                  </div>
                  <div className="sv-general-item-input">
                    <input
                      className="form-input"
                      type="number"
                      min="1"
                      max="200"
                      value={featuresEdit?.message_load_count ?? settings.features.message_load_count}
                      onChange={e => setFeaturesEdit({ message_load_count: parseInt(e.target.value) || 4 })}
                    />
                  </div>
                </div>
                <div className="sv-general-actions">
                  {featuresEdit && (
                    <>
                      <button className="btn btn-sm btn-ghost" onClick={() => setFeaturesEdit(null)}>取消</button>
                      <button className="btn btn-sm btn-primary" onClick={saveFeatures} disabled={featuresSaving}>
                        {featuresSaving ? '保存中…' : '💾 保存'}
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 🌸 秘密花园入口 */}
        <div className="sv-garden-entry" onClick={() => setView('secret-garden')}>
          <span className="sv-garden-icon">🌸</span>
          <span className="sv-garden-text">秘密花园</span>
          <span className="sv-garden-desc">专属的私密空间 · 路由在花园内配置</span>
          <span className="sv-garden-arrow">→</span>
        </div>

      </div>

      {/* ═══ Provider 弹窗 ═══ */}
      <div className={`modal-overlay${provModal ? ' show' : ''}`} onClick={() => !provSaving && setProvModal(false)}>
        <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
          <div className="modal-title">{editProv ? '✏️ 编辑 Provider' : '➕ 添加 Provider'} <button className="modal-close" onClick={() => !provSaving && setProvModal(false)}>✕</button></div>
          <div className="form-group"><label className="form-label">名称</label><input className="form-input" value={provForm.name} onChange={e => setProvForm(f => ({ ...f, name: e.target.value }))} placeholder="DeepSeek" autoFocus /></div>
          <div className="form-group"><label className="form-label">Base URL</label><input className="form-input" value={provForm.base_url} onChange={e => setProvForm(f => ({ ...f, base_url: e.target.value }))} placeholder="https://api.deepseek.com" /></div>
          <div className="form-group"><label className="form-label">API Key</label><input className="form-input" value={provForm.api_key} onChange={e => setProvForm(f => ({ ...f, api_key: e.target.value }))} placeholder="sk-..." type="password" /></div>
          <div className="form-group"><label className="form-label">类型</label><select className="sv-select" value={provForm.provider_type} onChange={e => setProvForm(f => ({ ...f, provider_type: e.target.value }))}><option value="openai-compatible">☁️ 云端 (OpenAI 兼容)</option><option value="local">💻 本地 (llama-server)</option></select></div>
          <div className="modal-actions"><button className="btn" onClick={() => setProvModal(false)} disabled={provSaving}>取消</button><button className="btn btn-primary" onClick={saveProv} disabled={provSaving || !provForm.name.trim() || !provForm.base_url.trim()}>{provSaving ? '保存中…' : '保存'}</button></div>
        </div>
      </div>

      {/* ═══ Model 弹窗 ═══ */}
      <div className={`modal-overlay${modelModal ? ' show' : ''}`} onClick={() => !modelSaving && setModelModal(false)}>
        <div className="modal modal-md" onClick={e => e.stopPropagation()}>
          <div className="modal-title">{editModel.m ? '✏️ 编辑模型' : '➕ 添加模型'} <button className="modal-close" onClick={() => !modelSaving && setModelModal(false)}>✕</button></div>
          <div className="sv-modal-grid">
            <div className="form-group"><label className="form-label">模型名称</label><input className="form-input" value={modelForm.name} onChange={e => setModelForm(f => ({ ...f, name: e.target.value }))} placeholder="deepseek-v4-flash" /></div>
            <div className="form-group"><label className="form-label">显示名称</label><input className="form-input" value={modelForm.display_name} onChange={e => setModelForm(f => ({ ...f, display_name: e.target.value }))} placeholder="DeepSeek v4 Flash" /></div>
            <div className="form-group"><label className="form-label">Temperature</label><input className="form-input" type="number" step="0.05" min="0" max="2" value={modelForm.temperature} onChange={e => setModelForm(f => ({ ...f, temperature: parseFloat(e.target.value) || 0 }))} /></div>
            <div className="form-group"><label className="form-label">Max Tokens</label><input className="form-input" type="number" step="128" min="128" max="131072" value={modelForm.max_tokens} onChange={e => setModelForm(f => ({ ...f, max_tokens: parseInt(e.target.value) || 4096 }))} /></div>
            <div className="form-group"><label className="form-label">Context Length</label><input className="form-input" type="number" step="1024" min="1024" max="2097152" value={modelForm.context_length} onChange={e => setModelForm(f => ({ ...f, context_length: parseInt(e.target.value) || 32768 }))} /></div>
            <div className="form-group"><label className="form-label">Repeat Penalty</label><input className="form-input" type="number" step="0.05" min="1.0" max="2.0" value={modelForm.repeat_penalty} onChange={e => setModelForm(f => ({ ...f, repeat_penalty: parseFloat(e.target.value) || 1.0 }))} /></div>
            <div className="form-group form-check-row"><label className="form-label">Vision</label><label className="sv-toggle"><input type="checkbox" checked={modelForm.vision} onChange={e => setModelForm(f => ({ ...f, vision: e.target.checked }))} /><span className="sv-toggle-slider"></span></label></div>
            <div className="form-group form-check-row"><label className="form-label">Function Calling</label><label className="sv-toggle"><input type="checkbox" checked={modelForm.function_calling} onChange={e => setModelForm(f => ({ ...f, function_calling: e.target.checked }))} /><span className="sv-toggle-slider"></span></label></div>
          </div>
          <div className="modal-actions"><button className="btn" onClick={() => setModelModal(false)} disabled={modelSaving}>取消</button><button className="btn btn-primary" onClick={saveModel} disabled={modelSaving || !modelForm.name.trim()}>{modelSaving ? '保存中…' : '保存'}</button></div>
        </div>
      </div>
      </div>
    </div>
  );
}
