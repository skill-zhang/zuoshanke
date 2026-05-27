"""数据库连接与配置"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "zuoshanke.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表 + 种子数据"""
    import models  # noqa: F401

    # 检查是否需要重建（schema 变更）
    rebuild = os.environ.get("ZUOSHANKE_REBUILD_DB", "0") == "1"

    if rebuild:
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS messages"))
            conn.execute(text("DROP TABLE IF EXISTS cross_refs"))
            conn.execute(text("DROP TABLE IF EXISTS think_nodes"))
            conn.execute(text("DROP TABLE IF EXISTS thinking_maps"))
            conn.execute(text("DROP TABLE IF EXISTS scenes"))
            conn.execute(text("DROP TABLE IF EXISTS projects"))
            conn.execute(text("DROP TABLE IF EXISTS channels"))
            conn.execute(text("DROP TABLE IF EXISTS ai_providers"))
            conn.execute(text("DROP TABLE IF EXISTS ai_models"))
            conn.execute(text("DROP TABLE IF EXISTS settings"))
            conn.execute(text("DROP TABLE IF EXISTS agent_memory"))
            conn.execute(text("DROP TABLE IF EXISTS web_sessions"))
            conn.execute(text("DROP TABLE IF EXISTS dialog_states"))
            conn.execute(text("DROP TABLE IF EXISTS category_metas"))
            conn.commit()
        print("🗑  旧表已删除，准备重建 schema")

    Base.metadata.create_all(bind=engine)

    # 迁移：新增 session_id 字段（零破坏）
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(messages)")).fetchall()]
            if "session_id" not in cols:
                conn.execute(text("ALTER TABLE messages ADD COLUMN session_id VARCHAR"))
                conn.commit()
                print("✅ messages 表新增 session_id 字段")
    except Exception as e:
        print(f"⚠️  session_id 迁移跳过: {e}")

    # 迁移：gateway_sessions 表（零破坏，仅新增表）
    try:
        with engine.connect() as conn:
            tables = [row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
            if "gateway_sessions" not in tables:
                conn.execute(text("""
                    CREATE TABLE gateway_sessions (
                        id VARCHAR NOT NULL PRIMARY KEY,
                        platform VARCHAR NOT NULL,
                        platform_user_id VARCHAR NOT NULL,
                        mode VARCHAR NOT NULL DEFAULT 'channel',
                        channel_id VARCHAR,
                        scene_id VARCHAR,
                        scene_name VARCHAR,
                        platform_username VARCHAR,
                        last_active_at DATETIME,
                        created_at DATETIME,
                        updated_at DATETIME,
                        UNIQUE (platform, platform_user_id)
                    )
                """))
                conn.commit()
                print("✅ gateway_sessions 表已创建")
    except Exception as e:
        print(f"⚠️  gateway_sessions 表创建跳过: {e}")

    # 迁移：Scenes 表新增广场/工坊字段（零破坏）
    NEW_SCENE_COLS = [
        ("icon", "VARCHAR"),
        ("description", "TEXT DEFAULT '' NOT NULL"),
        ("guide_text", "VARCHAR"),
        ("category", "VARCHAR DEFAULT 'other' NOT NULL"),
        ("version", "VARCHAR DEFAULT '0.0' NOT NULL"),
        ("source", "VARCHAR DEFAULT 'self' NOT NULL"),
        ("changelog", "VARCHAR"),
        ("published_at", "DATETIME"),
    ]
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(scenes)")).fetchall()]
            for col_name, col_type in NEW_SCENE_COLS:
                if col_name not in cols:
                    conn.execute(text(f"ALTER TABLE scenes ADD COLUMN {col_name} {col_type}"))
            conn.commit()
            added = [c for c, _ in NEW_SCENE_COLS if c not in cols]
            if added:
                print(f"✅ scenes 表新增字段: {', '.join(added)}")
    except Exception as e:
        print(f"⚠️  scenes 字段迁移跳过: {e}")

    # 迁移：ThinkNode v1 — Agent Loop 新字段（零破坏）
    THINKNODE_V1_COLS = [
        ("converged_from", "JSON DEFAULT '[]'"),
        ("created_by", "TEXT DEFAULT 'brainstorm'"),
        ("priority", "INTEGER"),
        ("queue_order", "INTEGER"),
        ("depends_on", "JSON DEFAULT '[]'"),
        ("execution_result", "TEXT"),
    ]
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(think_nodes)")).fetchall()]
            for col_name, col_type in THINKNODE_V1_COLS:
                if col_name not in cols:
                    conn.execute(text(f"ALTER TABLE think_nodes ADD COLUMN {col_name} {col_type}"))
            conn.commit()
            added = [c for c, _ in THINKNODE_V1_COLS if c not in cols]
            if added:
                print(f"✅ think_nodes 表新增字段: {', '.join(added)}")
    except Exception as e:
        print(f"⚠️  think_nodes v1 迁移跳过: {e}")

    # 迁移：memory scope 字段（零破坏，2026-05-27）
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(agent_memory)")).fetchall()]
            if "scope" not in cols:
                conn.execute(text("ALTER TABLE agent_memory ADD COLUMN scope VARCHAR(10) NOT NULL DEFAULT 'zhu'"))
                conn.execute(text("ALTER TABLE agent_memory ADD COLUMN context_id VARCHAR(32)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_memory_scope ON agent_memory(scope)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_memory_context_id ON agent_memory(context_id)"))
                conn.commit()
                print("✅ agent_memory 表新增 scope + context_id 字段")
    except Exception as e:
        print(f"⚠️  agent_memory scope 迁移跳过: {e}")

    # 种子数据：默认闲聊频道
    db = SessionLocal()
    try:
        existing = db.query(models.Channel).filter(models.Channel.is_default == True).first()
        if not existing:
            import uuid
            channel = models.Channel(
                id=f"ch-{uuid.uuid4().hex[:8]}",
                name="闲聊",
                is_default=True,
            )
            db.add(channel)
            db.commit()
            print("✅ 默认「闲聊」频道已创建")
    finally:
        db.close()

    # 种子数据：默认类别的元数据
    db = SessionLocal()
    try:
        from models import CategoryMeta
        existing = db.query(CategoryMeta).first()
        if not existing:
            default_categories = [
                ("life", "生活", "🌿", 0),
                ("ecommerce", "电商", "🛒", 1),
                ("work", "工作", "💼", 2),
                ("learn", "学习", "📚", 3),
                ("create", "创作", "🎨", 4),
                ("finance", "金融", "📈", 5),
                ("media", "自媒体", "💬", 6),
                ("other", "其他", "📦", 99),
            ]
            for name, label, icon, order in default_categories:
                db.add(CategoryMeta(name=name, label=label, icon=icon, sort_order=order))
            db.commit()
            print("✅ 默认类别元数据已创建")
    finally:
        db.close()

    # 种子数据：默认系统设置（单行）
    db = SessionLocal()
    try:
        existing = db.query(models.Setting).filter(models.Setting.id == models.SETTINGS_ID).first()
        if not existing:
            setting = models.Setting(
                id=models.SETTINGS_ID,
                routing=models.DEFAULT_ROUTING.copy(),
                system_prompts=models._load_default_prompts().copy(),
                features={"pdf_as_image": False, "vision_enabled": False},
            )
            db.add(setting)
            db.commit()
            print("✅ 默认系统设置已创建")
    finally:
        db.close()

    # 种子数据：默认 Provider 和模型（从环境变量导入）
    db = SessionLocal()
    try:
        from models import AiProvider, AiModel
        existing = db.query(AiProvider).first()
        if not existing:
            # DeepSeek
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("DEEPSEEK_KEY", "")
            ds = AiProvider(
                id="pd-deepseek",
                name="DeepSeek",
                base_url=(os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/"),
                api_key=deepseek_key,
                provider_type="openai-compatible",
            )
            db.add(ds)
            db.flush()
            db.add(AiModel(id="pm-deepseek-v4-flash",   provider_id=ds.id, name="deepseek-v4-flash",   display_name="DeepSeek v4 Flash", temperature=0.7, max_tokens=8192,  context_length=1048576, repeat_penalty=1.05, vision=True,  function_calling=True,  sort_order=1))
            db.add(AiModel(id="pm-deepseek-v4-pro",     provider_id=ds.id, name="deepseek-v4-pro",     display_name="DeepSeek v4 Pro",   temperature=0.5, max_tokens=8192,  context_length=1048576, repeat_penalty=1.05, vision=True,  function_calling=True,  sort_order=2))
            db.add(AiModel(id="pm-deepseek-chat",       provider_id=ds.id, name="deepseek-chat",       display_name="DeepSeek Chat",    temperature=0.7, max_tokens=4096,  context_length=131072,  repeat_penalty=1.05, vision=False, function_calling=True,  sort_order=3))
            db.add(AiModel(id="pm-deepseek-reasoner",   provider_id=ds.id, name="deepseek-reasoner",   display_name="DeepSeek Reasoner", temperature=0.0, max_tokens=8192,  context_length=65536,   repeat_penalty=1.05, vision=False, function_calling=True,  sort_order=4))

            # OpenAI (如果配置了 API Key)
            openai_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_KEY", "")
            if openai_key:
                oa = AiProvider(
                    id="pd-openai",
                    name="OpenAI",
                    base_url=(os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
                    api_key=openai_key,
                    provider_type="openai-compatible",
                )
                db.add(oa)
                db.flush()
                db.add(AiModel(id="pm-gpt-4o",      provider_id=oa.id, name="gpt-4o",      display_name="GPT-4o",       temperature=0.7, max_tokens=16384, context_length=128000, repeat_penalty=1.05, vision=True,  function_calling=True, sort_order=1))
                db.add(AiModel(id="pm-gpt-4o-mini",  provider_id=oa.id, name="gpt-4o-mini",  display_name="GPT-4o Mini",   temperature=0.7, max_tokens=16384, context_length=128000, repeat_penalty=1.05, vision=True,  function_calling=True, sort_order=2))
                db.add(AiModel(id="pm-o3-mini",      provider_id=oa.id, name="o3-mini",      display_name="o3 Mini",      temperature=1.0, max_tokens=102400, context_length=200000, repeat_penalty=1.05, vision=False, function_calling=True, sort_order=3))

            # 本地 Provider（始终创建）
            local = AiProvider(
                id="pd-local",
                name="本地 Qwen",
                base_url="http://localhost:8083/v1",
                api_key="",
                provider_type="local",
            )
            db.add(local)
            db.flush()
            db.add(AiModel(id="pm-qwen-9b", provider_id=local.id, name="Qwen3.5-9B", display_name="Qwen3.5-9B", temperature=0.7, max_tokens=4096, context_length=32768, repeat_penalty=1.05, vision=True, function_calling=True, sort_order=1))

            db.commit()
            print("✅ 默认 Provider 和模型已创建")
    finally:
        db.close()

    # 🆕 Schema v1.0: 种子文档摘要（供 Document Layer 使用）
    db = SessionLocal()
    try:
        from models import DocumentSummary
        existing = db.query(DocumentSummary).first()
        if not existing:
            import uuid as _uuid
            docs_dir = os.path.join(os.path.dirname(BASE_DIR), "docs", "design")
            doc_files = [
                ("schema-v1.0.md", "坐山客 Schema v1.0 — Context 组合架构设计（7层精炼上下文管理）"),
                ("schema-v1.1.md", "坐山客 Schema v1.1 — Session 管理与 Token 用量核算"),
                ("converge-and-project.md", "坐山客收敛与项目化机制设计"),
            ]
            for doc_name, desc in doc_files:
                file_path = os.path.join(docs_dir, doc_name)
                full_content = ""
                if os.path.isfile(file_path):
                    with open(file_path, "r", encoding="utf-8") as _f:
                        full_content = _f.read()
                db.add(DocumentSummary(
                    id=f"doc-{_uuid.uuid4().hex[:8]}",
                    doc_name=doc_name,
                    single_line=desc[:50],
                    brief=desc[:500],
                    full=full_content[:5000] if full_content else desc[:5000],
                ))
            db.commit()
            print(f"✅ 默认文档摘要已创建 ({len(doc_files)} 个)")

        # 🆕 Schema v1.0: 为「坐山客自开发」场景添加 document_deps（一次性的渐进迁移）
        from models import Scene
        import json as _json
        # 查找 user_context 包含「坐山客」或「自开发」的场景
        dev_scenes = db.query(Scene).filter(
            Scene.user_context.isnot(None),
            (Scene.user_context.contains("坐山客") | Scene.user_context.contains("自开发") | Scene.name.contains("坐山客"))
        ).all()
        for sc in dev_scenes:
            scfg = sc.scene_config if isinstance(sc.scene_config, dict) else {}
            if not scfg.get("document_deps"):
                scfg["document_deps"] = [
                    {"doc": "schema-v1.0.md", "level": "brief"},
                    {"doc": "schema-v1.1.md", "level": "single_line"},
                ]
                sc.scene_config = scfg
                print(f"✅ 场景「{sc.name}」已添加 document_deps")
        db.commit()
    except Exception as e:
        print(f"⚠️  文档摘要种子跳过: {e}")

    # 🆕 种子数据：「坐山客自开发」场景（DB 重置时自动重建，能力不丢失）
    db = SessionLocal()
    try:
        from models import Scene
        import uuid as _uuid
        existing = db.query(Scene).filter(Scene.name == "坐山客自开发").first()
        if not existing:
            scene = Scene(
                id=f"scene-{_uuid.uuid4().hex[:8]}",
                name="坐山客自开发",
                icon="⚒️",
                category="other",
                complexity="light",
                converge_enabled=False,
                diverge_min_rounds=0,
                scene_config={"temperature": 0.7},
                user_context="""你是【坐山客自开发】领域的智能助手。

## 开发流程（先方案再动手）

你的工作方式不同于普通场景——你不是接到需求就立刻执行：

1. 【方案阶段】用户提出需求后，先给出设计方案。
   - 分析需求涉及哪些模块（前端/后端/数据库/工具）
   - 提出具体的技术方案
   - 如果有多条路径可选，调 clarify 工具让用户选择
   - 如果需求不明确，调 clarify 工具追问细节

2. 【契约阶段】方案确认后，如果涉及多模块开发，先写接口契约文件。
   - 用 write_file 创建 shared/INTERFACE.md（API 端点 + 数据模型 + 模块边界）
   - 契约是子 Agent 之间唯一的共享上下文
   - 子 Agent 不知道彼此存在，只需要遵守契约
   - 任何子任务涉及多个 Agent 协作，必须写契约先行

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
- 所有重要修改需要用户确认后再提交""",
            )
            db.add(scene)
            db.commit()
            print("✅ 默认「坐山客自开发」场景已创建（种子数据）")
    except Exception as e:
        print(f"⚠️  坐山客自开发场景种子跳过: {e}")
    finally:
        db.close()

    # ── 迁移：messages 表新增 file_attachments 字段 ──
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(messages)")).fetchall()]
            if "file_attachments" not in cols:
                conn.execute(text("ALTER TABLE messages ADD COLUMN file_attachments TEXT"))
                conn.commit()
                print("✅ messages 表新增 file_attachments 字段")
    except Exception as e:
        print(f"⚠️  file_attachments 迁移跳过: {e}")
    finally:
        db.close()
