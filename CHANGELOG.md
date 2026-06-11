# Changelog

All notable changes to Questra-Search are documented in this file.

## [v1.0.2] - 2026-06-10

### Changed
- 更新 KB 集成方案文档：`get_db().__anext__()` → `aiosqlite.connect()`，与 v1.0.1 代码对齐
- 本地 `.env` 补齐 `BASE_PATH=/miro` 和 `COOKIE_SECURE=false`
- deploy.sh 新增 `--rollback` 参数说明

### Fixed
- 审计确认 `.env` API Key 从未泄露到 Git 历史

## [v1.0.1] - 2026-06-09

### Fixed
- `stream_recorder.py`：KB 入库成功后标记 `kb_sent=1`，避免 `kb_retry` 重复发送
- `main.py`：修复 lifespan `get_db()` generator 资源泄漏，改用直接 `aiosqlite.connect()`

### Changed
- `deploy.sh`：首次部署 `.env` 模板补充 `KB_API_BASE`/`KB_API_TOKEN`/`KB_AUTO_INGEST` 三项
- ECS Nginx：删除旧 `miromind.conf`（冲突 upstream），统一 `questra-search.conf`

## [v1.0.0] - 2026-06-09

### Added
- 品牌重命名: MiroMind → Questra-Search（28 个文件，~150 处修改）
- 完整 FastAPI 后端 + 前端 SPA
- SSE 流式 AI 对话（MiroThinker Deep Research / Mini）
- JWT 认证 + bcrypt 密码哈希 + 邀请码注册
- PDF 研究报告导出 (WeasyPrint + markdown-it-py + Pygments)
- 知识库集成：fire-and-forget 异步入库 + 定时重试调度器
- 会话管理（CRUD + 软删除）
- 账户管理（资料编辑、密码修改、邀请码生成）
- ECS 一键部署脚本（systemd + Nginx + Cloudflare）
- `deploy.sh` — 7 步自动化部署（备份 → 上传 → 依赖 → DB → systemd → Nginx → 验证）
- `README.md` — 完整项目文档
