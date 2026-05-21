"""修复脚本：清理 Memory 表中因乘法翻倍 bug 导致的异常权重值

背景：2026-05-20 左右 MemoryManager.reinforce() 曾使用乘法翻倍
（explicit_boost = boost * 2）而不是加法累加（explicit_boost += boost），
导致部分记忆的 explicit_boost 呈 2^n 指数增长，最高达到 262158。

当前代码已修正为加法，但已有数据仍残留异常权重值。

修复策略：
  - explicit_boost > 100  →  重置为 3（手动标记的合理上限）
  - explicit_boost 10~100 →  重置为 2（普通强化上限）
  - explicit_boost ≤ 10   →  保持不变（正常范围）

用法：
  python scripts/fix_memory_weights.py           # 干跑，只预览
  python scripts/fix_memory_weights.py --apply   # 实际写入
  python scripts/fix_memory_weights.py --apply --reset-access   # 同时重置 times_accessed 和 last_accessed_at
"""

import sqlite3
import sys
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zuoshanke.db")


def fmt_dt(dt_str):
    """格式化 datetime 字符串为短格式"""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return dt_str[:16] if dt_str else "N/A"


def main():
    dry_run = "--apply" not in sys.argv
    reset_access = "--reset-access" in sys.argv

    if dry_run:
        print("🟡 **干跑模式** — 不会实际修改数据库。加 --apply 执行写入。")
    else:
        print("🔴 **写入模式** — 将实际修改数据库。")
    if reset_access:
        print("   同时重置 times_accessed = 0 和 last_accessed_at = NULL")
    print()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── 1. 统计概况 ──
    total = conn.execute("SELECT COUNT(*) FROM agent_memory").fetchone()[0]
    gt100 = conn.execute(
        "SELECT COUNT(*) FROM agent_memory WHERE explicit_boost > 100"
    ).fetchone()[0]
    gt10 = conn.execute(
        "SELECT COUNT(*) FROM agent_memory WHERE explicit_boost > 10"
    ).fetchone()[0]
    between_10_100 = conn.execute(
        "SELECT COUNT(*) FROM agent_memory WHERE explicit_boost > 10 AND explicit_boost <= 100"
    ).fetchone()[0]

    print(f"记忆总数:         {total}")
    print(f"explicit_boost:")
    print(f"  > 100 (爆炸):    {gt100} 条 → 重置为 3")
    print(f"  10 ~ 100 (偏高): {between_10_100} 条 → 重置为 2")
    print(f"  ≤ 10 (正常):     {total - gt10} 条 (保持不变)")
    print()

    if gt10 == 0:
        print("✅ 没有异常权重记录，一切正常。")
        conn.close()
        return

    # ── 2. 获取待修复记录 ──
    rows = conn.execute(
        "SELECT id, key, explicit_boost, priority_level, content, "
        "times_accessed, last_accessed_at "
        "FROM agent_memory WHERE explicit_boost > 10 "
        "ORDER BY explicit_boost DESC"
    ).fetchall()

    # 打印修复前表格
    print(f"{'ID':>10} {'boost(旧)':>12} {'→新boost':>10} {'等级':>4} {'访问':>4} 内容")
    print("-" * 110)

    updates_gt100 = []    # → 3
    updates_10_100 = []   # → 2

    for r in rows:
        d = dict(r)
        old = d["explicit_boost"]
        pl = d["priority_level"]
        accessed = d["times_accessed"] or 0

        if old > 100:
            new_boost = 3
            updates_gt100.append(d["id"])
        else:
            new_boost = 2
            updates_10_100.append(d["id"])

        # 估算 2 的幂次
        log2_val = old.bit_length() - 1 if old > 0 else 0

        print(
            f"{d['id'][:10]:>10} "
            f"{old:>12}  →{new_boost:>8}   "
            f"{pl:>4} {accessed:>4}  "
            f"{d['content'][:60]}"
        )

    print()
    print(f"待修复合计: {len(updates_gt100) + len(updates_10_100)} 条")
    print(f"  > 100 → 3:  {len(updates_gt100)} 条")
    print(f"  10~100 → 2: {len(updates_10_100)} 条")
    if reset_access:
        print(f"  同时重置 times_accessed + last_accessed_at")

    # ── 3. 执行更新 ──
    if dry_run:
        print("\n🟡 **干跑模式** — 未执行任何写入。加 --apply 执行。")
    else:
        conn.execute("BEGIN")
        # 更新 > 100 → 3
        for mid in updates_gt100:
            if reset_access:
                conn.execute(
                    "UPDATE agent_memory SET explicit_boost = 3, "
                    "times_accessed = 0, last_accessed_at = NULL "
                    "WHERE id = ?",
                    (mid,),
                )
            else:
                conn.execute(
                    "UPDATE agent_memory SET explicit_boost = 3 WHERE id = ?",
                    (mid,),
                )
        # 更新 10~100 → 2
        for mid in updates_10_100:
            if reset_access:
                conn.execute(
                    "UPDATE agent_memory SET explicit_boost = 2, "
                    "times_accessed = 0, last_accessed_at = NULL "
                    "WHERE id = ?",
                    (mid,),
                )
            else:
                conn.execute(
                    "UPDATE agent_memory SET explicit_boost = 2 WHERE id = ?",
                    (mid,),
                )
        conn.commit()
        print(f"\n✅ 已更新 {len(updates_gt100) + len(updates_10_100)} 条记录。")

    # ── 4. 修复后验证 ──
    print()
    print("─" * 50)
    print("修复后验证统计:")
    after_gt100 = conn.execute(
        "SELECT COUNT(*) FROM agent_memory WHERE explicit_boost > 100"
    ).fetchone()[0]
    after_gt10 = conn.execute(
        "SELECT COUNT(*) FROM agent_memory WHERE explicit_boost > 10"
    ).fetchone()[0]
    new_dist = conn.execute(
        "SELECT explicit_boost, COUNT(*) as cnt "
        "FROM agent_memory GROUP BY explicit_boost "
        "ORDER BY explicit_boost DESC LIMIT 10"
    ).fetchall()

    print(f"  explicit_boost > 100: {after_gt100} 条 (应为 0)")
    print(f"  explicit_boost > 10:  {after_gt10} 条 (应为 0)")
    print(f"  前 10 个 explicit_boost 分布:")
    for r in new_dist:
        d = dict(r)
        print(f"    boost={d['explicit_boost']:>6}  count={d['cnt']}")

    conn.close()

    if dry_run:
        print("\n💡 提示：以上是预览。确认无误后运行:")
        print("   python scripts/fix_memory_weights.py --apply")
        print("   python scripts/fix_memory_weights.py --apply --reset-access  # 同时重置访问计数")


if __name__ == "__main__":
    main()
