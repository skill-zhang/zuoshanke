#!/usr/bin/env python3
"""Schema v1.5: ADD is_core / compressed / keywords / last_injected_at to agent_memory.

Run after schema-v1.5 design document implementation.

Steps:
1. ALTER TABLE to add 4 new columns (idempotent)
2. Tag existing P0 memories (base_weight >= 8, scope='zhu') as is_core=True
3. Auto-extract keywords for all scope='zhu' memories that have empty keywords
"""
import sys
sys.path.insert(0, "backend")

from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # ── Step 1: Check and add columns (idempotent) ──
    cols = {r[0] for r in db.execute(text("PRAGMA table_info(agent_memory)")).fetchall()}

    if "is_core" not in cols:
        db.execute(text("ALTER TABLE agent_memory ADD COLUMN is_core BOOLEAN DEFAULT 0"))
        print("✅ ADDED is_core")
    else:
        print("⏭️ is_core already exists")

    if "compressed" not in cols:
        db.execute(text("ALTER TABLE agent_memory ADD COLUMN compressed TEXT DEFAULT NULL"))
        print("✅ ADDED compressed")
    else:
        print("⏭️ compressed already exists")

    if "keywords" not in cols:
        db.execute(text("ALTER TABLE agent_memory ADD COLUMN keywords JSON DEFAULT '[]'"))
        print("✅ ADDED keywords")
    else:
        print("⏭️ keywords already exists")

    if "last_injected_at" not in cols:
        db.execute(text("ALTER TABLE agent_memory ADD COLUMN last_injected_at TIMESTAMP DEFAULT NULL"))
        print("✅ ADDED last_injected_at")
    else:
        print("⏭️ last_injected_at already exists")

    db.commit()

    # ── Step 2: Tag P0 scope='zhu' memories as is_core ──
    from agent_core.memory_manager import MemoryManager
    from models import AgentMemory

    mm = MemoryManager(db)

    p0_mems = db.query(AgentMemory).filter(
        AgentMemory.scope == "zhu",
        AgentMemory.base_weight >= 8,
        AgentMemory.is_core == False,
    ).all()

    marked_count = 0
    for mem in p0_mems:
        mem.is_core = True
        marked_count += 1
        print(f"  🔖 {mem.key} — marked as is_core=True (base_weight={mem.base_weight})")

    if marked_count:
        db.commit()
        print(f"✅ Tagged {marked_count} P0 memories as is_core=True")
    else:
        print("⏭️ No new P0 memories to tag")

    # ── Step 3: Extract keywords for scope='zhu' memories with empty keywords ──
    zhu_mems = db.query(AgentMemory).filter(
        AgentMemory.scope == "zhu",
    ).all()

    kw_updated = 0
    for mem in zhu_mems:
        current_kw = mem.keywords or []
        if not current_kw:
            mem.keywords = mm.extract_keywords(mem.content, max_count=10)
            kw_updated += 1

    if kw_updated:
        db.commit()
        print(f"✅ Extracted keywords for {kw_updated} zhu memories")
    else:
        print("⏭️ All zhu memories already have keywords")

    # ── Verify ──
    total = db.execute(text("SELECT COUNT(*) FROM agent_memory")).scalar()
    core_count = db.execute(text("SELECT COUNT(*) FROM agent_memory WHERE is_core=1")).scalar()
    kw_count = db.execute(
        text("SELECT COUNT(*) FROM agent_memory WHERE json_array_length(keywords) > 0")
    ).scalar()

    print(f"\n{'='*50}")
    print(f"📊 Migration Result:")
    print(f"   Total memories:      {total}")
    print(f"   is_core=True:        {core_count}")
    print(f"   Has keywords:        {kw_count}")
    print(f"   Fields added:        is_core, compressed, keywords, last_injected_at")

    # Show Core Tier candidates
    if core_count:
        print(f"\n📌 Core Tier memories:")
        cores = db.execute(
            text("SELECT key, base_weight, priority_level FROM agent_memory WHERE is_core=1 ORDER BY base_weight DESC")
        ).fetchall()
        for c in cores:
            print(f"   🏆 {c[0]} (weight={c[1]}, {c[2]})")

finally:
    db.close()
