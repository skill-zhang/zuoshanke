/** API 调用层 — 所有后端请求 */
const BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

// ═══ 场景 ═══
export interface Scene {
  id: string; project_id: string; name: string; pinned: boolean;
  complexity: string | null;
  constraints: any[] | null;
  constraints_locked: boolean;
  user_context: string | null;
  icon: string | null;
  description: string;
  guide_text: string | null;
  category: string;
  version: string;
  source: string;
  created_at: string;
  updated_at: string;
  // Schema v0.81: 收敛/发散参数
  converge_threshold: number;
  converge_enabled: boolean;
  diverge_min_rounds: number;
  // Schema v1.3: 工作台
  show_on_workbench: boolean;
  workbench_position: number;
  scene_config?: Record<string, any>;
}
export const listScenes = (projectId?: string) =>
  request<Scene[]>(`/scenes${projectId ? '?project_id=' + projectId : ''}`);
export const createScene = (name: string, opts?: { icon?: string; description?: string; category?: string; user_context?: string }) =>
  request<Scene>('/scenes', { method: 'POST', body: JSON.stringify({ name, ...opts }) });
export const updateScene = (sceneId: string, data: {
  name?: string; pinned?: boolean; user_context?: string | null;
  icon?: string | null; description?: string; category?: string; guide_text?: string | null;
  converge_threshold?: number; converge_enabled?: boolean; diverge_min_rounds?: number;
  scene_config?: Record<string, any>;
  show_on_workbench?: boolean; workbench_position?: number;
}) =>
  request<Scene>(`/scenes/${sceneId}`, { method: 'PATCH', body: JSON.stringify(data) });
export const deleteScene = (id: string) =>
  request(`/scenes/${id}`, { method: 'DELETE' });

// ═══ 场景广场 / 工坊 ═══
export const listPlazaScenes = (params?: { category?: string; q?: string }) => {
  const qs = new URLSearchParams();
  if (params?.category) qs.set('category', params.category);
  if (params?.q) qs.set('q', params.q);
  const q = qs.toString();
  return request<Scene[]>(`/scenes/plaza${q ? '?' + q : ''}`);
};
export const listWorkshopScenes = (params?: { category?: string; project_id?: string }) => {
  const qs = new URLSearchParams();
  if (params?.category) qs.set('category', params.category);
  if (params?.project_id) qs.set('project_id', params.project_id);
  const q = qs.toString();
  return request<Scene[]>(`/scenes/workshop${q ? '?' + q : ''}`);
};
export const publishScene = (sceneId: string, data: { version: string; changelog?: string }) =>
  request<Scene>(`/scenes/${sceneId}/publish`, { method: 'POST', body: JSON.stringify(data) });
export const exportScene = (sceneId: string) =>
  request<{ name: string; icon?: string; description: string; category: string; guide_text?: string;
    user_context?: string; complexity?: string; constraints?: any[]; constraints_locked?: boolean;
    version: string }>(`/scenes/${sceneId}/export`);
export const importScene = (projectId: string, sceneData: any) =>
  request<Scene>('/scenes/import', { method: 'POST', body: JSON.stringify({ project_id: projectId, scene: sceneData }) });

// ═══ 场景记忆提取 ═══
export const extractSceneMemory = (sceneId: string) =>
  request(`/scenes/${sceneId}/extract-memory`, { method: 'POST' });

// ═══ Thinking Map ═══
export interface ThinkNode {
  id: string; map_id: string; parent_id: string | null; type: string;
  label: string; status: string; actionable: boolean;
  context_ref: string | null; discussion: string[];
  linked_action_map: string | null; action_status: string | null;
  position_x: number | null; position_y: number | null;
  // Agent Loop v1
  converged_from: string[];
  created_by: string;        // brainstorm | reflect | manual
  priority: number | null;    // 1-4 (P1-P4)
  queue_order: number | null;
  depends_on: string[];
  execution_result: string | null;
}
export interface ThinkingMap {
  id: string; scene_id: string; title: string;
  status: string; version: number;
  created_at: string; updated_at: string;
  nodes: ThinkNode[];
}
export const getThinkingMap = (sceneId: string) =>
  request<ThinkingMap>(`/scenes/${sceneId}/thinking-map`);
export const addNode = (mapId: string, node: Partial<ThinkNode>) =>
  request<ThinkNode>(`/thinking-maps/${mapId}/nodes`, { method: 'POST', body: JSON.stringify(node) });
export const updateNode = (nodeId: string, data: Partial<ThinkNode>) =>
  request<ThinkNode>(`/think-nodes/${nodeId}`, { method: 'PATCH', body: JSON.stringify(data) });
export const deleteNode = (nodeId: string) =>
  request(`/think-nodes/${nodeId}`, { method: 'DELETE' });
export const convergeMap = (mapId: string) =>
  request<any>(`/thinking-maps/${mapId}/converge`, { method: 'POST' });
export const divergeMap = (mapId: string, params?: { context?: string; force?: boolean }) =>
  request<any>(`/thinking-maps/${mapId}/diverge`, {
    method: 'POST',
    body: JSON.stringify(params || {}),
  });
export const prioritizeMap = (mapId: string) =>
  request<any>(`/thinking-maps/${mapId}/prioritize`, { method: 'POST' });
export const getQueue = (mapId: string) =>
  request<any>(`/thinking-maps/${mapId}/queue`);
export const getFocusQueue = (mapId: string, limit = 5) =>
  request<any>(`/thinking-maps/${mapId}/focus-queue?limit=${limit}`);
export const reflectNode = (mapId: string, data: {
  node_id: string; result_summary: string;
  new_discoveries?: string[]; is_success?: boolean;
}) => request<any>(`/thinking-maps/${mapId}/reflect`, {
  method: 'POST', body: JSON.stringify(data),
});

// ═══ 消息 ═══
export interface Message {
  id: string; scene_id: string | null; channel_id: string | null;
  session_id: string | null;
  role: 'user' | 'ai' | 'system';
  content: string; map_ref: string | null; model: string | null; created_at: string;
  display?: boolean;  // 🆕 Schema v0.7: false=内部记录不渲染
  toolCards?: ToolCard[];
  asset?: { type: string; title: string; content: string };  // 🆕 场景产出
  outputRef?: { outputId: string; title: string; filePath: string };  // 🆕 自动提取的 HTML 产出链接
}
export const sendMessage = (sceneId: string, content: string, channel: string = 'main') =>
  request<Message>('/messages', { method: 'POST', body: JSON.stringify({ scene_id: sceneId, content, channel }) });
/** 分页消息结果 */
export interface PaginatedMessages {
  messages: Message[];
  has_more: boolean;
  total: number;
}

export const listSceneMessages = (sceneId: string, sessionId?: string, limit?: number, beforeId?: string) => {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  if (limit) params.set('limit', String(limit));
  if (beforeId) params.set('before_id', beforeId);
  const qs = params.toString();
  return request<PaginatedMessages>(`/scenes/${sceneId}/messages${qs ? '?' + qs : ''}`);
};
export const deleteMessage = (messageId: string) =>
  request(`/messages/${messageId}`, { method: 'DELETE' });
export const regenerateMessage = (messageId: string) =>
  request<Message>(`/messages/${messageId}/regenerate`, { method: 'POST' });
export const newSceneSession = (sceneId: string) =>
  request<{ session_id: string }>(`/scenes/${sceneId}/new-session`, { method: 'POST' });

export const batchDeleteMessages = (ids: string[]) =>
  request<{ ok: boolean; deleted: number }>('/messages/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  });

export const clearSceneMessages = (sceneId: string) =>
  request<{ ok: boolean; deleted: number }>(`/scenes/${sceneId}/messages`, { method: 'DELETE' });

export interface SceneSession {
  session_id: string;
  last_active: string | null;
  message_count: number;
}
export const listSceneSessions = (sceneId: string) =>
  request<SceneSession[]>(`/scenes/${sceneId}/sessions`);

/** 发送场景消息 + 流式接收 AI 回复（SSE） */
export async function* sendSceneMessageStream(
  sceneId: string,
  content: string,
  sessionId?: string,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/scenes/${sceneId}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, scene_id: sceneId, session_id: sessionId || null }),
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('data: ')) {
        const data = JSON.parse(trimmed.slice(6));
        yield data as StreamEvent;
      }
    }
  }
}

// ═══ 频道 ═══
export interface Channel {
  id: string; name: string; pinned: boolean; is_default: boolean;
  created_at: string; updated_at: string;
}
export const listChannels = () => request<Channel[]>('/channels');
export const createChannel = (name: string) =>
  request<Channel>('/channels', { method: 'POST', body: JSON.stringify({ name }) });
export const updateChannel = (channelId: string, data: { name?: string; pinned?: boolean }) =>
  request<Channel>(`/channels/${channelId}`, { method: 'PATCH', body: JSON.stringify(data) });
export const deleteChannel = (id: string) =>
  request(`/channels/${id}`, { method: 'DELETE' });
export const clearChannelMessages = (channelId: string) =>
  request(`/channels/${channelId}/messages`, { method: 'DELETE' });
export const sendChannelMessage = (channelId: string, content: string) =>
  request<Message>(`/channels/${channelId}/messages`, { method: 'POST', body: JSON.stringify({ content }) });
export const listChannelMessages = (channelId: string, limit?: number, beforeId?: string) => {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));
  if (beforeId) params.set('before_id', beforeId);
  const qs = params.toString();
  return request<PaginatedMessages>(`/channels/${channelId}/messages${qs ? '?' + qs : ''}`);
};


// ═══ 流式 SSE 类型 ═══
export interface ToolCard {
  type: 'weather' | 'attractions' | 'equipment';
  data: Record<string, any>;
}

export type StreamEvent =
  | { type: 'user_msg'; id: string; role: 'user'; content: string; created_at: string }
  | { type: 'tool_cards'; cards: ToolCard[] }
  | { type: 'tool_status'; tool: string; status: 'running' | 'done' | 'error'; success?: boolean; message: string }
  | { type: 'model_info'; model: string; complexity: string | null }
  | { type: 'context_info'; total_tokens: number; max_tokens: number; percentage: number; usage_str: string; progress_bar: string; history_count: number }
  | { type: 'capacity_warning'; total_tokens: number; max_tokens: number; percentage: number; message: string }
  // 🆕 Thought Stream: 思考流事件
  | { type: 'thought'; content: string; phase: string; mood: string }
  | { type: 'token'; token: string }
  | { type: 'done'; id: string; role: 'ai'; content: string; created_at: string; model?: string }
  | { type: 'error'; message: string }
  // 🆕 Schema v0.7: 仪表盘事件
  | { type: 'dashboard:converge'; merge_count: number; queue_count: number }
  | { type: 'dashboard:queue_update'; items: DashboardQueueItem[] }
  | { type: 'dashboard:reflect'; tool: string; tool_success: boolean; result_preview: string }
  | { type: 'thinking_map:diverged'; node_count: number }
  // 🆕 高危命令审批
  | { type: 'command_approval'; command: string; reason: string; category: string; description: string };

/** Schema v0.7: 仪表盘队列项 */
export interface DashboardQueueItem {
  id: string; title: string; priority: number; status: string; deps?: string[];
  sort_order?: number; created_at?: string; completed_at?: string | null;
}

/** Schema v0.7: 反馈时间线项 */
export interface DashboardReflectItem {
  id: string; type: string; icon: string; title: string; detail?: string;
  tag?: string; tag_text?: string; created_at?: string;
}

/** 工具执行记录（纯前端，不存库） */
export interface ToolLog {
  tool: string;
  status: 'running' | 'done' | 'error';
  success?: boolean;
  message: string;
}

/** 发送频道消息 + 流式接收 AI 回复（SSE） */
export async function* sendChannelMessageStream(
  channelId: string,
  content: string,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/channels/${channelId}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('data: ')) {
        const data = JSON.parse(trimmed.slice(6));
        yield data as StreamEvent;
      }
    }
  }
}


// ═══ Action Map ═══
export interface ActionNode {
  id: string; map_id: string; type: string; label: string;
  status: string; requires_approval: boolean;
  timeout: number; retry: number; retry_count: number;
  verification: any; fallback_node: string | null; origin: string;
  result_summary: string | null; artifacts: string[];
  context_ref: string | null;
  started_at: string | null; completed_at: string | null;
  order_index: number;
  position_x: number | null; position_y: number | null;
}

export interface ActionEdge {
  id: string; map_id: string;
  from_node_id: string; to_node_id: string;
  type: string; label: string | null; condition: string | null;
}

export interface ActionMap {
  id: string; think_map_id: string; think_node_id: string;
  title: string; status: string; version: number;
  replan_count: number; dynamic_nodes: string[];
  created_at: string; updated_at: string;
  nodes: ActionNode[]; edges: ActionEdge[];
}

export const createActionMap = (data: {
  think_map_id: string; think_node_id: string; title: string;
  nodes: any[]; edges: any[];
}) => request<ActionMap>('/action-maps', {
  method: 'POST', body: JSON.stringify(data),
});

export const listActionMaps = (params?: { think_map_id?: string; think_node_id?: string }) => {
  const qs = new URLSearchParams();
  if (params?.think_map_id) qs.set('think_map_id', params.think_map_id);
  if (params?.think_node_id) qs.set('think_node_id', params.think_node_id);
  const q = qs.toString();
  return request<ActionMap[]>(`/action-maps${q ? '?' + q : ''}`);
};

export const getActionMap = (id: string) =>
  request<ActionMap>(`/action-maps/${id}`);

export const updateActionMapStatus = (id: string, status: string) =>
  request(`/action-maps/${id}/status`, {
    method: 'PATCH', body: JSON.stringify({ status }),
  });

export const updateActionNodeStatus = (mapId: string, nodeId: string, status: string) =>
  request(`/action-maps/${mapId}/nodes/${nodeId}`, {
    method: 'PATCH', body: JSON.stringify({ status }),
  });

export const deleteActionMap = (id: string) =>
  request(`/action-maps/${id}`, { method: 'DELETE' });

export const generateActionMap = (thinkNodeId: string) =>
  request<ActionMap>('/action-maps/generate', {
    method: 'POST',
    body: JSON.stringify({ think_node_id: thinkNodeId }),
  });

// ═══ Action Map 流式生成（Hermes 子进程 SSE）═══
export type ActionMapStreamEvent =
  | { type: 'hermes_log'; line: string }
  | { type: 'status'; line: string }
  | { type: 'result'; action_map: ActionMap }
  | { type: 'done' }
  | { type: 'error'; message: string };

export async function* generateActionMapStream(
  thinkNodeId: string,
): AsyncGenerator<ActionMapStreamEvent> {
  const res = await fetch(`${BASE}/action-maps/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ think_node_id: thinkNodeId }),
  });

  if (!res.ok) throw new Error(await res.text());

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('data: ')) {
        try {
          yield JSON.parse(trimmed.slice(6)) as ActionMapStreamEvent;
        } catch { /* skip malformed */ }
      }
    }
  }
}

// ═══ Action Map 执行流式（Hermes 子进程执行节点）═══
export type ExecuteStreamEvent =
  | { type: 'map_status'; status: string }
  | { type: 'node_start'; node_id: string; label: string }
  | { type: 'node_done'; node_id: string; status: string; label: string; result?: string }
  | { type: 'node_retry'; node_id: string; label: string; retry: number }
  | { type: 'hermes_log'; node_id: string; line: string }
  | { type: 'map_done'; status: string }
  | { type: 'tools_documented'; count: number; tools: Array<{ name: string; description: string }> }
  | { type: 'error'; message: string };

export async function* executeActionMapStream(
  actionMapId: string,
): AsyncGenerator<ExecuteStreamEvent> {
  const res = await fetch(`${BASE}/action-maps/${actionMapId}/execute`, {
    method: 'POST',
  });

  if (!res.ok) throw new Error(await res.text());

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('data: ')) {
        try {
          yield JSON.parse(trimmed.slice(6)) as ExecuteStreamEvent;
        } catch { /* skip malformed */ }
      }
    }
  }
}

// ═══ Action Map 执行日志 ═══
export interface ActionExecutionLog {
  id: string;
  node_id: string | null;
  node_label: string | null;
  event_type: string;
  line: string | null;
  status: string | null;
  result: string | null;
  created_at: string | null;
}

export const getActionMapLogs = (actionMapId: string) =>
  request<ActionExecutionLog[]>(`/action-maps/${actionMapId}/logs`);


// ═══ 记忆系统 🆕 ═══
export interface AgentMemory {
  id: string; category: string; key: string; content: string;
  tags: string[]; priority_level: string; base_weight: number;
  explicit_boost: number; times_accessed: number; source: string;
  last_accessed_at: string | null; created_at: string | null;
  weight?: number;
  scope?: string;           // 🆕 记忆作用域
  context_id?: string | null;  // 🆕 场景/频道ID
}
export interface MemoryGroup {
  scope: string;
  context_id: string | null;
  name: string;
  icon: string;
  count: number;
  preview: string;
  latest: string | null;
}
export const listMemories = (params?: {
  category?: string; scope?: string; context_id?: string; scope_only?: boolean;
}) => {
  const qs = new URLSearchParams();
  if (params?.category) qs.set('category', params.category);
  if (params?.scope) qs.set('scope', params.scope);
  if (params?.context_id) qs.set('context_id', params.context_id);
  if (params?.scope_only) qs.set('scope_only', 'true');
  const q = qs.toString();
  return request<{ success: boolean; data: AgentMemory[] }>(`/memory${q ? '?' + q : ''}`);
};
export const listMemoryGroups = () =>
  request<{ success: boolean; data: MemoryGroup[] }>('/memory/groups');
export const createMemory = (data: {
  key: string; content: string; category?: string;
  tags?: string[]; base_weight?: number;
  scope?: string; context_id?: string;
}) =>
  request<{ success: boolean; data: { id: string; key: string } }>('/memory', { method: 'POST', body: JSON.stringify(data) });
export const getMemory = (key: string) =>
  request<{ success: boolean; data: AgentMemory }>('/memory/' + encodeURIComponent(key));
export const deleteMemory = (key: string) =>
  request<{ success: boolean }>('/memory/' + encodeURIComponent(key), { method: 'DELETE' });
export const batchDeleteMemories = (keys: string[]) =>
  request<{ success: boolean; deleted: number; total: number }>('/memory/batch-delete', { method: 'POST', body: JSON.stringify({ keys }) });
export const clearScopeMemories = (scope: string, contextId: string) =>
  request<{ success: boolean; deleted: number }>('/memory/scope/' + encodeURIComponent(scope) + '/' + encodeURIComponent(contextId), { method: 'DELETE' });
export const reinforceMemory = (key: string) =>
  request<{ success: boolean }>('/memory/' + encodeURIComponent(key) + '/reinforce', { method: 'POST' });
export const pinMemory = (key: string) =>
  request<{ success: boolean }>('/memory/' + encodeURIComponent(key) + '/pin', { method: 'POST' });

// ═══ 技能系统 🆕 ═══
export interface SkillMeta {
  name: string; description: string; version: string;
  category: string; triggers: string[];
}
export const listSkills = (category?: string) => {
  const qs = category ? '?category=' + encodeURIComponent(category) : '';
  return request<{ success: boolean; data: SkillMeta[] }>('/skills' + qs);
};
export const getSkill = (name: string) =>
  request<{ success: boolean; data: SkillMeta & { content: string } }>('/skills/' + encodeURIComponent(name));
export const createSkill = (data: { name: string; description: string; content: string; triggers?: string[]; category?: string }) =>
  request<{ success: boolean; data: SkillMeta }>('/skills', { method: 'POST', body: JSON.stringify(data) });
export const updateSkill = (name: string, data: { description?: string; content?: string; triggers?: string[]; category?: string }) =>
  request<{ success: boolean }>('/skills/' + encodeURIComponent(name), { method: 'PUT', body: JSON.stringify(data) });
export const deleteSkill = (name: string) =>
  request<{ success: boolean }>('/skills/' + encodeURIComponent(name), { method: 'DELETE' });

// ═══ 技能分类管理 ═══
export interface SkillCategory {
  name: string; count: number; protected: boolean;
}
export const listSkillCategories = () =>
  request<{ success: boolean; data: SkillCategory[] }>('/skills/categories');
export const renameSkillCategory = (old_name: string, new_name: string) =>
  request<{ success: boolean; count: number }>('/skills/categories/rename', { method: 'PUT', body: JSON.stringify({ old_name, new_name }) });

// ═══ 工具管理 ═══
export interface ToolSummary {
  name: string; description: string; category: string; verified: boolean;
  params_count: number; preexecute_enabled: boolean;
  preexecute_triggers_count: number; has_skill: boolean;
}
export interface ToolParam {
  name: string; type: string; required: boolean; description: string;
}
export interface ToolDetail {
  name: string; description: string; file: string; function: string;
  parameters: ToolParam[]; returns: string; category: string; verified: boolean;
  preexecute: { enabled: boolean; triggers: string[]; requires_city: boolean };
  has_skill: boolean; skill_content: string | null;
}
export const listTools = (category?: string) => {
  const qs = category ? '?category=' + encodeURIComponent(category) : '';
  return request<{ success: boolean; data: ToolSummary[] }>('/tools' + qs);
};
export const getTool = (name: string) =>
  request<{ success: boolean; data: ToolDetail }>('/tools/' + encodeURIComponent(name));
export const createTool = (data: {
  name: string; description: string; file: string; function: string;
  parameters?: ToolParam[]; returns?: string; category?: string; verified?: boolean;
  preexecute?: { enabled?: boolean; triggers?: string[]; requires_city?: boolean };
}) => request<{ success: boolean; data: ToolDetail }>('/tools', { method: 'POST', body: JSON.stringify(data) });
export const updateTool = (name: string, data: {
  description?: string; file?: string; function?: string;
  parameters?: ToolParam[]; returns?: string; category?: string; verified?: boolean;
}) => request<{ success: boolean; data: ToolDetail }>('/tools/' + encodeURIComponent(name), { method: 'PUT', body: JSON.stringify(data) });
export const deleteTool = (name: string) =>
  request<{ success: boolean }>('/tools/' + encodeURIComponent(name), { method: 'DELETE' });
export const updatePreexecute = (name: string, data: {
  enabled?: boolean; triggers?: string[]; requires_city?: boolean;
}) => request<{ success: boolean; data: ToolDetail }>('/tools/' + encodeURIComponent(name) + '/preexecute', { method: 'PUT', body: JSON.stringify(data) });
export const getToolSkill = (name: string) =>
  request<{ success: boolean; data: { name: string; content: string } }>('/tools/' + encodeURIComponent(name) + '/skill');
export const putToolSkill = (name: string, content: string) =>
  request<{ success: boolean }>('/tools/' + encodeURIComponent(name) + '/skill', { method: 'PUT', body: JSON.stringify({ content }) });
export const deleteToolSkill = (name: string) =>
  request<{ success: boolean }>('/tools/' + encodeURIComponent(name) + '/skill', { method: 'DELETE' });

// ═══ 系统设置 ═══
export interface RouteConfig {
  model: string;
  provider: string;
  provider_id?: string;
  model_id?: string;
  temperature: number;
  max_tokens: number;
  repeat_penalty: number;
  context_length: number;
}

export interface SystemPrompts {
  channel: string;
  scene: string;
}

export interface Features {
  pdf_as_image: boolean;
  vision_enabled: boolean;
  message_load_count: number;
}

export interface SettingsData {
  routing: Record<string, RouteConfig>;
  system_prompts: SystemPrompts;
  features: Features;
  updated_at: string | null;
}

export interface ServiceStatus {
  llama_server: string;
  port: number;
  flash_attention: string | null;
  cache_reuse: number | null;
  context_size: number | null;
  vram_used_mb: number | null;
  vram_total_mb: number | null;
  model_name: string | null;
  is_sleeping: boolean | null;
  slots: number;
  processing: boolean;
}

export const getSettings = () => request<SettingsData>('/settings');

export const updateSettings = (data: Record<string, any>) =>
  request<SettingsData>('/settings', { method: 'PATCH', body: JSON.stringify(data) });

export const getDefaultPrompts = () => request<{ channel: string; scene: string }>('/settings/defaults');

export const getServiceStatus = () => request<ServiceStatus>('/settings/service');

// ═══ 用户画像 ═══
export interface UserProfile {
  id: string;
  key: string;
  content: string;
  category: string;
  priority: string;
  tags: string[];
  source_scenes: string[];
  merged_from: string[];
  is_active: boolean;
  deprecated_by: string | null;
  total_injections: number;
  last_injected_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PendingTrait {
  id: string;
  content: string;
  source_scene: string | null;
  source_scene_id: string | null;
  confidence: string;
  context_snippet: string | null;
  status: string;
  created_at: string | null;
}

export interface ProfilesResponse {
  success: boolean;
  profiles: Record<string, UserProfile[]>;
  total: number;
}

export interface ProfileProcessResponse {
  success: boolean;
  message: string;
  stats?: { pending_count: number; merged: number; new_profiles: number; discarded: number; merged_into_existing: number; };
}

export const listProfiles = (category?: string, activeOnly?: boolean) => {
  const qs = new URLSearchParams();
  if (category) qs.set('category', category);
  if (activeOnly !== undefined) qs.set('active_only', String(activeOnly));
  const q = qs.toString();
  return request<ProfilesResponse>(`/user-profile${q ? '?' + q : ''}`);
};

export const getProfile = (key: string) =>
  request<{ success: boolean; data: UserProfile }>('/user-profile/' + encodeURIComponent(key));

export const updateProfile = (key: string, data: { content?: string; category?: string; priority?: string; tags?: string[]; is_active?: boolean }) =>
  request<{ success: boolean; data: UserProfile }>('/user-profile/' + encodeURIComponent(key), { method: 'PUT', body: JSON.stringify(data) });

export const deleteProfile = (key: string) =>
  request<{ success: boolean; message: string }>('/user-profile/' + encodeURIComponent(key), { method: 'DELETE' });

export const listPendingTraits = () =>
  request<{ success: boolean; data: PendingTrait[]; total: number }>('/user-profile/pending');

export const acceptPendingTrait = (traitId: string) =>
  request<{ success: boolean; profile_id: string; key: string }>('/user-profile/pending/' + encodeURIComponent(traitId) + '/accept', { method: 'POST' });

export const rejectPendingTrait = (traitId: string) =>
  request<{ success: boolean; message: string }>('/user-profile/pending/' + encodeURIComponent(traitId) + '/reject', { method: 'POST' });

export const triggerProfileProcess = () =>
  request<ProfileProcessResponse>('/user-profile/process', { method: 'POST' });

// ═══ 类别管理 ═══
export interface Category {
  name: string;
  label: string;
  icon: string;
  count: number;
}
export const listCategories = () => request<Category[]>('/categories');
export const renameCategory = (oldName: string, newName: string) =>
  request<{ ok: boolean; updated: number }>(`/categories/${encodeURIComponent(oldName)}`, {
    method: 'PUT', body: JSON.stringify({ new_name: newName }),
  });
export const createCategory = (data: { name: string; label?: string; icon?: string }) =>
  request<{ ok: boolean; category: Category }>('/categories', {
    method: 'POST', body: JSON.stringify(data),
  });
export const deleteCategory = (name: string) =>
  request<{ ok: boolean; deleted: string }>(`/categories/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });

// ═══ 上下文压缩 ═══
export const compressChannelHistory = (channelId: string) =>
  request<{ ok: boolean; summary?: string; deleted?: number; error?: string }>(
    `/channels/${channelId}/compress`, { method: 'POST' }
  );

// ═══ Schema v0.7: 仪表盘 ═══
export const getDashboardQueue = (sceneId: string) =>
  request<{ items: DashboardQueueItem[] }>(`/dashboard/${sceneId}/queue`);

export const getDashboardReflect = (sceneId: string) =>
  request<{ items: DashboardReflectItem[] }>(`/dashboard/${sceneId}/reflect`);

export const getDashboardStatus = (sceneId: string) =>
  request<{ queue_total: number; completed: number; current_task: DashboardQueueItem | null }>(
    `/dashboard/${sceneId}/status`
  );

export const triggerDashboardConverge = (sceneId: string) =>
  request<{ ok: boolean; queue_count: number; items: DashboardQueueItem[] }>(
    `/dashboard/${sceneId}/converge`, { method: 'POST' }
  );

// ═══ 秘密花园 ═══
export interface GardenData {
  name: string;
  mood: string;
  observation: string;
  memory_garden: {
    total: number;
    items: { content: string; key: string; weight: number; level: number; is_narrative: boolean; is_immortal: boolean; correction_count: number; created_at: string | null }[];
  };
  growth: {
    scenes: number;
    tools: number;
    skills: number;
    channels: number;
    thoughts: number;
    versions: string;
  };
  milestones: { date: string; icon: string; text: string }[];
  updated_at: string;
}

export const getSecretGarden = () => request<GardenData>('/zhu-agent/garden');

// 🆕 起居室 SSE 聊天
export interface GardenMessageData {
  id: string;
  role: string;
  content: string;
  created_at: string | null;
}

export const getGardenChatHistory = () =>
  request<{ success: boolean; data: GardenMessageData[] }>('/zhu-agent/garden/chat/history');

export const sendGardenChatMessage = (
  message: string,
  onToken: (text: string) => void
): Promise<string> => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/zhu-agent/garden/chat/stream', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'text';
    let full = '';
    let lastIndex = 0;
    xhr.onprogress = () => {
      const chunk = xhr.responseText.slice(lastIndex);
      lastIndex = xhr.responseText.length;
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        try {
          const d = JSON.parse(line.slice(6));
          if (d.text) { full += d.text; onToken(d.text); }
        } catch { /* ignore */ }
        if (line.includes('"type":"done"') || line.includes('"event":"done"')) {
          resolve(full);
        }
      }
    };
    xhr.onerror = () => reject(new Error('garden chat error'));
    xhr.send(JSON.stringify({ message }));
  });
};

// ═══ Schema v1.1: Session 管理 ═══
export interface WebSession {
  id: string;
  context_type: string;
  context_id: string;
  context_name: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  last_active_at: string | null;
  duration_seconds: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  reasoning_tokens: number;
  api_calls: number;
  estimated_cost_usd: number;
  cost_status: string;
  cost_source: string | null;
}

/** 创建或激活 Web session（sidebar 点击时调用） */
export const activateSession = (contextType: string, contextId: string, contextName?: string) =>
  request<WebSession>('/sessions/activate', {
    method: 'POST',
    body: JSON.stringify({ context_type: contextType, context_id: contextId, context_name: contextName }),
  });

/** 获取指定上下文的活跃 session */
export const getActiveSession = (contextType: string, contextId: string) =>
  request<WebSession | null>(`/sessions/active?context_type=${encodeURIComponent(contextType)}&context_id=${encodeURIComponent(contextId)}`);

/** 刷新 session 的 last_active_at */
export const touchSession = (sessionId: string) =>
  request<{ ok: boolean }>(`/sessions/${sessionId}/touch`, { method: 'POST' });

/** 累加 token 用量 */
export const accumulateTokens = (sessionId: string, data: {
  prompt_tokens?: number; completion_tokens?: number; total_tokens?: number;
  input_tokens?: number; output_tokens?: number; cache_read_tokens?: number;
  cache_write_tokens?: number; reasoning_tokens?: number; api_calls?: number;
  estimated_cost_usd?: number; cost_status?: string; cost_source?: string | null;
}) =>
  request<{ ok: boolean }>(`/sessions/${sessionId}/token`, {
    method: 'POST',
    body: JSON.stringify(data),
  });

/** 列出 Web session */
export const listSessions = (contextType?: string, status?: string) => {
  const qs = new URLSearchParams();
  if (contextType) qs.set('context_type', contextType);
  if (status) qs.set('status', status);
  const q = qs.toString();
  return request<WebSession[]>(`/sessions${q ? '?' + q : ''}`);
};

// ═══ 场景自省地图 🆕 ═══
export interface SceneSelfMapTree {
  id: string;
  icon: string;
  label: string;
  sublabel?: string;
  children?: SceneSelfMapTree[];
  detail?: {
    description: string;
    rows?: [string, string][];
    codePath?: string;
  };
  hasDiagram?: boolean;
}

export interface SceneSelfMapDiagramNode {
  id: string; x: number; y: number; w?: number; h?: number;
  icon: string; label: string; sub?: string; style?: string;
}

export interface SceneSelfMapDiagram {
  title: string;
  nodes: SceneSelfMapDiagramNode[];
  edges: [string, string][];
}

export interface SceneSelfMapData {
  exists: boolean;
  title: string;
  tree: SceneSelfMapTree[];
  diagrams: Record<string, SceneSelfMapDiagram>;
  updated_at: string;
}

export const fetchSceneSelfMap = (sceneId: string) =>
  request<SceneSelfMapData>(`/scenes/${encodeURIComponent(sceneId)}/self-map`);

// ═══ AI Provider ═══
export interface AiProviderData {
  id: string;
  name: string;
  base_url: string;
  api_key: string;
  provider_type: string;
  is_active: boolean;
  models: AiModelData[];
}

export interface AiModelData {
  id: string;
  provider_id: string;
  name: string;
  display_name: string | null;
  temperature: number;
  max_tokens: number;
  context_length: number;
  repeat_penalty: number;
  vision: boolean;
  function_calling: boolean;
  sort_order: number;
}

export const listProviders = () =>
  request<{ providers: AiProviderData[] }>('/providers');

export const getProvider = (id: string) =>
  request<{ provider: AiProviderData }>('/providers/' + encodeURIComponent(id));

export const createProvider = (data: { name: string; base_url: string; api_key?: string; provider_type?: string }) =>
  request<{ provider: AiProviderData }>('/providers', { method: 'POST', body: JSON.stringify(data) });

export const updateProvider = (id: string, data: Record<string, any>) =>
  request<{ provider: AiProviderData }>('/providers/' + encodeURIComponent(id), { method: 'PUT', body: JSON.stringify(data) });

export const deleteProvider = (id: string) =>
  request<{ ok: boolean }>('/providers/' + encodeURIComponent(id), { method: 'DELETE' });

export const createModel = (providerId: string, data: Record<string, any>) =>
  request<{ model: AiModelData }>('/providers/' + encodeURIComponent(providerId) + '/models', { method: 'POST', body: JSON.stringify(data) });

export const updateModel = (providerId: string, modelId: string, data: Record<string, any>) =>
  request<{ model: AiModelData }>('/providers/' + encodeURIComponent(providerId) + '/models/' + encodeURIComponent(modelId), { method: 'PUT', body: JSON.stringify(data) });

export const deleteModel = (providerId: string, modelId: string) =>
  request<{ ok: boolean }>('/providers/' + encodeURIComponent(providerId) + '/models/' + encodeURIComponent(modelId), { method: 'DELETE' });



