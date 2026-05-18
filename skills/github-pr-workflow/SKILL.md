---
name: github-pr-workflow
description: GitHub PR 工作流 — 分支创建、提交、创建 PR、CI 监控、合并
version: 1.0
category: development
triggers: [PR, Pull Request, 分支, 提交, CI, 合并, git工作流, 代码合并]
---

# Pull Request 工作流

## 1. 创建分支

```bash
# 确保在最新的 main 上
git fetch origin
git checkout main && git pull origin main

# 创建新分支
git checkout -b feat/add-user-authentication
```

分支命名规范：
- `feat/description` — 新功能
- `fix/description` — Bug 修复
- `refactor/description` — 重构
- `docs/description` — 文档
- `ci/description` — CI/CD

## 2. 提交

```bash
git add src/auth.py src/models/user.py
git commit -m "feat: add JWT-based user authentication

- Add login/register endpoints
- Add User model with password hashing
- Add unit tests for auth flow"
```

提交信息格式（Conventional Commits）：
```
type(scope): short description

Longer explanation if needed.
```

类型：`feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `chore`, `perf`

## 3. 推送并创建 PR

### 推送

```bash
git push -u origin HEAD
```

### 创建 PR

```bash
gh pr create \
  --title "feat: add JWT-based user authentication" \
  --body "## Summary\n- Adds login and register API endpoints\n\nCloses #42" \
  --label "enhancement" \
  --draft  # 可选：草稿模式
```

## 4. 监控 CI

```bash
# 一次性检查
gh pr checks

# 持续监控
gh pr checks --watch
```

### 自动修复 CI 失败循环

1. 检查 CI 状态 → 识别失败
2. 读取失败日志 → 理解错误
3. 修复代码
4. `git add && git commit -m "fix: ..." && git push`
5. 等待 CI → 重新检查状态
6. 最多 3 次尝试，然后问用户

## 5. 合并

```bash
# Squash 合并 + 删除分支
gh pr merge --squash --delete-branch

# 启用自动合并（CI 通过后自动合并）
gh pr merge --auto --squash --delete-branch
```

## 6. 完整工作流示例

```bash
# 1. 从 main 开始
git checkout main && git pull origin main

# 2. 建分支
git checkout -b fix/login-redirect-bug

# 3. 修改代码...

# 4. 提交
git add src/auth/login.py tests/test_login.py
git commit -m "fix: correct redirect URL after login"

# 5. 推送
git push -u origin HEAD

# 6. 创建 PR
gh pr create --title "fix: correct redirect URL" --body "..."

# 7. CI 通过后合并
gh pr merge --squash --delete-branch
```

## 本地 Git 工作流（无 GitHub）

> ⚠️ 如果 GitHub 无法访问（如 GFW），纯 git 工作流仍然完整可用：
> - 本地分支、提交、diff 审查完全不受影响
> - 备份 remote 可用 `git push backup`（参见 zuoshanke 项目的 `backup.sh`）
> - GitHub PR/CI 功能暂时跳过
