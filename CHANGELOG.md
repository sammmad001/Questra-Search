# Changelog

All notable changes to Questra-Search are documented in this file.

## [v1.3.0] - 2026-06-12

### Fixed
- 根本性修复流式传输中切换会话消息丢失（v1.2.2 渐进式保存策略已实现但间隔过大+无轮询机制）

### Added
- 后端：渐进式保存频率提升（3事件/2秒双触发），新增活跃流注册表 is_session_streaming()
- 后端：新增 GET /api/sessions/{id}/status 轻量轮询端点，返回流式消息状态+部分内容
- 后端：get_session 自动清理过期 streaming 消息，返回 has_streaming 元数据
- 后端：main.py 新增过期流清理后台任务（每60秒扫描，5分钟超时标记 interrupted）
- 前端：新增 StreamingPoller 模块，切回有流式消息的会话时自动轮询直到完成
- 前端：修复 Chat.send() 与 Sessions.switchTo() 的竞态条件（DOM 操作加会话守卫）
- 前端：addContent() 添加 DOM 存在性检查防止操作已销毁元素
- 前端：流式消息显示蓝色「正在生成中...」动画横幅，中断消息显示橙色横幅

## [v1.2.2] - 2026-06-12

### Fixed
- 修复流式传输中切换会话导致消息丢失（根因：Nginx 代理不传播客户端断开，GeneratorExit 不可靠）：改为渐进式保存策略，流开始即创建 DB 占位，定期 UPDATE，前端缓存破坏

## [v1.2.1] - 2026-06-12

### Fixed
- 修复流式传输中切换会话导致消息丢失：后端捕获 GeneratorExit 保存已累积的部分内容，前端切换前取消活跃流并跟踪流式会话 ID 避免错误重载

## [v1.2.0] - 2026-06-12

### Added
- 修复 GitHub Actions Node.js 20 弃用警告：ssh-agent v0.9.0→v0.10.0，CI/CD 添加 FORCE_JAVASCRIPT_ACTIONS_TO_NODE24

## [v1.1.2] - 2026-06-12

### Fixed
- 修复 CI 后端测试：conftest.py 显式调用 init_db() 确保数据库表在 TestClient 启动前初始化

## [v1.1.1] - 2026-06-12

### Fixed
- 修复 CI 失败：app.js 模板字面量修复 node --check 语法错误；requirements.txt 新增 pyyaml 依赖

## [v1.1.0] - 2026-06-12

### Added
- 修复 .gitignore 缺少 node_modules 排除规则；提交 package.json/package-lock.json 作为 setup-github-secrets.js 的 Node.js 依赖配置

## [v1.0.3] - 2026-06-11

### Fixed
- 修复 chat.py 缺少 await 导致聊天请求返回空内容

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
