---
name: requesting-code-review
description: 预提交代码审查 — 安全扫描、质量门禁、自动修复循环
version: 1.0
category: development
triggers: [审查, 代码检查, 预提交, 质量, 代码质量, 安全扫描]
---

# 预提交代码验证

自动验证流水线，在代码落地前运行。静态扫描、质量门禁、独立审查、自动修复。

**核心理念：不要在代理自己验证自己的工作。新鲜上下文能发现你漏掉的东西。**

## 何时使用

- 实现功能或修复 bug 后，在 `git commit` 前
- 当用户说"提交"、"推送"、"完成"、"验证"、"合并前审查"时
- 完成2+个文件编辑的任务后
- 子代理驱动的每个任务后的两阶段审查

## 第一步 — 获取 diff

```bash
git diff --cached
```

如果为空，试 `git diff` 然后 `git diff HEAD~1 HEAD`。

如果 diff 超过 15000 字符，按文件拆分。

## 第二步 — 静态安全扫描

只扫描新增行。任何命中都是安全问题：

```bash
# 硬编码密钥
git diff --cached | grep "^+" | grep -iE "(api_key|secret|password|token|passwd)\s*=\s*['\"][^'\"]{6,}['\"]"

# Shell 注入
git diff --cached | grep "^+" | grep -E "os\.system\(|subprocess.*shell=True"

# 危险 eval/exec
git diff --cached | grep "^+" | grep -E "\beval\(|\bexec\("

# 不安全反序列化
git diff --cached | grep "^+" | grep -E "pickle\.loads?\("

# SQL 注入（查询中字符串格式化）
git diff --cached | grep "^+" | grep -E "execute\(f\"|\.format\(.*SELECT|\.format\(.*INSERT"
```

## 第三步 — 基线测试

检测项目语言并运行适当的测试工具。**你的变更之前**的失败数量作为基线（暂存变更，运行测试，恢复）。只有**新引入的**失败才阻止提交。

## 第四步 — 自查清单

- [ ] 没有硬编码的密钥、密码、凭证
- [ ] 用户输入有校验
- [ ] SQL 查询使用参数化语句
- [ ] 文件操作验证路径（无遍历）
- [ ] 外部调用有错误处理
- [ ] 没有遗留的调试打印
- [ ] 没有注释掉的代码
- [ ] 新代码有测试

## 第五步 — 派发独立审查子代理

审查者只拿到 diff 和静态扫描结果。不共享实现者的上下文。

审查者返回 JSON 裁决：
- `passed`：通过/不通过
- `security_concerns`：安全问题列表
- `logic_errors`：逻辑错误列表
- `suggestions`：建议（非阻塞）
- `summary`：一句话裁决

**自动失败条件：** 硬编码密钥、后门、数据外泄、shell注入、SQL注入、路径遍历、eval()/exec()、pickle.loads()、混淆命令。

## 第六步 — 评估结果

**全部通过：** 进入第八步（提交）。

**有任何失败：** 报告失败，进入第七步（自动修复）。

## 第七步 — 自动修复循环

**最多 2 次修复-重验证循环。**

派发**第三个**代理上下文（不是你实现者，也不是审查者）。它只修复报告的问题。不重构、不改名、不做任何额外改动。

修复后重新运行第一至第六步。
- 通过 → 第八步
- 失败且尝试 < 2 → 重复第七步
- 尝试2次仍失败 → 上报给用户

## 第八步 — 提交

```bash
git add -A && git commit -m "[verified] 描述"
```

`[verified]` 前缀表示经过独立审查者批准。

## 常见模式标记

### Python
```python
# 不好：SQL注入
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
# 好：参数化
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))

# 不好：shell注入
os.system(f"ls {user_input}")
# 好：安全 subprocess
subprocess.run(["ls", user_input], check=True)
```

### JavaScript
```javascript
// 不好：XSS
element.innerHTML = userInput;
// 好：安全
element.textContent = userInput;
```

## 坑

- **空的 diff** — 检查 `git status`，告诉用户没东西要验证
- **不是 git 仓库** — 跳过并告知用户
- **大 diff（>15k字符）** — 按文件拆分，逐个审查
- **审查者返回非 JSON** — 重试一次，仍失败则标记 FAIL
- **误报** — 如果审查者标记了故意为之的内容，在修复提示中注明
- **找不到测试框架** — 跳过回归检查，审查裁决仍然执行
- **自动修复引入新问题** — 作为新失败，循环继续
