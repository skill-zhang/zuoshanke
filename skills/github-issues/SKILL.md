---
name: github-issues
description: GitHub Issue 管理 — 创建、分类、打标签、指派、搜索与批量操作
version: 1.0
category: development
triggers: [Issue, 问题管理, BUG跟踪, 任务管理, GitHub Issues, 报告bug, 提issue, 问题追踪]
---

# GitHub Issues 管理

## 前提

```bash
# 检测认证方式
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  AUTH="gh"
else
  AUTH="git"
  # 从 git 凭证或环境变量获取 token
fi

# 提取 owner/repo
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=$(echo "$OWNER_REPO" | cut -d/ -f1)
REPO=$(echo "$OWNER_REPO" | cut -d/ -f2)
```

## 查看 Issues

```bash
gh issue list
gh issue list --state open --label "bug"
gh issue list --assignee @me
gh issue view 42
```

## 创建 Issue

```bash
gh issue create \
  --title "登录后 redirect 忽略 ?next= 参数" \
  --body "## 描述\n登录后用户总是跳转到 /dashboard\n\n## 复现步骤\n..." \
  --label "bug,backend" \
  --assignee "username"
```

### Bug Report 模板

```
## Bug 描述
<发生了什么>

## 复现步骤
1. <步骤>
2. <步骤>

## 预期行为
<应该发生什么>

## 实际行为
<实际发生了什么>
```

### Feature Request 模板

```
## 功能描述
<想要什么>

## 动机
<为什么有用>

## 方案
<怎么做>

## 替代方案
<其他考虑过的>
```

## 管理 Issue

### 标签

```bash
gh issue edit 42 --add-label "priority:high,bug"
gh issue edit 42 --remove-label "needs-triage"
```

### 指派

```bash
gh issue edit 42 --add-assignee username
```

### 评论

```bash
gh issue comment 42 --body "已调查，根因在 auth 中间件"
```

### 关闭/重开

```bash
gh issue close 42
gh issue close 42 --reason "not planned"
gh issue reopen 42
```

## 批量操作

```bash
# 批量关闭带特定标签的 Issue
gh issue list --label "wontfix" --json number --jq '.[].number' | \
  xargs -I {} gh issue close {} --reason "not planned"
```

## 快速参考

| 操作 | gh 命令 | curl 端点 |
|------|---------|----------|
| 列表 | `gh issue list` | `GET /repos/{o}/{r}/issues` |
| 查看 | `gh issue view N` | `GET /repos/{o}/{r}/issues/N` |
| 创建 | `gh issue create` | `POST /repos/{o}/{r}/issues` |
| 加标签 | `gh issue edit N --add-label` | `POST /repos/{o}/{r}/issues/N/labels` |
| 指派 | `gh issue edit N --add-assignee` | `POST /repos/{o}/{r}/issues/N/assignees` |
| 评论 | `gh issue comment N` | `POST /repos/{o}/{r}/issues/N/comments` |
| 关闭 | `gh issue close N` | `PATCH /repos/{o}/{r}/issues/N` |
