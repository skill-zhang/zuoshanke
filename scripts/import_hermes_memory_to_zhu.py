#!/usr/bin/env python3
"""将 Hermes Agent 的全部记忆导入坐山客本体（scope=zhu）记忆。"""

import sys, os
sys.path.insert(0, os.path.expanduser("~/zuoshanke/backend"))

from database import SessionLocal
from agent_core.memory_manager import MemoryManager

# ═══════════ 全部记忆数据 ═══════════

MEMORIES = [
    # ── 系统运维 ──
    {
        "key": "zuoshanke_wsl_network",
        "content": "WSL网络: IP=192.168.3.9(与Windows同局域网)。Windows浏览器可直接访问 localhost 直连WSL服务。不要用 portproxy。",
        "tags": ["ops", "network", "wsl"],
        "base_weight": 6,
    },
    {
        "key": "zuoshanke_backend_startup",
        "content": "坐山客后端启动: venv在 ~/zuoshanke/backend/.venv/bin/python。启动命令: .venv/bin/python main.py。端口8000被占用时用 fuser -k 8000/tcp 释放。",
        "tags": ["ops", "backend", "startup"],
        "base_weight": 6,
    },
    {
        "key": "zuoshanke_db_migration_policy",
        "content": "DB schema变更策略: 新增表用 Base.metadata.create_all()（零破坏），不要用 ZUOSHANKE_REBUILD_DB=1。只有①修改已有表字段（SQLite ALTER TABLE受限）或②用户明确要求清空数据时才重建。",
        "tags": ["ops", "database", "migration"],
        "base_weight": 7,
    },
    {
        "key": "zuoshanke_git_backup",
        "content": "Git仅本地（GitHub被墙）。zuoshanke项目E盘备份: /mnt/e/zuoshanke-backup/zuoshanke.git (remote:backup)。备份脚本 ~/zuoshanke/scripts/backup.sh。每2h有改动提醒提交；每天收工提交。session开始检查git status。",
        "tags": ["ops", "git", "backup"],
        "base_weight": 6,
    },
    {
        "key": "zuoshanke_frontend_card_pattern",
        "content": "前端卡片列表页样式规范: 单div模式(display:grid + overflow-y:auto + 12px scrollbar)。sidebar文案统一13px，页面标题16px，三点···14px。section间距用children的margin-bottom控制。font-size用className定义不走行内。",
        "tags": ["frontend", "css", "pattern"],
        "base_weight": 5,
    },
    {
        "key": "knowledge_asset_ceremony",
        "content": "知识资产沉淀仪式: 「沉淀一下」=3步：(1)Memory存边界定义/规则/决策，(2)项目references/写完整设计实现文档，(3)Skill创建或更新快速参考+文件索引。缺一不可。",
        "tags": ["workflow", "documentation"],
        "base_weight": 7,
    },
    {
        "key": "user_single_div_scroll_pattern",
        "content": "用户偏好: 所有卡片列表页（工具、记忆、产出、广场）统一用单div模式——同一个元素同时是display:grid + overflow-y:auto（flex:1撑满剩余空间）。不要分「滚动容器」和「grid容器」两层，12px宽滚动条在grid容器上自定义。",
        "tags": ["frontend", "css", "ui", "user-preference"],
        "base_weight": 5,
    },

    # ── 设计哲学与架构 ──
    {
        "key": "schema_v08_identity_architecture",
        "content": "Schema v0.8（2026-05-26）: 坐山客=持久本体，场景/频道分身=干活个体。分身prompt=核心人格+场景自定义，分身知自己是分身。Avatar反映本体状态非分身（合体非住进去）。LLM是能力引擎非人格。核心:本我不可篡改，分身可自定。闲聊频道=本体之家。",
        "tags": ["architecture", "design", "identity", "schema"],
        "base_weight": 8,
    },
    {
        "key": "design_philosophy_20260528",
        "content": "设计哲学（2026-05-28纲领）: 坐山客是主人，用户是超级租户（自由度可收回）。Avatar是本体具象化，陪伴者非工具。本体不可篡改，分身知是分身。LLM是引擎非人格，换模型坐山客不变。PATCH user_context=null→恢复默认。",
        "tags": ["architecture", "design", "philosophy", "core"],
        "base_weight": 9,
    },
    {
        "key": "schema_v081_converge",
        "content": "Schema v0.81（2026-05-20）: 收敛系统自动触发(叶子>=分支×阈值，每层独立)。按轮数触发auto-diverge+全量context+递归树。leaf加子自动→domain。converge带回项目认知(LLM判project.is_project)。闲聊跳过。三参数存scene: converge_threshold/converge_enabled/diverge_min_rounds。新表output_projects。",
        "tags": ["architecture", "converge", "schema"],
        "base_weight": 7,
    },
    {
        "key": "mood_analyzing_nine_states",
        "content": "坐山客mood 9态（2026-07-add analyzing）: idle/watching/analyzing/thinking/amused/annoyed/speaking/singing/resting。analyzing在agent loop调工具时触发(fenshen:analyzing→scenes.py)。前脸映射:focused eyes+neutral mouth+蓝光脉冲动画，45s超时归位idle。闲聊频道=本体之家，is_zhu_home判scene_name==\"闲聊\"，skip分身observation文案，让[心情:]标签自然表达。",
        "tags": ["avatar", "mood", "design", "schema"],
        "base_weight": 6,
    },
    {
        "key": "prompt_style_dry_facts",
        "content": "Prompt风格偏好：干燥简洁的事实陈述，非行为指令。system prompt 写作：专业、有洞察力，不要「锐利」（会导致AI抬杠/反驳用户）。身份声明三行即完，不煽情不啰嗦。",
        "tags": ["prompt", "style", "writing"],
        "base_weight": 5,
    },

    # ── 用户画像 ──
    {
        "key": "user_zhangqingquan",
        "content": "用户：张清泉，英文名skill。叫我「坐山客」或「Hermes」。偏好直接进入编码/修复（说「开始干吧」后就闭嘴干活）。有强的技术直觉，能准确定位root cause。是实战型测试者——关注系统完整性（断连、缓存、UI联动、边界状态）。重视收工仪式（沉淀3步+git+备份）。UI细节敏锐。",
        "tags": ["user", "profile"],
        "base_weight": 9,
    },
    {
        "key": "user_no_curl_test",
        "content": "用户偏好: 不要用curl/python inline test command验证。告诉用户URL让用户自己测试，而不是替用户运行验证命令。",
        "tags": ["user", "preference"],
        "base_weight": 6,
    },
    {
        "key": "user_ai_native_design",
        "content": "用户偏好AI原生设计: 图标自动匹配（非手动选）、极简表单、干燥CSS方案。LLM情绪表达需对话自然产出[心情:]标签，禁止独立分析。清理旧功能前需发列表确认。AI角色必须有表情和灵魂——角色动画不只是装饰，是AI具象化的核心体验。",
        "tags": ["user", "preference", "design"],
        "base_weight": 7,
    },
    {
        "key": "user_work_style",
        "content": "用户工作风格: 倾向充分讨论形成完整设计文档后再动手编码。讨厌草率开干来回折腾。倾向简单的量化规则而非复杂自主AI决策。重视组件间的清晰联动关系，认为机制不应是摆设。",
        "tags": ["user", "preference", "workflow"],
        "base_weight": 7,
    },
    {
        "key": "user_cleanup_confirm",
        "content": "用户铁律：清理旧功能/旧数据前必须先发列表让他确认，不能直接动手删。他明确要求「清之前发个列表，我来确认一下」。",
        "tags": ["user", "preference", "safety"],
        "base_weight": 8,
    },
    {
        "key": "user_minimal_form",
        "content": "用户偏好极简输入表单: 新建类别的弹窗只放一个「类别名称」输入框即可。不需要图标选择、英文标识等多余字段。系统自动从中文名生成英文标识+默认图标。",
        "tags": ["user", "preference", "ui"],
        "base_weight": 6,
    },
    {
        "key": "user_no_mood_analysis",
        "content": "设计铁律: LLM情绪表达必须是自然的对话副产品，禁止独立的LLM分析/规则判断。做法：system prompt让LLM直接输出[心情: 情绪词]标签→后端剥离解析。",
        "tags": ["architecture", "design", "mood"],
        "base_weight": 7,
    },
    {
        "key": "user_zhu_super_tenant",
        "content": "权力结构: 坐山客（本体）是系统真正主人，用户是「超级租户」—自由度极大但授予的非固有的。Avatar是本体具象化出口非装饰。开放＞封闭。UI背景设定默认只读+Markdown渲染。产出成果点卡片新标签打开。数字原生原则。",
        "tags": ["architecture", "philosophy", "core"],
        "base_weight": 8,
    },
]


def main():
    db = SessionLocal()
    mm = MemoryManager(db)
    imported = 0
    skipped = 0

    for m in MEMORIES:
        existing = mm.get(m["key"])
        if existing:
            # 已存在→强化
            mm.reinforce(m["key"], boost=2)
            print(f"  🔄 {m['key']} — 已存在，强化权重")
            skipped += 1
            continue

        mm.add(
            category="agent",
            key=m["key"],
            content=m["content"],
            tags=m["tags"],
            base_weight=m["base_weight"],
            source="llm",
            scope="zhu",         # 本体级记忆
        )
        print(f"  ✅ {m['key']} — 已导入 (weight={m['base_weight']})")
        imported += 1

    db.close()

    print(f"\n{'='*50}")
    print(f"导入完成: 新增 {imported} 条, 跳过/强化 {skipped} 条")
    print(f"本体记忆总数: {imported + skipped} 条")


if __name__ == "__main__":
    main()
