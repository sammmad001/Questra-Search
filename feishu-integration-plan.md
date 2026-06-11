# Questra-Search V3 飞书 Bot 集成方案

> **📋 状态：计划阶段 — 尚未实现。** 以下为完整设计方案，代码开发待排期。

## 概述

将 Questra-Search V3 的 AI 深度研究能力接入飞书企业聊天系统，让用户在飞书中直接 @机器人提问，获得流式打字机效果的 AI 回答。当前系统部署在新加坡 ECS (43.106.12.79)。

---

## 一、为什么选择飞书

| 维度 | 飞书优势 |
|------|---------|
| 新加坡部署 | Lark 国际版天然支持新加坡区域，网络延迟低 |
| 流式消息 | CardKit 流式卡片 API 成熟（2024+），打字机效果 |
| API 质量 | 中英双语文档、API 调试台、Python SDK `lark-oapi` |
| Markdown | Card JSON 2.0 原生支持表格、代码高亮、引用 |
| 用户画像 | 科技/知识工作者为主，与 AI 工具用户群高度重合 |

---

## 二、集成架构

```
┌─────────────────────────────────────────────────────┐
│                    飞书客户端                         │
│   用户 @Questra-Search Bot "分析 React 19 新特性"          │
└──────────────────────────┬──────────────────────────┘
                           │ HTTPS
                           ▼
┌─────────────────────────────────────────────────────┐
│                  飞书开放平台                         │
│  Event Subscription → POST /api/bot/feishu/event    │
│  (im.message.receive_v1 事件)                        │
│                                                      │
│  CardKit API:                                        │
│  POST /cards (创建)                                  │
│  POST /messages (发送)                               │
│  PUT /cards/:id/elements/... (流式更新)              │
│  PATCH /cards/:id/settings (关闭流式)                │
└──────────────────────────┬──────────────────────────┘
                           │ HTTPS (公网)
                           ▼
┌─────────────────────────────────────────────────────┐
│            新加坡 ECS (43.106.12.79)                 │
│                                                      │
│  Nginx :80                                           │
│  ├── /miro/       → 网页版 (不变)                    │
│  └── /api/bot/    → Bot 端点 (新增)                  │
│                                                      │
│  FastAPI :8900                                       │
│  ├── bot_feishu.py      ← 事件接收+消息路由          │
│  ├── feishu_cardkit.py  ← CardKit 流式封装           │
│  ├── feishu_client.py   ← 飞书 API 客户端            │
│  ├── chat.py            ← 复用 SSE 生成器            │
│  ├── stream_recorder.py ← 复用消息持久化             │
│  └── database.py        ← 新增 user_feishu_map 表    │
│                                                      │
│  SQLite: user_feishu_map (open_id ↔ user_id)         │
└─────────────────────────────────────────────────────┘
```

---

## 三、SSE → 飞书 CardKit 流式转换

```
SSE 事件 (Questra-Search API)            飞书 CardKit 操作
──────────────────────              ──────────────────
start                               ① 创建卡片实体 + 发送卡片消息
  ▼
thinking (delta)                    ② 流式更新思考区域 (200ms 累积)
  ▼
tool_start / tool_done              ③ 更新工具调用进度
  ▼
content (delta)  ──────────────→    ④ 核心流式更新 (打字机效果)
  │                                    策略: 200ms 累积, 发送全量文本
  │                                    限制: 单卡 30KB, 超限分段
  │                                    频率: 5次/秒 << 50次/秒 限制
  ▼
done (usage)                        ⑤ 关闭 streaming_mode, 显示完成
```

**关键技术要点：**
- 飞书流式更新要求传入**全量文本**（非增量），本地累积 delta
- 打字机效果：新文本是旧文本前缀 → 增量部分自动动画
- 卡片实体有效期 14 天

---

## 四、用户身份映射

```
飞书用户首次发消息
  ↓
事件: { sender: { open_id: "ou_xxx" }, tenant_key: "t_xxx" }
  ↓
查询 user_feishu_map
  ↓
┌─ 存在 → 直接使用 Questra-Search user_id
└─ 不存在 → 自动创建用户（免邀请码）
            username = "feishu_{open_id_suffix}"
            写入映射 → 继续对话
```

**所需权限：** `im:message`, `im:message:send_as_bot`, `im:message.p2p_msg:readonly`

---

## 五、异步处理设计

飞书要求事件回调 **3 秒内返回 HTTP 200**，Questra-Search API 最长 300 秒：

```python
@router.post("/api/bot/feishu/event")
async def feishu_event(request: Request):
    body = await request.json()
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}
    event = decrypt_and_verify(body)
    background_tasks.add_task(process_feishu_message, event)
    return {"code": 0}
```

---

## 六、新增文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `app/routers/bot_feishu.py` | ~200 | 事件回调、验签、消息分发 |
| `app/services/feishu_cardkit.py` | ~150 | CardKit 创建/更新/关闭 |
| `app/services/feishu_client.py` | ~80 | token 管理、API 调用 |
| `app/database.py` (迁移) | +15 | `user_feishu_map` 表 |
| `app/config.py` (新增) | +5 | FEISHU_APP_ID/SECRET/TOKEN |
| `deploy.sh` (Nginx) | +10 | `/api/bot/` location |

**新增依赖：** `lark-oapi>=1.3.0`, `pycryptodome>=3.20.0`

---

## 七、数据隔离

```
飞书企业 A (tenant_key=t_a)
├── 用户 X (open_id=ou_aaa) → user_id=5 → 会话隔离
└── 用户 Y (open_id=ou_bbb) → user_id=6 → 会话隔离

飞书企业 B (tenant_key=t_b)
└── 用户 Z (open_id=ou_ccc) → user_id=7 → 会话隔离
```

- 同企业不同用户：open_id → 不同 user_id，天然隔离
- 不同企业：tenant_key + open_id 双重区分
- Bot 端点通过飞书签名验证 + open_id 查找内部用户

---

## 八、实施路径

| 阶段 | 内容 | 工时 |
|------|------|------|
| Phase 1: 基础通道 | 创建飞书应用、事件订阅、URL 验证、Echo 回复 | 1-2 天 |
| Phase 2: 流式回答 | CardKit 流式卡片、SSE 转换、200ms 累积 | 2-3 天 |
| Phase 3: 体验完善 | 用户映射、多轮会话、思考折叠、取消任务 | 1-2 天 |
| Phase 4: 钉钉(可选) | 复用 70% 代码, dingtalk-stream 集成 | 2-3 天 |

**推荐执行 Phase 1-3，预计 1-1.5 周。**

---

## 九、验证清单

```
□ 飞书开发者后台 URL 验证通过 (challenge 响应正确)
□ 用户 @机器人 "你好" → 收到回复
□ 发送研究问题 → 卡片流式打字机效果
□ 思考过程可折叠、工具调用有进度
□ 首次对话 → 自动创建 Questra-Search 账号
□ 多次对话归属同一 user_id
□ 内容持久化到 SQLite
□ 超长回答 (>30KB) 自动分段
□ 网页版功能不受影响 (回归验证)
```

---

## 十、飞书开发者后台配置

| 配置项 | 值 |
|--------|-----|
| 应用类型 | 企业自建应用 |
| 机器人模式 | 启用 |
| 事件订阅 URL | `http://43.106.12.79/api/bot/feishu/event` |
| 订阅事件 | `im.message.receive_v1` |
| 权限范围 | `im:message`, `im:message:send_as_bot`, `im:message.p2p_msg:readonly` |
| 可用范围 | 指定人员 (≤5 人) |
