#!/usr/bin/env python3
"""Fix user_work_style memory and add rule→LLM journey."""
import sys
sys.path.insert(0, "backend")

from database import SessionLocal
from agent_core.memory_manager import MemoryManager

db = SessionLocal()
mm = MemoryManager(db)

m = mm.get("user_work_style")
if m:
    mm.update("user_work_style", content='用户设计哲学: 核心主张LLM自主决策，而非量化规则。完整经历了"造规则→规则太脆弱→清理规则→回归LLM自主决策"的迭代。部分LLM决策效果不好是因context构建不充分/引导不够精准，非LLM自主决策本身问题。量化规则只用于真正简单的事（如收敛阈值检测），是务实选择非哲学偏好。')
    print("✅ user_work_style corrected")

m2 = mm.get("rule_to_llm_journey")
if not m2:
    mm.add(category="agent", key="rule_to_llm_journey",
            content='坐山客规则→LLM自主决策迭代史: 从v0.1开始就让LLM自主决策→逐步添加规则层（预执行、关键词匹配、收敛规则等）→发现规则太脆弱、无法覆盖边界情况→逐步清理规则、移交给LLM function calling→目前收敛走系统自动检测阈值（纯数学），其余全走LLM自主。这个迭代过程是重要的设计知识，代表了"用规则兜底→用LLM做主"的演进路线。',
            tags=["architecture", "history", "design-evolution"],
            base_weight=7, source="llm", scope="zhu")
    print("✅ rule_to_llm_journey created")
else:
    print("⏭️ rule_to_llm_journey already exists")

m = mm.get("user_work_style")
print(f"\nuser_work_style: {m.content[:80] if m else 'MISSING'}...")
db.close()
print("done")
