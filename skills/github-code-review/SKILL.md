---
name: github-code-review
description: 代码审查 — git diff 本地审查 + GitHub PR 代码审查工作流
version: 1.0
category: development
triggers: ["代码审查", "Code Review", "审查代码", "PR审查", "git diff", "审查清单", "代码走查", "审一下", "review代码", "审查", "审阅"]
---

# 代码审查

## 1. 本地变更审查（Pre-Push）

纯 `git` 操作，不需要 GitHub 连接：

### 获取 Diff

```bash
# 已暂存的变更
git diff --staged

# 与 main 分支的差异
git diff main...HEAD

# 仅文件名
git diff main...HEAD --name-only

# 统计
git diff main...HEAD --stat
```

### 审查策略

1. **先看大局：**
```bash
git diff main...HEAD --stat
git log main..HEAD --oneline
```

2. **逐个文件审查：**
```bash
git diff main...HEAD -- src/auth/login.py
```

3. **检查常见问题：**
```bash
# 残留调试语句
git diff main...HEAD | grep -n "print(\|console\.log\|TODO\|FIXME\|debugger"

# 大文件异常
git diff main...HEAD --stat | sort -t'|' -k2 -rn | head -10

# 密钥泄露
git diff main...HEAD | grep -in "password\|secret\|api_key\|token.*="

# 合并冲突标记
git diff main...HEAD | grep -n "<<<<<<\|>>>>>>\|======="
```

### 审查输出格式

```
## 代码审查摘要

### 🔴 严重
- src/auth.py:45 — SQL注入风险，建议使用参数化查询

### ⚠️ 警告
- src/models/user.py:23 — 明文存储密码，建议用 bcrypt

### 💡 建议
- tests/test_auth.py — 缺少过期 token 测试用例

### ✅ 没问题
- 中间件层分离清晰
- 主路径测试覆盖良好
```

## 2. GitHub PR 审查

### 查看 PR 详情

```bash
# 用 gh
gh pr view 123
gh pr diff 123

# 用 curl
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/files
```

### 本地检出 PR

```bash
git fetch origin pull/123/head:pr-123
git checkout pr-123
```

### 提交审查意见

```bash
# 总体评论
gh pr comment 123 --body "整体不错，有几个建议"

# 提交正式审查
gh pr review 123 --approve --body "LGTM!"
gh pr review 123 --request-changes --body "见 inline 注释"
```

## 3. 审查清单

### 正确性
- [ ] 代码做了它声称的功能？
- [ ] 边界情况处理了（空输入、null、大数据、并发）？
- [ ] 错误路径优雅处理？

### 安全
- [ ] 无硬编码密钥/凭证
- [ ] 用户输入有校验
- [ ] 无 SQL 注入、XSS、路径遍历
- [ ] 权限检查到位

### 代码质量
- [ ] 命名清晰
- [ ] 无过度复杂或过早抽象
- [ ] DRY — 无重复逻辑
- [ ] 函数职责单一

### 测试
- [ ] 新代码路径有测试？
- [ ] 主路径和错误路径都覆盖？
- [ ] 测试可读性好？
