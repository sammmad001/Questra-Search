# Questra-Search V3 国内用户双域名访问架构方案

## 概述

设计国内用户通过 `mmaoresearch.com` 访问 Questra-Search 服务的技术方案，解决国内用户直连新加坡 ECS (43.106.12.79) 的延迟和不稳定问题。

---

## 一、架构总览

```
国内用户                海外用户
   │                      │
   ▼                      ▼
mmaoresearch.com        43.106.12.79/miro/
   │                      │
   ▼                      ▼
┌──────────┐          ┌──────────────┐
│  DNS 智能解析          │   直连 ECS    │
│  (DNSPod/阿里云)       │              │
└─────┬────┘          └──────────────┘
      │
      ├─ 未备案路线 ──→ Cloudflare CDN (香港/日本节点)
      │                   │ 回源
      │                   ▼
      │              新加坡 ECS (43.106.12.79)
      │
      └─ 已备案路线 ──→ 国内 CDN (阿里云/腾讯云)
                          │ 回源 (跨境专线/公网)
                          ▼
                     新加坡 ECS (43.106.12.79)
```

---

## 二、方案对比

| 维度 | 方案 A: Cloudflare (免备案) | 方案 B: 国内 CDN (需备案) |
|------|---------------------------|--------------------------|
| **ICP 备案** | 不需要 | 必须备案（约 2-4 周） |
| **国内延迟** | 50-100ms（经香港节点） | 20-50ms（国内边缘节点） |
| **静态加速** | 香港/日本节点缓存 | 全国 2000+ 节点 |
| **SSE 流式** | Cloudflare 透传（需配置） | 回源长连接（需配置） |
| **HTTPS** | Cloudflare 免费证书 | CDN 免费证书 |
| **成本** | 免费（Free 计划） | 按流量计费（低用量便宜） |
| **稳定性** | 依赖 Cloudflare 香港节点 | 高（国内骨干网） |
| **DDoS 防护** | Cloudflare 内置 | CDN 厂商提供 |

**推荐：先使用方案 A（Cloudflare 免备案方案）快速上线，后续如需更低延迟再走备案流程切换方案 B。**

---

## 三、方案 A：Cloudflare 免备案方案（推荐先实施）

### 3.1 架构细节

```
国内用户 → mmaoresearch.com
             │
             ▼
     Cloudflare DNS (Anycast)
             │
             ▼
     Cloudflare 香港边缘节点
     ├── 静态资源（HTML/CSS/JS）→ Cloudflare Cache (命中率 ~90%)
     └── API/SSE 请求 → 回源 → 新加坡 ECS (43.106.12.79)
```

### 3.2 Cloudflare 配置步骤

**第 1 步：域名接入 Cloudflare**
1. 在 Cloudflare 添加 `mmaoresearch.com`
2. 在域名注册商修改 NS 记录指向 Cloudflare NS
3. 等待 DNS 传播（通常 < 24h）

**第 2 步：DNS 记录配置**
```
类型    名称           内容                    代理状态
A       mmaoresearch.com  →  43.106.12.79     ☁️ Proxied (橙色云)
A       www              →  43.106.12.79     ☁️ Proxied
```

**第 3 步：SSL/TLS 设置**
- SSL 模式：`Full (Strict)`（ECS 需配置证书）或 `Flexible`（先用）
- 最低 TLS 版本：TLS 1.2
- 始终使用 HTTPS：开启

**第 4 步：缓存规则**

Page Rules:
```
*mmaoresearch.com/miro/static/*
  - Cache Level: Cache Everything
  - Edge Cache TTL: 7 days
  - Browser Cache TTL: 1 day

*mmaoresearch.com/miro/api/chat
  - Cache Level: Bypass
  - Disable Performance (关闭 Rocket Loader/Minification)

*mmaoresearch.com/miro/api/*
  - Cache Level: Bypass
```

**第 5 步：SSE 支持配置**

Cloudflare 默认缓冲响应，SSE 必须关闭缓冲：

方案一：通过 HTTP Header（推荐）
```nginx
# ECS Nginx 配置新增
location /miro/api/chat {
    add_header X-Accel-Buffering no;
    proxy_http_version 1.1;
    proxy_buffering off;
    # Cloudflare 识别此 header 自动禁用缓冲
    add_header Cache-Control "no-cache, no-store";
}
```

方案二：Cloudflare Transform Rules
- 创建 Response Header 修改规则
- 对 `/miro/api/chat` 路径添加 `Cache-Control: no-cache`

### 3.3 Nginx 配置更新 (ECS)

```nginx
# /etc/nginx/conf.d/questra-search.conf

# 新增：国内域名 server block
server {
    listen 80;
    server_name mmaoresearch.com www.mmaoresearch.com;

    # 安全头
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # SSE 流式聊天
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
        # Cloudflare SSE 支持
        add_header Cache-Control "no-cache, no-store" always;
        add_header X-Accel-Buffering no always;
    }

    # 主应用
    location /miro/ {
        proxy_pass http://questra_search_backend/;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 360s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
    }

    # 静态文件缓存
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

    # 根路径重定向到 /miro/
    location = / {
        return 302 /miro/;
    }

    location / { return 404; }
}
```

### 3.4 前端适配（可选）

如果希望通过国内域名直接访问（无需 /miro/ 前缀），可在 Nginx 添加：

```nginx
server {
    listen 80;
    server_name mmaoresearch.com;

    # 根路径直接服务 Questra-Search
    location / {
        proxy_pass http://questra_search_backend/;
        ...
    }

    # API 和静态文件同上
}
```

这样国内用户访问 `https://mmaoresearch.com/` 即可直接使用。

---

## 四、方案 B：国内 CDN 加速（需 ICP 备案）

### 4.1 前置条件

- `mmaoresearch.com` 完成 ICP 备案（约 2-4 周）
- 如使用阿里云 CDN，域名需在阿里云备案
- 服务器源站位于海外（新加坡 ECS）

### 4.2 架构

```
国内用户 → mmaoresearch.com
             │
             ▼
     智能DNS (DNSPod/阿里云解析)
     ├── 国内 IP → 国内 CDN (阿里云/腾讯云)
     │              ├── 静态资源 → 边缘节点缓存
     │              └── API/SSE → 回源 → 新加坡 ECS
     └── 海外 IP → 直连新加坡 ECS
```

### 4.3 CDN 配置要点

**静态资源加速：**
- 加速域名：`mmaoresearch.com`
- 源站：`43.106.12.79`（公网 IP）
- 回源协议：HTTP（或 HTTPS 如已配置）
- 缓存策略：
  - `/miro/static/*` → 缓存 7 天
  - `/miro/*.html` → 缓存 1 天
  - `/miro/api/*` → 不缓存

**SSE 流式支持：**
- API 路径需关闭响应缓冲
- 设置回源超时 ≥ 300 秒
- 阿里云 CDN：开启「回源跟随」+「SSE/长连接支持」

### 4.4 HTTPS 配置

```nginx
# ECS Nginx 添加 HTTPS 支持
server {
    listen 443 ssl http2;
    server_name mmaoresearch.com;

    ssl_certificate /etc/nginx/ssl/mmaoresearch.com.pem;
    ssl_certificate_key /etc/nginx/ssl/mmaoresearch.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    # ... 其余 proxy 配置同上
}
```

可用 Let's Encrypt 免费证书 + certbot 自动续期。

---

## 五、网络稳定性优化

### 5.1 跨境连接保障

| 措施 | 说明 |
|------|------|
| Cloudflare Railgun | 压缩+增量传输，减少跨境数据量（Business 计划） |
| Cloudflare Argo Smart Routing | 智能路由选择最优路径（付费） |
| 连接重试 | 前端 SSE 断线自动重连（3 次，指数退避） |
| 超时配置 | Nginx proxy_read_timeout 600s 匹配 API 300s 超时 |

### 5.2 前端网络容错

```javascript
// SSE 断线重连
const MAX_RETRIES = 3;
const RETRY_DELAYS = [2000, 5000, 10000]; // 指数退避

async function sendWithRetry(message, retries = 0) {
    try {
        await Chat.send(message);
    } catch(e) {
        if (retries < MAX_RETRIES) {
            UI.toast(`连接中断，${RETRY_DELAYS[retries]/1000}s 后重试...`, 'error');
            await new Promise(r => setTimeout(r, RETRY_DELAYS[retries]));
            return sendWithRetry(message, retries + 1);
        }
        UI.toast('连接失败，请检查网络后重试', 'error');
    }
}
```

### 5.3 静态资源优化

```
                    用户首次访问
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    index.html      app.css        app.js
    (CDN 缓存 1d)  (CDN 缓存 7d)  (CDN 缓存 7d)
         │              │              │
         └──────────────┼──────────────┘
                        ▼
                  marked.min.js
                  (jsDelivr CDN，国内镜像)
```

- `marked.js` 使用 jsDelivr CDN（有国内节点 mirror）
- 或改用 `cdn.staticfile.org`（七牛云国内 CDN）
- HTML/CSS/JS 通过 Cloudflare CDN 缓存，二次访问命中边缘节点

---

## 六、双域名最终配置

| 域名 | 用途 | 指向 | CDN |
|------|------|------|-----|
| `43.106.12.79/miro/` | 海外直连 | ECS 直接访问 | 无 |
| `mmaoresearch.com` | 国内入口 | Cloudflare → ECS | Cloudflare Free |

**前端无需改动**：`app.js` 使用 `basePath` 变量（`window.__BASE_PATH__ || ''`），两个域名都能正常工作。

**Nginx 同时服务两个域名**：同一个 `questra_search_backend` upstream，两个 server block。

---

## 七、实施步骤（方案 A - Cloudflare）

| 步骤 | 操作 | 时间 |
|------|------|------|
| 1 | 在 Cloudflare 添加 `mmaoresearch.com` | 10 min |
| 2 | 修改域名 NS 记录指向 Cloudflare | 5 min |
| 3 | 配置 DNS A 记录 → 43.106.12.79 (Proxied) | 5 min |
| 4 | 部署 Nginx 双域名配置（deploy.sh 已更新） | 15 min |
| 5 | Cloudflare 配置 SSL + Cache Rules + SSE bypass | 15 min |
| 6 | 验证：国内访问 https://mmaoresearch.com | 10 min |
| **总计** | | **~1h** |

### 7.1 步骤 1: Cloudflare 添加站点

1. 访问 https://dash.cloudflare.com
2. 点击 **Add a site**
3. 输入 `mmaoresearch.com`
4. 选择 **Free** 计划
5. Cloudflare 会扫描现有 DNS 记录

### 7.2 步骤 2: 修改域名 NS 记录

1. Cloudflare 会分配两个 NS 服务器，例如：
   - `xxx.ns.cloudflare.com`
   - `yyy.ns.cloudflare.com`
2. 前往域名注册商控制台
3. 找到 mmaoresearch.com 的 **Nameserver** 设置
4. 将默认 NS 改为 Cloudflare 提供的两个 NS
5. 等待 DNS 传播（通常 1-24 小时）
6. Cloudflare 控制台会显示 **Status: Active** 表示生效

### 7.3 步骤 3: DNS 记录配置

在 Cloudflare DNS 管理页添加：

```
类型    名称              内容               代理状态
A       mmaoresearch.com  43.106.12.79      ☁️ Proxied (橙色云朵)
A       www               43.106.12.79      ☁️ Proxied (橙色云朵)
```

> **重要**: 必须开启 Proxy（橙色云朵），灰色云朵是 DNS Only 不经过 CDN。

### 7.4 步骤 4: 部署 Nginx 双域名配置

已在 `deploy.sh` 中自动配置，执行部署即可：

```bash
# 从本地执行部署
./deploy.sh
```

部署后 Nginx 配置包含：
- `mmaoresearch.com` server block → 根路径重定向到 /miro/ + SSE 无缓冲
- `43.106.12.79` server block → 原有 IP 直连（不变）
- `cloudflare-realip.conf` → Cloudflare IP 段的真实 IP 恢复

手动验证 Nginx 配置：
```bash
ssh root@43.106.12.79 'nginx -t && systemctl reload nginx'
```

### 7.5 步骤 5: Cloudflare SSL 和缓存配置

#### SSL/TLS 设置
1. Cloudflare 控制台 → **SSL/TLS** → **Overview**
2. 选择 **Flexible**（Cloudflare → ECS 走 HTTP，浏览器 → Cloudflare 走 HTTPS）
3. **Always Use HTTPS**: 开启
4. **Automatic HTTPS Rewrites**: 开启
5. **Minimum TLS Version**: TLS 1.2

#### 缓存规则 (Page Rules)

Cloudflare 控制台 → **Rules** → **Page Rules** → **Create Page Rule**

**规则 1: 静态资源缓存**
```
URL: *mmaoresearch.com/miro/static/*
设置:
  - Cache Level: Cache Everything
  - Edge Cache TTL: a month
  - Browser Cache TTL: a day
```

**规则 2: SSE 流式接口不缓存**
```
URL: *mmaoresearch.com/miro/api/chat*
设置:
  - Cache Level: Bypass
```

**规则 3: API 不缓存**
```
URL: *mmaoresearch.com/miro/api/*
设置:
  - Cache Level: Bypass
```

#### 缓存规则 (Cache Rules) — 推荐

如果账户支持 Cache Rules（新方式），优先使用：

1. Cloudflare 控制台 → **Caching** → **Cache Rules** → **Create rule**
2. 规则名: `Static assets cache`
   - 条件: URI Path starts with `/miro/static/`
   - 操作: Edge TTL = 30 days, Browser TTL = 1 day
3. 规则名: `SSE no cache`
   - 条件: URI Path contains `/miro/api/chat`
   - 操作: Cache status = Bypass

### 7.6 步骤 6: 验证

```bash
# 1. 检查域名是否指向 Cloudflare
dig mmaoresearch.com
# 应看到 Cloudflare IP (104.x.x.x 或 172.x.x.x)

# 2. 检查 HTTPS 是否生效
curl -I https://mmaoresearch.com/miro/api/health
# 应返回 200 + cf-cache-status header

# 3. 检查 SSE 流式（登录后测试）
curl -N https://mmaoresearch.com/miro/api/chat \
  -H "Content-Type: application/json" \
  -H "Cookie: questra_search_token=YOUR_TOKEN" \
  -d '{"message":"hello","model":"mirothinker-1-7-deepresearch"}'
# 应看到流式输出，无缓冲延迟

# 4. IP 直连仍正常
curl http://43.106.12.79/miro/api/health
```

### 验证清单

```
□ https://mmaoresearch.com 可访问（Cloudflare 证书生效）
□ 静态资源通过 CDN 缓存（检查 CF-Cache-Status: HIT）
□ SSE 流式响应正常（非缓冲）
□ 登录/注册/聊天功能正常
□ Cookie 跨子路径正确设置
□ 移动端通过国内域名访问正常
□ 原始 IP 43.106.12.79/miro/ 仍可访问
□ Cloudflare Analytics 显示国内流量
□ Cloudflare Real IP 恢复（Nginx 日志显示真实客户端 IP）
```

---

## 八、后续优化（可选）

| 优化 | 收益 | 条件 |
|------|------|------|
| Cloudflare Argo | 减少 30% 延迟 | $5/月 |
| ICP 备案 + 国内 CDN | 延迟降至 20-50ms | 备案完成 |
| WebSocket 端点 | 更稳定的流式体验 | 前端改造 |
| 域名级别 A/B 测试 | 灰度发布 | 两个域名都配置 |
