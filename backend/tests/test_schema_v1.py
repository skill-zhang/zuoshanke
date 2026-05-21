"""
Schema v1.0 — Context 组合架构单元测试
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# 添加 backend 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestDiffExtractor(unittest.TestCase):
    """diff_extractor.py 单元测试"""

    def setUp(self):
        from agent_core.diff_extractor import extract_diff, format_diff_block
        self.extract_diff = extract_diff
        self.format_diff = format_diff_block

    def test_no_previous_snapshot(self):
        """首次写入：无上次快照"""
        result = self.extract_diff("/tmp/test.py", "line1\nline2\nline3", None)
        self.assertEqual(result["file_path"], "/tmp/test.py")
        self.assertEqual(result["summary"], "首次创建，共 3 行")
        self.assertEqual(len(result["added_lines"]), 3)
        self.assertEqual(result["removed_lines"], [])

    def test_identical_content(self):
        """内容不变：无差异"""
        old = "line1\nline2\nline3\n"
        new = "line1\nline2\nline3\n"
        result = self.extract_diff("/tmp/test.py", new, old)
        self.assertEqual(result["summary"], "无变化")
        self.assertEqual(result["added_lines"], [])
        self.assertEqual(result["removed_lines"], [])

    def test_added_lines(self):
        """新增行：检测到 added_lines"""
        old = "line1\nline2\n"
        new = "line1\nline2\nline3\nline4\n"
        result = self.extract_diff("/tmp/test.py", new, old)
        self.assertIn("新增 2 行", result["summary"])
        self.assertEqual(len(result["hunks"]), 1)
        self.assertIn("+line3", result["hunks"][0]["content"])
        self.assertIn("+line4", result["hunks"][0]["content"])

    def test_removed_lines(self):
        """删除行：检测到 removed_lines"""
        old = "line1\nline2\nline3\n"
        new = "line1\nline3\n"
        result = self.extract_diff("/tmp/test.py", new, old)
        self.assertIn("删除 1 行", result["summary"])

    def test_modified_lines(self):
        """修改行：同时新增和删除"""
        old = "keep\nremove\nkeep\n"
        new = "keep\nchanged\nkeep\n"
        result = self.extract_diff("/tmp/test.py", new, old)
        self.assertIn("新增 1 行", result["summary"])
        self.assertIn("删除 1 行", result["summary"])

    def test_format_diff_block(self):
        """格式化 diff 为引导文本"""
        result = {
            "file_path": "/tmp/test.py",
            "added_lines": [2, 3],
            "removed_lines": [1],
            "hunks": [{
                "old_start": 1, "old_count": 3,
                "new_start": 1, "new_count": 4,
                "content": "@@ -1,3 +1,4 @@\n line1\n+line2\n+line3\n-line0\n",
            }],
            "summary": "新增 2 行，删除 1 行",
        }
        block = self.format_diff(result)
        self.assertIn("== 文件: /tmp/test.py ==", block)
        self.assertIn("新增代码", block)
        self.assertIn("删除代码", block)
        self.assertIn("改动详情", block)
        self.assertIn("@@ -1,3 +1,4 @@", block)


class TestPriorityAssigner(unittest.TestCase):
    """priority_assigner.py 单元测试"""

    def setUp(self):
        from agent_core.priority_assigner import extract_priority, PRIORITY_GUIDE
        self.extract = extract_priority
        self.guide = PRIORITY_GUIDE

    def test_no_marker_default(self):
        """无标记：默认 normal"""
        text, pri = self.extract("你好，这是回复")
        self.assertEqual(pri, "normal")
        self.assertEqual(text, "你好，这是回复")

    def test_high_priority(self):
        """[P:high] 标记"""
        text, pri = self.extract("[P:high] 这是重要决策")
        self.assertEqual(pri, "high")
        self.assertEqual(text, "这是重要决策")

    def test_low_priority(self):
        """[P:low] 标记"""
        text, pri = self.extract("[P:low] 发散内容")
        self.assertEqual(pri, "low")
        self.assertEqual(text, "发散内容")

    def test_normal_priority_marker(self):
        """[P:normal] 显式标记"""
        text, pri = self.extract("[P:normal] 普通回复")
        self.assertEqual(pri, "normal")
        self.assertEqual(text, "普通回复")

    def test_leading_whitespace(self):
        """前导空白不影响解析"""
        text, pri = self.extract("  [P:high] 有前导空白")
        self.assertEqual(pri, "high")
        self.assertEqual(text, "有前导空白")

    def test_marker_then_multiline(self):
        """标记后多行内容"""
        text, pri = self.extract("[P:high] 第一行\n第二行\n第三行")
        self.assertEqual(pri, "high")
        self.assertIn("第一行", text)
        self.assertIn("第二行", text)

    def test_empty_string(self):
        """空字符串"""
        text, pri = self.extract("")
        self.assertEqual(pri, "normal")
        self.assertEqual(text, "")

    def test_guide_content(self):
        """PRIORITY_GUIDE 包含关键说明"""
        self.assertIn("[P:high]", self.guide)
        self.assertIn("[P:normal]", self.guide)
        self.assertIn("[P:low]", self.guide)


class TestSnapshotManager(unittest.TestCase):
    """snapshot_manager.py 单元测试（文件系统 fallback 模式）"""

    def setUp(self):
        from agent_core.snapshot_manager import record, get_previous
        self.record = record
        self.get_previous = get_previous

    def test_record_and_get(self):
        """记录和读取快照"""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b"hello world")
            fname = f.name

        try:
            # 记录快照
            snap_id = self.record(fname, "hello world", db=None)
            self.assertIsNotNone(snap_id)

            # 获取上次快照
            prev = self.get_previous(fname, db=None)
            self.assertEqual(prev, "hello world")
        finally:
            os.unlink(fname)

    def test_no_previous(self):
        """首次查询：返回 None"""
        prev = self.get_previous("/nonexistent/file.txt", db=None)
        self.assertIsNone(prev)


class TestContextComposer(unittest.TestCase):
    """context_composer.py 单元测试（使用 mock DB）"""

    def setUp(self):
        from agent_core.context_composer import compose_context
        self.compose = compose_context

    def _make_mock_db(self):
        """创建 mock DB"""
        db = MagicMock()
        db.query.return_value.first.return_value = None
        return db

    def test_basic_composition(self):
        """基础组合：7 层结构正确"""
        db = self._make_mock_db()
        messages = self.compose(
            user_content="你好",
            scene_id="scene_001",
            scene_name="测试场景",
            db=db,
            history_messages=[
                {"role": "user", "content": "之前的问题", "priority": "normal"},
                {"role": "ai", "content": "之前的回复", "priority": "high"},
            ],
        )
        # 应该有 system + 多层 user + history + 最终 user 消息
        self.assertGreater(len(messages), 3)
        # 第一条应该是 system role
        self.assertEqual(messages[0]["role"], "system")
        # 最后一条应该是用户消息
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "你好")

    def test_empty_history(self):
        """无历史消息"""
        db = self._make_mock_db()
        messages = self.compose(
            user_content="测试",
            db=db,
        )
        self.assertGreater(len(messages), 1)
        self.assertEqual(messages[-1]["content"], "测试")

    def test_no_db(self):
        """无 DB 连接"""
        messages = self.compose(
            user_content="离线测试",
            db=None,
        )
        self.assertGreater(len(messages), 1)

    def test_history_priority_sorting(self):
        """历史消息按优先级组织"""
        history = [
            {"role": "user", "content": "低优先级", "priority": "low"},
            {"role": "user", "content": "高优先级", "priority": "high"},
            {"role": "user", "content": "普通", "priority": "normal"},
        ]
        from agent_core.context_composer import _build_history_layer
        result = _build_history_layer(history)

        # high 应该在 normal 前面
        high_idx = None
        normal_idx = None
        for i, m in enumerate(result):
            if m.get("content") == "高优先级":
                high_idx = i
            if m.get("content") == "普通":
                normal_idx = i
        if high_idx is not None and normal_idx is not None:
            self.assertLess(high_idx, normal_idx, "high 应在 normal 之前")

    def test_document_layer_with_deps(self):
        """Document Layer — 传入 deps 时返回摘要"""
        from agent_core.context_composer import _build_document_layer
        db = self._make_mock_db()
        deps = [{"doc": "test-doc", "level": "brief"}]
        # mock 掉 document_summarizer.get_document 返回空时，应返回 doc name
        result = _build_document_layer("scene_001", db, deps)
        # 有 deps 时，即使摘要为空也应返回文档列表
        self.assertIn("参考文档", result)
        self.assertIn("test-doc", result)

    def test_document_layer_no_deps(self):
        """Document Layer — 无 deps 时返回空"""
        from agent_core.context_composer import _build_document_layer
        result = _build_document_layer("scene_001", self._make_mock_db(), None)
        self.assertEqual(result, "")


class TestConfigInjector(unittest.TestCase):
    """config_injector.py 单元测试"""

    def setUp(self):
        from agent_core.config_injector import get_cascade, format_config_block
        self.get_cascade = get_cascade
        self.format_config = format_config_block

    def test_empty_db(self):
        """无 DB 时的行为"""
        config = self.get_cascade(db=None)
        self.assertEqual(config, {})

    def test_format_empty(self):
        """空配置格式化"""
        block = self.format_config({})
        self.assertEqual(block, "")

    def test_format_with_data(self):
        """有数据格式化"""
        config = {"model": "deepseek-v4-flash", "temperature": 0.3}
        block = self.format_config(config, "测试场景")
        self.assertIn("deepseek-v4-flash", block)
        self.assertIn("0.3", block)
        self.assertIn("当前运行配置", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
