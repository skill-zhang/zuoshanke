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

// ═══ 项目 ═══
export interface Project {
  id: string; name: string; description: string;
  status: string; created_at: string; updated_at: string;
}
export const listProjects = () => request<Project[]>('/projects');
export const createProject = (name: string, desc: string = '') =>
  request<Project>('/projects', { method: 'POST', body: JSON.stringify({ name, description: desc }) });
export const deleteProject = (id: string) =>
  request('/projects/' + id, { method: 'DELETE' });

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
  changelog: string | null;
  published_at: string | null;
  created_at: string; updated_at: string;
}
export const listScenes = (projectId?: string) =>
  request<Scene[]>(`/scenes${projectId ? '?project_id=' + projectId : ''}`);
export const createScene = (projectId: string, name: string, opts?: { icon?: string; description?: string; category?: string }) =>
  request<Scene>('/scenes', { method: 'POST', body: JSON.stringify({ project_id: projectId, name, ...opts }) });
export const updateScene = (sceneId: string, data: {
  name?: string; pinned?: boolean; user_context?: string | null;
  icon?: string | null; description?: string; category?: string; guide_text?: string | null;
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

// ═══ Thinking Map ═══
export interface ThinkNode {
  id: string; map_id: string; parent_id: string | null; type: string;
  label: string; status: string; actionable: boolean;
  context_ref: string | null; discussion: string[];
  linked_action_map: string | null; action_status: string | null;
  position_x: number | null; position_y: number | null;
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

// ═══ 消息 ═══
export interface Message {
  id: string; scene_id: string | null; channel_id: string | null;
  session_id: string | null;
  role: 'user' | 'ai' | 'system';
  content: string; map_ref: string | null; model: string | null; created_at: string;
  toolCards?: ToolCard[];
}
export const sendMessage = (sceneId: string, content: string, channel: string = 'main') =>
  request<Message>('/messages', { method: 'POST', body: JSON.stringify({ scene_id: sceneId, content, channel }) });
export const listSceneMessages = (sceneId: string, sessionId?: string) => {
  const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return request<Message[]>(`/scenes/${sceneId}/messages${params}`);
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
export const listChannelMessages = (channelId: string) =>
  request<Message[]>(`/channels/${channelId}/messages`);


// ═══ 流式 SSE 类型 ═══
export interface ToolCard {
  type: 'weather' | 'attractions' | 'equipment';
  data: Record<string, any>;
}

export type StreamEvent =
  | { type: 'user_msg'; id: string; role: 'user'; content: string; created_at: string }
  | { type: 'tool_cards'; cards: ToolCard[] }
  | { type: 'model_info'; model: string; complexity: string | null }
  | { type: 'token'; token: string }
  | { type: 'done'; id: string; role: 'ai'; content: string; created_at: string; model?: string }
  | { type: 'error'; message: string };

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

// ═══ 工具文档 ═══
export const getToolSkill = (toolName: string) =>
  request<{ name: string; content: string }>(`/tools/${toolName}/skill`);


// ═══ 系统设置 ═══
export interface RouteConfig {
  model: string;
  provider: string;
  temperature: number;
  max_tokens: number;
  repeat_penalty: number;
}

export interface SystemPrompts {
  channel: string;
  scene: string;
}

export interface Features {
  pdf_as_image: boolean;
  vision_enabled: boolean;
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

export const getServiceStatus = () => request<ServiceStatus>('/settings/service');
