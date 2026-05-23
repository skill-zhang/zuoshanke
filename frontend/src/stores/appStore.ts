/** 全局状态管理 — Zustand */
import { create } from 'zustand';
import {
  listScenes, createScene, updateScene, deleteScene,
  listPlazaScenes, listWorkshopScenes, publishScene, exportScene, importScene,
  getThinkingMap, addNode, updateNode, deleteNode, convergeMap, prioritizeMap, getQueue, getFocusQueue, reflectNode,
  sendMessage, listSceneMessages, sendSceneMessageStream,
  deleteMessage as apiDeleteMessage, regenerateMessage as apiRegenerateMessage,
  newSceneSession as apiNewSceneSession,
  batchDeleteMessages, clearSceneMessages, listSceneSessions,
  SceneSession,
  listChannels, createChannel, updateChannel, deleteChannel, clearChannelMessages,
  sendChannelMessage, listChannelMessages, sendChannelMessageStream,
  compressChannelHistory,
  listActionMaps, getActionMap, createActionMap, updateActionMapStatus, deleteActionMap, generateActionMap, generateActionMapStream,
  Scene, ThinkingMap, ThinkNode, Message, Channel, StreamEvent, ToolCard,
  ActionMap as ActionMapType, ActionMapStreamEvent, ToolLog,
  getSettings, updateSettings, getServiceStatus,
  SettingsData, ServiceStatus, RouteConfig,
  DashboardQueueItem, DashboardReflectItem,  // 🆕 Schema v0.7
  getDashboardQueue, getDashboardReflect, getDashboardStatus,  // 🆕 Schema v0.7
  activateSession,  // 🆕 Schema v1.1: Session 管理
} from '../api/client';

export type ViewPage = 'chat' | 'plaza' | 'workshop' | 'tools' | 'capability-verify' | 'skills' | 'memory' | 'dashboard' | 'outputs' | 'delegate-results' | 'secret-garden';

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
  reflectNode: (nodeId: string, resultSummary: string, options?: {
    newDiscoveries?: string[]; isSuccess?: boolean;
  }) => Promise<any>;
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

  // ═══ 场景消息（分页） ═══
  messages: Message[];
  messageTotalCount: number;
  hasOlderMessages: boolean;
  messagesLoading: boolean;
  currentSessionId: string | null;   // 场景当前会话 ID
  sessions: SceneSession[];          // 历史会话列表
  loadSceneMessages: (sceneId: string) => Promise<void>;
  loadOlderMessages: (sceneId: string) => Promise<void>;
  sendSceneMsg: (sceneId: string, content: string) => Promise<void>;
  newSceneSession: (sceneId: string) => Promise<string | null>;  // 开始新会话
  batchDeleteMsgs: (ids: string[]) => Promise<void>;             // 批量删除
  clearSceneMsgs: (sceneId: string) => Promise<void>;            // 一键清空
  loadSceneSessions: (sceneId: string) => Promise<void>;         // 加载会话列表
  switchSceneSession: (sessionId: string | null) => void;        // 切换会话

  // ═══ 频道 ═══
  channels: Channel[];
  currentChannel: Channel | null;
  loadChannels: () => Promise<void>;
  createChannelAndReload: (name: string) => Promise<Channel>;
  updateChannelAndReload: (id: string, data: { name?: string; pinned?: boolean }) => Promise<void>;
  deleteChannelAndReload: (id: string) => Promise<void>;
  clearChannelHistory: (id: string) => Promise<void>;
  setCurrentChannel: (c: Channel) => void;

  // ═══ 频道消息（分页） ═══
  channelMessages: Message[];
  channelMessageTotalCount: number;
  channelHasOlder: boolean;
  channelMessagesLoading: boolean;
  loadChannelMessages: (channelId: string) => Promise<void>;
  loadOlderChannelMessages: (channelId: string) => Promise<void>;
  sendChannelMsg: (channelId: string, content: string) => Promise<void>;

  // ═══ 流式状态 ═══
  isGenerating: boolean;
  generatingEntityId: string | null;  // 当前在生成的实体ID（场景/频道），null=无
  currentModelName: string | null;   // 当前使用的模型名（来自 SSE model_info 事件）
  contextUsage: { totalTokens: number; maxTokens: number; percentage: number; usageStr: string; progressBar: string; historyCount: number } | null;
  capacityWarning: { message: string; percentage: number } | null;
  currentToolCards: ToolCard[];      // 当前 AI 回复的工具卡片数据
  currentToolLogs: ToolLog[];        // 当前工具执行记录（纯前端，不存库）

  // 🆕 Schema v0.7: 仪表盘
  priorityQueue: DashboardQueueItem[];
  reflectTimeline: DashboardReflectItem[];
  dashboardPhase: string;            // diverge | converge | sort | focus | reflect
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
  publishSceneVersion: (sceneId: string, version: string, changelog?: string) => Promise<Scene | null>;
  createSceneModalOpen: boolean;
  setCreateSceneModalOpen: (v: boolean) => void;

  // ═══ 上下文压缩 ═══
  compressChannel: (channelId: string) => Promise<string | null>;

  // ═══ AI 角色动画 ═══
  agentStatus: AgentStatus;
  agentMessage: string;
  agentHidden: boolean;
  setAgentStatus: (s: AgentStatus) => void;
  setAgentMessage: (m: string) => void;
  setAgentHidden: (h: boolean) => void;
  toggleAgentHidden: () => void;
}

export type AgentStatus =
  | 'idle' | 'greeting' | 'thinking' | 'working' | 'analyzing'
  | 'done' | 'error' | 'notify'
  | 'resting' | 'angry' | 'laugh' | 'sad';

export const useStore = create<AppState>((set, get) => ({
  view: 'chat',  // 默认进入聊天视图
  setView: (v) => set({ view: v, contextUsage: null, capacityWarning: null }),
  isGenerating: false,
  generatingEntityId: null,
  currentModelName: null,
  contextUsage: null,
  capacityWarning: null,
  currentToolCards: [],
  currentToolLogs: [],

  // 🆕 Schema v0.7: 仪表盘初始值
  priorityQueue: [],
  reflectTimeline: [],
  dashboardPhase: 'diverge',
  dashboardLoopCount: 0,
  dashboardStepCount: 0,
  mindMapOpen: false,
  toggleMindMap: () => set(s => ({ mindMapOpen: !s.mindMapOpen })),

  // ═══ AI 角色动画默认值 ═══
  agentStatus: 'idle' as AgentStatus,
  agentMessage: '在线待命',
  agentHidden: false,
  setAgentStatus: (s) => set({ agentStatus: s }),
  setAgentMessage: (m) => set({ agentMessage: m }),
  setAgentHidden: (h) => set({ agentHidden: h }),
  toggleAgentHidden: () => set((s) => ({ agentHidden: !s.agentHidden })),

  currentScene: null,
  setCurrentScene: (s) => {
    // 切场景时不触发记忆提取，只保留页面关闭（visibilitychange）触发
    set({ currentScene: s, messages: [], messageTotalCount: 0, hasOlderMessages: false, contextUsage: null, capacityWarning: null });
    if (s) {
      get().loadUserContext(s.id);
      // 🆕 Schema v1.1: 激活 session（异步，不阻塞 UI）
      activateSession('scene', s.id, s.name).catch(e =>
        console.error('[store] activateSession failed:', e)
      );
    }
  },
  userContext: '',
  loadUserContext: async (sceneId) => {
    try {
      const scenes = await listScenes();
      const scene = scenes.find(s => s.id === sceneId);
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

  // ═══ 场景消息（分页） ═══
  messages: [],
  messageTotalCount: 0,
  hasOlderMessages: false,
  messagesLoading: false,
  currentSessionId: null,
  sessions: [],
  loadSceneMessages: async (sceneId) => {
    try {
      set({ messagesLoading: true });
      const sessionId = get().currentSessionId;
      const result = await listSceneMessages(sceneId, sessionId || undefined, 50);
      set({
        messages: result.messages,
        hasOlderMessages: result.has_more,
        messageTotalCount: result.total,
        messagesLoading: false,
      });
    } catch (e) {
      console.error('[store] loadSceneMessages failed:', e);
      set({ messagesLoading: false });
    }
  },
  loadOlderMessages: async (sceneId) => {
    const state = get();
    if (!state.messages.length || !state.hasOlderMessages || state.messagesLoading) return;
    try {
      set({ messagesLoading: true });
      const oldestId = state.messages[0].id;
      const sessionId = state.currentSessionId;
      const result = await listSceneMessages(sceneId, sessionId || undefined, 50, oldestId);
      set({
        messages: [...result.messages, ...state.messages],
        hasOlderMessages: result.has_more,
        messageTotalCount: result.total,
        messagesLoading: false,
      });
    } catch (e) {
      console.error('[store] loadOlderMessages failed:', e);
      set({ messagesLoading: false });
    }
  },
  sendSceneMsg: async (sceneId, content) => {
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

    set({
      isGenerating: true,
      generatingEntityId: sceneId,
      currentToolCards: [],
      currentToolLogs: [],
      messages: [...get().messages, tempUserMsg, tempAiMsg],
    });

    try {
      const sessionId = get().currentSessionId;
      const stream = sendSceneMessageStream(sceneId, content, sessionId || undefined);

      for await (const event of stream) {
        if (event.type === 'tool_cards') {
          set({ currentToolCards: event.cards });
        } else if (event.type === 'tool_status') {
          set(state => ({
            currentToolLogs: [...state.currentToolLogs, {
              tool: event.tool,
              status: event.status,
              success: event.success,
              message: event.message,
            }],
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
          set(state => ({
            messages: state.messages.map(m =>
              m.id === tempUserId
                ? { ...m, id: event.id, created_at: event.created_at }
                : m
            ),
          }));
        } else if (event.type === 'token') {
          set(state => ({
            messages: state.messages.map(m =>
              m.id === tempAiId
                ? { ...m, content: m.content === '🤔 正在分析...' ? event.token : m.content + event.token }
                : m
            ),
          }));
          // 打断 React 18 批量化，让每个 token 独立渲染
          await new Promise(r => setTimeout(r, 0));
        } else if (event.type === 'done') {
          set(state => ({
            isGenerating: false,
            generatingEntityId: null,
            messages: state.messages.map(m =>
              m.id === tempAiId
                ? { ...m, id: event.id, content: event.content, created_at: event.created_at, model: event.model || null, toolCards: state.currentToolCards }
                : m
            ),
          }));
          // 流式完成后刷新 Thinking Map
          get().loadThinkingMap(sceneId);
        } else if (event.type === 'child:started') {
          const { setDelegateTasks } = await import('../components/DelegationMonitor');
          setDelegateTasks(event.tasks || []);
        } else if (event.type === 'child:done') {
          const { setDelegateResults } = await import('../components/DelegationMonitor');
          setDelegateResults(event.children || []);
        } else if (event.type === 'asset') {
          set(state => ({
            messages: [...state.messages, {
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
            }],
          }));
        } else if (event.type === 'output:created') {
          // 🆕 自动提取的 HTML 产出 — 附加到最后一条 AI 消息
          set(state => {
            const msgs = [...state.messages];
            for (let i = msgs.length - 1; i >= 0; i--) {
              if (msgs[i].role === 'ai' && !msgs[i].id.startsWith('temp-')) {
                msgs[i] = { ...msgs[i], outputRef: { outputId: event.output_id, title: event.title, filePath: event.file_path } };
                break;
              }
            }
            return { messages: msgs };
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
          set(s => ({
            reflectTimeline: [...s.reflectTimeline, newItem].slice(-20),
            dashboardLoopCount: s.dashboardLoopCount + 1,
            dashboardStepCount: s.dashboardStepCount + 1,
          }));
        } else if (event.type === 'error') {
          set(state => ({
            isGenerating: false,
            generatingEntityId: null,
            currentToolCards: [],
            currentToolLogs: [],
            messages: state.messages.map(m =>
              m.id === tempAiId
                ? { ...m, content: `❌ ${event.message}` }
                : m
            ),
          }));
        }
      }
    } catch (e) {
      console.error('[store] sendSceneMsg stream failed:', e);
      set(state => ({
        isGenerating: false,
        generatingEntityId: null,
        messages: state.messages.map(m =>
          m.id === tempAiId
            ? { ...m, content: '❌ 网络请求失败，请重试' }
            : m
        ),
      }));
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
      const chs = get().channels.filter(c => c.id !== id);
      set({ currentChannel: chs[0] || null, channelMessages: [] });
    }
  },
  clearChannelHistory: async (id) => {
    await clearChannelMessages(id);
    if (get().currentChannel?.id === id) {
      set({ channelMessages: [] });
    }
  },
  setCurrentChannel: (c) => {
    set({ currentChannel: c, channelMessages: [], channelMessageTotalCount: 0, channelHasOlder: false, contextUsage: null, capacityWarning: null });
    // 🆕 Schema v1.1: 激活 session（异步，不阻塞 UI）
    activateSession('channel', c.id, c.name).catch(e =>
      console.error('[store] activateSession failed:', e)
    );
  },

  // ═══ 频道消息（分页） ═══
  channelMessages: [],
  channelMessageTotalCount: 0,
  channelHasOlder: false,
  channelMessagesLoading: false,
  loadChannelMessages: async (channelId) => {
    try {
      set({ channelMessagesLoading: true });
      const result = await listChannelMessages(channelId, 50);
      set({
        channelMessages: result.messages,
        channelHasOlder: result.has_more,
        channelMessageTotalCount: result.total,
        channelMessagesLoading: false,
      });
    } catch (e) {
      console.error('[store] loadChannelMessages failed:', e);
      set({ channelMessagesLoading: false });
    }
  },
  loadOlderChannelMessages: async (channelId) => {
    const state = get();
    if (!state.channelMessages.length || !state.channelHasOlder || state.channelMessagesLoading) return;
    try {
      set({ channelMessagesLoading: true });
      const oldestId = state.channelMessages[0].id;
      const result = await listChannelMessages(channelId, 50, oldestId);
      set({
        channelMessages: [...result.messages, ...state.channelMessages],
        channelHasOlder: result.has_more,
        channelMessageTotalCount: result.total,
        channelMessagesLoading: false,
      });
    } catch (e) {
      console.error('[store] loadOlderChannelMessages failed:', e);
      set({ channelMessagesLoading: false });
    }
  },
  sendChannelMsg: async (channelId, content) => {
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

    set({
      isGenerating: true,
      generatingEntityId: channelId,
      channelMessages: [...get().channelMessages, tempUserMsg, tempAiMsg],
    });

    try {
      const stream = sendChannelMessageStream(channelId, content);

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
          set(state => ({
            channelMessages: state.channelMessages.map(m =>
              m.id === tempUserId
                ? { ...m, id: event.id, created_at: event.created_at }
                : m
            ),
          }));
        } else if (event.type === 'token') {
          // 逐 token 追加到 AI 消息
          set(state => ({
            channelMessages: state.channelMessages.map(m =>
              m.id === tempAiId
                ? { ...m, content: m.content + event.token }
                : m
            ),
          }));
          // 打断 React 18 批量化，让每个 token 独立渲染
          await new Promise(r => setTimeout(r, 0));
        } else if (event.type === 'done') {
          // 服务器保存完成 → 用真实 ID 替换占位
          set(state => ({
            isGenerating: false,
            generatingEntityId: null,
            channelMessages: state.channelMessages.map(m =>
              m.id === tempAiId
                ? { ...m, id: event.id, content: event.content, created_at: event.created_at, model: event.model || null }
                : m
            ),
          }));
        } else if (event.type === 'error') {
          set(state => ({
            isGenerating: false,
            generatingEntityId: null,
            channelMessages: state.channelMessages.map(m =>
              m.id === tempAiId
                ? { ...m, content: `❌ ${event.message}` }
                : m
            ),
          }));
        }
      }
    } catch (e) {
      console.error('[store] sendChannelMsg stream failed:', e);
      set(state => ({
        isGenerating: false,
        generatingEntityId: null,
        channelMessages: state.channelMessages.map(m =>
          m.id === tempAiId
            ? { ...m, content: '❌ 网络请求失败，请重试' }
            : m
        ),
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
      set({ currentSessionId: session_id, messages: [], messageTotalCount: 0, hasOlderMessages: false });
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
    set({ messages: [], messageTotalCount: 0, hasOlderMessages: false, currentSessionId: null });
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
    set({ currentSessionId: sessionId, messages: [], messageTotalCount: 0, hasOlderMessages: false, currentToolCards: [] });
    const state = get();
    if (state.currentScene) {
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
      // 同步刷新工坊列表
      get().loadWorkshopScenes();
      return updated;
    } catch (e) {
      console.error('[store] publishScene failed:', e);
      return null;
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
      const [settingsData, serviceStatus] = await Promise.all([
        getSettings(),
        getServiceStatus(),
      ]);
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
