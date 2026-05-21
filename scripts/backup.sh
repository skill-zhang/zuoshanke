#!/bin/bash
# 坐山客每日备份脚本 — 推送到 E 盘 + 本地备份
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

echo "✅ Git 推送完成"

# 确保备份目录存在
mkdir -p ~/zuoshanke/backup

# 备份 DB
cp ~/zuoshanke/backend/zuoshanke.db ~/zuoshanke/backup/zuoshanke-$(date +%Y%m%d).db
echo "✅ DB 备份完成: zuoshanke-$(date +%Y%m%d).db"

# 备份前端 build 产物
tar -czf ~/zuoshanke/backup/frontend-dist-$(date +%Y%m%d).tar.gz -C ~/zuoshanke/frontend dist/
echo "✅ 前端产物备份完成: frontend-dist-$(date +%Y%m%d).tar.gz"

# 清理 7 天前的旧备份
find ~/zuoshanke/backup/ -name 'zuoshanke-*.db' -mtime +7 -delete
find ~/zuoshanke/backup/ -name 'frontend-dist-*.tar.gz' -mtime +7 -delete
echo "✅ 旧备份清理完成（保留 7 天）"

echo "✅ 全部备份完成: $(date)"
