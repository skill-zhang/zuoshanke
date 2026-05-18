---
name: github-repo-management
description: GitHub 仓库管理 — 克隆、创建、分叉、备份、GFW 镜像下载方案
version: 1.0
category: development
triggers: [仓库管理, 克隆, GitHub, git克隆, 备份, 镜像, GFW, 分叉, Release, 远程仓库, 翻墙, 代理]
---

# GitHub 仓库管理

## 1. 克隆仓库

```bash
# HTTPS
git clone https://github.com/owner/repo-name.git

# 指定目录
git clone https://github.com/owner/repo-name.git ./my-dir

# 浅克隆（大仓库更快）
git clone --depth 1 https://github.com/owner/repo-name.git

# SSH（如果配置了 SSH）
git clone git@github.com:owner/repo-name.git
```

## 2. 创建仓库

```bash
# 创建并克隆
gh repo create my-project --public --clone

# 从已有本地目录创建
cd /path/to/existing/project
gh repo create my-project --source . --public --push
```

## 3. 分叉（Fork）

```bash
gh repo fork owner/repo-name --clone

# 添加上游 remote
git remote add upstream https://github.com/owner/repo-name.git

# 同步分叉
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

## 4. 远程仓库管理

```bash
# 查看 remote
git remote -v

# 添加 remote
git remote add backup /mnt/e/zuoshanke-backup/zuoshanke.git

# 推送到多个 remote
git push origin main
git push backup main
```

## 5. Release 管理

```bash
# 创建 Release
gh release create v1.0.0 --title "v1.0.0" --generate-notes

# 草稿/预发布
gh release create v2.0.0-rc1 --draft --prerelease

# 上传二进制文件
gh release create v1.0.0 ./dist/binary --title "v1.0.0"

# 列表
gh release list

# 下载
gh release download v1.0.0 --dir ./downloads
```

## 6. GitHub Actions

```bash
# 列出 workflow
gh workflow list

# 查看运行记录
gh run list --limit 10

# 查看失败日志
gh run view <RUN_ID> --log-failed

# 重新运行
gh run rerun <RUN_ID>
gh run rerun <RUN_ID> --failed
```

## 7. GFW 环境下的镜像下载方案

当 `github.com` 无法直接访问时：

### 检测连接

```bash
timeout 5 curl -sI https://github.com 2>&1 | head -1
```

### 测试可用镜像

```bash
for mirror in \
  "https://ghfast.top/https://github.com" \
  "https://ghproxy.net/https://github.com"; do
  echo -n "$(echo $mirror | cut -d/ -f3): "
  timeout 5 curl -sI "$mirror" 2>&1 | head -1
done
```

### 通过镜像下载仓库

```bash
# 先查默认分支
REPO="owner/repo-name"
BRANCH=$(curl -s "https://api.github.com/repos/${REPO}" 2>/dev/null | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('default_branch','main'))" 2>/dev/null || echo "main")

# 通过镜像下载 zip
MIRROR="https://ghfast.top"
curl -L -o /tmp/repo.zip \
  "${MIRROR}/https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"
```

### 解压到本地（安全模式）

```bash
# 第一阶段：解压到 /tmp
python3 -c "
import zipfile, os
zf = '/tmp/repo.zip'
out = '/tmp/_extract_repo'
os.makedirs(out, exist_ok=True)
with zipfile.ZipFile(zf, 'r') as z:
    z.extractall(out)
print('Contents:', os.listdir(out))
"

# 第二阶段：移动到目标位置
mv /tmp/_extract_repo/<repo-dir> /home/administrator/<target-dir>

# 第三阶段：清理
rm -rf /tmp/_extract_repo /tmp/repo.zip
```

**坑：Git LFS 指针问题**
通过 zip 下载的仓库中，Git LFS 跟踪的文件会被替换为约 130 字节的指针文件，不是实际内容。检测方法：`file <suspicious-file>` 返回 "ASCII text" 但预期是二进制。修复：用 `git clone`（会解析 LFS），或单独下载 LFS 文件。

## 8. 快速参考

| 操作 | gh 命令 | git/curl |
|------|---------|----------|
| 克隆 | `gh repo clone o/r` | `git clone https://github.com/o/r.git` |
| 创建仓库 | `gh repo create name` | `curl POST /user/repos` |
| 分叉 | `gh repo fork o/r` | `curl POST /repos/o/r/forks` |
| Release | `gh release create v1.0` | `curl POST /repos/o/r/releases` |
| CI 列表 | `gh workflow list` | `curl GET /repos/o/r/actions/workflows` |
