---
name: github-auth
description: GitHub 认证配置 — HTTPS Token、SSH 密钥、gh CLI 登录，含 GFW 环境说明
version: 1.0
category: development
triggers: [GitHub认证, gh CLI, SSH密钥, Personal Access Token, git配置]
---

# GitHub 认证配置

## 检测流程

```bash
# 检查可用的工具
git --version
gh --version 2>/dev/null || echo "gh not installed"

# 检查认证状态
gh auth status 2>/dev/null || echo "gh not authenticated"
git config --global credential.helper 2>/dev/null || echo "no git credential helper"
```

## 方法一：HTTPS + Personal Access Token

### 创建 token
访问：**https://github.com/settings/tokens**
- 选 classic token
- 勾选 `repo`（完整仓库访问）、`workflow`（Actions）
- 复制 token

### 配置 git

```bash
# 存储凭证
git config --global credential.helper store

# 测试认证（输入用户名和 token）
git ls-remote https://github.com/<username>/<repo>.git

# 设置提交身份
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

### 直接在远程 URL 中嵌入 Token

```bash
git remote set-url origin https://<username>:<token>@github.com/<owner>/<repo>.git
```

## 方法二：SSH 密钥

```bash
# 生成密钥
ssh-keygen -t ed25519 -C "your@email.com" -f ~/.ssh/id_ed25519 -N ""

# 显示公钥
cat ~/.ssh/id_ed25519.pub
```

把公钥添加到 **https://github.com/settings/keys**

测试连接：
```bash
ssh -T git@github.com
```

## 方法三：gh CLI

```bash
# 浏览器登录（桌面环境）
gh auth login

# Token 登录（无头模式）
echo "<token>" | gh auth login --with-token
gh auth setup-git
```

## GFW 环境下说明

> ⚠️ 国内访问 GitHub 可能不稳定。以上配置仍可正常使用（HTTPS/SSH 均可），只是 clone/push 速度较慢。
> 如果完全无法连接，参见 `github-repo-management` 技能中的镜像代理方案。
