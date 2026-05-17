/** 全局状态管理 — Zustand */
import { create } from 'zustand';
import {
  listProjects, createProject, deleteProject,
  listScenes, createScene, updateScene, deleteScene,
  listPlazaScenes, listWorkshopScenes, publishScene, exportScene, importScene,
  getThinkingMap, addNode, updateNode, deleteNode,
  sendMessage, listSceneMessages, sendSceneMessageStream,
  deleteMessage as apiDeleteMessage, regenerateMessage as apiRegenerateMessage,
  newSceneSession as apiNewSceneSession,
  batchDeleteMessages, clearSceneMessages, listSceneSessions,
  SceneSession,
  listChannels, createChannel, updateChannel, deleteChannel, clearChannelMessages,
  sendChannelMessage, listChannelMessages, sendChannelMessageStream,
  listActionMaps, getActionMap, createActionMap, updateActionMapStatus, deleteActionMap, generateActionMap, generateActionMapStream,
  Project, Scene, ThinkingMap, ThinkNode, Message, Channel, StreamEvent, ToolCard,
  ActionMap as ActionMapType, ActionMapStreamEvent,
  getSettings, updateSettings, getServiceStatus,
  SettingsData, ServiceStatus, RouteConfig,
} from '../api/client';

export type ViewPage = 'projects' | 'chat' | 'plaza' | 'workshop';

interface AppState {
  view: ViewPage;
  setView: (v: ViewPage) => void;

  // ═══ 项目 ═══
  projects: Project[];
  loadProjects: () => Promise<void>;
  createProjectAndReload: (name: string, desc?: string) => Promise<Project>;

  currentProject: Project | null;
  setCurrentProject: (p: Project | null) => void;
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

  // ═══ 场景消息 ═══
  messages: Message[];
  currentSessionId: string | null;   // 场景当前会话 ID
  sessions: SceneSession[];          // 历史会话列表
  loadSceneMessages: (sceneId: string) => Promise<void>;
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

  // ═══ 频道消息 ═══
  channelMessages: Message[];
  loadChannelMessages: (channelId: string) => Promise<void>;
  sendChannelMsg: (channelId: string, content: string) => Promise<void>;

  // ═══ 流式状态 ═══
  isGenerating: boolean;
  currentModelName: string | null;   // 当前使用的模型名（来自 SSE model_info 事件）
  currentToolCards: ToolCard[];      // 当前 AI 回复的工具卡片数据

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

  // ═══ 记忆系统抽屉 🆕 ═══
  memoryDrawerOpen: boolean;
  openMemoryDrawer: () => void;
  closeMemoryDrawer: () => void;

  // ═══ 技能系统抽屉 🆕 ═══
  skillsDrawerOpen: boolean;
  openSkillsDrawer: () => void;
  closeSkillsDrawer: () => void;
}

export const useStore = create<AppState>((set, get) => ({
  view: 'chat',  // 默认进入聊天视图
  setView: (v) => set({ view: v }),
  isGenerating: false,
  currentModelName: null,
  currentToolCards: [],

  // ═══ 项目 ═══
  projects: [],
  loadProjects: async () => {
    try {
      const projects = await listProjects();
      set({ projects });
    } catch (e) {
      console.error('[store] loadProjects failed:', e);
    }
  },
  createProjectAndReload: async (name, desc = '') => {
    const p = await createProject(name, desc);
    await get().loadProjects();
    return p;
  },

  currentProject: null,
  setCurrentProject: (p) => set({ currentProject: p, currentScene: null, messages: [] }),
  currentScene: null,
  setCurrentScene: (s) => { set({ currentScene: s, messages: [] }); if (s) get().loadUserContext(s.id); },
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

  // ═══ 场景消息 ═══
  messages: [],
  currentSessionId: null,
  sessions: [],
  loadSceneMessages: async (sceneId) => {
    try {
      const sessionId = get().currentSessionId;
      const msgs = await listSceneMessages(sceneId, sessionId || undefined);
      set({ messages: msgs });
    } catch (e) {
      console.error('[store] loadSceneMessages failed:', e);
    }
  },
  sendSceneMsg: async (sceneId, content) => {
    // 0. 乐观更新：立即插入临时用户消息 + 空壳 AI 消息
    const tempUserId = 'temp-user-' + Date.now();
    const tempUserMsg: Message = {
      id: tempUserId,
      scene_id: sceneId,
      channel_id: null,
      role: 'user',
      content,
      map_ref: null,
      created_at: new Date().toISOString(),
    };

    const tempAiId = 'temp-ai-' + Date.now();
    const tempAiMsg: Message = {
      id: tempAiId,
      scene_id: sceneId,
      channel_id: null,
      role: 'ai',
      content: '🤔 正在分析...',
      map_ref: null,
      created_at: new Date().toISOString(),
    };

    set({
      isGenerating: true,
      currentToolCards: [],
      messages: [...get().messages, tempUserMsg, tempAiMsg],
    });

    try {
      const sessionId = get().currentSessionId;
      const stream = sendSceneMessageStream(sceneId, content, sessionId || undefined);

      for await (const event of stream) {
        if (event.type === 'tool_cards') {
          set({ currentToolCards: event.cards });
        } else if (event.type === 'model_info') {
          set({ currentModelName: event.model });
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
            messages: state.messages.map(m =>
              m.id === tempAiId
                ? { ...m, id: event.id, content: event.content, created_at: event.created_at, model: event.model || null, toolCards: state.currentToolCards }
                : m
            ),
          }));
          // 流式完成后刷新 Thinking Map
          get().loadThinkingMap(sceneId);
        } else if (event.type === 'error') {
          set(state => ({
            isGenerating: false,
            currentToolCards: [],
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
  setCurrentChannel: (c) => set({ currentChannel: c, channelMessages: [] }),

  // ═══ 频道消息 ═══
  channelMessages: [],
  loadChannelMessages: async (channelId) => {
    try {
      const msgs = await listChannelMessages(channelId);
      set({ channelMessages: msgs });
    } catch (e) {
      console.error('[store] loadChannelMessages failed:', e);
    }
  },
  sendChannelMsg: async (channelId, content) => {
    // 1. 乐观更新：立即插入临时用户消息
    const tempUserId = 'temp-user-' + Date.now();
    const tempUserMsg: Message = {
      id: tempUserId,
      scene_id: null,
      channel_id: channelId,
      role: 'user',
      content,
      map_ref: null,
      created_at: new Date().toISOString(),
    };

    // 2. 插入占位 AI 消息（空壳）
    const tempAiId = 'temp-ai-' + Date.now();
    const tempAiMsg: Message = {
      id: tempAiId,
      scene_id: null,
      channel_id: channelId,
      role: 'ai',
      content: '',
      map_ref: null,
      created_at: new Date().toISOString(),
    };

    set({
      isGenerating: true,
      channelMessages: [...get().channelMessages, tempUserMsg, tempAiMsg],
    });

    try {
      const stream = sendChannelMessageStream(channelId, content);

      for await (const event of stream) {
        if (event.type === 'model_info') {
          set({ currentModelName: event.model });
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
            channelMessages: state.channelMessages.map(m =>
              m.id === tempAiId
                ? { ...m, id: event.id, content: event.content, created_at: event.created_at, model: event.model || null }
                : m
            ),
          }));
        } else if (event.type === 'error') {
          set(state => ({
            isGenerating: false,
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
        channelMessages: state.channelMessages.map(m =>
          m.id === tempAiId
            ? { ...m, content: '❌ 网络请求失败，请重试' }
            : m
        ),
      }));
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
      set({ currentSessionId: session_id, messages: [] });
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
    set({ messages: [], currentSessionId: null });
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
    set({ currentSessionId: sessionId, messages: [], currentToolCards: [] });
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

  memoryDrawerOpen: false,
  openMemoryDrawer: () => set({ memoryDrawerOpen: true, skillsDrawerOpen: false }),
  closeMemoryDrawer: () => set({ memoryDrawerOpen: false }),

  skillsDrawerOpen: false,
  openSkillsDrawer: () => set({ skillsDrawerOpen: true, memoryDrawerOpen: false }),
  closeSkillsDrawer: () => set({ skillsDrawerOpen: false }),

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
