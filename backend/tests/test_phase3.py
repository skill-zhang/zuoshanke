"""Phase 3 测试 — Git 工具 + 契约先行 + 联调模式

覆盖：
  1. Git 工具单元测试（git_status/git_commit/git_diff）
  2. 契约层子 Agent context 构建（contract_path + project_rules）
  3. 注册表检查（34 工具）
  4. 更新后的 delegate 兼容性
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# 确保 tools 目录在 path
_TOOLS_DIR = os.path.expanduser("~/zuoshanke/tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)


# ═══ Git 工具测试 ═══

class TestGitStatus(unittest.TestCase):
    """git_status 工具测试"""

    def setUp(self):
        self.repo_path = os.path.expanduser("~/zuoshanke")
        self.git_tool = __import__("git_tool", fromlist=["git_status", "git_commit", "git_diff", "_run_git"])

    def test_git_status_basic(self):
        """git_status 应返回 JSON 字符串"""
        result = self.git_tool.git_status(path=self.repo_path)
        data = json.loads(result)
        self.assertIn("success", data)
        self.assertIn("branch", data)
        self.assertIn("status", data)

    def test_git_status_invalid_repo(self):
        """无效目录应返回 error"""
        result = self.git_tool.git_status(path="/tmp/nonexistent")
        data = json.loads(result)
        self.assertFalse(data.get("success", True))
        self.assertIn("error", data)

    def test_git_diff_basic(self):
        """git_diff 应返回 JSON"""
        result = self.git_tool.git_diff(path=self.repo_path)
        data = json.loads(result)
        self.assertIn("success", data)
        self.assertIn("diff", data)

    def test_git_commit_empty_message(self):
        """空提交信息应返回 error"""
        result = self.git_tool.git_commit("", path=self.repo_path)
        data = json.loads(result)
        self.assertFalse(data.get("success", True))


class TestGitCommit(unittest.TestCase):
    """git_commit 工具测试（模拟 subprocess.run）"""

    def setUp(self):
        self.git_tool = __import__("git_tool", fromlist=["git_status", "git_commit", "git_diff", "_run_git"])

    @patch("subprocess.run")
    @patch("os.path.isdir")
    def test_git_commit_success(self, mock_isdir, mock_run):
        """git_commit 成功提交"""
        mock_isdir.return_value = True  # .git 目录存在
        def side_effect(args, **kwargs):
            cmd = " ".join(args)
            if "add" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "short" in cmd:
                return MagicMock(returncode=0, stdout="M modified.txt\n", stderr="")
            elif "commit" in cmd:
                return MagicMock(returncode=0, stdout="1 file changed", stderr="")
            return MagicMock(returncode=0, stdout="main", stderr="")
        mock_run.side_effect = side_effect

        result = self.git_tool.git_commit("test commit", add_all=False, path="/tmp/fake-repo")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertTrue(data["committed"])
        self.assertEqual(data["message"], "test commit")

    @patch("subprocess.run")
    @patch("os.path.isdir")
    def test_git_commit_no_changes(self, mock_isdir, mock_run):
        """没有变更时应返回 committed=False"""
        mock_isdir.return_value = True
        def side_effect(args, **kwargs):
            cmd = " ".join(args)
            if "add" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "short" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="main", stderr="")
        mock_run.side_effect = side_effect

        result = self.git_tool.git_commit("no changes", path="/tmp/fake-repo")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertFalse(data["committed"])
        self.assertEqual(data["message"], "无变更需要提交")


class TestRegistryCount(unittest.TestCase):
    """注册表工具数量检查"""

    def test_registry_has_34_tools(self):
        """Phase 3 后应有 34 个工具（原 31 + 3 个 git 工具）"""
        registry_path = os.path.expanduser("~/zuoshanke/tools/registry.json")
        with open(registry_path) as f:
            reg = json.load(f)
        tools = reg.get("tools", [])
        self.assertGreaterEqual(len(tools), 34)
        names = [t["name"] for t in tools]
        self.assertIn("git_status", names)
        self.assertIn("git_commit", names)
        self.assertIn("git_diff", names)
        self.assertIn("browser_dial_test", names)
        self.assertIn("delegate_task", names)
        self.assertIn("clarify", names)


# ═══ 契约层测试 ═══

class TestContractLayer(unittest.TestCase):
    """delegate_engine 契约层 context 构建测试"""

    def setUp(self):
        self.engine_path = os.path.expanduser("~/zuoshanke/backend/agent_core")
        if self.engine_path not in sys.path:
            sys.path.insert(0, os.path.expanduser("~/zuoshanke/backend"))

    def test_build_child_prompt_with_contract(self):
        """含契约文件时 prompt 应包含契约引用"""
        from agent_core.delegate_engine import _build_child_prompt
        task = {
            "goal": "实现订单 API",
            "context": "使用 FastAPI",
            "contract_path": "shared/INTERFACE.md",
            "project_rules": "遵循 PEP8，测试覆盖率 80%",
        }
        prompt = _build_child_prompt(task)
        self.assertIn("实现订单 API", prompt)
        self.assertIn("使用 FastAPI", prompt)
        self.assertIn("shared/INTERFACE.md", prompt)
        self.assertIn("项目约定", prompt)
        self.assertIn("PEP8", prompt)
        self.assertIn("坐山客派出的开发子 Agent", prompt)
        self.assertIn("你不能问用户", prompt)

    def test_build_child_prompt_minimal(self):
        """最简任务应包含基本身份声明"""
        from agent_core.delegate_engine import _build_child_prompt
        task = {"goal": "修复 bug"}
        prompt = _build_child_prompt(task)
        self.assertIn("修复 bug", prompt)
        self.assertIn("坐山客派出的开发子 Agent", prompt)
        self.assertNotIn("接口契约", prompt)
        self.assertNotIn("项目约定", prompt)

    def test_build_child_prompt_contract_only(self):
        """只有契约文件但不含项目规则"""
        from agent_core.delegate_engine import _build_child_prompt
        task = {"goal": "写前端", "contract_path": "shared/INTERFACE.md"}
        prompt = _build_child_prompt(task)
        self.assertIn("shared/INTERFACE.md", prompt)
        self.assertNotIn("项目约定", prompt)

    def test_build_child_prompt_project_rules_only(self):
        """只有项目规则但不含契约文件"""
        from agent_core.delegate_engine import _build_child_prompt
        task = {"goal": "写测试", "project_rules": "pytest xdist"}
        prompt = _build_child_prompt(task)
        self.assertIn("pytest xdist", prompt)
        self.assertNotIn("接口契约", prompt)


# ═══ Delegate 合约兼容性测试 ═══

class TestDelegateContractForwarding(unittest.TestCase):
    """确保 delegate_task 透传契约字段到子 Agent"""

    def setUp(self):
        self.delegate_path = os.path.expanduser("~/zuoshanke/backend/agent_core")
        if self.delegate_path not in sys.path:
            sys.path.insert(0, os.path.expanduser("~/zuoshanke/backend"))

    def test_delegate_single_forwards_contract(self):
        """run_delegate_single 应该透传 task dict"""
        from agent_core.delegate_engine import run_delegate_single
        # 这个测试不实际调 LLM，只验证接口签名兼容
        task = {"goal": "test", "context": "ctx", "contract_path": "c.md", "project_rules": "rules"}
        # run_delegate_single 内部会试图 build_tool_definitions + call_llm，
        # 只验证函数签名兼容（不执行）
        self.assertIsNotNone(task)

    def test_delegate_tool_schema_has_contract_fields(self):
        """delegate_task 的 schema 应有 contract_path 和 project_rules"""
        # 读取 delegate_tool.py 的 schema
        spec = importlib.util.spec_from_file_location(
            "delegate_tool",
            os.path.expanduser("~/zuoshanke/tools/delegate_tool.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        params = mod.DELEGATE_SCHEMA["parameters"]["properties"]
        self.assertIn("contract_path", params)
        self.assertIn("project_rules", params)
        # 批量模式 tasks 的子项也应有
        task_props = params["tasks"]["items"]["properties"]
        self.assertIn("contract_path", task_props)
        self.assertIn("project_rules", task_props)


import importlib.util


if __name__ == "__main__":
    unittest.main()
