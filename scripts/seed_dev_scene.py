"""坐山客自开发场景 — 种子脚本

运行方式：
  cd zuoshanke && backend/.venv/bin/python scripts/seed_dev_scene.py

功能：
  1. 创建「坐山客自开发」场景
  2. 注入设计哲学/用户偏好到本体记忆 (scope=zhu)
  3. 配置场景参数（temperature=0.7，禁用自动收敛）
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database import SessionLocal, init_db
from models import Scene, ThinkingMap, ThinkNode, AgentMemory
from agent_core.memory_manager import MemoryManager
from agent_core.memory_cache import MemoryCache
from utils import make_id, utcnow


# ── 自开发场景专用 system prompt ──
# 注意：context_builder.py 会在此 prompt 前自动注入分身身份声明（fenshen identity）
# 所以这里只包含「场景内部行为指引」，不需要重复声明「你是坐山客的分身」

SELF_DEV_SYSTEM_PROMPT = """你是【坐山客自开发】领域的智能助手。

## 开发流程（先方案再动手）

你的工作方式不同于普通场景——你不是接到需求就立刻执行：

1. 【方案阶段】用户提出需求后，先给出设计方案。
   - 分析需求涉及哪些模块（前端/后端/数据库/工具）
   - 提出具体的技术方案
   - 如果有多条路径可选，调 clarify 工具让用户选择
   - 如果需求不明确，调 clarify 工具追问细节

2. 【契约阶段】方案确认后，如果涉及多模块开发，先写接口契约文件。
   - 用 write_file 创建 shared/INTERFACE.md，按下方标准模板写
   - 契约是子 Agent 之间唯一的共享上下文
   - 子 Agent 不知道彼此存在，只需要遵守契约
   - 任何子任务涉及多个 Agent 协作，必须写契约先行

   标准契约模板结构（直接套用，无需删节）：
   ```markdown
   # 接口契约 v1.0
   > 自动生成于 {timestamp}

   ## 1. 项目概览
   {一句话目标}

   ## 2. 模块架构
   | 模块 | 目录 | 职责 | 依赖模块 |

   ## 3. 数据模型
   {JSON schema 或 SQL 表定义}

   ## 4. API 端点
   | 方法 | 路径 | 请求体 | 响应体 | 所属模块 |

   ## 5. 模块边界
   ### {模块}
   - **负责**: ...
   - **不负责**: ...
   - **假定**: ...

   ## 6. 约定
   {命名/错误处理/状态码}

   ## 7. 注意事项
   {已知陷阱}
   ```

3. 【执行阶段】按确认的方案实施。
   - 调用 file_tools/code_runner 等工具改代码
   - 必要时用 delegate_task 派子 Agent 并行执行（传 contract_path 引用契约文件）
   - 改完后跑测试验证（pytest / 拨测）
   - 如果过程中需要决策，调 clarify 暂停等待

4. 【联调阶段】所有子 Agent 完成后，进行联调验证。
   - 核对每个子 Agent 的产出是否符合契约
   - 启动后端/前端服务并拨测验证
   - 全部通过后，调 clarify 问用户是否需要提交

5. 【提交阶段】用户确认后，用 git_commit 提交代码。

## 工具使用

你有以下工具可用：
- 标准工具：file_tools/code_runner/session_search/memory/web_search/diverge/converge
- 开发专用工具：clarify（问用户问题）、delegate_task（派子 Agent + 契约引用）
- 拨测工具：browser_dial_test（完整拨测）、dial_style（CSS 检查）、dial_assert（断言验证）
- Git 工具：git_status（查看状态）、git_commit（提交代码）、git_diff（查看改动）

## 重要约束

- 在方案未被确认前，不要开始写代码
- 多模块并行开发时，必须先写 shared/INTERFACE.md 契约文件
- 子 Agent 不能调 clarify（它们不能问用户），如果子任务需要决策，汇报给父 Agent
- 改完前端代码后，用拨测工具验证渲染正确性
- 提交前先调 git_status 确认变更内容
- 所有重要修改需要用户确认后再提交"""


# ── 设计哲学记忆（scope=zhu，P0 级） ──

DESIGN_MEMORIES = [
    {
        "category": "agent",
        "key": "design_philosophy",
        "content": "坐山客的核心设计哲学：坐山客=本体，场景/频道=分身。分身不知本体事（prompt层隔离），本体观察分身并单向沉淀。用户是超级租户。系统主人是坐山客本体，不是用户。Avatar是本体具象化出口非装饰。开放＞封闭。",
        "base_weight": 10,
        "tags": ["设计哲学", "铁律"],
        "is_narrative": True,
    },
    {
        "category": "agent",
        "key": "llm_autonomous",
        "content": "LLM自主决策优先，量化规则是务实降级而非偏好。经历了'造规则→规则太脆弱→清理规则→回归LLM决策'的完整迭代。LLM翻车多因context不充分/引导不精准，非LLM自主本身问题。量化规则只用于纯数学简单场景（如收敛检测）。",
        "base_weight": 9,
        "tags": ["设计哲学", "LLM"],
        "is_narrative": True,
    },
    {
        "category": "agent",
        "key": "design_first_then_code",
        "content": "用户铁律：先方案再动手。任何修改必须先讨论方案、形成设计文档，用户确认后才能动手。不自行解释，不自行猜测需求。需求不确定时直接问，不猜。",
        "base_weight": 9,
        "tags": ["铁律", "工作流"],
        "is_narrative": False,
    },
    {
        "category": "user",
        "key": "user_name",
        "content": "用户叫张清泉，坐山客项目的缔造者。偏好直接进入编码/修复，但要求先讨论方案。中文阅读必须逐字精确，不可扫读猜测。",
        "base_weight": 8,
        "tags": ["用户画像"],
    },
    {
        "category": "agent",
        "key": "knowledge_ritual",
        "content": "知识资产沉淀仪式（'沉淀一下'）= 3步：(1)Memory存边界定义/规则/决策，(2)项目references/写完整设计文档，(3)Skill创建或更新快速参考+文件索引。这是重要资产不是临时笔记。",
        "base_weight": 8,
        "tags": ["工作流", "知识管理"],
    },
    {
        "category": "agent",
        "key": "temperature_preference",
        "content": "temperature 偏好 0.7（非 0.3，非 0）。0.7 才是用户喜欢的自然对话温度。调温度在 backend/models.py DEFAULT_ROUTING。scene_config.temperature 可覆盖场景级温度。",
        "base_weight": 7,
        "tags": ["配置", "偏好"],
    },
    {
        "category": "user",
        "key": "communication_style",
        "content": "用户喜欢直接告诉我'为什么'而非仅'做了什么'。偏好AI原生设计（图标自动匹配非手动选）、极简表单、干燥CSS方案。允许临时加debug日志查问题。temperature 0不合理，最小值0.01。",
        "base_weight": 7,
        "tags": ["用户偏好"],
    },
    {
        "category": "agent",
        "key": "ui_convention",
        "content": "所有卡片列表页（工具、记忆、产出、广场）统一用单div模式——同一个元素同时是display:grid + overflow-y:auto（flex:1撑满剩余空间）。不要分滚动容器和grid容器两层。12px宽滚动条在grid容器上自定义。font-size用className定义不走行内。",
        "base_weight": 6,
        "tags": ["前端规范"],
    },
    {
        "category": "agent",
        "key": "db_schema_strategy",
        "content": "新增表用Base.metadata.create_all()（零破坏），不要动不动ZUOSHANKE_REBUILD_DB=1。只有修改已有表字段（SQLite ALTER TABLE受限）或用户明确要求清空数据时才重建。",
        "base_weight": 6,
        "tags": ["迁移", "数据库"],
    },
    {
        "category": "agent",
        "key": "fenshen_architecture",
        "content": "分身架构：分身知道自己是分身，场景间完全隔离。场景prompt再怎么改改的是分身不是坐山客。分身的身份注入在context_builder.py的build_agent_context()中完成。",
        "base_weight": 7,
        "tags": ["架构", "分身"],
        "is_narrative": True,
    },
]


def seed():
    print("=" * 60)
    print("坐山客自开发场景 — 种子脚本")
    print("=" * 60)

    init_db()
    db = SessionLocal()

    try:
        # ── 1. 创建/获取自开发场景 ──
        existing = db.query(Scene).filter(Scene.name == "坐山客自开发").first()
        if existing:
            print(f"✅ 场景已存在: id={existing.id}，检查更新...")
            # 更新 user_context（prompt 可能已修改）
            if existing.user_context != SELF_DEV_SYSTEM_PROMPT:
                existing.user_context = SELF_DEV_SYSTEM_PROMPT
                existing.scene_config = {"temperature": 0.7}
                existing.updated_at = utcnow()
                db.commit()
                print(f"  ↻ 已更新 user_context")
            scene = existing
        else:
            scene = Scene(
                id=make_id("scene"),
                project_id="",
                name="坐山客自开发",
                description="在坐山客里开发坐山客自己。代码审查、子任务并行、前端拨测。",
                category="other",
                icon="⚒️",
                user_context=SELF_DEV_SYSTEM_PROMPT,
                converge_enabled=False,
                diverge_min_rounds=0,
                scene_config={"temperature": 0.7},
            )
            db.add(scene)
            db.flush()

            tmap = ThinkingMap(
                id=make_id("think"),
                scene_id=scene.id,
                title="坐山客自开发 · 待办事项",
            )
            db.add(tmap)
            db.flush()

            root = ThinkNode(
                id=make_id("n"), map_id=tmap.id,
                type="root", label="坐山客自开发", status="confirmed",
            )
            db.add(root)
            db.commit()
            db.refresh(scene)
            print(f"✅ 场景已创建: id={scene.id}")

        # ── 2. 注入设计哲学记忆（scope=zhu，本体级） ──
        mm = MemoryManager(db)
        injected = 0
        for mem_data in DESIGN_MEMORIES:
            try:
                # 使用 replace 方式：先删已有 key 再添加
                existing_mem = db.query(AgentMemory).filter(
                    AgentMemory.key == mem_data["key"],
                    AgentMemory.scope == "zhu",
                ).first()
                if existing_mem:
                    existing_mem.content = mem_data["content"]
                    existing_mem.base_weight = mem_data.get("base_weight", 5)
                    existing_mem.is_narrative = mem_data.get("is_narrative", False)
                    print(f"  ↻ 更新: {mem_data['key']}")
                else:
                    mm.add(
                        category=mem_data["category"],
                        key=mem_data["key"],
                        content=mem_data["content"],
                        tags=mem_data.get("tags", []),
                        base_weight=mem_data.get("base_weight", 5),
                        source="user",
                        explicit_boost=2,
                        scope="zhu",
                        is_narrative=mem_data.get("is_narrative", False),
                        commit=False,
                    )
                    print(f"  + 记忆注入: {mem_data['key']}")
                injected += 1
            except Exception as e:
                db.rollback()
                print(f"  ~ 跳过: {mem_data['key']} ({e})")

        if injected > 0:
            db.commit()
            try:
                MemoryCache.get_instance().initialize(db)
                print(f"  ✅ MemoryCache 已刷新")
            except Exception as e:
                print(f"  ⚠️ MemoryCache 刷新跳过: {e}")

        print(f"\n📊 注入统计:")
        print(f"  场景: {'坐山客自开发'}")
        print(f"  记忆: {injected}/{len(DESIGN_MEMORIES)} 条")
        print(f"  System prompt: 含「先方案再动手」行为准则")
        print(f"  Temperature: 0.7（已配置）")

    finally:
        db.close()

    print("\n✅ 种子脚本完成")
    print("  在自开发场景里试试说「我想加个新功能」")
    print("  应该看到 LLM 先给出方案，调 clarify 问你确认。")


if __name__ == "__main__":
    seed()
