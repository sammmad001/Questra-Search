# Questra-Search

AI 深度研究平台 — 多步推理、联网搜索、流式对话、研究报告自动生成。

## 核心功能

- **流式 AI 对话** — SSE (Server-Sent Events) 实时打字机效果，支持中断/暂停
- **深度研究引擎** — 多轮搜索 + 多步推理，自动探索复杂问题
- **会话管理** — 多会话并行，历史记录持久化
- **研究报告导出** — 一键生成结构化 PDF 报告 (WeasyPrint)，支持 Markdown 表格、代码高亮
- **用户认证** — JWT 认证 + bcrypt 密码哈希 + 邀请码注册
- **多模型支持** — MiroThinker Deep Research（旗舰）& MiroThinker Mini（快速）
- **知识库集成** — 聊天内容自动入库，支持 KB 重试机制
- **数据隔离** — 基于 user_id 的扁平化权限模型

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python 3.11+) |
| 数据库 | SQLite (aiosqlite 异步驱动) |
| 认证 | JWT (python-jose) + bcrypt + HttpOnly Cookie |
| 流式通信 | SSE (Server-Sent Events) |
| PDF 生成 | WeasyPrint + markdown-it-py + Pygments |
| 前端 | 原生 SPA (Vanilla JS + CSS) |
| 部署 | systemd + Nginx 反向代理 + ECS 一键部署脚本 |

## 项目结构

```
.
├── app/
│   ├── main.py              # FastAPI 应用入口 + 生命周期
│   ├── config.py            # .env 集中配置管理
│   ├── auth.py              # JWT + 密码验证工具
│   ├── database.py          # SQLite 初始化 + 连接管理
│   ├── models.py            # Pydantic 请求/响应模型
│   ├── routers/
│   │   ├── auth.py          # 登录/注册/账户管理/邀请码
│   │   ├── chat.py          # SSE 流式对话 + MiroThinker API
│   │   ├── sessions.py      # 会话 CRUD
│   │   ├── history.py       # 聊天历史查询
│   │   ├── export.py        # PDF 导出
│   │   └── pages.py         # SPA 页面路由
│   └── services/
│       ├── pdf_generator.py  # WeasyPrint PDF 渲染引擎
│       ├── stream_recorder.py # SSE 流录制 + 知识库导入
│       └── kb_retry.py       # 知识库重试调度器
├── static/
│   ├── index.html           # 前端 SPA
│   ├── app.js               # 前端逻辑 (Auth, Chat, Export)
│   └── app.css              # 样式
├── deploy.sh                # 一键部署到 ECS
├── requirements.txt         # Python 依赖
└── init_db.py               # 独立数据库初始化脚本
```

## 快速开始

### 环境要求

- Python 3.11+
- 系统依赖（WeasyPrint）：`pango`, `gdk-pixbuf`, `cairo`

```bash
# macOS
brew install pango gdk-pixbuf cairo

# Ubuntu/Debian
sudo apt install libpango-1.0-0 libgdk-pixbuf2.0-0 libcairo2
```

### 本地开发

```bash
# 1. 克隆仓库
git clone https://github.com/sammmad001/Questra-Search.git
cd Questra-Search

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 MIROMIND_API_KEY

# 5. 初始化数据库
python init_db.py

# 6. 启动服务
python server.py
# 访问 http://localhost:8900/miro/
```

### 生产部署

```bash
# 一键部署到 ECS (43.106.12.79)
./deploy.sh

# 跳过备份（首次部署）
./deploy.sh --skip-backup
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MIROMIND_API_BASE` | 上游 API 地址 | `https://api.miromind.ai/v1` |
| `MIROMIND_API_KEY` | 上游 API 密钥 | (必填) |
| `DEFAULT_MODEL` | 默认模型 | `mirothinker-1-7-deepresearch` |
| `PORT` | 服务端口 | `8900` |
| `BASE_PATH` | 路由前缀 | `/miro` |
| `REQUEST_TIMEOUT` | 请求超时(秒) | `300` |
| `JWT_SECRET` | JWT 签名密钥 | (部署时自动生成) |
| `JWT_EXPIRE_HOURS` | JWT 过期时间 | `168` |
| `COOKIE_SECURE` | Cookie Secure 标志 | `false` |
| `KB_API_BASE` | 知识库 API 地址 | `http://localhost:8080` |
| `KB_API_TOKEN` | 知识库认证令牌 | (可选) |
| `KB_AUTO_INGEST` | 自动导入知识库 | `true` |

## API 端点

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/miro/api/health` | 健康检查 | 无 |
| `POST` | `/miro/api/auth/register` | 用户注册（需邀请码） | 无 |
| `POST` | `/miro/api/auth/login` | 用户登录 | 无 |
| `POST` | `/miro/api/auth/logout` | 登出 | Cookie |
| `GET` | `/miro/api/auth/me` | 当前用户信息 | Bearer/Cookie |
| `GET` | `/miro/api/sessions` | 会话列表 | Bearer/Cookie |
| `POST` | `/miro/api/sessions` | 创建会话 | Bearer/Cookie |
| `DELETE` | `/miro/api/sessions/{id}` | 删除会话 | Bearer/Cookie |
| `POST` | `/miro/api/chat` | SSE 流式对话 | Bearer/Cookie |
| `GET` | `/miro/api/history` | 聊天历史 | Bearer/Cookie |
| `POST` | `/miro/api/export/pdf` | 导出 PDF 报告 | Bearer/Cookie |

## 设计文档

- [国内双域名访问架构方案](domestic-access-architecture.md)
- [飞书 Bot 集成方案](feishu-integration-plan.md)
- [前端现代化改造方案](frontend-modernization-plan.md)
- [移动端适配方案](mobile-web-adaptation-plan.md)
- [知识库集成方案](questra-search-kb-integration/Questra-Search集成方案文档.md)

## 独立子项目

- `questra-search-kb-integration/` — 个人知识库集成（KB ingest + 自动入库）
- `训练任务/` — ETF 策略 ML 训练系统（传统策略 vs ML 策略对比）

## License

MIT
