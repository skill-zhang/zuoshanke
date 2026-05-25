"""批量运行测试工具 — 运行 backend/tests/ 下的测试

工具名: run_tests
功能: 运行 backend/tests/ 下的测试
参数:
  - pattern (string, optional) — 文件名过滤
  - filter (string, optional) — 方法名过滤
返回: {total, passed, failed, errors, details}
"""

import os
import sys
import json
import unittest
import fnmatch


def _discover_tests(pattern: str | None = None) -> unittest.TestSuite:
    """发现测试用例

    Args:
        pattern: 文件名过滤（如 "test_*.py"）

    Returns:
        TestSuite
    """
    # 确定 tests 目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(os.path.dirname(script_dir), "backend")
    tests_dir = os.path.join(backend_dir, "tests")

    if not os.path.isdir(tests_dir):
        # 尝试从当前工作目录找
        tests_dir = os.path.join(os.getcwd(), "backend", "tests")
        if not os.path.isdir(tests_dir):
            raise FileNotFoundError(f"测试目录不存在: backend/tests/")

    # 确保 backend 在 sys.path 中
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    if os.path.dirname(backend_dir) not in sys.path:
        sys.path.insert(0, os.path.dirname(backend_dir))

    pattern = pattern or "test_*.py"
    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir, pattern=pattern)
    return suite


class _TestResultCollector(unittest.TestResult):
    """自定义 TestResult，收集详细信息"""

    def __init__(self):
        super().__init__()
        self.collected = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.collected.append({
            "test": str(test),
            "status": "passed",
        })

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.collected.append({
            "test": str(test),
            "status": "failed",
            "message": self._format_error(err),
        })

    def addError(self, test, err):
        super().addError(test, err)
        self.collected.append({
            "test": str(test),
            "status": "error",
            "message": self._format_error(err),
        })

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.collected.append({
            "test": str(test),
            "status": "skipped",
            "message": str(reason),
        })

    @staticmethod
    def _format_error(err):
        """格式化异常信息"""
        exc_type, exc_value, tb = err
        import traceback
        return "".join(traceback.format_exception(exc_type, exc_value, tb))


def run_tests(pattern: str | None = None, filter: str | None = None) -> dict:
    """运行 backend/tests/ 下的测试

    Args:
        pattern: 文件名过滤（glob 模式，如 "test_auth*"）
        filter: 方法名过滤（如 "test_login"）

    Returns:
        {total, passed, failed, errors, details}
    """
    try:
        suite = _discover_tests(pattern)
    except FileNotFoundError as e:
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "details": [],
            "error": str(e),
        }

    # 如果有 filter，过滤测试方法
    if filter:
        filtered_suite = unittest.TestSuite()
        for test_group in suite:
            if hasattr(test_group, "_tests"):
                for test_case in test_group:
                    if hasattr(test_case, "_tests"):
                        for test in test_case:
                            if filter in str(test):
                                filtered_suite.addTest(test)
                    else:
                        if filter in str(test_case):
                            filtered_suite.addTest(test_case)
            else:
                if filter in str(test_group):
                    filtered_suite.addTest(test_group)
        suite = filtered_suite

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=0, resultclass=_TestResultCollector)
    result = runner.run(suite)

    details = result.collected
    total = len(details)
    passed = sum(1 for d in details if d["status"] == "passed")
    failed = sum(1 for d in details if d["status"] == "failed")
    errors = sum(1 for d in details if d["status"] == "error")
    skipped = sum(1 for d in details if d["status"] == "skipped")

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "details": details,
    }
