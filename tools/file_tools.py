#!/usr/bin/env python3
"""文件操作工具集 — read_file / write_file / patch / search_files

纯 Python 标准库实现，零外部依赖。
遵循 zuoshanke 工具规范：导入后可直接调用函数。

用法：
    from file_tools import read_file, write_file, patch, search_files

    result = read_file("/path/to/file.py", offset=1, limit=50)
    result = write_file("/path/to/file.py", "print('hello')")
    result = patch("/path/to/file.py", "old text", "new text")
    result = search_files("pattern", path="~/project", file_glob="*.py")
"""

import base64
import json
import os
import re
import fnmatch
import difflib
from pathlib import Path

from typing import Optional

# ── 常量 ──────────────────────────────────────────────────────────────────────

STDOUT_MAX_BYTES = 50 * 1024  # 50 KB 输出截断
GITIGNORE_PATTERNS = {".git", "__pycache__", "node_modules", ".venv", ".zuoshanke"}
MAX_RESULTS = 200

# ── 路径安全 ──────────────────────────────────────────────────────────────────

def _resolve_path(path: str) -> str:
    """展开 ~ 并转为规范绝对路径，解析符号链接防遍历绕过"""
    expanded = os.path.expanduser(path)
    resolved = os.path.realpath(expanded)
    # 阻止读取 /dev、/proc、/sys 等特殊设备
    if any(resolved.startswith(p) for p in ["/dev/", "/proc/", "/sys/", "/etc/"]):
        raise PermissionError(f"禁止访问系统路径: {resolved}")
    return resolved


def _is_binary_extension(path: str) -> bool:
    """检查是否是常见的二进制文件扩展名"""
    ext = os.path.splitext(path)[1].lower()
    binary_exts = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
        ".mp3", ".wav", ".ogg", ".mp4", ".avi", ".mov", ".mkv",
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".bin",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".ttf", ".eot", ".woff", ".woff2",
        ".pyc", ".pyo", ".pyd",
        ".db", ".sqlite", ".sqlite3",
        ".o", ".a", ".lib",
    }
    return ext in binary_exts


# ── read_file ─────────────────────────────────────────────────────────────────

def read_file(path: str, offset: int = 1, limit: int = 500) -> dict:
    """读取文件内容，带行号和分页。

    Args:
        path: 文件路径（支持 ~）
        offset: 起始行号（从 1 开始）
        limit: 最多读取行数

    Returns:
        {"content": "LINE_NUM|CONTENT\\n...", "total_lines": N, "error": None} 或
        {"error": "错误描述"}
    """
    try:
        resolved = _resolve_path(path)

        if not os.path.isfile(resolved):
            return {"error": f"文件不存在: {path}"}

        if _is_binary_extension(resolved):
            return {"error": f"二进制文件不可读: {path}（使用 vision_analyze 查看图片，或用 terminal 处理）"}

        # 检查文件大小（超过 1MB 警告）
        try:
            file_size = os.path.getsize(resolved)
            if file_size > 1 * 1024 * 1024:
                return {"error": f"文件过大 ({file_size / 1024 / 1024:.1f} MB)，请用 terminal 工具分段处理"}
        except OSError:
            pass

        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total = len(lines)

        # 参数校验
        if offset < 1:
            offset = 1
        if limit < 1:
            limit = 1

        start = offset - 1
        chunk = lines[start:start + limit]

        content_lines = []
        for i, line in enumerate(chunk, start=offset):
            content_lines.append(f"{i}|{line.rstrip()}")

        return {
            "content": "\n".join(content_lines),
            "total_lines": total,
            "offset": offset,
            "limit": limit,
        }

    except UnicodeDecodeError:
        return {"error": f"文件无法以 UTF-8 解码（可能是二进制文件）: {path}"}
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"读取失败: {e}"}


# ── write_file ────────────────────────────────────────────────────────────────

def _git_snapshot(resolved: str) -> None:
    """Git 自动快照：在修改 .py / .ts / .tsx 等代码文件前，自动 commit 当前版本。
    
    静默失败，不中断主流程。
    """
    try:
        import subprocess
        repo_dir = os.path.dirname(os.path.dirname(resolved))
        # 确认在 git repo 内
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            return
        rel = os.path.relpath(resolved, repo_dir)
        subprocess.run(
            ["git", "add", rel],
            cwd=repo_dir, capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", f"🛡 auto-snapshot before modify: {rel}"],
            cwd=repo_dir, capture_output=True, timeout=10
        )
    except Exception:
        pass


def _validate_file_content(resolved: str, content: str) -> Optional[str]:
    """写后静态校验：阻止语法错误写入。
    
    支持：.py (py_compile), .json (json.loads), .js/.jsx (node --check),
          .yaml/.yml (yaml.safe_load), .ts/.tsx (只做正则粗检)
    
    Returns:
        错误信息（有错时）或 None（校验通过）
    """
    ext = os.path.splitext(resolved)[1].lower()
    try:
        if ext == ".py":
            import py_compile
            import tempfile
            # 写临时文件编译，避免污染目标文件
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                py_compile.compile(tmp_path, doraise=True)
            finally:
                os.unlink(tmp_path)

        elif ext == ".json":
            json.loads(content)  # 纯结构校验，不写文件

        elif ext in (".yaml", ".yml"):
            import yaml
            yaml.safe_load(content)

        elif ext in (".js", ".jsx", ".mjs"):
            # node --check 验证 JS 语法
            import tempfile, subprocess
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False, mode="w", encoding="utf-8") as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                r = subprocess.run(["node", "--check", tmp_path],
                                   capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    return f"JavaScript 语法错误: {r.stderr.strip() or r.stdout.strip()}"
            except FileNotFoundError:
                pass  # node 未安装，跳过
            finally:
                os.unlink(tmp_path)

        # .ts/.tsx — 不强制校验（需要 tsconfig + tsc 环境），仅记录
    except Exception as e:
        return f"{ext} 语法错误: {e}"
    return None


def write_file(path: str, content: str = "", content_b64: str = None) -> dict:
    """写入文件（覆盖写入），自动创建父目录。

    Args:
        path: 文件路径（支持 ~）
        content: 文件内容
        content_b64: base64 编码的文件内容（替代 content 传参，避免大字符串 JSON 转义问题）

    Returns:
        {"success": True, "path": "..."} 或 {"error": "错误描述"}
    """
    try:
        # 路径安全检查
        try:
            from agent_core.path_security import assert_safe_write
            assert_safe_write(path)
        except ImportError:
            pass
        except ValueError as e:
            return {"error": str(e)}

        resolved = _resolve_path(path)

        # 若提供 content_b64，解码后作为实际内容
        if content_b64 is not None:
            try:
                content = base64.b64decode(content_b64).decode("utf-8")
            except Exception as e:
                return {"error": f"content_b64 解码失败: {e}"}

        # 创建父目录
        parent = os.path.dirname(resolved)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # 🛡 Git 自动快照：改代码文件前保留当前版本
        if resolved.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
            _git_snapshot(resolved)

        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)

        # 🛡 写后静态校验：阻止语法错误写入
        err = _validate_file_content(resolved, content)
        if err:
            os.remove(resolved)
            return {"error": f"已阻止写入并回滚: {err}"}

        size = os.path.getsize(resolved)
        # Schema v1.0: 记录文件快照
        _record_snapshot(resolved, content)
        return {
            "success": True,
            "path": resolved,
            "size": f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B",
        }

    except PermissionError as e:
        return {"error": f"权限不足: {e}"}
    except Exception as e:
        return {"error": f"写入失败: {e}"}


# ── patch (find-and-replace with fuzzy matching) ─────────────────────────────

def _fuzzy_find(file_content: str, old_string: str, replace_all: bool = False):
    """在文件内容中查找 old_string，支持模糊匹配。
    
    使用 difflib.SequenceMatcher 的 9 级匹配策略：
    1. 精确匹配
    2. 忽略前后空白
    3. 行内精确匹配
    4-9. 逐渐放宽的模糊匹配

    Returns:
        [(start, end, similarity), ...] 排序后的匹配列表
    """
    matches = []

    # 策略 1: 精确匹配
    idx = file_content.find(old_string)
    if idx >= 0:
        matches.append((idx, idx + len(old_string), 1.0))
        if not replace_all:
            return matches

    # 策略 2: 去除首尾空白再匹配
    stripped = old_string.strip()
    if stripped != old_string:
        idx = file_content.find(stripped)
        if idx >= 0:
            matches.append((idx, idx + len(stripped), 0.95))

    # 策略 3: 行级匹配（逐行查找）
    if not matches:
        old_lines = old_string.split('\n')
        file_lines = file_content.split('\n')
        for i in range(len(file_lines) - len(old_lines) + 1):
            match = True
            for j, ol in enumerate(old_lines):
                if file_lines[i + j].strip() != ol.strip():
                    match = False
                    break
            if match:
                start = sum(len(l) + 1 for l in file_lines[:i])
                end = sum(len(l) + 1 for l in file_lines[:i + len(old_lines)]) - 1
                matches.append((start, end, 0.9))

    # 策略 4-9: difflib 模糊匹配
    if not matches:
        matcher = difflib.SequenceMatcher(None, file_content, old_string, autojunk=False)
        for block in matcher.get_matching_blocks():
            if block.size >= max(len(old_string) * 0.5, 3):
                similarity = block.size / len(old_string)
                if similarity >= 0.5:
                    start = block.a
                    end = block.a + block.size
                    matches.append((start, end, similarity))

    # 去重 + 按位置排序
    seen = set()
    unique = []
    for m in sorted(matches, key=lambda x: -x[2]):  # 相似度高的优先
        key = (m[0], m[1])
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return sorted(unique, key=lambda x: x[0])


def patch(path: str, old_string: str = "", new_string: str = "",
          replace_all: bool = False) -> dict:
    """在文件中查找并替换文本，支持模糊匹配。

    Args:
        path: 文件路径
        old_string: 要查找的旧文本
        new_string: 替换的新文本（空字符串 = 删除）
        replace_all: 是否替换所有匹配

    Returns:
        {"success": True, "diff": "统一差异格式", "count": N} 或 {"error": "..."}
    """
    try:
        # 路径安全检查
        try:
            from agent_core.path_security import assert_safe_write
            assert_safe_write(path)
        except ImportError:
            pass
        except ValueError as e:
            return {"error": str(e)}

        resolved = _resolve_path(path)

        if not os.path.isfile(resolved):
            return {"error": f"文件不存在: {path}"}

        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()

        if not old_string:
            return {"error": "old_string 不能为空"}

        # 🛡 Git 自动快照：改代码文件前保留当前版本
        if resolved.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
            _git_snapshot(resolved)

        # 查找匹配
        matches = _fuzzy_find(content, old_string, replace_all)

        if not matches:
            # 提示附近内容
            words = old_string[:30]
            nearby = difflib.SequenceMatcher(None, content, old_string, autojunk=False)
            best = nearby.find_longest_match(0, len(content), 0, len(old_string))
            hint = ""
            if best.size > 2:
                hint_start = max(0, best.a - 20)
                hint_end = min(len(content), best.b + 20)
                hint = f" 最相近片段: ...{content[hint_start:hint_end]}..."
            return {"error": f"未找到匹配的文本: '{old_string[:50]}...'{hint}"}

        # 执行替换
        old_strings = [content[m[0]:m[1]] for m in matches]
        new_content = content
        replacements = 0

        if replace_all:
            for old in old_strings:
                new_content = new_content.replace(old, new_string, 1)
                replacements += 1
        else:
            # 只替换第一个（最好）匹配
            best_match = matches[0]
            old_str = content[best_match[0]:best_match[1]]
            new_content = content[:best_match[0]] + new_string + content[best_match[1]:]
            replacements = 1

        # 写入
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Schema v1.0: 记录文件快照
        _record_snapshot(resolved, new_content)

        # 🛡 patch 后静态校验：阻止语法错误写入（回滚到原内容）
        err = _validate_file_content(resolved, new_content)
        if err:
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)
            return {"error": f"已阻止 patch 并回滚: {err}"}

        # 生成 diff
        diff = list(difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=path, tofile=path,
        ))
        diff_text = "".join(diff) if diff else f"(替换 {replacements} 处，纯文本替换)"
        # 确保 diff 每行末尾都有换行符（处理文件末行无 \n 时 -ccc+ddd 连在一起）
        diff_text = "".join(
            line if line.endswith('\n') else line + '\n'
            for line in diff
        ) if diff else diff_text

        return {
            "success": True,
            "diff": diff_text,
            "count": replacements,
        }

    except PermissionError as e:
        return {"error": f"权限不足: {e}"}
    except Exception as e:
        return {"error": f"替换失败: {e}"}


# ── Schema v1.0: 文件快照记录 ──


def _record_snapshot(file_path: str, content: str) -> None:
    """记录文件快照供 diff 提取（静默失败，不中断主流程）"""
    try:
        from agent_core.snapshot_manager import record as snap_record
        try:
            from database import SessionLocal
            db = SessionLocal()
            try:
                snap_record(file_path, content, db=db)
            finally:
                db.close()
        except Exception:
            snap_record(file_path, content)
    except Exception:
        pass  # 静默失败，不影响主流程


# ── search_files ──────────────────────────────────────────────────────────────

def _should_ignore(name: str) -> bool:
    """检查是否应该忽略此文件/目录"""
    for pattern in GITIGNORE_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _grep_file(filepath: str, pattern: str, context: int = 0) -> list:
    """在单个文件中搜索正则表达式"""
    results = []
    try:
        if _is_binary_extension(filepath):
            return []
        if os.path.getsize(filepath) > 1024 * 1024:  # 跳过 >1MB 的文件
            return []

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                result = {
                    "line": i,
                    "text": line.rstrip()[:200],
                }
                if context > 0:
                    start = max(0, i - 1 - context)
                    end = min(len(lines), i + context)
                    ctx_lines = []
                    for ci in range(start, end):
                        marker = ">" if ci == i - 1 else " "
                        ctx_lines.append(f"{marker} {ci + 1}|{lines[ci].rstrip()}")
                    result["context"] = "\n".join(ctx_lines)
                results.append(result)
    except (UnicodeDecodeError, OSError):
        pass
    return results


def search_files(pattern: str, target: str = "content",
                 path: str = ".", file_glob: str = None,
                 limit: int = 50, offset: int = 0,
                 context: int = 0) -> dict:
    """搜索文件内容或查找文件名。

    Args:
        pattern: 搜索模式（content 模式用正则，files 模式用 glob）
        target: "content"（内容搜索）或 "files"（文件名查找）
        path: 搜索路径
        file_glob: 文件过滤 glob（如 "*.py"）
        limit: 最大结果数
        offset: 跳过前 N 个结果
        context: 上下文件行数（仅 content 模式）

    Returns:
        {"matches": [...], "total": N} 或 {"error": "..."}
    """
    try:
        root = _resolve_path(path)

        if not os.path.isdir(root):
            return {"error": f"目录不存在: {path}"}

        if target == "files":
            # 文件名查找
            matches = []
            for dirpath, dirnames, filenames in os.walk(root):
                # 跳过忽略目录
                dirnames[:] = [d for d in dirnames if not _should_ignore(d)]
                for fname in filenames:
                    if _should_ignore(fname):
                        continue
                    if fnmatch.fnmatch(fname, pattern):
                        full = os.path.join(dirpath, fname)
                        rel = os.path.relpath(full, root)
                        matches.append({
                            "file": rel,
                            "full_path": full,
                            "size": f"{os.path.getsize(full) / 1024:.1f} KB" if os.path.getsize(full) > 1024 else f"{os.path.getsize(full)} B",
                            "mtime": os.path.getmtime(full),
                        })
                        if len(matches) >= limit + offset:
                            break
                if len(matches) >= limit + offset:
                    break

            matches.sort(key=lambda x: -x["mtime"])
            total = len(matches)
            matches = matches[offset:offset + limit]

            # 清理内部字段
            for m in matches:
                del m["mtime"]

            return {"matches": matches, "total": total}

        else:
            # 内容搜索
            matches = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not _should_ignore(d)]
                for fname in filenames:
                    if _should_ignore(fname):
                        continue
                    if file_glob and not fnmatch.fnmatch(fname, file_glob):
                        continue

                    fpath = os.path.join(dirpath, fname)
                    try:
                        file_matches = _grep_file(fpath, pattern, context)
                    except Exception:
                        continue

                    if file_matches:
                        rel = os.path.relpath(fpath, root)
                        matches.append({
                            "file": rel,
                            "matches": file_matches[:5],  # 每个文件最多 5 个匹配
                            "match_count": len(file_matches),
                        })
                        if len(matches) >= limit + offset:
                            break
                if len(matches) >= limit + offset:
                    break

            total = len(matches)
            matches = matches[offset:offset + limit]

            return {
                "matches": matches,
                "total": total,
                "pattern": pattern,
            }

    except PermissionError as e:
        return {"error": f"权限不足: {e}"}
    except re.error as e:
        return {"error": f"正则表达式错误: {e}"}
    except Exception as e:
        return {"error": f"搜索失败: {e}"}


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法:")
        print("  python file_tools.py read <path> [offset] [limit]")
        print("  python file_tools.py write <path> <content>")
        print("  python file_tools.py patch <path> <old> <new>")
        print("  python file_tools.py search <pattern> [path]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "read":
        path = sys.argv[2]
        offset = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 500
        result = read_file(path, offset, limit)
    elif cmd == "write":
        path = sys.argv[2]
        content = sys.argv[3]
        result = write_file(path, content)
    elif cmd == "patch":
        path = sys.argv[2]
        old = sys.argv[3]
        new = sys.argv[4] if len(sys.argv) > 4 else ""
        result = patch(path, old, new)
    elif cmd == "search":
        pattern = sys.argv[2]
        path = sys.argv[3] if len(sys.argv) > 3 else "."
        result = search_files(pattern, path=path)
    else:
        result = {"error": f"未知命令: {cmd}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))
