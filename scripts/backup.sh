#!/bin/bash
# 坐山客每日备份脚本 — 推送到 E 盘
# 用法: bash ~/zuoshanke/scripts/backup.sh

set -e

cd ~/zuoshanke

# 检查是否有变更
if [[ -z $(git status --porcelain) ]]; then
    echo "✅ 无变更，跳过"
    exit 0
fi

# 提交并推送到 E 盘
git add -A
git commit -m "自动备份 $(date '+%Y-%m-%d %H:%M')"
git push backup main

echo "✅ 备份完成: $(date)"
