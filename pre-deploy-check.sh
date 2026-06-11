#!/bin/bash
# ============================================================
# Layer 2: 本地全量部署前验证 (pre-deploy-check)
# 用法: bash pre-deploy-check.sh
# 耗时目标: < 60 秒
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PASS=0
FAIL=0
WARN=0

pass() { echo "    ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "    ✗ $1"; FAIL=$((FAIL + 1)); }
warn() { echo "    ⚠ $1"; WARN=$((WARN + 1)); }

echo ""
echo "============================================"
echo "  Questra-Search 全量部署前验证"
echo "============================================"

# ═══════════════════════════════════════════════
# Step 1: Python 编译检查（全量）
# ═══════════════════════════════════════════════
echo ""
echo "[Step 1/6] Python 编译检查"

for f in $(find app tests -name '*.py' 2>/dev/null); do
    if python3 -m py_compile "$f" 2>/dev/null; then
        pass "$f"
    else
        fail "$f"
    fi
done
for f in server.py init_db.py; do
    if [ -f "$f" ]; then
        python3 -m py_compile "$f" 2>/dev/null && pass "$f" || fail "$f"
    fi
done

# ═══════════════════════════════════════════════
# Step 2: 依赖完整性检查
# ═══════════════════════════════════════════════
echo ""
echo "[Step 2/6] 依赖完整性检查"

DEPS=(
    "fastapi" "uvicorn" "httpx"
    "jose" "passlib" "bcrypt" "dotenv"
    "aiosqlite" "pydantic"
    "markdown_it" "bs4" "lxml"
    "pygments"
)
for pkg in "${DEPS[@]}"; do
    if python3 -c "import $pkg" 2>/dev/null; then
        pass "import $pkg"
    else
        fail "import $pkg (运行 pip install -r requirements.txt)"
    fi
done

# weasyprint 需要系统级依赖（pango/cairo），本地可能不可用，使用警告
if python3 -c "import weasyprint" 2>/dev/null; then
    pass "import weasyprint"
else
    warn "import weasyprint 失败 (需要系统库 pango/cairo，CI 中会自动安装)"
fi

# ═══════════════════════════════════════════════
# Step 3: 应用导入完整性检查
# ═══════════════════════════════════════════════
echo ""
echo "[Step 3/6] 应用导入完整性检查"

MODULES=(
    "app.config" "app.database" "app.models" "app.auth" "app.main"
    "app.routers.auth" "app.routers.chat" "app.routers.export"
    "app.routers.history" "app.routers.pages" "app.routers.sessions"
    "app.services.kb_retry" "app.services.pdf_generator" "app.services.stream_recorder"
)
for mod in "${MODULES[@]}"; do
    if python3 -c "import $mod" 2>/dev/null; then
        pass "$mod"
    else
        fail "$mod"
    fi
done

# ═══════════════════════════════════════════════
# Step 4: pytest 全量测试
# ═══════════════════════════════════════════════
echo ""
echo "[Step 4/6] pytest 全量测试"

if python3 -m pytest tests/ -v --tb=short 2>&1; then
    pass "全部测试通过"
else
    fail "测试失败，请检查上方日志"
fi

# ═══════════════════════════════════════════════
# Step 5: 前端静态文件完整性
# ═══════════════════════════════════════════════
echo ""
echo "[Step 5/6] 前端静态文件完整性"

STATIC_FILES=("static/index.html" "static/app.js" "static/app.css")
for f in "${STATIC_FILES[@]}"; do
    if [ -f "$f" ] && [ -s "$f" ]; then
        SIZE=$(wc -c < "$f" | tr -d ' ')
        pass "$f ($SIZE bytes)"
    else
        fail "$f 缺失或为空"
    fi
done

# HTML 结构检查
if grep -q '</html>' static/index.html 2>/dev/null; then
    pass "HTML 结构完整"
else
    fail "HTML 结构不完整（缺少 </html>）"
fi

# JS 语法检查
if node --check static/app.js 2>/dev/null; then
    pass "JavaScript 语法正确"
else
    warn "JavaScript 语法有问题（node --check 失败）"
fi

# ═══════════════════════════════════════════════
# Step 6: 配置文件检查
# ═══════════════════════════════════════════════
echo ""
echo "[Step 6/6] 配置文件检查"

if [ -f ".env.example" ]; then
    pass ".env.example 存在"
else
    fail ".env.example 缺失"
fi

if [ -f "requirements.txt" ]; then
    pass "requirements.txt 存在"
else
    fail "requirements.txt 缺失"
fi

# 关键配置变量检查
for var in PORT JWT_SECRET DATABASE_PATH MIROMIND_API_KEY; do
    if grep -q "^${var}=" .env.example 2>/dev/null; then
        pass "$var 已配置"
    else
        warn "$var 未在 .env.example 中配置"
    fi
done

# ═══════════════════════════════════════════════
# 汇总报告
# ═══════════════════════════════════════════════
echo ""
echo "============================================"
TOTAL=$((PASS + FAIL + WARN))
echo "  结果: $PASS 通过 / $FAIL 失败 / $WARN 警告 (共 $TOTAL 项)"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "  ❌ 状态: 验证失败"
    echo "  请修复上述 [FAIL] 项后重新运行本脚本"
    echo "============================================"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    echo ""
    echo "  ⚠ 状态: 验证通过（有警告）"
    echo "============================================"
    exit 0
else
    echo ""
    echo "  ✅ 状态: 全部通过，可以部署"
    echo "============================================"
    exit 0
fi
