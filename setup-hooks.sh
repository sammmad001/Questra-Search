#!/bin/bash
# ============================================================
# setup-hooks.sh — 一键安装 Git Hooks
# 开发环境初始化时运行一次
# 用法: bash setup-hooks.sh
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
GIT_HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "🔧 安装 Git Hooks..."

for hook in pre-commit pre-push; do
    SRC="$REPO_ROOT/hooks/$hook"
    DST="$GIT_HOOKS_DIR/$hook"
    if [ -f "$SRC" ]; then
        cp "$SRC" "$DST"
        chmod +x "$DST"
        echo "  ✓ $hook → .git/hooks/$hook"
    else
        echo "  ⚠ $hook 源文件不存在: $SRC"
    fi
done

echo ""
echo "✅ Git Hooks 安装完成"
echo ""
echo "现在每次 git commit 将自动执行:"
echo "  • Python 编译检查"
echo "  • pytest 快速测试"
echo "  • 静态文件完整性检查"
echo ""
echo "每次 git push 将自动执行:"
echo "  • pre-deploy-check.sh 全量 6 步验证"
