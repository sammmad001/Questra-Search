#!/bin/bash
# ============================================================
# Questra-Search 生产环境部署脚本
# 用法: ./deploy.sh [--skip-backup]
# ============================================================
set -euo pipefail

# ---------- 配置 ----------
ECS_HOST="43.106.12.79"
ECS_USER="root"
REMOTE_DIR="/opt/questra-search"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="/opt/questra-search-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SKIP_BACKUP=false

# 解析参数
for arg in "$@"; do
    case $arg in
        --skip-backup) SKIP_BACKUP=true ;;
    esac
done

echo "============================================"
echo "  Questra-Search 生产环境部署"
echo "  目标: $ECS_USER@$ECS_HOST:$REMOTE_DIR"
echo "  时间: $TIMESTAMP"
echo "============================================"

SSH="ssh -T -o StrictHostKeyChecking=no $ECS_USER@$ECS_HOST"

# ============================================================
# 第一步: 上传文件到 ECS 临时目录
# ============================================================
echo ""
echo "[1/7] 上传文件到 ECS..."

$SSH "mkdir -p /tmp/questra-search-deploy"

# 使用 rsync 增量传输
rsync -az --delete \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude '*.pyc' \
    --exclude '*.db' \
    --exclude 'data/' \
    "$LOCAL_DIR/app/" \
    $ECS_USER@$ECS_HOST:/tmp/questra-search-deploy/app/

rsync -az \
    "$LOCAL_DIR/static/" \
    $ECS_USER@$ECS_HOST:/tmp/questra-search-deploy/static/

rsync -az \
    "$LOCAL_DIR/server.py" \
    "$LOCAL_DIR/init_db.py" \
    "$LOCAL_DIR/requirements.txt" \
    $ECS_USER@$ECS_HOST:/tmp/questra-search-deploy/

# 上传 .env.example
if [ -f "$LOCAL_DIR/.env.example" ]; then
    rsync -az "$LOCAL_DIR/.env.example" $ECS_USER@$ECS_HOST:/tmp/questra-search-deploy/
fi

echo "  文件上传完成"

# ============================================================
# 第二步: 上传远程执行脚本
# ============================================================
echo ""
echo "[2/7] 生成远程部署脚本..."

# 将远程执行逻辑写入临时脚本并上传
REMOTE_SCRIPT=$(mktemp /tmp/questra-search-remote-XXXXXX.sh)
cat > "$REMOTE_SCRIPT" << 'REMOTE_SCRIPT'
#!/bin/bash
set -euo pipefail

REMOTE_DIR="__REMOTE_DIR__"
BACKUP_DIR="__BACKUP_DIR__"
TIMESTAMP="__TIMESTAMP__"
SKIP_BACKUP="__SKIP_BACKUP__"

# --- 备份当前版本 ---
mkdir -p $REMOTE_DIR/data $REMOTE_DIR/static $BACKUP_DIR

if [ -d "$REMOTE_DIR/app" ] && [ "$SKIP_BACKUP" != "true" ]; then
    echo "  备份当前版本到 $BACKUP_DIR/$TIMESTAMP ..."
    mkdir -p $BACKUP_DIR/$TIMESTAMP
    cp -r $REMOTE_DIR/app $BACKUP_DIR/$TIMESTAMP/ 2>/dev/null || true
    cp -r $REMOTE_DIR/static $BACKUP_DIR/$TIMESTAMP/ 2>/dev/null || true
    cp $REMOTE_DIR/server.py $BACKUP_DIR/$TIMESTAMP/ 2>/dev/null || true
    cp $REMOTE_DIR/requirements.txt $BACKUP_DIR/$TIMESTAMP/ 2>/dev/null || true
    cp $REMOTE_DIR/init_db.py $BACKUP_DIR/$TIMESTAMP/ 2>/dev/null || true

    if [ -f "$REMOTE_DIR/data/questra_search.db" ]; then
        sqlite3 "$REMOTE_DIR/data/questra_search.db" ".backup $BACKUP_DIR/questra_search_db_$TIMESTAMP" 2>/dev/null || true
        echo "  数据库已备份"
    fi
    echo "  备份完成"
else
    echo "  跳过备份"
fi

# --- 部署文件 ---
echo "  部署新文件..."
rm -rf $REMOTE_DIR/app
cp -r /tmp/questra-search-deploy/app $REMOTE_DIR/
rm -rf $REMOTE_DIR/static/*
cp -r /tmp/questra-search-deploy/static/* $REMOTE_DIR/static/
cp /tmp/questra-search-deploy/server.py $REMOTE_DIR/
cp /tmp/questra-search-deploy/init_db.py $REMOTE_DIR/
cp /tmp/questra-search-deploy/requirements.txt $REMOTE_DIR/
cp /tmp/questra-search-deploy/.env.example $REMOTE_DIR/ 2>/dev/null || true

# .env 配置管理
if [ ! -f $REMOTE_DIR/.env ]; then
    echo "  首次部署: 创建 .env（自动生成 JWT_SECRET）"
    if [ -f /tmp/questra-search-deploy/.env.example ]; then
        cp /tmp/questra-search-deploy/.env.example $REMOTE_DIR/.env
    else
        cat > $REMOTE_DIR/.env << 'ENVFILE'
MIROMIND_API_BASE=https://api.miromind.ai/v1
MIROMIND_API_KEY=CHANGE_ME
DEFAULT_MODEL=mirothinker-1-7-deepresearch
PORT=8900
REQUEST_TIMEOUT=300
BASE_PATH=/miro
JWT_SECRET=CHANGE_ME
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=168
COOKIE_SECURE=false
DATABASE_PATH=data/questra_search.db

# ── 个人知识库集成 ──
# KB_API_BASE: 知识库 API 地址（需根据实际部署调整）
KB_API_BASE=http://localhost:8080
# KB_API_TOKEN: 知识库 API 认证令牌（需与 KB 侧 KNOWLEDGE_API_TOKEN 一致）
KB_API_TOKEN=
# KB_AUTO_INGEST: 是否自动导入聊天内容到知识库（true/false）
KB_AUTO_INGEST=true
ENVFILE
    fi
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" $REMOTE_DIR/.env
    echo ""
    echo "  !! 重要: 请手动设置 MIROMIND_API_KEY !!"
    echo "  执行: vi $REMOTE_DIR/.env"
    echo "  然后重启: systemctl restart questra-search"
    echo ""
else
    echo "  .env 已存在，保留生产配置"
    grep -q "COOKIE_SECURE" $REMOTE_DIR/.env || echo "COOKIE_SECURE=false" >> $REMOTE_DIR/.env
fi

# 清理临时文件
rm -rf /tmp/questra-search-deploy

# 文件权限
chmod 600 $REMOTE_DIR/.env
chmod 700 $REMOTE_DIR/data
chown -R root:root $REMOTE_DIR/

echo "  文件安装完成"

# --- Python 虚拟环境 ---
echo ""
echo "[3/7] 安装 Python 依赖..."
cd $REMOTE_DIR

if [ ! -d "venv" ]; then
    echo "  创建 Python 虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate
# 升级 pip（避免 pip 23.x 的 urllib3 兼容性 bug）
pip install --upgrade pip 2>/dev/null
# 安装系统依赖（WeasyPrint 需要 pango/cairo，CJK 字体解决中文 PDF 乱码）
dnf install -y pango cairo-devel gdk-pixbuf2-devel libffi-devel shared-mime-info google-noto-sans-cjk-ttc-fonts 2>/dev/null || \
apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info fonts-noto-cjk 2>/dev/null || true
# 安装 Python 依赖
pip install -r requirements.txt

echo "  依赖安装完成"

# --- 数据库 ---
echo ""
echo "[4/7] 数据库初始化/迁移..."

if [ ! -f "$REMOTE_DIR/data/questra_search.db" ]; then
    echo "  首次初始化数据库..."
    python init_db.py
else
    echo "  数据库已存在，应用启动时自动迁移"
fi

echo "  数据库就绪"

# --- systemd ---
echo ""
echo "[5/7] 配置 systemd 服务..."

cat > /etc/systemd/system/questra-search.service << 'SERVICE'
[Unit]
Description=Questra-Search API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/questra-search
Environment=PATH=/opt/questra-search/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/opt/questra-search/venv/bin/python /opt/questra-search/server.py
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

LimitNOFILE=65536
MemoryMax=512M

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERVICE

# 日志轮转
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/questra-search.conf << 'JOURNALD'
[Journal]
SystemMaxUse=500M
SystemMaxFileSize=50M
MaxRetentionSec=30day
JOURNALD

systemctl daemon-reload
systemctl enable questra-search
systemctl restart questra-search

echo "  systemd 服务已配置"

# --- Nginx ---
echo ""
echo "[6/7] 配置 Nginx..."

if ! command -v nginx &> /dev/null; then
    echo "  Nginx 未安装，跳过"
else
    # --- Cloudflare Real IP 恢复 ---
    # 写入 Cloudflare IP 段到独立配置
    cat > /etc/nginx/conf.d/cloudflare-realip.conf << 'REALIP'
# Cloudflare IPv4
set_real_ip_from 173.245.48.0/20;
set_real_ip_from 103.21.244.0/22;
set_real_ip_from 103.22.200.0/22;
set_real_ip_from 103.31.4.0/22;
set_real_ip_from 141.101.64.0/18;
set_real_ip_from 108.162.192.0/18;
set_real_ip_from 190.93.240.0/20;
set_real_ip_from 188.114.96.0/20;
set_real_ip_from 197.234.240.0/22;
set_real_ip_from 198.41.128.0/17;
set_real_ip_from 162.158.0.0/15;
set_real_ip_from 104.16.0.0/13;
set_real_ip_from 104.24.0.0/14;
set_real_ip_from 172.64.0.0/13;
set_real_ip_from 131.0.72.0/22;
# Cloudflare IPv6
set_real_ip_from 2400:cb00::/32;
set_real_ip_from 2606:4700::/32;
set_real_ip_from 2803:f800::/32;
set_real_ip_from 2405:b500::/32;
set_real_ip_from 2405:8100::/32;
set_real_ip_from 2a06:98c0::/29;
set_real_ip_from 2c0f:f248::/32;
real_ip_header CF-Connecting-IP;
REALIP

    # --- Questra-Search 主配置 ---
    cat > /etc/nginx/conf.d/questra-search.conf << 'NGINX'
upstream questra_search_backend {
    server 127.0.0.1:8900;
    keepalive 32;
}

# ============================================================
# 域名访问: mmaoresearch.com (Cloudflare CDN -> ECS)
# ============================================================
server {
    listen 80;
    server_name mmaoresearch.com www.mmaoresearch.com;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # 根路径重定向到 /miro/
    location = / {
        return 302 /miro/;
    }

    # SSE 流式聊天 (关键: 无缓冲)
    location /miro/api/chat {
        proxy_pass http://questra_search_backend/api/chat;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        chunked_transfer_encoding on;
        add_header Cache-Control "no-cache, no-store" always;
        add_header X-Accel-Buffering no always;
    }

    # 主应用
    location /miro/ {
        proxy_pass http://questra_search_backend/;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 360s;
        proxy_send_timeout 360s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
    }

    # 静态文件 (Cloudflare 边缘缓存)
    location /miro/static/ {
        proxy_pass http://questra_search_backend/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # 健康检查
    location /miro/api/health {
        proxy_pass http://questra_search_backend/api/health;
        access_log off;
    }

    # Cloudflare 健康检查端点
    location /health {
        proxy_pass http://questra_search_backend/api/health;
        access_log off;
    }

    location / { return 404; }
}

# ============================================================
# IP 直连: 43.106.12.79 (海外用户)
# ============================================================
server {
    listen 80;
    server_name 43.106.12.79;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location /miro/api/chat {
        proxy_pass http://questra_search_backend/api/chat;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection "";
        chunked_transfer_encoding on;
    }

    location /miro/ {
        proxy_pass http://questra_search_backend/;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 360s;
        proxy_send_timeout 360s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection "";
    }

    location /miro/static/ {
        proxy_pass http://questra_search_backend/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location /miro/api/health {
        proxy_pass http://questra_search_backend/api/health;
        access_log off;
    }

    location / {
        return 404;
    }
}
NGINX

    if nginx -t 2>/dev/null; then
        systemctl reload nginx
        echo "  Nginx 配置已更新"
    else
        echo "  [WARN] Nginx 配置测试失败，请手动检查: nginx -t"
    fi
fi

# --- 验证 ---
echo ""
echo "[7/7] 验证部署..."
sleep 3

FAILED=false

if curl -sf http://localhost:8900/api/health > /dev/null 2>&1; then
    echo "  [OK] FastAPI 服务正常"
    curl -s http://localhost:8900/api/health
else
    echo "  [FAIL] FastAPI 服务异常"
    journalctl -u questra-search -n 30 --no-pager 2>/dev/null || true
    FAILED=true
fi

if command -v nginx &> /dev/null; then
    if curl -sf http://localhost/miro/api/health > /dev/null 2>&1; then
        echo "  [OK] Nginx 代理正常"
    else
        echo "  [FAIL] Nginx 代理异常"
        FAILED=true
    fi
fi

if [ -f "$REMOTE_DIR/data/questra_search.db" ]; then
    TABLE_COUNT=$(sqlite3 "$REMOTE_DIR/data/questra_search.db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "?")
    echo "  [OK] 数据库存在, $TABLE_COUNT 张表"
    CODE_COUNT=$(sqlite3 "$REMOTE_DIR/data/questra_search.db" "SELECT COUNT(*) FROM invite_codes WHERE used_by IS NULL;" 2>/dev/null || echo "?")
    echo "  [INFO] 可用邀请码: $CODE_COUNT 个"
else
    echo "  [FAIL] 数据库不存在"
    FAILED=true
fi

echo ""
if [ "$FAILED" = true ]; then
    echo "============================================"
    echo "  部署完成（存在问题，请检查上方日志）"
    echo "============================================"
else
    echo "=========================================="
    echo "  部署成功!"
    echo "  IP 直连:  http://43.106.12.79/miro/"
    echo "  域名访问: https://mmaoresearch.com/miro/ (需先配置 Cloudflare)"
    echo "=========================================="
fi
REMOTE_SCRIPT

# 替换占位符
sed -i '' "s|__REMOTE_DIR__|$REMOTE_DIR|g" "$REMOTE_SCRIPT"
sed -i '' "s|__BACKUP_DIR__|$BACKUP_DIR|g" "$REMOTE_SCRIPT"
sed -i '' "s|__TIMESTAMP__|$TIMESTAMP|g" "$REMOTE_SCRIPT"
sed -i '' "s|__SKIP_BACKUP__|$SKIP_BACKUP|g" "$REMOTE_SCRIPT"

# 上传并执行远程脚本
echo "  上传远程脚本..."
scp -o StrictHostKeyChecking=no -q "$REMOTE_SCRIPT" $ECS_USER@$ECS_HOST:/tmp/questra-search-remote-deploy.sh
rm -f "$REMOTE_SCRIPT"

echo "  执行远程部署..."
$SSH "bash /tmp/questra-search-remote-deploy.sh && rm -f /tmp/questra-search-remote-deploy.sh"

echo ""
echo "=== 部署流程结束 ==="
echo ""
echo "常用命令:"
echo "  查看日志: ssh $ECS_USER@$ECS_HOST 'journalctl -u questra-search -f'"
echo "  重启服务: ssh $ECS_USER@$ECS_HOST 'systemctl restart questra-search'"
echo "  服务状态: ssh $ECS_USER@$ECS_HOST 'systemctl status questra-search'"
echo "  查看邀请码: ssh $ECS_USER@$ECS_HOST 'sqlite3 /opt/questra-search/data/questra_search.db \"SELECT code FROM invite_codes WHERE used_by IS NULL;\"'"
echo "  编辑配置: ssh $ECS_USER@$ECS_HOST 'vi /opt/questra-search/.env'"
echo "  Nginx 测试: ssh $ECS_USER@$ECS_HOST 'nginx -t && systemctl reload nginx'"
echo "  Cloudflare 配置参考: cat domestic-access-architecture.md"
