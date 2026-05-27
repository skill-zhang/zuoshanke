"""Phase 2 测试 — Browser Dial Test + Delegate 子 Agent

测试覆盖：
  1. browser_dial_test 单元测试（mock Playwright）
  2. delegate_engine 单元测试（_run_loop_blocking + 并行执行）
  3. delegate_tool 调用测试
"""

import json
import os
import sys
import pytest
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))


# ═══════════════════════════════════════════
# Browser Dial Test 测试
# ═══════════════════════════════════════════

@pytest.mark.server
class TestBrowserDialTestMocked(unittest.TestCase):
    """Browser Dial Test — mock Playwright 测试"""

    def _ensure_mock_browser(self, mock_evaluate_list=None):
        """Patch _ensure_browser to return a mock browser with controlled evaluate returns"""
        mock_page = MagicMock()
        mock_page.goto = MagicMock()
        if mock_evaluate_list:
            mock_page.evaluate = MagicMock(side_effect=mock_evaluate_list)
        else:
            mock_page.evaluate = MagicMock(return_value=[])
        mock_page.screenshot = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        import browser_dial_test as bdt
        bdt._ensure_browser = MagicMock(return_value=mock_browser)
        return mock_page

    def test_dial_test_basic(self):
        """dial_test 应返回包含 URL/dom/console 的结构化报告"""
        self._ensure_mock_browser([
            [{"selector": "body", "tag": "body", "rect": {"x": 0, "y": 0, "w": 1440, "h": 900},
              "visible": True, "children": [], "computed_style": {"display": "block"}}],
            [],
            [],
            {"fcp_ms": 500},
        ])

        from browser_dial_test import dial_test
        result_str = dial_test("http://localhost:5173/test")
        result = json.loads(result_str)

        self.assertEqual(result["url"], "http://localhost:5173/test")
        self.assertIn("dom", result)
        self.assertIn("console", result)
        self.assertIn("network", result)
        self.assertIn("summary", result)
        self.assertIsNotNone(result["duration_ms"])

    def test_dial_test_error_handling(self):
        """页面加载失败应返回错误报告"""
        mock_page = MagicMock()
        mock_page.goto = MagicMock(side_effect=Exception("Connection refused"))
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        import browser_dial_test as bdt
        bdt._ensure_browser = MagicMock(return_value=mock_browser)

        from browser_dial_test import dial_test
        result_str = dial_test("http://localhost:9999/nonexistent")
        result = json.loads(result_str)

        self.assertIn("error", result)
        self.assertIn("Connection refused", result["error"])

    def test_dial_style_basic(self):
        """dial_style 应返回指定选择器的计算样式"""
        mock_page = MagicMock()
        mock_page.goto = MagicMock()
        mock_page.evaluate = MagicMock(return_value={
            "selector": ".card-grid",
            "visible": True,
            "rect": {"x": 240, "y": 56, "w": 1200, "h": 844},
            "style": {"display": "grid", "overflow": "hidden auto"},
            "text": "卡片内容",
        })
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        import browser_dial_test as bdt
        bdt._ensure_browser = MagicMock(return_value=mock_browser)

        from browser_dial_test import dial_style
        result_str = dial_style("http://localhost:5173/test", [".card-grid", ".sidebar"])
        result = json.loads(result_str)

        self.assertIn("elements", result)
        self.assertIn("duration_ms", result)
        self.assertEqual(result["url"], "http://localhost:5173/test")

    def test_dial_assert_style(self):
        """dial_assert style 类型应检查 CSS 属性"""
        mock_page = MagicMock()
        mock_page.goto = MagicMock()
        mock_page.on = MagicMock()
        mock_page.wait_for_timeout = MagicMock()
        mock_page.evaluate = MagicMock(return_value="hidden auto")
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        import browser_dial_test as bdt
        bdt._ensure_browser = MagicMock(return_value=mock_browser)

        from browser_dial_test import dial_assert
        result_str = dial_assert("http://localhost:5173/test", [
            {"name": "溢出 auto", "type": "style", "selector": ".card-grid",
             "style_rules": [{"property": "overflow", "operator": "contains", "value": "auto"}]},
        ])
        results = json.loads(result_str)
        self.assertTrue(len(results) >= 1)

    def test_dial_assert_count(self):
        """dial_assert count 类型应检查元素数量"""
        mock_page = MagicMock()
        mock_page.goto = MagicMock()
        mock_page.on = MagicMock()
        mock_page.wait_for_timeout = MagicMock()

        def mock_eval(script):
            if "querySelectorAll" in str(script):
                return 6
            return ""

        mock_page.evaluate = MagicMock(side_effect=mock_eval)
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        import browser_dial_test as bdt
        bdt._ensure_browser = MagicMock(return_value=mock_browser)

        from browser_dial_test import dial_assert
        result_str = dial_assert("http://localhost:5173/test", [
            {"name": "至少 3 张卡片", "type": "count",
             "count_selector": ".card", "count_rule": {"operator": "gte", "value": 3}},
        ])
        results = json.loads(result_str)
        self.assertTrue(len(results) >= 1)


# ═══════════════════════════════════════════
# Delegate Engine 测试
# ═══════════════════════════════════════════

class TestDelegateEngine(unittest.TestCase):
    """Delegate Engine 单元测试"""

    def test_run_loop_blocking_basic(self):
        """_run_loop_blocking 应运行 LLM 循环并返回结果"""
        from agent_core.delegate_engine import _run_loop_blocking

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "获取当前时间",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        with patch("agent_core.agent_loop.call_llm_with_tools") as mock_llm:
            mock_llm.return_value = {
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "子任务完成了"},
                    "finish_reason": "stop",
                }],
            }
            result = _run_loop_blocking("测试任务", tools, max_steps=5)

        self.assertTrue(result["success"])
        self.assertIn("子任务", result["summary"])

    def test_run_loop_blocking_clarify_blocked(self):
        """子 Agent 调 clarify 应被拦截"""
        from agent_core.delegate_engine import _run_loop_blocking

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "clarify",
                    "description": "问用户",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        call_count = [0]

        def mock_llm(*a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "clarify", "arguments": "{}"},
                            }],
                        },
                        "finish_reason": "tool_calls",
                    }],
                }
            return {
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "我自行决定"},
                    "finish_reason": "stop",
                }],
            }

        with patch("agent_core.agent_loop.call_llm_with_tools", side_effect=mock_llm):
            result = _run_loop_blocking("测试", tools, max_steps=5)

        self.assertTrue(result["success"])

    def test_run_delegate_single(self):
        """run_delegate_single 应返回结构化结果"""
        from agent_core.delegate_engine import run_delegate_single

        with patch("agent_core.delegate_engine._run_loop_blocking") as mock_run:
            mock_run.return_value = {
                "success": True,
                "summary": "后端模块完成",
                "steps": 3,
            }
            result_str = run_delegate_single({"goal": "实现后端API", "context": "参照 INTERFACE.md"})
            results = json.loads(result_str)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
        self.assertEqual(results[0]["summary"], "后端模块完成")

    def test_run_delegate_parallel(self):
        """run_delegate_tasks 并行多任务应返回所有结果"""
        from agent_core.delegate_engine import run_delegate_tasks

        results_map = {
            "实现后端API": {"success": True, "summary": "后端完成", "steps": 3},
            "实现前端组件": {"success": True, "summary": "前端完成", "steps": 4},
        }

        def mock_run(task, **kw):
            for key, val in results_map.items():
                if key in task:
                    return val
            return {"success": False, "summary": "未知任务", "steps": 0, "error": "?"}

        with patch("agent_core.delegate_engine._run_loop_blocking", side_effect=mock_run):
            result_str = run_delegate_tasks([
                {"goal": "实现后端API", "context": "文件路径: backend/routes"},
                {"goal": "实现前端组件", "context": "文件路径: frontend/pages"},
            ])
            results = json.loads(result_str)

        self.assertEqual(len(results), 2)
        statuses = [r["status"] for r in results]
        self.assertEqual(statuses, ["success", "success"])


class TestDelegateTool(unittest.TestCase):
    """delegate_tool 工具函数测试"""

    def test_delegate_tool_single(self):
        """单任务模式应正常委派"""
        from delegate_tool import delegate_task

        with patch("agent_core.delegate_engine.run_delegate_single") as mock_single:
            mock_single.return_value = json.dumps([{
                "task": "查资料",
                "status": "success",
                "summary": "查完了",
                "steps": 2,
            }])
            result_str = delegate_task(goal="查资料", context="搜一下天气")
            results = json.loads(result_str)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["task"], "查资料")

    def test_delegate_tool_batch(self):
        """批量模式应并行执行"""
        from delegate_tool import delegate_task

        with patch("agent_core.delegate_engine.run_delegate_tasks") as mock_batch:
            mock_batch.return_value = json.dumps([
                {"task": "A", "status": "success", "summary": "A完成"},
                {"task": "B", "status": "success", "summary": "B完成"},
            ])
            result_str = delegate_task(tasks=[
                {"goal": "A", "context": ""},
                {"goal": "B", "context": ""},
            ])
            results = json.loads(result_str)

        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
