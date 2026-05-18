# 工具管理设计（最终实现版）

> 对应原型 `prototypes/tools-plaza.html` v1.0 → 代码实现提交 `9addfc2`
> 定型日期：2026-05-18

## 能力体系定义（已焊死）

| 类型 | 定义 | 文件结构 | 管理入口 |
|------|------|----------|----------|
| 🛠️ **工具(Tool)** | 可执行的代码函数，可以有 SKILL.md 作为使用手册 | `tools/<name>.py` + 可选 `tools/<name>/SKILL.md` | 工具管理（全页卡片视图） |
| 📘 **技能(Skill)** | 纯文本知识，**无**可执行代码 | `skills/<name>/SKILL.md` | 技能管理（抽屉，待优化为全页） |

**核心规则**：
- 工具必须有可调用的 Python 函数（注册在 `tools/registry.json`）
- 工具可以附带 SKILL.md 作为"使用说明书"（格式化规范、参数说明、示例）
- 纯知识文档（法律条文、写作规范等）属于技能，不是工具
- 两者**分开管理**，并列在侧边栏「🧰 系统工具」下

## 界面实现

### 侧边栏入口

`frontend/src/components/Sidebar.tsx` 中「🧰 系统工具」区域：

```
🧰 系统工具
├── 🛠️ 工具管理    ← 全页卡片视图（新增）
├── 📘 技能管理    ← 现有抽屉
└── 🧠 记忆管理    ← 现有抽屉
```

点击「🛠️ 工具管理」→ `setView('tools')` + `setCurrentScene(null)` → 渲染 `<ToolsView />`

### 视图注册

`frontend/src/stores/appStore.ts`:
```typescript
export type ViewPage = 'projects' | 'chat' | 'plaza' | 'workshop' | 'tools';
```

`frontend/src/App.tsx`: view === 'tools' 时渲染 `<ToolsView />`

### 工具主视图 — ToolsView

`frontend/src/components/ToolsView.tsx` (~590行)

#### 组件结构

```
ToolsView（主组件）
├── Category tabs（全部 / 🌐搜索 / 📊数据 / ⚙️系统 / ⚠️未验证）
├── 搜索框 + 【➕ 注册新工具】按钮
├── 卡片网格（工具卡片列表）
├── DetailModal（详情弹窗子组件）
├── RegisterModal（注册表单子组件）
└── 注销确认弹窗（内联 modal）
```

#### UI 特征

- **背景色**：`#0d1117`（深色）
- **卡片**：`#161b22` 背景，hover 时上移 2px + 阴影
- **所有样式**：全部用**内联 style**，不依赖外部 CSS（避免污染其他页面）
- **分类 tab**：选中态用 `#1f6feb33` 背景 + `#1f6feb66` 边框
- **标签行**：预执行状态用圆点（绿色=开启，灰色=关闭）+ 触发词数量

#### 数据加载

```typescript
const load = useCallback(async (cat?: string) => {
  setLoading(true);
  setError('');
  try {
    const res = await listTools(cat === 'all' ? undefined : cat);
    setTools(res.data);
  } catch (e: any) {
    setError(e.message || '加载失败');
  } finally {
    setLoading(false);
  }
}, []);

useEffect(() => { load(); }, [load]);
```

分类过滤 + 搜索是**前端过滤**（加载一次后本地 filter），不是每次重新请求 API。

### 详情 Modal — DetailModal

子组件，接收 `tool: ToolDetail` + 回调函数。

结构（从上到下）：
1. **📝 基本信息** — 描述、文件路径、函数名、分类 + 验证状态
2. **📋 参数表** — table 布局：参数名(`code`)、类型(蓝色)、必填(✅/❌)、说明
3. **📤 返回值说明**
4. **⚡ 预执行配置** — 状态(🟢已启用/⚪已禁用)、触发词标签列表、需要城市
5. **📄 使用手册(SKILL.md)** — 有则预览(带 `tools/<name>/SKILL.md` 路径)，无则显示"未创建"
6. **🧪 测试工具**（重点设计）

底部操作栏：【✏️ 编辑】→ alert 占位 | 【⚙️ 预执行】→ alert 占位 | 【📄 编辑手册】→ alert 占位 | 【🗑 注销】→ 打开确认弹窗

#### 测试面板设计（用户亲自定稿）

**参数输入区**：每个参数一个输入框，label 显示 `参数名(类型)` 和 `必填/可选` 标记
- 有默认值（city→"北京", query→"今天新闻", forecast_days→"3" 等）
- 无参数时提示"该工具无参数，直接运行即可"

**运行按钮**：点后延迟 600ms 模拟执行（原型阶段）

**结果展示**：
- ❌ 不是 JSON 代码块（用户说：一般人哪懂 JSON）
- ✅ 是 **Markdown 聊天气泡**风格，白色文字预换行展示
- 带 header：✅ 执行成功 + 耗时显示
- 不同工具有不同模拟结果（天气→表格预报、搜索→结果列表、待办→任务表格、路线→路线表）

```typescript
const mockResults: Record<string, string> = {
  get_weather: `## 🌤 北京天气\n\n**当前**：18°C...\n\n**未来3天预报**：\n| 日期 | 温度 | 天气 |\n...`,
  web_search: `## 🔍 搜索结果\n\n### 1. 全球科技巨头...`,
  todo_list: `## 📋 我的任务\n\n| 状态 | 内容 | ...`,
  geo_route: `## 🚗 路线规划\n\n**北京站 → 天安门**`,
};
```

测试用的是纯前端的模拟结果（`onTest` 回调），**不调后端**。后端集成测试是后续迭代。

### 注册 Modal — RegisterModal

标准表单，包含：
- 工具名称 + 分类（下拉）
- 描述 + 文件路径 + 函数名 + 返回值说明
- **动态参数列表**：每行一个参数（参数名 + 类型下拉 + 必填 checkbox + 移除按钮），可增删
- **预执行配置**：启用 checkbox + 触发词输入（逗号分隔）+ 需要城市 checkbox
- 提交时验证必填项，调 `createTool()` API

### 注销确认 Modal

**原则**：不弹系统 `confirm()` 弹窗。

```
┌──────────────────┐
│ ⚠️ 确认注销工具   │
│ 🗑️  「get_weather」│
│ 注销后将从registry│
│ 中移除，无法调用。│
│ ⚠️ 此操作不可撤销 │
│  [取消] [确认注销] │
└──────────────────┘
```

- 红色警告边框（`#f85149`）+ 红色确认按钮
- 取消按钮为标准灰色
- 点击背景蒙版也可关闭
- 确认后：关详情弹窗 → 调 `deleteTool()` API → 重新加载列表

## 后端实现

### 文件

`backend/router/tools_crud.py` (~335行)

以 `prefix="/api/tools"` 注册的 APIRouter，Pydantic 模型定义在文件头部：

```python
class ParamDef(BaseModel):
    name: str; type: str = "string"; required: bool = True; description: str = ""

class PreexecuteConfig(BaseModel):
    enabled: bool = False; triggers: list[str] = []; requires_city: bool = False

class ToolCreate(BaseModel):
    name: str; description: str; file: str; function: str
    parameters: list[ParamDef] = []; returns: str = ""; category: str = "data"
    verified: bool = False; preexecute: PreexecuteConfig = PreexecuteConfig()
```

### 9 个 API 端点

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/api/tools` | `list_tools` | 列表，支持 `?category=` 过滤 |
| POST | `/api/tools` | `create_tool` | 注册新工具 |
| GET | `/api/tools/{name}` | `get_tool` | 完整详情（含 SKILL.md 内容） |
| PUT | `/api/tools/{name}` | `update_tool` | 更新配置（可局部更新） |
| DELETE | `/api/tools/{name}` | `delete_tool` | 注销（从 registry.json 移除） |
| PUT | `/api/tools/{name}/preexecute` | `update_preexecute` | 管理预执行配置 |
| GET | `/api/tools/{name}/skill` | `get_tool_skill` | 读取 SKILL.md |
| PUT | `/api/tools/{name}/skill` | `put_tool_skill` | 创建/更新 SKILL.md |
| DELETE | `/api/tools/{name}/skill` | `delete_tool_skill` | 删除 SKILL.md |

### 参数格式转换

registry.json 中参数存为 `{name: {type, description, optional}}` 格式（兼容旧格式），API 返回时统一转为 `ParamDef[]` 数组格式：

```python
def _param_to_dict(p: ParamDef) -> dict:
    d = {"type": p.type, "description": p.description}
    if not p.required: d["optional"] = True
    return d

def _param_from_dict(name: str, pd: dict) -> dict:
    return {"name": name, "type": pd.get("type","string"),
            "required": not pd.get("optional", False),
            "description": pd.get("description","")}
```

### 列表摘要 vs 详情

两个函数分别返回不同粒度的数据：

```python
def _tool_to_summary(t: dict) -> dict:
    """工具列表用的摘要：不含参数明细、不含 SKILL.md 内容"""
    return {
        "name", "description", "category", "verified",
        "params_count", "preexecute_enabled",
        "preexecute_triggers_count", "has_skill",
    }

def _tool_to_detail(t: dict) -> dict:
    """完整详情：含参数列表、SKILL.md 原文"""
    return {
        "name", "description", "file", "function",
        "parameters": ParamDef[], "returns", "category", "verified",
        "preexecute": {enabled, triggers[], requires_city},
        "has_skill", "skill_content": str | null,
    }
```

### 前端 API 封装

`frontend/src/api/client.ts`:

```typescript
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
```

注意：之前的旧 API `getToolSkill(toolName: string)`（返回 `{name, content}` 格式）已移除，统一用新的 `getToolSkill(name: string)`（返回 `{success, data: {name, content}}` 格式）。

### 注册路由

`backend/router/__init__.py`:
```python
from router.tools_crud import router as tools_crud_router
...
app.include_router(tools_crud_router)
```

## 历史决策记录

### v1.0 定型 (2026-05-18)

- **原型完成**：`prototypes/tools-plaza.html` v1.0，用户确认后编码
- **全页视图**：不用抽屉，用场景广场一样的 card-grid 全页模式
- **工具 vs Skill 分离**：经用户讨论确认，工具=可执行代码，技能=纯文本知识
- **测试结果格式**：用户要求 Markdown（聊天风格）而非 JSON（开发风格）
- **注销确认**：自定义 Modal 而非浏览器 `confirm()`
- **检测结果**：原型已经 git 提交 + E 盘备份
- **代码实现**：18 个文件，1485 行新增，全部在 commit `9addfc2` 中

### 与旧 API 的兼容性

- 旧的 `router/tools.py` 中的 `GET /api/tools/{tool_name}/skill` 端点保留（兼容旧调用）
- 新的 `router/tools_crud.py` 中的同名端点会与之冲突——先注册的（旧）优先生效
- 前端已全部使用新的 API 格式（`{success, data}` 包裹）
