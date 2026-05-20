"""迁移脚本：修复 explicit_boost 爆炸问题

背景：memory_manager.py:reinforce() 之前用乘法（×2）而非加法，
导致部分记忆的 explicit_boost 呈指数增长（2^n）。
部分记忆高达 2^62 ≈ 4.6×10^18。

修复策略：
- explicit_boost <= 10 的保持不变（合理范围）
- explicit_boost > 10 的，按等级重新设定合理值：
  - P0 → 8（"记住这个"级）
  - P1 → 4（"重要"级）
  - P2 → 2（"有点印象"级）
  - 其他 → 1
"""

import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zuoshanke.db")

def main(dry_run=True):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. 统计爆炸情况
    total = conn.execute("SELECT COUNT(*) FROM agent_memory").fetchone()[0]
    exploded = conn.execute(
        "SELECT COUNT(*) FROM agent_memory WHERE explicit_boost > 10"
    ).fetchone()[0]

    print(f"记忆总数: {total}")
    print(f"explicit_boost > 10 (爆炸): {exploded}")
    print()

    if exploded == 0:
        print("没有需要修复的记忆，一切正常 ✅")
        return

    # 2. 看爆炸分布
    rows = conn.execute(
        "SELECT id, key, explicit_boost, priority_level, content "
        "FROM agent_memory WHERE explicit_boost > 10 "
        "ORDER BY explicit_boost DESC"
    ).fetchall()

    print(f"{'boost(原)':>22} {'等级':>4} {'新boost':>8}  内容")
    print("-" * 90)

    updates = []
    for r in rows:
        d = dict(r)
        old = d["explicit_boost"]
        pl = d["priority_level"]

        # 按等级设定合理值
        new_boost = {"P0": 8, "P1": 4, "P2": 2}.get(pl, 1)
        updates.append((new_boost, d["id"]))

        log2_val = old.bit_length() - 1  # ≈log2
        print(f"{old:>22} {pl:>4} {new_boost:>8}  ~2^{log2_val}  {d['content'][:55]}")

    print()
    print(f"需要更新的记录: {len(updates)} 条")

    if dry_run:
        print("\n🟡 **干跑模式**——未执行实际更新。加 --apply 参数来实际执行。")
    else:
        conn.execute("BEGIN")
        for new_b, mid in updates:
            conn.execute(
                "UPDATE agent_memory SET explicit_boost = ? WHERE id = ?",
                (new_b, mid),
            )
        conn.commit()
        print(f"✅ 已更新 {len(updates)} 条记忆")

    conn.close()


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    main(dry_run=dry_run)
