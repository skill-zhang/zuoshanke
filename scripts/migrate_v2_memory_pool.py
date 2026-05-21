#!/usr/bin/env python3
"""ALERT TABLE: add v2 fields to agent_memory + migrate existing scope=zhu as is_immortal."""
import sys
sys.path.insert(0, "backend")

from database import engine, SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # Check if columns exist
    cols = [r[0] for r in db.execute(text("PRAGMA table_info(agent_memory)")).fetchall()]
    
    if "is_narrative" not in cols:
        db.execute(text("ALTER TABLE agent_memory ADD COLUMN is_narrative BOOLEAN DEFAULT 0"))
        print("✅ ADDED is_narrative")
    else:
        print("⏭️ is_narrative already exists")
    
    if "is_immortal" not in cols:
        db.execute(text("ALTER TABLE agent_memory ADD COLUMN is_immortal BOOLEAN DEFAULT 0"))
        print("✅ ADDED is_immortal")
    else:
        print("⏭️ is_immortal already exists")
    
    if "correction_trail" not in cols:
        db.execute(text("ALTER TABLE agent_memory ADD COLUMN correction_trail TEXT DEFAULT '[]'"))
        print("✅ ADDED correction_trail")
    else:
        print("⏭️ correction_trail already exists")
    
    # Migrate: existing scope='zhu' → is_immortal=1
    db.execute(text("UPDATE agent_memory SET is_immortal=1 WHERE scope='zhu' AND is_immortal=0"))
    print("✅ Migrated existing scope='zhu' memories to is_immortal=1")
    
    db.commit()
    print("\n✅ All migrations complete")
    
    # Verify
    count = db.execute(text("SELECT COUNT(*) FROM agent_memory WHERE is_immortal=1")).scalar()
    total = db.execute(text("SELECT COUNT(*) FROM agent_memory")).scalar()
    narrative_count = db.execute(text("SELECT COUNT(*) FROM agent_memory WHERE is_narrative=1")).scalar()
    print(f"   Total memories: {total}")
    print(f"   Immortal: {count}")
    print(f"   Narrative: {narrative_count}")
finally:
    db.close()
