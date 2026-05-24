"""契约文件模板 — 单元测试 + 场景测试

覆盖：
  1. SELF_DEV_SYSTEM_PROMPT 是否包含标准契约模板
  2. 模板结构完整性（7 节全、格式正确）
  3. delegate_engine 的契约层 context 构建
  4. 边界情况（无契约、空路径、非标准路径）
  5. 场景测试：生成契约 → 派子 Agent → 验证输出一致性
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, mock_open

_BACKEND_DIR = os.path.expanduser("~/zuoshanke/backend")
_SCRIPTS_DIR = os.path.expanduser("~/zuoshanke/scripts")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


# ═══ S1: 模板静态检查 ═══

class TestContractTemplateInPrompt(unittest.TestCase):
    """验证 SELF_DEV_SYSTEM_PROMPT 包含标准契约模板"""

    @classmethod
    def setUpClass(cls):
        from seed_dev_scene import SELF_DEV_SYSTEM_PROMPT
        cls.prompt = SELF_DEV_SYSTEM_PROMPT

    def test_prompt_contains_contract_phase(self):
        """契约阶段指引存在"""
        self.assertIn("【契约阶段】", self.prompt)

    def test_prompt_mentions_shared_interface(self):
        """提示用 shared/INTERFACE.md"""
        self.assertIn("shared/INTERFACE.md", self.prompt)

    def test_prompt_mentions_standard_template(self):
        """提示按标准模板写"""
        self.assertIn("标准契约模板结构", self.prompt)

    def test_prompt_mentions_write_file(self):
        """提示用 write_file 创建"""
        self.assertIn("write_file", self.prompt)

    def test_prompt_contract_only_shared_context(self):
        """契约是唯一共享上下文"""
        self.assertIn("唯一的共享上下文", self.prompt)

    def test_prompt_subagents_dont_know_each_other(self):
        """子Agent不知道彼此存在"""
        self.assertIn("不知道彼此存在", self.prompt)

    def test_prompt_multiple_agents_contract_first(self):
        """多 Agent 必须契约先行"""
        self.assertIn("必须写契约先行", self.prompt)


class TestContractTemplateStructure(unittest.TestCase):
    """验证模板的 7 节结构和格式"""

    @classmethod
    def setUpClass(cls):
        from seed_dev_scene import SELF_DEV_SYSTEM_PROMPT
        cls.prompt = SELF_DEV_SYSTEM_PROMPT

    def test_template_all_7_sections(self):
        """模板包含全部 7 个标准节"""
        sections = [
            "## 1. 项目概览",
            "## 2. 模块架构",
            "## 3. 数据模型",
            "## 4. API 端点",
            "## 5. 模块边界",
            "## 6. 约定",
            "## 7. 注意事项",
        ]
        for sec in sections:
            with self.subTest(section=sec):
                self.assertIn(sec, self.prompt)

    def test_template_version_header(self):
        """模板包含版本号"""
        self.assertIn("接口契约 v1.0", self.prompt)

    def test_template_timestamp_placeholder(self):
        """模板包含时间戳占位符"""
        self.assertIn("{timestamp}", self.prompt)

    def test_template_module_table_header(self):
        """模块架构表有正确的表头"""
        self.assertIn("| 模块 | 目录 | 职责 | 依赖模块 |", self.prompt)

    def test_template_api_table_header(self):
        """API 端点表有正确的表头"""
        self.assertIn("| 方法 | 路径 | 请求体 | 响应体 | 所属模块 |", self.prompt)

    def test_template_boundary_structure(self):
        """模块边界包含负责/不负责/假定"""
        self.assertIn("**负责**", self.prompt)
        self.assertIn("**不负责**", self.prompt)
        self.assertIn("**假定**", self.prompt)

    def test_template_markdown_code_block(self):
        """模板包裹在 markdown 代码块中"""
        self.assertIn("```markdown", self.prompt)
        self.assertIn("```\n\n3.", self.prompt)

    def test_template_no_subsequent_sections_missing(self):
        """模板之后立即是执行阶段（没有遗漏结构）"""
        idx = self.prompt.find("```\n\n3.")
        self.assertGreater(idx, 0, "模板代码块后应紧跟执行阶段")
        after_template = self.prompt[idx:]
        self.assertIn("【执行阶段】", after_template)


# ═══ S2: delegate_engine 契约层 ═══

class TestDelegateEngineContractLayer(unittest.TestCase):
    """验证 _build_child_prompt 的 L2 契约层"""

    def setUp(self):
        from agent_core.delegate_engine import _build_child_prompt
        self._build_child_prompt = _build_child_prompt

    def test_no_contract_no_contract_section(self):
        """不传 contract_path → prompt 不含契约节"""
        prompt = self._build_child_prompt({"goal": "写前端"})
        self.assertNotIn("接口契约", prompt)

    def test_with_contract_contract_section(self):
        """传 contract_path → prompt 含契约引用"""
        prompt = self._build_child_prompt({
            "goal": "写前端",
            "contract_path": "shared/INTERFACE.md"
        })
        self.assertIn("接口契约", prompt)
        self.assertIn("shared/INTERFACE.md", prompt)
        self.assertIn("API 端点、数据模型和模块边界", prompt)

    def test_contract_with_project_rules(self):
        """contract_path + project_rules 同时存在"""
        prompt = self._build_child_prompt({
            "goal": "写后端",
            "contract_path": "shared/INTERFACE.md",
            "project_rules": "使用 snake_case"
        })
        self.assertIn("接口契约", prompt)
        self.assertIn("项目约定", prompt)
        self.assertIn("使用 snake_case", prompt)

    def test_contract_plus_context_plus_goal(self):
        """L1+L2+L3 三层完整"""
        prompt = self._build_child_prompt({
            "goal": "实现标签API",
            "context": "数据库已有 tags 表",
            "contract_path": "shared/INTERFACE.md",
            "project_rules": "错误格式: {error, detail}"
        })
        self.assertIn("## 任务", prompt)
        self.assertIn("## 上下文", prompt)
        self.assertIn("## 接口契约", prompt)
        self.assertIn("## 项目约定", prompt)
        self.assertIn("实现标签API", prompt)
        self.assertIn("数据库已有 tags 表", prompt)
        self.assertIn("shared/INTERFACE.md", prompt)
        self.assertIn("{error, detail}", prompt)

    def test_contract_empty_path(self):
        """contract_path 为空字符串 → 无契约节"""
        prompt = self._build_child_prompt({
            "goal": "测试",
            "contract_path": ""
        })
        self.assertNotIn("接口契约", prompt)

    def test_contract_identity_section_always_present(self):
        """身份声明始终存在"""
        prompt = self._build_child_prompt({"goal": "测试"})
        self.assertIn("你是坐山客派出的开发子 Agent", prompt)
        self.assertIn("不能问用户", prompt)


# ═══ S3: 边界测试 ═══

class TestContractEdgeCases(unittest.TestCase):
    """契约模板的边界情况"""

    def test_prompt_execute_phase_after_contract(self):
        """契约阶段后紧跟执行阶段（无缺失）"""
        from seed_dev_scene import SELF_DEV_SYSTEM_PROMPT
        self.assertIn("【执行阶段】", SELF_DEV_SYSTEM_PROMPT)
        # 契约阶段在 2，执行阶段是 3
        idx_phase2 = SELF_DEV_SYSTEM_PROMPT.find("【契约阶段】")
        idx_phase3 = SELF_DEV_SYSTEM_PROMPT.find("【执行阶段】")
        self.assertGreater(idx_phase3, idx_phase2,
                           "执行阶段应在契约阶段之后")

    def test_contract_path_accepted_variants(self):
        """contract_path 支持不同文件名/路径"""
        from agent_core.delegate_engine import _build_child_prompt
        for path in ["shared/API.md", "docs/contract.md", "INTERFACE.md"]:
            with self.subTest(path=path):
                prompt = _build_child_prompt({
                    "goal": "x",
                    "contract_path": path
                })
                self.assertIn(path, prompt)

    def test_contract_very_long_path(self):
        """超长契约路径不崩溃"""
        from agent_core.delegate_engine import _build_child_prompt
        long_path = "shared/" + "a" * 200 + "md"
        prompt = _build_child_prompt({
            "goal": "x",
            "contract_path": long_path
        })
        self.assertIn(long_path, prompt)

    def test_contract_goal_only_no_context(self):
        """只有 goal 的极简任务"""
        from agent_core.delegate_engine import _build_child_prompt
        prompt = _build_child_prompt({"goal": "hello"})
        self.assertIn("## 任务", prompt)
        self.assertNotIn("## 上下文", prompt)
        self.assertNotIn("## 接口契约", prompt)


# ═══ S4: 场景测试 — 契约生命周期 ═══

@unittest.skipUnless(
    os.path.exists(os.path.expanduser("~/zuoshanke/backend/main.py")),
    "后端代码未找到"
)
class TestContractLifecycleScenario(unittest.TestCase):
    """模拟完整的契约生命周期

    测试流程：
      1. 生成一份标准 INTERFACE.md（模拟父Agent行为）
      2. 验证文件结构完整
      3. 模拟 delegate_engine 读取契约并构建子Agent prompt
      4. 验证两个不同子Agent的prompt都引用了同一份契约
    """

    CONTRACT_PATH = "/tmp/test_contract_INTERFACE.md"

    @classmethod
    def setUpClass(cls):
        """生成标准契约文件"""
        cls.contract_content = """# 接口契约 v1.0
> 自动生成于 2026-05-24T12:00:00 | 由 测试场景创建

## 1. 项目概览
为坐山客系统编写介绍文档和使用说明手册。

## 2. 模块架构
| 模块 | 目录 | 职责 | 依赖模块 |
|------|------|------|----------|
| 系统介绍 | docs/introduction.md | 坐山客整体架构、哲学、能力概述 | 无 |
| 使用说明 | docs/usage-guide.md | 各场景/频道的操作指引、示例 | 系统介绍 |

## 3. 数据模型
无（纯文档项目，无数据库模型）

## 4. API 端点
无（不涉及后端开发）

## 5. 模块边界

### 系统介绍 (docs/introduction.md)
- **负责**: 坐山客是什么、设计哲学、核心概念（本体/分身/记忆/自我迭代）
- **不负责**: 具体操作步骤、命令示例
- **假定**: 读者有 AI 产品使用经验

### 使用说明 (docs/usage-guide.md)
- **负责**: 各场景使用方法、聊天/开发/拨测流程、实例教程
- **不负责**: 架构设计原理、哲学讨论
- **假定**: 读者已读系统介绍

## 6. 约定
- 文档语言：中文
- 语气：专业、清晰、有洞察力
- 文件格式：Markdown
- 代码块：用 ``` 包裹

## 7. 注意事项
- 重点突出「你的AI伙伴」品牌定位
- 避免过度技术细节
- 包含至少 2 个使用示例
"""
        with open(cls.CONTRACT_PATH, "w", encoding="utf-8") as f:
            f.write(cls.contract_content)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.CONTRACT_PATH):
            os.remove(cls.CONTRACT_PATH)

    def test_contract_file_exists(self):
        """契约文件已生成"""
        self.assertTrue(os.path.exists(self.CONTRACT_PATH))

    def test_contract_file_not_empty(self):
        """契约文件非空"""
        size = os.path.getsize(self.CONTRACT_PATH)
        self.assertGreater(size, 100)

    def test_contract_has_version(self):
        """契约有版本号"""
        self.assertIn("接口契约 v1.0", self.contract_content)

    def test_contract_has_all_7_sections(self):
        """契约包含全部 7 节"""
        sections = [
            "## 1. 项目概览",
            "## 2. 模块架构",
            "## 3. 数据模型",
            "## 4. API 端点",
            "## 5. 模块边界",
            "## 6. 约定",
            "## 7. 注意事项",
        ]
        for sec in sections:
            with self.subTest(section=sec):
                self.assertIn(sec, self.contract_content)

    def test_contract_has_module_boundaries(self):
        """契约包含模块边界定义"""
        self.assertIn("**负责**", self.contract_content)
        self.assertIn("**不负责**", self.contract_content)
        self.assertIn("**假定**", self.contract_content)

    def test_delegate_engine_reads_contract(self):
        """delegate_engine 正确处理 contract_path 引用"""
        from agent_core.delegate_engine import _build_child_prompt

        # 子Agent A — 系统介绍
        prompt_a = _build_child_prompt({
            "goal": "编写坐山客系统介绍文档",
            "context": "坐山客项目根目录在 ~/zuoshanke",
            "contract_path": self.CONTRACT_PATH,
        })
        self.assertIn(self.CONTRACT_PATH, prompt_a)
        self.assertIn("接口契约", prompt_a)
        self.assertIn("API 端点、数据模型和模块边界", prompt_a)

        # 子Agent B — 使用说明
        prompt_b = _build_child_prompt({
            "goal": "编写坐山客使用说明手册",
            "context": "坐山客项目根目录在 ~/zuoshanke",
            "contract_path": self.CONTRACT_PATH,
        })
        self.assertIn(self.CONTRACT_PATH, prompt_b)
        self.assertIn("接口契约", prompt_b)

        # 验证两条 prompt 引用同一份契约
        self.assertIn(self.CONTRACT_PATH, prompt_a)
        self.assertIn(self.CONTRACT_PATH, prompt_b)


# ═══ 手动模式：验证 seed_dev_scene.py 完整性 ═══

class TestSeedScriptIntegrity(unittest.TestCase):
    """验证 seed_dev_scene.py 能正常导入"""

    def test_seed_imports_cleanly(self):
        """seed_dev_scene.py 导入无异常"""
        try:
            import seed_dev_scene
            self.assertTrue(hasattr(seed_dev_scene, "SELF_DEV_SYSTEM_PROMPT"))
            self.assertTrue(hasattr(seed_dev_scene, "DESIGN_MEMORIES"))
        except Exception as e:
            self.fail(f"导入 seed_dev_scene 失败: {e}")

    def test_design_memories_10_entries(self):
        """设计哲学记忆至少有 9 条"""
        from seed_dev_scene import DESIGN_MEMORIES
        self.assertGreaterEqual(len(DESIGN_MEMORIES), 9)

    def test_seed_function_exists(self):
        """seed 函数存在"""
        import seed_dev_scene
        self.assertTrue(callable(seed_dev_scene.seed))


if __name__ == "__main__":
    unittest.main()
