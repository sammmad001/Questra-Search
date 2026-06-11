#!/bin/bash
# ============================================================
# rollback.sh — Questra-Search 独立回滚脚本
# 用法: bash rollback.sh [backup_name]
#   - 无参数: 交互式选择，默认使用最新备份
#   - 指定备份名: bash rollback.sh 20260611_120000
# ============================================================
set -euo pipefail

ECS_HOST="${ECS_HOST:-43.106.12.79}"
ECS_USER="${ECS_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/questra-search}"
BACKUP_DIR="${BACKUP_DIR:-/opt/questra-search-backups}"

echo "============================================"
echo "  Questra-Search 回滚"
echo "============================================"

# 如果指定了备份名称，使用指定备份；否则列出可用备份
if [ -n "${1:-}" ]; then
    TARGET="$BACKUP_DIR/$1"
else
    echo "可用备份:"
    ssh -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} "ls -dt ${BACKUP_DIR}/*/ 2>/dev/null | head -5 || echo '  (无备份)'"
    echo ""

    TARGET=$(ssh -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} "ls -dt ${BACKUP_DIR}/*/ 2>/dev/null | head -1 | tr -d '\n'")
    if [ -z "$TARGET" ]; then
        echo "错误: 没有可用的备份"
        exit 1
    fi
fi

echo "回滚目标: $TARGET"
echo ""
echo "确认回滚? 这将:"
echo "  1. 停止 questra-search 服务"
echo "  2. 恢复代码 (app/, static/, server.py, requirements.txt)"
echo "  3. 恢复数据库（如果存在对应备份）"
echo "  4. 重启服务并验证健康检查"
echo ""
read -r -p "输入 y 确认: " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "已取消"
    exit 0
fi

echo ""

ssh -o StrictHostKeyChecking=no ${ECS_USER}@${ECS_HOST} "
    set -euo pipefail
    echo '[1/4] 停止服务...'
    systemctl stop questra-search 2>/dev/null || true
    sleep 1

    echo '[2/4] 恢复代码...'
    rm -rf ${REMOTE_DIR}/app ${REMOTE_DIR}/static
    cp -r ${TARGET}/app ${REMOTE_DIR}/app 2>/dev/null || true
    cp -r ${TARGET}/static ${REMOTE_DIR}/static 2>/dev/null || true
    cp ${TARGET}/server.py ${REMOTE_DIR}/ 2>/dev/null || true
    cp ${TARGET}/requirements.txt ${REMOTE_DIR}/ 2>/dev/null || true

    echo '[3/4] 恢复数据库...'
    TIMESTAMP=\$(basename ${TARGET})
    DB_BACKUP=${BACKUP_DIR}/questra_search_db_\${TIMESTAMP}
    if [ -f \"\$DB_BACKUP\" ]; then
        cp \"\$DB_BACKUP\" ${REMOTE_DIR}/data/questra_search.db
        echo '  数据库已恢复'
    else
        echo '  (无对应数据库备份，跳过)'
    fi

    echo '[4/4] 重启服务并验证...'
    systemctl start questra-search
    sleep 3

    if curl -sf http://localhost:8900/api/health > /dev/null 2>&1; then
        echo ''
        echo '============================================'
        echo '  ✅ 回滚成功'
        echo '============================================'
    else
        echo ''
        echo '============================================'
        echo '  ⚠ 警告: 回滚后服务未响应'
        echo '  请手动检查: systemctl status questra-search'
        echo '============================================'
    fi
"
