/** 全局状态管理 — Zustand */
import { create } from 'zustand';
import {
  listScenes,
  createScene,
  updateScene,
  deleteScene,
  listPlazaScenes,
  listWorkshopScenes,
  publishScene,
  exportScene,
  importScene,
  getThinkingMap,
  addNode,
  updateNode,
  deleteNode,
  convergeMap,
  prioritizeMap,
  getQueue,
  getFocusQueue,
  reflectNode,
  sendMessage,
  listSceneMessages,
  sendSceneMessageStream,
  deleteMessage as apiDeleteMessage,
  regenerateMessage as apiRegenerateMessage,
  newSceneSession as apiNewSceneSession,
  batchDeleteMessages,
  clearSceneMessages,
  listSceneSessions,
  sendChannelMessageStream,
  uploadFile,
  SceneSession,
  listChannels,
  createChannel,
  updateChannel,
  deleteChannel,
  clearChannelMessages,
  sendChannelMessage,
  listChannelMessages,
  sendChannelMessageStream,
  compressChannelHistory,
  listActionMaps,
  getActionMap,
  createActionMap,
  updateActionMapStatus,
  deleteActionMap,
  generateActionMap,
  generateActionMapStream,
  Scene,
  ThinkingMap,
  ThinkNode,
  Message,
  Channel,
  StreamEvent,
  ToolCard,
  ActionMap as ActionMapType,
  ActionMapStreamEvent,
  ToolLog,
  getSettings,
  updateSettings,
  getServiceStatus,
  SettingsData,
  ServiceStatus,
  RouteConfig,
  DashboardQueueItem,
  DashboardReflectItem, // 🆕 Schema v0.7
  getDashboardQueue,
  getDashboardReflect,
  getDashboardStatus, // 🆕 Schema v0.7
  activateSession, // 🆕 Schema v1.1: Session 管理
} from '../api/client';

export type ViewPage =
  | 'chat'
  | 'plaza'
  | 'workshop'
  | 'tools'
  | 'capability-verify'
  | 'skills'
  | 'memory'
  | 'dashboard'
  | 'outputs'
  | 'delegate-results'
  | 'secret-garden'
  | 'settings'
  | 'workbench';

/** 从 settings 读取每次加载的聊天记录条数（默认 4） */
function getMsgLimit(): number {
  try {
    const s = useStore.getState().settingsData;
    return s?.features?.message_load_count ?? 4;
  } catch {
    return 4;
  }
}

/** per-entity 消息存储单元 */
export interface EntityMessages {
  messages: Message[];
  hasOlder: boolean;
  totalCount: number;
  loading: boolean;
}

/** 生成 per-entity key：场景/频道/默认闲聊 */
export function entityKey(entityType: 'scene' | 'channel' | 'default', id?: string): string {
  if (entityType === 'default') return 'default';
  return `${entityType}:${id}`;
}

/** 空的 EntityMessages 默认值 */
function emptyEntity(): EntityMessages {
  return { messages: [], hasOlder: false, totalCount: 0, loading: false };
}

interface AppState {
  view: ViewPage;
  setView: (v: ViewPage) => void;

  currentScene: Scene | null;
  setCurrentScene: (s: Scene | null) => void;

  // ═══ 用户输入背景设定 ═══
  userContext: string;
  loadUserContext: (sceneId: string) => Promise<void>;
  saveUserContext: (sceneId: string, content: string) => Promise<void>;

  // ═══ Thinking Map ═══
  thinkingMap: ThinkingMap | null;
  loadThinkingMap: (sceneId: string) => Promise<void>;

  drawerOpen: boolean;
  openDrawer: () => void;
  closeDrawer: () => void;
  toggleNodeActionable: (nodeId: string, actionable: boolean) => Promise<void>;

  // ═══ Agent Loop v1 ═══
  updateNodeStatus: (nodeId: string, status: string) => Promise<void>;
  updateNodePriority: (nodeId: string, priority: number | null) => Promise<void>;
  updateNodeQueueOrder: (nodeId: string, queueOrder: number | null) => Promise<void>;
  updateNodeDependsOn: (nodeId: string, dependsOn: string[]) => Promise<void>;
  convergeThinkingMap: () => Promise<any>;
  prioritizeThinkingMap: () => Promise<any>;
  getPriorityQueue: () => Promise<any>;
  getFocusQueue: (limit?: number) => Promise<any>;
  reflectNode: (
    nodeId: string,
    resultSummary: string,
    options?: {
      newDiscoveries?: string[];
      isSuccess?: boolean;
    }
  ) => Promise<any>;
  focusQueue: any[];

  // ═══ Action Map ═══
  actionMaps: ActionMapType[];
  currentActionMap: ActionMapType | null;
  actionMapDrawerOpen: boolean;
  loadActionMaps: (thinkMapId: string) => Promise<void>;
  setCurrentActionMap: (m: ActionMapType | null) => void;
  openActionMapDrawer: () => void;
  closeActionMapDrawer: () => void;
  updateActionMapStatusAndReload: (id: string, status: string) => Promise<void>;
  deleteActionMapAndReload: (id: string) => Promise<void>;
  generateActionMapAndReload: (thinkNodeId: string) => Promise<void>;

  // ═══ per-entity 消息（取代场景+频道分开的两套） ═══
  messagesByEntity: Record<string, EntityMessages>;
  currentSessionId: string | null; // 场景当前会话 ID
  sessions: SceneSession[]; // 历史会话列表
  loadSceneMessages: (sceneId: string) => Promise<void>;
  loadOlderMessages: (sceneId: string) => Promise<void>;
  sendSceneMsg: (
    sceneId: string,
    content: string,
    attachments?: Attachment[],
    skipOptimistic?: boolean
  ) => Promise<void>;
  _retryCount: Record<string, number>;
  _retryStream: (
    sceneKey: string,
    entityId: string,
    content: string,
    tempAiId: string,
    attachments?: Attachment[]
  ) => Promise<void>;
  newSceneSession: (sceneId: string) => Promise<string | null>; // 开始新会话
  batchDeleteMsgs: (ids: string[]) => Promise<void>; // 批量删除
  clearSceneMsgs: (sceneId: string) => Promise<void>; // 一键清空
  loadSceneSessions: (sceneId: string) => Promise<void>; // 加载会话列表
  switchSceneSession: (sessionId: string | null) => void; // 切换会话

  // ═══ 频道 ═══
  channels: Channel[];
  currentChannel: Channel | null;
  loadChannels: () => Promise<void>;
  createChannelAndReload: (name: string) => Promise<Channel>;
  updateChannelAndReload: (id: string, data: { name?: string; pinned?: boolean }) => Promise<void>;
  deleteChannelAndReload: (id: string) => Promise<void>;
  clearChannelHistory: (id: string) => Promise<void>;
  setCurrentChannel: (c: Channel) => void;

  // ═══ 频道消息（分页 — 已统一为 messagesByEntity） ═══
  loadChannelMessages: (channelId: string) => Promise<void>;
  loadOlderChannelMessages: (channelId: string) => Promise<void>;
  sendChannelMsg: (channelId: string, content: string, attachments?: Attachment[]) => Promise<void>;

  // ═══ 流式状态 ═══
  isGenerating: boolean;
  generatingEntityId: string | null; // 当前在生成的实体ID（场景/频道），null=无
  currentModelName: string | null; // 当前使用的模型名（来自 SSE model_info 事件）
  contextUsage: {
    totalTokens: number;
    maxTokens: number;
    percentage: number;
    usageStr: string;
    progressBar: string;
    historyCount: number;
  } | null;
  capacityWarning: { message: string; percentage: number } | null;
  currentToolCards: ToolCard[]; // 当前 AI 回复的工具卡片数据
  currentToolLogs: ToolLog[]; // 当前工具执行记录（纯前端，不存库）
  lastError: string | null; // 最后一次 SSE 错误消息（ChatView 展示横幅）

  // 🆕 Schema v0.7: 仪表盘
  priorityQueue: DashboardQueueItem[];
  reflectTimeline: DashboardReflectItem[];
  dashboardPhase: string; // diverge | converge | sort | focus | reflect
  dashboardLoopCount: number;
  dashboardStepCount: number;
  loadDashboardQueue: (sceneId: string) => Promise<void>;
  loadDashboardReflect: (sceneId: string) => Promise<void>;
  loadDashboardStatus: (sceneId: string) => Promise<void>;
  mindMapOpen: boolean;
  toggleMindMap: () => void;

  // ═══ 消息操作 ═══
  deleteMsg: (messageId: string) => Promise<void>;
  regenerateMsg: (messageId: string) => Promise<void>;
  reloadCurrentMessages: () => Promise<void>;

  // ═══ 系统设置 ═══
  settingsData: SettingsData | null;
  serviceStatus: ServiceStatus | null;
  settingsDrawerOpen: boolean;
  settingsLoading: boolean;
  openSettingsDrawer: () => void;
  closeSettingsDrawer: () => void;
  loadSettings: () => Promise<void>;
  refreshServiceStatus: () => Promise<void>;
  updateSettingsPartial: (data: Record<string, any>) => Promise<boolean>;

  // ═══ 场景广场 / 工坊 ═══
  plazaScenes: Scene[];
  workshopScenes: Scene[];
  loadingPlaza: boolean;
  loadingWorkshop: boolean;
  loadPlazaScenes: (params?: { category?: string; q?: string }) => Promise<void>;
  loadWorkshopScenes: (params?: { category?: string; project_id?: string }) => Promise<void>;
  publishSceneVersion: (
    sceneId: string,
    version: string,
    changelog?: string
  ) => Promise<Scene | null>;

  // ═══ 工作台 ═══
  scenes: Scene[];
  loadingScenes: boolean;
  loadScenes: () => Promise<void>;
  createSceneModalOpen: boolean;
  setCreateSceneModalOpen: (v: boolean) => void;

  // ═══ 上下文压缩 ═══
  compressChannel: (channelId: string) => Promise<string | null>;

  // ═══ AI 角色动画 ═══
  agentStatus: AgentStatus;
  agentMessage: string;
  agentHidden: boolean;
  agentSpeaking: boolean; // 🆕 Avatar 说话状态（工作台）
  setAgentStatus: (s: AgentStatus) => void;
  setAgentMessage: (m: string) => void;
  setAgentHidden: (h: boolean) => void;
  toggleAgentHidden: () => void;
  setAgentSpeaking: (s: boolean) => void; // 🆕
}

export type AgentStatus =
  | 'idle'
  | 'greeting'
  | 'thinking'
  | 'working'
  | 'analyzing'
  | 'done'
  | 'error'
  | 'notify'
  | 'resting'
  | 'angry'
  | 'laugh'
  | 'sad';

export const useStore = create<AppState>((set, get) => ({
  view: 'chat', // 默认进入聊天视图
  setView: (v) => set({ view: v, contextUsage: null, capacityWarning: null }),
  isGenerating: false,
  generatingEntityId: null,
  currentModelName: null,
  contextUsage: null,
  capacityWarning: null,
  currentToolCards: [],
  currentToolLogs: [],
  lastError: null,
  _retryCount: {} as Record<string, number>,

  // 🆕 Schema v0.7: 仪表盘初始值
  priorityQueue: [],
  reflectTimeline: [],
  dashboardPhase: 'diverge',
  dashboardLoopCount: 0,
  dashboardStepCount: 0,
  mindMapOpen: false,
  toggleMindMap: () => set((s) => ({ mindMapOpen: !s.mindMapOpen })),

  // ═══ AI 角色动画默认值 ═══
  agentStatus: 'idle' as AgentStatus,
  agentMessage: '在线待命',
  agentHidden: false,
  agentSpeaking: false, // 🆕
  setAgentStatus: (s) => set({ agentStatus: s }),
  setAgentMessage: (m) => set({ agentMessage: m }),
  setAgentHidden: (h) => set({ agentHidden: h }),
  toggleAgentHidden: () => set((s) => ({ agentHidden: !s.agentHidden })),
  setAgentSpeaking: (s) => set({ agentSpeaking: s }),

  currentScene: null,
  setCurrentScene: async (s) => {
    // 切换场景时只换指针，不重置消息（per-entity 隔离）
    set({ currentScene: s, contextUsage: null, capacityWarning: null, currentSessionId: null });
    if (s) {
      get().loadUserContext(s.id);
      try {
        // 🆕 Schema v1.1: 激活 session，必须存 session_id 否则 session 隔离不生效
        const session = await activateSession('scene', s.id, s.name);
        set({ currentSessionId: session.id });
      } catch (e) {
        console.error('[store] setCurrentScene activateSession failed:', e);
      }
    }
  },
  userContext: '',
  loadUserContext: async (sceneId) => {
    try {
      const scenes = await listScenes();
      const scene = scenes.find((s) => s.id === sceneId);
      if (scene) {
        set({ userContext: scene.user_context || '' });
      }
    } catch (e) {
      console.error('[store] loadUserContext failed:', e);
    }
  },
  saveUserContext: async (sceneId, content) => {
    try {
      const trimmed = content.trim();
      const scene = await updateScene(sceneId, { user_context: trimmed || null });
      set({ userContext: scene.user_context || '' });
    } catch (e) {
      console.error('[store] saveUserContext failed:', e);
    }
  },

  // ═══ Thinking Map ═══
  thinkingMap: null,
  loadThinkingMap: async (sceneId) => {
    try {
      const tm = await getThinkingMap(sceneId);
      set({ thinkingMap: tm });
    } catch (e) {
      console.error('[store] loadThinkingMap failed:', e);
    }
  },

  drawerOpen: false,
  openDrawer: () => set({ drawerOpen: true }),
  closeDrawer: () => set({ drawerOpen: false }),
  toggleNodeActionable: async (nodeId, actionable) => {
    await updateNode(nodeId, { actionable });
    const state = get();
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
  },

  // ═══ Agent Loop v1 ═══
  updateNodeStatus: async (nodeId, status) => {
    await updateNode(nodeId, { status });
    const state = get();
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
  },
  updateNodePriority: async (nodeId, priority) => {
    await updateNode(nodeId, { priority });
    const state = get();
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
  },
  updateNodeQueueOrder: async (nodeId, queue_order) => {
    await updateNode(nodeId, { queue_order });
    const state = get();
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
  },
  updateNodeDependsOn: async (nodeId, depends_on) => {
    await updateNode(nodeId, { depends_on });
    const state = get();
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
  },
  focusQueue: [],
  convergeThinkingMap: async () => {
    const state = get();
    if (!state.thinkingMap) return;
    const result = await convergeMap(state.thinkingMap.id);
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
    return result;
  },
  divergeThinkingMap: async (opts?: { context?: string; force?: boolean }) => {
    const state = get();
    if (!state.thinkingMap) return;
    const result = await divergeMap(state.thinkingMap.id, opts);
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
    return result;
  },

  // 🆕 Schema v0.7: 仪表盘数据加载
  loadDashboardQueue: async (sceneId) => {
    try {
      const result = await getDashboardQueue(sceneId);
      set({ priorityQueue: result.items || [] });
    } catch (e) {
      console.error('[store] loadDashboardQueue failed:', e);
    }
  },
  loadDashboardReflect: async (sceneId) => {
    try {
      const result = await getDashboardReflect(sceneId);
      set({ reflectTimeline: result.items || [] });
    } catch (e) {
      console.error('[store] loadDashboardReflect failed:', e);
    }
  },
  loadDashboardStatus: async (sceneId) => {
    try {
      const status = await getDashboardStatus(sceneId);
      if (status.current_task) {
        set({ dashboardPhase: 'focus' });
      }
    } catch (e) {
      console.error('[store] loadDashboardStatus failed:', e);
    }
  },
  prioritizeThinkingMap: async () => {
    const state = get();
    if (!state.thinkingMap) return;
    const result = await prioritizeMap(state.thinkingMap.id);
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
    return result;
  },
  getPriorityQueue: async () => {
    const state = get();
    if (!state.thinkingMap) return null;
    return getQueue(state.thinkingMap.id);
  },
  getFocusQueue: async (limit = 5) => {
    const state = get();
    if (!state.thinkingMap) return null;
    const result = await getFocusQueue(state.thinkingMap.id, limit);
    set({ focusQueue: result.items || [] });
    return result;
  },
  reflectNode: async (nodeId, resultSummary, options = {}) => {
    const state = get();
    if (!state.thinkingMap) return null;
    const result = await reflectNode(state.thinkingMap.id, {
      node_id: nodeId,
      result_summary: resultSummary,
      new_discoveries: options.newDiscoveries || [],
      is_success: options.isSuccess !== false,
    });
    if (state.currentScene) {
      await state.loadThinkingMap(state.currentScene.id);
    }
    return result;
  },

  // ═══ Action Map ═══
  actionMaps: [],
  currentActionMap: null,
  actionMapDrawerOpen: false,
  loadActionMaps: async (thinkMapId) => {
    try {
      const maps = await listActionMaps({ think_map_id: thinkMapId });
      set({ actionMaps: maps });
    } catch (e) {
      console.error('[store] loadActionMaps failed:', e);
    }
  },
  setCurrentActionMap: (m) => set({ currentActionMap: m }),
  openActionMapDrawer: () => set({ actionMapDrawerOpen: true }),
  closeActionMapDrawer: () => set({ actionMapDrawerOpen: false, currentActionMap: null }),
  updateActionMapStatusAndReload: async (id, status) => {
    await updateActionMapStatus(id, status);
    const state = get();
    if (state.thinkingMap) {
      await state.loadActionMaps(state.thinkingMap.id);
    }
  },
  deleteActionMapAndReload: async (id) => {
    await deleteActionMap(id);
    const state = get();
    if (state.thinkingMap) {
      await state.loadActionMaps(state.thinkingMap.id);
      const sceneId = state.currentScene?.id;
      if (sceneId) await state.loadThinkingMap(sceneId);
    }
  },
  generateActionMapAndReload: async (thinkNodeId) => {
    await generateActionMap(thinkNodeId);
    const state = get();
    if (state.thinkingMap) {
      await state.loadActionMaps(state.thinkingMap.id);
      const sceneId = state.currentScene?.id;
      if (sceneId) await state.loadThinkingMap(sceneId);
    }
    // 自动打开 Action Map 抽屉查看结果
    set({ actionMapDrawerOpen: true });
  },

  // ═══ per-entity 消息 ═══
  messagesByEntity: {},
  currentSessionId: null,
  sessions: [],
  loadSceneMessages: async (sceneId) => {
    try {
      const key = entityKey('scene', sceneId);
      set((state) => ({
        messagesByEntity: {
          ...state.messagesByEntity,
          [key]: { ...(state.messagesByEntity[key] || emptyEntity()), loading: true },
        },
      }));
      const sessionId = get().currentSessionId;
      const result = await listSceneMessages(sceneId, sessionId || undefined, getMsgLimit());
      set((state) => ({
        messagesByEntity: {
          ...state.messagesByEntity,
          [key]: {
            messages: result.messages,
            hasOlder: result.has_more,
            totalCount: result.total,
            loading: false,
          },
        },
      }));
    } catch (e) {
      console.error('[store] loadSceneMessages failed:', e);
      set((state) => {
        const key = entityKey('scene', sceneId);
        const cur = state.messagesByEntity[key];
        return cur
          ? { messagesByEntity: { ...state.messagesByEntity, [key]: { ...cur, loading: false } } }
          : {};
      });
    }
  },
  loadOlderMessages: async (sceneId) => {
    const state = get();
    const key = entityKey('scene', sceneId);
    const em = state.messagesByEntity[key];
    if (!em || !em.messages.length || !em.hasOlder || em.loading) return;
    try {
      set((state) => {
        const cur = state.messagesByEntity[key];
        return cur
          ? { messagesByEntity: { ...state.messagesByEntity, [key]: { ...cur, loading: true } } }
          : {};
      });
      const oldestId = em.messages[0].id;
      const sessionId = state.currentSessionId;
      const result = await listSceneMessages(
        sceneId,
        sessionId || undefined,
        getMsgLimit(),
        oldestId
      );
      set((state) => {
        const cur = state.messagesByEntity[key];
        return {
          messagesByEntity: {
            ...state.messagesByEntity,
            [key]: {
              messages: [...result.messages, ...(cur?.messages || em.messages)],
              hasOlder: result.has_more,
              totalCount: result.total,
              loading: false,
            },
          },
        };
      });
    } catch (e) {
      console.error('[store] loadOlderMessages failed:', e);
      set((state) => {
        const cur = state.messagesByEntity[key];
        return cur
          ? { messagesByEntity: { ...state.messagesByEntity, [key]: { ...cur, loading: false } } }
          : {};
      });
    }
  },
  sendSceneMsg: async (sceneId, content, attachments, skipOptimistic) => {
    // 0. 乐观更新：立即插入临时用户消息 + 空壳 AI 消息
    const tempUserId = 'temp-user-' + Date.now();
    const tempUserMsg: Message = {
      id: tempUserId,
      scene_id: sceneId,
      channel_id: null,
      session_id: null,
      role: 'user',
      content,
      map_ref: null,
      model: null,
      attachments,
      created_at: new Date().toISOString(),
    };

    const tempAiId = 'temp-ai-' + Date.now();
    const tempAiMsg: Message = {
      id: tempAiId,
      scene_id: sceneId,
      channel_id: null,
      session_id: null,
      role: 'ai',
      content: '🤔 正在分析...',
      map_ref: null,
      model: null,
      created_at: new Date().toISOString(),
    };

    const sceneKey = entityKey('scene', sceneId);

    if (!skipOptimistic) {
      set((state) => ({
        isGenerating: true,
        generatingEntityId: sceneId,
        currentToolCards: [],
        currentToolLogs: [],
        messagesByEntity: {
          ...state.messagesByEntity,
          [sceneKey]: {
            ...(state.messagesByEntity[sceneKey] || emptyEntity()),
            messages: [
              ...(state.messagesByEntity[sceneKey]?.messages || []),
              tempUserMsg,
              tempAiMsg,
            ],
          },
        },
      }));
    } else {
      set((state) => ({
        isGenerating: true,
        generatingEntityId: sceneId,
        currentToolCards: [],
        currentToolLogs: [],
        messagesByEntity: {
          ...state.messagesByEntity,
          [sceneKey]: {
            ...(state.messagesByEntity[sceneKey] || emptyEntity()),
            messages: [...(state.messagesByEntity[sceneKey]?.messages || []), tempAiMsg],
          },
        },
      }));
    }

    try {
      // 🆕 新轮 Agent Loop 开始，清空上一轮的执行追踪数据
      const { useTraceStore } = await import('../stores/traceStore');
      useTraceStore.getState().clearTraces(sceneId);

      const sessionId = get().currentSessionId;
      const stream = sendSceneMessageStream(sceneId, content, sessionId || undefined, attachments);

      for await (const event of stream) {
        if (event.type === 'tool_cards') {
          set({ currentToolCards: event.cards });
        } else if (event.type === 'tool_status') {
          set((state) => ({
            currentToolLogs: [
              ...state.currentToolLogs,
              {
                tool: event.tool,
                status: event.status,
                success: event.success,
                message: event.message,
              },
            ],
          }));
          // 🆕 Thought Stream: 思考流事件
        } else if (event.type === 'thought') {
          const thoughtId = 'thought-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
          set((state) => ({
            messagesByEntity: {
              ...state.messagesByEntity,
              [sceneKey]: {
                ...(state.messagesByEntity[sceneKey] || emptyEntity()),
                messages: [
                  ...(state.messagesByEntity[sceneKey]?.messages || []),
                  {
                    id: thoughtId,
                    scene_id: sceneId,
                    channel_id: null,
                    session_id: null,
                    role: 'thought' as any,
                    content: event.content,
                    map_ref: null,
                    model: null,
                    created_at: new Date().toISOString(),
                  },
                ],
              },
            },
          }));
        } else if (event.type === 'model_info') {
          set({ currentModelName: event.model, contextUsage: null, capacityWarning: null });
        } else if (event.type === 'context_info') {
          set({
            contextUsage: {
              totalTokens: event.total_tokens,
              maxTokens: event.max_tokens,
              percentage: event.percentage,
              usageStr: event.usage_str,
              progressBar: event.progress_bar,
              historyCount: event.history_count,
            },
          });
        } else if (event.type === 'capacity_warning') {
          set({
            capacityWarning: { message: event.message, percentage: event.percentage },
          });
        } else if (event.type === 'user_msg') {
          set((state) => ({
            messagesByEntity: {
              ...state.messagesByEntity,
              [sceneKey]: {
                ...(state.messagesByEntity[sceneKey] || emptyEntity()),
                messages: (state.messagesByEntity[sceneKey]?.messages || []).map((m) =>
                  m.id === tempUserId ? { ...m, id: event.id, created_at: event.created_at } : m
                ),
              },
            },
          }));
        } else if (event.type === 'token') {
          set((state) => ({
            messagesByEntity: {
              ...state.messagesByEntity,
              [sceneKey]: {
                ...(state.messagesByEntity[sceneKey] || emptyEntity()),
                messages: (state.messagesByEntity[sceneKey]?.messages || []).map((m) =>
                  m.id === tempAiId
                    ? {
                        ...m,
                        content:
                          m.content === '🤔 正在分析...' ? event.token : m.content + event.token,
                      }
                    : m
                ),
              },
            },
          }));
          // 打断 React 18 批量化，让每个 token 独立渲染
          await new Promise((r) => setTimeout(r, 0));
        } else if (event.type === 'done') {
          set((state) => ({
            isGenerating: false,
            generatingEntityId: null,
            messagesByEntity: {
              ...state.messagesByEntity,
              [sceneKey]: {
                ...(state.messagesByEntity[sceneKey] || emptyEntity()),
                messages: (state.messagesByEntity[sceneKey]?.messages || []).map((m) =>
                  m.id === tempAiId
                    ? {
                        ...m,
                        id: event.id,
                        content: event.content,
                        created_at: event.created_at,
                        model: event.model || null,
                        toolCards: state.currentToolCards,
                      }
                    : m
                ),
              },
            },
          }));
          // 🆕 Schema v1.1: Token 用量核算
          if (event.usage && currentSessionId) {
            try {
              const { accumulateTokens } = await import('../api/client');
              await accumulateTokens(currentSessionId, event.usage);
            } catch (e) {
              console.warn('[store] accumulateTokens failed:', e);
            }
          }
          // 流式完成后刷新 Thinking Map
          get().loadThinkingMap(sceneId);
        } else if (event.type === 'child:started') {
          const { setDelegateTasks } = await import('../components/DelegationMonitor');
          setDelegateTasks(event.tasks || []);
        } else if (event.type === 'child:done') {
          const { setDelegateResults } = await import('../components/DelegationMonitor');
          setDelegateResults(event.children || []);
        } else if (event.type === 'asset') {
          set((state) => ({
            messagesByEntity: {
              ...state.messagesByEntity,
              [sceneKey]: {
                ...(state.messagesByEntity[sceneKey] || emptyEntity()),
                messages: [
                  ...(state.messagesByEntity[sceneKey]?.messages || []),
                  {
                    id: event.asset_id || 'asset-' + Date.now(),
                    scene_id: sceneId,
                    channel_id: null,
                    session_id: null,
                    role: 'ai',
                    content: '',
                    asset: { type: event.type, title: event.title, content: event.content },
                    map_ref: null,
                    model: null,
                    created_at: new Date().toISOString(),
                  },
                ],
              },
            },
          }));
        } else if (event.type === 'output:created') {
          // 🆕 自动提取的 HTML 产出 — 附加到最后一条 AI 消息
          set((state) => {
            const em = state.messagesByEntity[sceneKey];
            const msgs = em ? [...em.messages] : [];
            for (let i = msgs.length - 1; i >= 0; i--) {
              if (msgs[i].role === 'ai' && !msgs[i].id.startsWith('temp-')) {
                msgs[i] = {
                  ...msgs[i],
                  outputRef: {
                    outputId: event.output_id,
                    title: event.title,
                    filePath: event.file_path,
                  },
                };
                break;
              }
            }
            return {
              messagesByEntity: {
                ...state.messagesByEntity,
                [sceneKey]: {
                  ...(state.messagesByEntity[sceneKey] || emptyEntity()),
                  messages: msgs,
                },
              },
            };
          });
        } else if (event.type === 'thinking_map:diverged') {
          // 自动发散完成，刷新 Thinking Map
          get().loadThinkingMap(sceneId);
          // 🆕 Schema v0.7: 仪表盘 SSE 事件
        } else if (event.type === 'dashboard:converge') {
          // 收敛完成，刷新 PV 和 TM
          set({ dashboardPhase: 'sort' });
          get().loadDashboardQueue(sceneId);
          get().loadThinkingMap(sceneId);
        } else if (event.type === 'dashboard:queue_update') {
          set({
            priorityQueue: event.items || [],
            dashboardPhase: 'focus',
          });
        } else if (event.type === 'dashboard:reflect') {
          // 新反馈记录，刷新反射时间线
          const icon = event.tool_success ? '✅' : '🔴';
          const newItem: DashboardReflectItem = {
            id: Date.now().toString(),
            type: event.tool_success ? 'success' : 'fail',
            icon,
            title: event.tool_success ? `完成: ${event.tool}` : `失败: ${event.tool}`,
            detail: event.result_preview,
            created_at: new Date().toISOString(),
          };
          set((s) => ({
            reflectTimeline: [...s.reflectTimeline, newItem].slice(-20),
            dashboardLoopCount: s.dashboardLoopCount + 1,
            dashboardStepCount: s.dashboardStepCount + 1,
          }));
        } else if (event.type === 'error') {
          set((state) => ({
            isGenerating: false,
            generatingEntityId: null,
            lastError: event.message,
            currentToolCards: [],
            currentToolLogs: [],
            messagesByEntity: {
              ...state.messagesByEntity,
              [sceneKey]: {
                ...(state.messagesByEntity[sceneKey] || emptyEntity()),
                messages: (state.messagesByEntity[sceneKey]?.messages || []).map((m) =>
                  m.id === tempAiId ? { ...m, content: `❌ ${event.message}` } : m
                ),
              },
            },
          }));
          // 🆕 高危命令审批
        } else if (event.type === 'command_approval') {
          const { showApproval } = await import('../stores/approvalStore');
          showApproval(event);
          // 🆕 Schema v1.6: Agent Loop 追踪事件
        } else if (event.type === 'agent_trace') {
          const { useTraceStore } = await import('../stores/traceStore');
          const ts = useTraceStore.getState();

          if (event.trace_type === 'tool_start') {
            // 新建 trace 事件
            ts.appendTrace(sceneId, {
              id: `${event.trace_type}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              step: event.trace_step ?? 0,
              eventType: 'tool_start',
              tool: event.tool,
              args: event.args,
              toolCallId: event.tool_call_id,
              receivedAt: new Date().toISOString(),
            });
          } else if (event.trace_type === 'tool_done') {
            // 更新对应 tool_start 到完成态
            ts.updateToolDone(sceneId, event.tool_call_id || '', event.result, 0);
          } else if (event.trace_type === 'tool_error') {
            ts.updateToolError(sceneId, event.tool_call_id || '', event.error || '执行失败');
          } else if (event.trace_type === 'thinking') {
            ts.appendTrace(sceneId, {
              id: `thinking-${Date.now()}`,
              step: event.trace_step ?? 0,
              eventType: 'thinking',
              text: event.text,
              receivedAt: new Date().toISOString(),
            });
          }
          // 🆕 Schema v1.7: 子 Agent trace 事件（delegate_task 内部步骤）
        } else if (
          event.type === 'sub_tool_start' ||
          event.type === 'sub_tool_done' ||
          event.type === 'sub_tool_error' ||
          event.type === 'sub_thinking' ||
          event.type === 'sub_done'
        ) {
          const { useTraceStore } = await import('../stores/traceStore');
          const ts = useTraceStore.getState();
          const subTaskId = event.sub_task_id;
          if (!subTaskId) {
            console.warn('[store] sub_trace missing sub_task_id');
          } else {
            const base = {
              id: `${event.type}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              subTaskId,
              receivedAt: new Date().toISOString(),
            };

            if (event.type === 'sub_thinking') {
              ts.appendSubTrace(sceneId, subTaskId, {
                ...base,
                subStep: event.sub_step ?? 0,
                eventType: 'sub_thinking',
                text: event.text || '',
              });
            } else if (event.type === 'sub_tool_start') {
              ts.appendSubTrace(sceneId, subTaskId, {
                ...base,
                subStep: event.sub_step ?? 0,
                eventType: 'sub_tool_start',
                tool: event.tool,
                args: event.args,
                toolCallId: event.tool_call_id || '',
              });
            } else if (event.type === 'sub_tool_done') {
              ts.appendSubTrace(sceneId, subTaskId, {
                ...base,
                subStep: event.sub_step ?? 0,
                eventType: 'sub_tool_done',
                tool: event.tool,
                result: event.result,
                durationMs: event.duration_ms,
              });
            } else if (event.type === 'sub_tool_error') {
              ts.appendSubTrace(sceneId, subTaskId, {
                ...base,
                subStep: event.sub_step ?? 0,
                eventType: 'sub_tool_error',
                tool: event.tool,
                error: event.error || '子工具执行失败',
              });
            } else if (event.type === 'sub_done') {
              ts.appendSubTrace(sceneId, subTaskId, {
                ...base,
                subStep: event.sub_step ?? 0,
                eventType: 'sub_done',
                summary: event.summary || '',
              });
            }
          }
        }
      }
    } catch (e) {
      console.error('[store] sendSceneMsg stream failed:', e);
      const errMsg = (e as any)?.message || String(e);

      // 🛡 自动重试：如果后端正在热更新，等几秒后自动重发
      if (
        errMsg.includes('超时') ||
        errMsg.includes('Failed to fetch') ||
        errMsg.includes('NetworkError')
      ) {
        await get()._retryStream(sceneKey, sceneId, content, tempAiId, attachments);
        return;
      }

      set((state) => ({
        isGenerating: false,
        generatingEntityId: null,
        messagesByEntity: {
          ...state.messagesByEntity,
          [sceneKey]: {
            ...(state.messagesByEntity[sceneKey] || emptyEntity()),
            messages: (state.messagesByEntity[sceneKey]?.messages || []).map((m) =>
              m.id === tempAiId ? { ...m, content: `❌ ${errMsg}` } : m
            ),
          },
        },
      }));
    }
  },

  // ═══ 自动重试：后端热更新后恢复发送 ═══
  _retryStream: async (sceneKey, entityId, content, tempAiId, attachments) => {
    const maxRetries = 3;
    const state = get();
    state._retryCount[entityId] = (state._retryCount[entityId] || 0) + 1;
    const attempt = state._retryCount[entityId];

    if (attempt > maxRetries) {
      get()._retryCount[entityId] = 0;
      set((s) => ({
        isGenerating: false,
        generatingEntityId: null,
        messagesByEntity: {
          ...s.messagesByEntity,
          [sceneKey]: {
            ...(s.messagesByEntity[sceneKey] || emptyEntity()),
            messages: (s.messagesByEntity[sceneKey]?.messages || []).map((m) =>
              m.id === tempAiId ? { ...m, content: '❌ 后端服务不稳定，请稍后重试' } : m
            ),
          },
        },
      }));
      return;
    }

    // 显示重试中
    set((s) => ({
      messagesByEntity: {
        ...s.messagesByEntity,
        [sceneKey]: {
          ...(s.messagesByEntity[sceneKey] || emptyEntity()),
          messages: (s.messagesByEntity[sceneKey]?.messages || []).map((m) =>
            m.id === tempAiId
              ? {
                  ...m,
                  content: `🔄 后端热更新中，${attempt <= 1 ? '自动重试' : '第' + attempt + '次重试'}...`,
                }
              : m
          ),
        },
      },
    }));

    // 等待 3 秒后检查后端健康状态
    await new Promise((r) => setTimeout(r, 3000));
    try {
      const resp = await fetch('/api/health', { signal: AbortSignal.timeout(5000) });
      if (!resp.ok) throw new Error('not ready');
      await resp.json();
    } catch {
      // 后端还没起来，递归重试
      await get()._retryStream(sceneKey, entityId, content, tempAiId, attachments);
      return;
    }

    // 后端已恢复，清除旧的 AI 消息，重新发送
    get()._retryCount[entityId] = 0;
    set((s) => ({
      isGenerating: false,
      generatingEntityId: null,
      messagesByEntity: {
        ...s.messagesByEntity,
        [sceneKey]: {
          ...(s.messagesByEntity[sceneKey] || emptyEntity()),
          messages: (s.messagesByEntity[sceneKey]?.messages || []).filter((m) => m.id !== tempAiId),
        },
      },
    }));
    // 重新发送（skipOptimistic=true 避免重复插用户消息）
    // 判断是场景还是频道，用对应的方法
    if (entityId.startsWith('ch-')) {
      await get().sendChannelMsg(entityId, content, attachments);
    } else {
      await get().sendSceneMsg(entityId, content, attachments, true);
    }
  },

  // ═══ 频道 ═══
  channels: [],
  currentChannel: null,
  loadChannels: async () => {
    try {
      const chs = await listChannels();
      set({ channels: chs });
      // 自动选中默认频道
      if (!get().currentChannel && chs.length > 0) {
        set({ currentChannel: chs[0] });
      }
    } catch (e) {
      console.error('[store] loadChannels failed:', e);
    }
  },
  createChannelAndReload: async (name) => {
    const ch = await createChannel(name);
    await get().loadChannels();
    return ch;
  },
  updateChannelAndReload: async (id, data) => {
    await updateChannel(id, data);
    await get().loadChannels();
  },
  deleteChannelAndReload: async (id) => {
    await deleteChannel(id);
    await get().loadChannels();
    // 如果删的是当前频道，切回第一个
    if (get().currentChannel?.id === id) {
      const chs = get().channels.filter((c) => c.id !== id);
      const key = entityKey('channel', id);
      set((state) => {
        const { [key]: _, ...rest } = state.messagesByEntity;
        return { currentChannel: chs[0] || null, messagesByEntity: rest };
      });
    }
  },
  clearChannelHistory: async (id) => {
    await clearChannelMessages(id);
    if (get().currentChannel?.id === id) {
      set((state) => {
        const key = entityKey('channel', id);
        return { messagesByEntity: { ...state.messagesByEntity, [key]: emptyEntity() } };
      });
    }
  },
  setCurrentChannel: (c) => {
    // 切换频道时只换指针，不重置消息（per-entity 隔离）
    set({ currentChannel: c, contextUsage: null, capacityWarning: null });
    // 🆕 Schema v1.1: 激活 session（异步，不阻塞 UI）
    activateSession('channel', c.id, c.name).catch((e) =>
      console.error('[store] activateSession failed:', e)
    );
  },

  // ═══ 频道消息（分页 — 已统一） ═══
  channelMessagesLoading: false,
  loadChannelMessages: async (channelId) => {
    try {
      const key = entityKey('channel', channelId);
      set((state) => ({
        messagesByEntity: {
          ...state.messagesByEntity,
          [key]: { ...(state.messagesByEntity[key] || emptyEntity()), loading: true },
        },
      }));
      const result = await listChannelMessages(channelId, getMsgLimit());
      set((state) => ({
        messagesByEntity: {
          ...state.messagesByEntity,
          [key]: {
            messages: result.messages,
            hasOlder: result.has_more,
            totalCount: result.total,
            loading: false,
          },
        },
      }));
    } catch (e) {
      console.error('[store] loadChannelMessages failed:', e);
      set((state) => {
        const key = entityKey('channel', channelId);
        const cur = state.messagesByEntity[key];
        return cur
          ? { messagesByEntity: { ...state.messagesByEntity, [key]: { ...cur, loading: false } } }
          : {};
      });
    }
  },
  loadOlderChannelMessages: async (channelId) => {
    const state = get();
    const key = entityKey('channel', channelId);
    const em = state.messagesByEntity[key];
    if (!em || !em.messages.length || !em.hasOlder || em.loading) return;
    try {
      set((state) => {
        const cur = state.messagesByEntity[key];
        return cur
          ? { messagesByEntity: { ...state.messagesByEntity, [key]: { ...cur, loading: true } } }
          : {};
      });
      const oldestId = em.messages[0].id;
      const result = await listChannelMessages(channelId, getMsgLimit(), oldestId);
      set((state) => ({
        messagesByEntity: {
          ...state.messagesByEntity,
          [key]: {
            messages: [
              ...result.messages,
              ...(state.messagesByEntity[key]?.messages || em.messages),
            ],
            hasOlder: result.has_more,
            totalCount: result.total,
            loading: false,
          },
        },
      }));
    } catch (e) {
      console.error('[store] loadOlderChannelMessages failed:', e);
      set((state) => {
        const cur = state.messagesByEntity[key];
        return cur
          ? { messagesByEntity: { ...state.messagesByEntity, [key]: { ...cur, loading: false } } }
          : {};
      });
    }
  },
  sendChannelMsg: async (channelId, content, attachments) => {
    // 1. 乐观更新：立即插入临时用户消息
    const tempUserId = 'temp-user-' + Date.now();
    const tempUserMsg: Message = {
      id: tempUserId,
      scene_id: null,
      channel_id: channelId,
      session_id: null,
      role: 'user',
      content,
      map_ref: null,
      model: null,
      attachments,
      created_at: new Date().toISOString(),
    };

    // 2. 插入占位 AI 消息（空壳）
    const tempAiId = 'temp-ai-' + Date.now();
    const tempAiMsg: Message = {
      id: tempAiId,
      scene_id: null,
      channel_id: channelId,
      session_id: null,
      role: 'ai',
      content: '',
      map_ref: null,
      model: null,
      created_at: new Date().toISOString(),
    };

    const channelKey = entityKey('channel', channelId);

    set((state) => ({
      isGenerating: true,
      generatingEntityId: channelId,
      messagesByEntity: {
        ...state.messagesByEntity,
        [channelKey]: {
          ...(state.messagesByEntity[channelKey] || emptyEntity()),
          messages: [
            ...(state.messagesByEntity[channelKey]?.messages || []),
            tempUserMsg,
            tempAiMsg,
          ],
        },
      },
    }));

    try {
      const stream = sendChannelMessageStream(channelId, content, attachments);

      for await (const event of stream) {
        if (event.type === 'model_info') {
          set({ currentModelName: event.model, contextUsage: null, capacityWarning: null });
        } else if (event.type === 'context_info') {
          set({
            contextUsage: {
              totalTokens: event.total_tokens,
              maxTokens: event.max_tokens,
              percentage: event.percentage,
              usageStr: event.usage_str,
              progressBar: event.progress_bar,
              historyCount: event.history_count,
            },
          });
        } else if (event.type === 'capacity_warning') {
          set({
            capacityWarning: { message: event.message, percentage: event.percentage },
          });
        } else if (event.type === 'user_msg') {
          // 收到服务器确认的用户消息 → 替换临时 ID
          set((state) => ({
            messagesByEntity: {
              ...state.messagesByEntity,
              [channelKey]: {
                ...(state.messagesByEntity[channelKey] || emptyEntity()),
                messages: (state.messagesByEntity[channelKey]?.messages || []).map((m) =>
                  m.id === tempUserId
                    ? {
                        ...m,
                        id: event.id,
                        created_at: event.created_at,
                        attachments: event.attachments || m.attachments,
                      }
                    : m
                ),
              },
            },
          }));
        } else if (event.type === 'token') {
          // 逐 token 追加到 AI 消息
          set((state) => ({
            messagesByEntity: {
              ...state.messagesByEntity,
              [channelKey]: {
                ...(state.messagesByEntity[channelKey] || emptyEntity()),
                messages: (state.messagesByEntity[channelKey]?.messages || []).map((m) =>
                  m.id === tempAiId ? { ...m, content: m.content + event.token } : m
                ),
              },
            },
          }));
          // 打断 React 18 批量化，让每个 token 独立渲染
          await new Promise((r) => setTimeout(r, 0));
        } else if (event.type === 'done') {
          // 服务器保存完成 → 用真实 ID 替换占位
          set((state) => ({
            isGenerating: false,
            generatingEntityId: null,
            messagesByEntity: {
              ...state.messagesByEntity,
              [channelKey]: {
                ...(state.messagesByEntity[channelKey] || emptyEntity()),
                messages: (state.messagesByEntity[channelKey]?.messages || []).map((m) =>
                  m.id === tempAiId
                    ? {
                        ...m,
                        id: event.id,
                        content: event.content,
                        created_at: event.created_at,
                        model: event.model || null,
                      }
                    : m
                ),
              },
            },
          }));
        } else if (event.type === 'error') {
          set((state) => ({
            isGenerating: false,
            generatingEntityId: null,
            lastError: event.message,
            messagesByEntity: {
              ...state.messagesByEntity,
              [channelKey]: {
                ...(state.messagesByEntity[channelKey] || emptyEntity()),
                messages: (state.messagesByEntity[channelKey]?.messages || []).map((m) =>
                  m.id === tempAiId ? { ...m, content: `❌ ${event.message}` } : m
                ),
              },
            },
          }));
        }
      }
    } catch (e) {
      console.error('[store] sendChannelMsg stream failed:', e);
      set((state) => ({
        isGenerating: false,
        generatingEntityId: null,
        messagesByEntity: {
          ...state.messagesByEntity,
          [channelKey]: {
            ...(state.messagesByEntity[channelKey] || emptyEntity()),
            messages: (state.messagesByEntity[channelKey]?.messages || []).map((m) =>
              m.id === tempAiId ? { ...m, content: '❌ 网络请求失败，请重试' } : m
            ),
          },
        },
      }));
    }
  },

  // ═══ 上下文压缩 ═══
  compressChannel: async (channelId) => {
    try {
      const result = await compressChannelHistory(channelId);
      if (result.ok) {
        await get().loadChannelMessages(channelId);
        set({ capacityWarning: null });
        return result.summary || null;
      } else {
        console.error('[store] compress failed:', result.error);
        return null;
      }
    } catch (e) {
      console.error('[store] compressChannel error:', e);
      return null;
    }
  },

  // ═══ 消息操作 ═══
  deleteMsg: async (messageId) => {
    await apiDeleteMessage(messageId);
    await get().reloadCurrentMessages();
  },
  regenerateMsg: async (messageId) => {
    await apiRegenerateMessage(messageId);
    await get().reloadCurrentMessages();
  },
  reloadCurrentMessages: async () => {
    const state = get();
    if (state.currentScene) {
      await state.loadSceneMessages(state.currentScene.id);
    } else if (state.currentChannel) {
      await state.loadChannelMessages(state.currentChannel.id);
    }
  },
  newSceneSession: async (sceneId) => {
    try {
      const { session_id } = await apiNewSceneSession(sceneId);
      const key = entityKey('scene', sceneId);
      set((state) => ({
        currentSessionId: session_id,
        messagesByEntity: { ...state.messagesByEntity, [key]: emptyEntity() },
      }));
      // 新会话后刷新会话列表
      get().loadSceneSessions(sceneId);
      return session_id;
    } catch (e) {
      console.error('[store] newSceneSession failed:', e);
      return null;
    }
  },
  batchDeleteMsgs: async (ids) => {
    if (ids.length === 0) return;
    await batchDeleteMessages(ids);
    await get().reloadCurrentMessages();
  },
  clearSceneMsgs: async (sceneId) => {
    await clearSceneMessages(sceneId);
    const key = entityKey('scene', sceneId);
    set((state) => ({
      messagesByEntity: { ...state.messagesByEntity, [key]: emptyEntity() },
      currentSessionId: null,
    }));
    // 清空后刷新会话列表
    get().loadSceneSessions(sceneId);
  },
  loadSceneSessions: async (sceneId) => {
    try {
      const sessions = await listSceneSessions(sceneId);
      set({ sessions });
    } catch (e) {
      console.error('[store] loadSceneSessions failed:', e);
    }
  },
  switchSceneSession: (sessionId) => {
    const state = get();
    if (state.currentScene) {
      const key = entityKey('scene', state.currentScene.id);
      set({
        currentSessionId: sessionId,
        messagesByEntity: { ...state.messagesByEntity, [key]: emptyEntity() },
        currentToolCards: [],
      });
      state.loadSceneMessages(state.currentScene.id);
    }
  },

  // ═══ 场景广场 / 工坊 ═══
  plazaScenes: [],
  workshopScenes: [],
  loadingPlaza: false,
  loadingWorkshop: false,
  loadPlazaScenes: async (params) => {
    set({ loadingPlaza: true });
    try {
      const scenes = await listPlazaScenes(params);
      set({ plazaScenes: scenes });
    } catch (e) {
      console.error('[store] loadPlazaScenes failed:', e);
    } finally {
      set({ loadingPlaza: false });
    }
  },
  loadWorkshopScenes: async (params) => {
    set({ loadingWorkshop: true });
    try {
      const scenes = await listWorkshopScenes(params);
      set({ workshopScenes: scenes });
    } catch (e) {
      console.error('[store] loadWorkshopScenes failed:', e);
    } finally {
      set({ loadingWorkshop: false });
    }
  },
  publishSceneVersion: async (sceneId, version, changelog) => {
    try {
      const updated = await publishScene(sceneId, { version, changelog });
      get().loadWorkshopScenes();
      return updated;
    } catch (e) {
      console.error('[store] publishScene failed:', e);
      return null;
    }
  },

  // ═══ 工作台 ═══
  scenes: [],
  loadingScenes: false,
  loadScenes: async () => {
    set({ loadingScenes: true });
    try {
      const scenes = await listScenes();
      set({ scenes });
    } catch (e) {
      console.error('[store] loadScenes failed:', e);
    } finally {
      set({ loadingScenes: false });
    }
  },

  createSceneModalOpen: false,
  setCreateSceneModalOpen: (v) => set({ createSceneModalOpen: v }),

  // ═══ 系统设置 ═══
  settingsData: null,
  serviceStatus: null,
  settingsDrawerOpen: false,
  settingsLoading: false,

  openSettingsDrawer: () => set({ settingsDrawerOpen: true }),

  closeSettingsDrawer: () => set({ settingsDrawerOpen: false }),

  loadSettings: async () => {
    set({ settingsLoading: true });
    try {
      const [settingsData, serviceStatus] = await Promise.all([getSettings(), getServiceStatus()]);
      set({ settingsData, serviceStatus, settingsLoading: false });
    } catch (e) {
      console.error('[store] loadSettings failed:', e);
      set({ settingsLoading: false });
    }
  },

  refreshServiceStatus: async () => {
    try {
      const serviceStatus = await getServiceStatus();
      set({ serviceStatus });
    } catch {
      // 静默失败，服务可能已停
    }
  },

  updateSettingsPartial: async (data: Record<string, any>) => {
    try {
      const settingsData = await updateSettings(data);
      set({ settingsData });
      return true;
    } catch (e) {
      console.error('[store] updateSettings failed:', e);
      return false;
    }
  },
}));
