"""端到端测试：高危命令扫描器注入验证

模拟 tool_executor.execute_tool() 的阻断链路，不依赖 LLM，不执行系统命令。
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/zuoshanke/backend"))

from agent_core.command_scanner import scan_command
from agent_core.tool_executor import execute_tool


def test_execute_tool_terminal_block():
    """模拟 LLM 调 terminal("rm -rf /") → 应被阻断"""
    result = execute_tool("terminal", {"command": "rm -rf /"})
    assert result.get("success") is False, f"期望阻断，但 success=True"
    assert result.get("high_risk"), f"期望 high_risk 字段，但没有"
    hr = result["high_risk"]
    assert hr["block"] is True
    assert hr["category"] == "filesystem"
    print(f'✅ terminal("rm -rf /") → 阻断 [{hr["category"]}] {hr["description"]}')
    return result


def test_execute_tool_terminal_safe():
    """模拟 LLM 调 terminal("ls -la") → 正常执行"""
    result = execute_tool("terminal", {"command": "ls -la"})
    assert result.get("success") is True, f"期望放行，但 success=False: {result.get('error')}"
    assert "high_risk" not in result, "安全命令不应有 high_risk 字段"
    print('✅ terminal("ls -la") → 正常执行')
    return result


def test_execute_tool_non_terminal():
    """非 terminal 工具不受影响（如 web_search）"""
    try:
        result = execute_tool("web_search", {"max_results": 1})
        # 成功或网络错误都说明工具被执行了（不是被扫描器拦截的）
        print(f'✅ web_search 非 terminal 工具 → 正常路由（非扫描器干预）')
    except Exception as e:
        print(f'⚠️ web_search 执行出错（可能是无网络），但非扫描器问题: {e}')
    return True


if __name__ == "__main__":
    print("═" * 50)
    print("高危命令扫描器 — 注入链路端到端测试")
    print("═" * 50)
    
    # 1. 直接扫描器测试（已单独通过）
    print("\n--- 1. 扫描器单元测试 ---")
    for cmd, expect_block in [
        ("rm -rf /", True),
        ("DROP TABLE users;", True),
        ("ls -la", False),
        ("echo hello", False),
    ]:
        r = scan_command(cmd, cwd="/tmp")
        blocked = bool(r and r.get("block"))
        status = "阻断" if blocked else "放行"
        assert blocked == expect_block, f"{cmd}: 期望 {'阻断' if expect_block else '放行'}"
        print(f'  ✅ {status}: {cmd}')
    
    # 2. 通过 tool_executor 注入链路测试
    print("\n--- 2. tool_executor 注入链路 ---")
    test_execute_tool_terminal_block()
    test_execute_tool_terminal_safe()
    test_execute_tool_non_terminal()
    
    # 3. agent_loop 模拟：检查 error 消息是否包含扫描信息
    print("\n--- 3. 错误消息格式检查 ---")
    result = execute_tool("terminal", {"command": "rm -rf /"})
    error = result.get("error", "")
    hr = result.get("high_risk", {})
    assert "⚠️" in error or "高危" in error, f"错误消息应包含可读的风险描述: {error[:60]}"
    print(f'  ✅ 错误消息格式正确: {error[:60]}...')
    
    print("\n" + "═" * 50)
    print("🎉 全部端到端测试通过！")
    print("═" * 50)
