#!/bin/bash
# ============================================================
# backup.sh — Questra-Search 独立备份脚本
# 用法: bash backup.sh
# 可用于 cron 定时任务或手动执行
# ============================================================
set -euo pipefail

ECS_HOST="${ECS_HOST:-43.106.12.79}"
ECS_USER="${ECS_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/questra-search}"
BACKUP_DIR="${BACKUP_DIR:-/opt/questra-search-backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "============================================"
echo "  Questra-Search 备份"
echo "  时间: $TIMESTAMP"
echo "  目标: $ECS_USER@$ECS_HOST"
echo "============================================"

ssh -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} "
    set -euo pipefail
    mkdir -p ${BACKUP_DIR}/${TIMESTAMP}

    echo '[1/3] 备份应用代码...'
    if [ -d '${REMOTE_DIR}/app' ]; then
        cp -r ${REMOTE_DIR}/app ${BACKUP_DIR}/${TIMESTAMP}/
        cp -r ${REMOTE_DIR}/static ${BACKUP_DIR}/${TIMESTAMP}/ 2>/dev/null || true
        cp ${REMOTE_DIR}/server.py ${BACKUP_DIR}/${TIMESTAMP}/ 2>/dev/null || true
        cp ${REMOTE_DIR}/requirements.txt ${BACKUP_DIR}/${TIMESTAMP}/ 2>/dev/null || true
        cp ${REMOTE_DIR}/.env ${BACKUP_DIR}/${TIMESTAMP}/.env.backup 2>/dev/null || true
        echo '  代码备份完成'
    else
        echo '  (app/ 目录不存在，跳过)'
    fi

    echo '[2/3] 备份数据库...'
    if [ -f '${REMOTE_DIR}/data/questra_search.db' ]; then
        sqlite3 ${REMOTE_DIR}/data/questra_search.db \".backup ${BACKUP_DIR}/questra_search_db_${TIMESTAMP}\"
        DB_SIZE=\$(stat -c%s ${BACKUP_DIR}/questra_search_db_${TIMESTAMP} 2>/dev/null || stat -f%z ${BACKUP_DIR}/questra_search_db_${TIMESTAMP} 2>/dev/null || echo '?')
        echo \"  数据库: ${BACKUP_DIR}/questra_search_db_${TIMESTAMP} (\${DB_SIZE} bytes)\"
    else
        echo '  (数据库不存在，跳过)'
    fi

    echo '[3/3] 清理旧备份 (保留最近 10 次)...'
    cd ${BACKUP_DIR}
    ls -dt */ 2>/dev/null | tail -n +11 | xargs rm -rf 2>/dev/null || true
    ls questra_search_db_* 2>/dev/null | sort | head -n -10 | xargs rm -f 2>/dev/null || true
    echo '  清理完成'
"

echo ""
echo "============================================"
echo "  ✅ 备份成功"
echo "  位置: $BACKUP_DIR/$TIMESTAMP"
echo "============================================"
