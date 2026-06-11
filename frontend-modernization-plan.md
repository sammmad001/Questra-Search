# Questra-Search V3 前端现代化改造方案

## Context

Questra-Search V3 当前前端为纯 HTML/CSS/JS 架构（index.html 177行 + app.css 506行 + app.js 1063行），存在以下问题：
1. **"AI味"严重**：紫色渐变(#7c3aed)、emoji图标(🧠🔍💡)、气泡消息布局、打字光标动画、AI导向文案
2. **移动端适配不足**：仅13行响应式CSS，无safe-area处理、无dvh单位、无触摸目标优化
3. **PDF导出乱码**：xhtml2pdf不支持PingFang SC/Microsoft YaHei，ECS无CJK字体
4. **SSE处理原始**：手写fetch+ReadableStream解析，无错误重试机制

本方案基于公网搜索评估，选择轻量级、兼容vanilla JS的开源组件，在**不引入React/Vue框架**的前提下完成现代化改造。

---

## 技术选型评估

### 1. CSS框架：保留自定义CSS + Pico.css参考（不直接引入）

| 候选 | GitHub Stars | 大小 | 优势 | 劣势 |
|------|-------------|------|------|------|
| **Pico.css** | 13k+ | ~10KB gzip | 语义化、暗色主题自动适配、classless | 无工具类，大项目需额外CSS |
| Tailwind CSS | 85k+ | ~10KB+ (JIT) | 生态完善 | 需构建工具，与当前CDN模式冲突 |
| Bootstrap 5 | 172k+ | ~25KB gzip | 组件丰富 | 太重，风格不匹配 |

**决策**：**不引入任何CSS框架**。当前app.css 506行结构清晰，改造成本远低于引入新框架。参考Pico.css的设计语言（语义化、克制的配色），重写CSS变量和组件样式。理由：
- 项目仅3个静态文件，引入框架增加复杂度
- 当前布局（sidebar + main + messages）需大量自定义
- CDN加载框架影响首屏速度

### 2. 图标库：Lucide Icons ✅

| 候选 | 图标数 | 大小 | 风格 | CDN |
|------|--------|------|------|-----|
| **Lucide** | 1600+ | ~3KB/图标 | 线性、一致、专业 | jsDelivr ✅ |
| Tabler Icons | 6100+ | 类似 | 线性、略粗 | jsDelivr ✅ |
| Feather | 280+ | ~2KB/图标 | 已停止维护 | - |
| Heroicons | 300+ | 类似 | Tailwind生态 | jsDelivr ✅ |

**决策**：**采用 Lucide Icons**
- GitHub: https://github.com/lucide-icons/lucide (13k+ stars)
- CDN: `https://cdn.jsdelivr.net/npm/lucide@latest/dist/umd/lucide.min.js` (~45KB UMD)
- ISC许可，完全免费商用
- 替换映射：🧠→`brain`、🔍→`search`、💡→`lightbulb`、🔧→`wrench`、🐍→`terminal`、⚡→`zap`、📄→`file-text`、⚙→`settings`、🚪→`log-out`、📝→`edit`、☰→`menu`

### 3. 代码高亮：highlight.js ✅

| 候选 | 大小 | 速度 | 语言数 | vanilla JS |
|------|------|------|--------|------------|
| **highlight.js** | ~15KB core | 中 | 190+ | ✅ 完美 |
| Prism.js | ~10KB core | 最快 | 280+ | ✅ |
| Shiki | 大(需Node) | 慢7x | TextMate语法 | ❌ 需构建 |

**决策**：**采用 highlight.js**
- CDN: `https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js`
- 与marked.js集成：通过`marked-highlight`插件或自定义renderer
- 暗色主题：使用`atom-one-dark`或`github-dark`主题CSS
- 当前已用marked.js，highlight.js集成最简单

### 4. SSE流式处理：优化现有实现（不引入新库）

| 候选 | GitHub | 大小 | 特点 |
|------|--------|------|------|
| **eventsource-parser** | rexxars (500+ stars) | ~3KB | 流式解析、TransformStream |
| sse.js | mpetazzoni (600+ stars) | ~5KB | EventSource替代、支持POST |
| fetch-event-source | Azure (1.5k stars) | ~5KB | fetch API + SSE |
| **当前实现** | - | 0 | fetch + ReadableStream |

**决策**：**保持当前fetch+ReadableStream方案，增加错误处理和重连逻辑**
- 当前实现已能正常工作，SSE协议简单（`data:` 行解析）
- 添加：连接超时、JSON解析错误处理、断线重连（指数退避）
- 不引入外部库减少依赖，避免UMD/ESM兼容问题

### 5. 移动端适配：纯CSS方案（无外部库）

搜索评估后确认：移动端适配不需要外部库，通过CSS原生能力解决：
- `100dvh` 替代 `100vh`（解决iOS Safari地址栏问题）
- `env(safe-area-inset-*)` 处理刘海屏
- `touch-action: manipulation` 消除300ms点击延迟
- `@supports` 渐进增强
- 最小触摸目标 44x44px（Apple HIG）

### 6. PDF生成：WeasyPrint替换xhtml2pdf ✅

| 候选 | CJK支持 | @font-face | 安装难度 | CSS支持 |
|------|---------|------------|----------|---------|
| xhtml2pdf (当前) | ❌ 差 | 需嵌入TTF | pip | CSS子集 |
| **WeasyPrint** | ✅ 系统字体 | ✅ 完整支持 | pip + 系统依赖 | CSS Paged Media |
| pdfkit (wkhtmltopdf) | ✅ | ✅ | 需外部二进制 | WebKit CSS |
| Playwright/Puppeteer | ✅ | ✅ | 需Chromium | 完整 |

**决策**：**采用 WeasyPrint 替换 xhtml2pdf**
- GitHub: https://github.com/Kozea/WeasyPrint (7k+ stars, BSD许可)
- 安装：`apt install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info`
- CJK：`apt install -y fonts-noto-cjk` 或使用 @font-face 嵌入 Noto Sans SC
- 优势：完整CSS支持、系统字体自动识别、纯Python无外部进程

---

## 实施计划

### Task 1: 去AI味 - CSS变量和配色重构

**文件**: `static/app.css`

修改CSS变量，从紫色AI风格转为蓝色专业研究工具风格：
```css
:root {
    --bg: #0f1117;        /* 深灰底，非纯黑 */
    --surface: #1a1d27;   /* 卡片底色 */
    --surface2: #232733;  /* 次级表面 */
    --border: #2d3348;    /* 边框 */
    --text: #d4d4d8;      /* 正文 - zinc-200 */
    --dim: #71717a;       /* 次要文字 - zinc-500 */
    --accent: #3b82f6;    /* 主色 - blue-500 */
    --accent2: #2563eb;   /* 次主色 - blue-600 */
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --blue: #0ea5e9; --orange: #f59e0b; --cyan: #7dd3fc;
}
```

具体修改：
- 移除所有 `linear-gradient(90deg, var(--accent2), var(--accent))` 渐变文字效果（6处）
- 标题改为纯色 `var(--text)` 或 `var(--accent)`
- 按钮改为纯色背景 `var(--accent)`，无渐变
- `.answer-area` 标题颜色从 `#c4b5fd`(紫) 改为 `#93c5fd`(蓝)

### Task 2: 去AI味 - 图标替换（emoji → Lucide SVG）

**文件**: `static/index.html`, `static/app.js`

引入Lucide CDN：
```html
<script src="https://cdn.jsdelivr.net/npm/lucide@latest/dist/umd/lucide.min.js"></script>
```

替换清单：
| 位置 | 当前 | 替换为 |
|------|------|--------|
| index.html L14 登录logo | 🧠 | SVG logo（自定义简洁图形） |
| index.html L31 注册logo | 📝 | Lucide `user-plus` |
| index.html L55 汉堡菜单 | ☰ | Lucide `menu` |
| index.html L62 设置按钮 | ⚙ | Lucide `settings` |
| index.html L81 空状态logo | 🧠 | SVG logo |
| index.html L170 账户菜单 | ⚙ 🚪 | Lucide `settings` `log-out` |
| app.js 动态DOM 💡 | 思考图标 | Lucide `lightbulb` |
| app.js 动态DOM 🔍 | 搜索图标 | Lucide `search` |
| app.js 动态DOM 🐍 | Python图标 | Lucide `terminal` |
| app.js 动态DOM ⚡ | 命令图标 | Lucide `zap` |
| app.js 动态DOM 🔧 | 工具图标 | Lucide `wrench` |
| app.js 动态DOM 📄 | 文件图标 | Lucide `file-text` |

实现方式：创建辅助函数
```javascript
function icon(name, size = 16) {
    return `<i data-lucide="${name}" style="width:${size}px;height:${size}px;stroke-width:1.5"></i>`;
}
// 渲染后调用 lucide.createIcons()
```

### Task 3: 去AI味 - 布局与文案优化

**文件**: `static/app.css`, `static/app.js`, `static/index.html`

布局改动：
- 用户消息：取消右对齐气泡，改为左对齐文档流样式（与assistant一致）
- 移除 `.msg-user .msg-bubble` 的 `border-radius: 14px 14px 4px 14px`
- 改为：用户消息用浅色背景块 + 左侧蓝色边线标识

文案替换：
| 当前 | 改为 |
|------|------|
| "Questra-Search Deep Research" | "Questra-Search 研究平台" 或保持（品牌名） |
| "AI 将自主搜索、分析并生成深度研究报告" | "输入问题，系统将自动搜索、分析并生成研究报告" |
| "研究ing..." | "分析中..." |
| "推理中..." | "处理中..." |
| "推理过程" | "处理过程" |
| "新对话" | "新研究" |
| "展开推理过程" | "展开处理过程" |

### Task 4: 代码高亮集成

**文件**: `static/index.html`, `static/app.css`

添加highlight.js CDN和暗色主题：
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
```

在marked配置中集成：
```javascript
marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    }
});
```

在`addContent`渲染后调用 `hljs.highlightAll()` 或针对新代码块高亮。

### Task 5: 移动端完整适配

**文件**: `static/app.css`, `static/index.html`

index.html viewport meta增强：
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0f1117">
```

app.css 响应式重构（替换现有13行@media）：
```css
/* 基础高度用dvh */
body { height: 100dvh; }
.app-body { height: calc(100dvh - 48px); }

/* Safe area */
.header { padding-top: env(safe-area-inset-top); }
.input-area { padding-bottom: calc(14px + env(safe-area-inset-bottom)); }
.sidebar { padding-bottom: env(safe-area-inset-bottom); }

/* 触摸目标 */
@media (max-width: 768px) {
    .session-item { min-height: 44px; }
    .msg-action-btn { min-height: 44px; min-width: 44px; padding: 8px 12px; }
    .btn { min-height: 44px; }
    .model-btn { min-height: 44px; }
    
    /* 侧边栏全屏 */
    .sidebar { width: 85vw; max-width: 320px; }
    
    /* 输入区优化 */
    .input-row { flex-wrap: wrap; }
    .input-row textarea { min-height: 44px; }
    
    /* 模态框全屏化 */
    .modal { width: 100%; max-height: 95vh; border-radius: 12px 12px 0 0; margin-top: auto; }
}

/* 防止iOS缩放 */
textarea, input { font-size: 16px; } /* iOS Safari zoom fix */
```

### Task 6: SSE流式处理增强

**文件**: `static/app.js`

在Chat.send()中增加：
```javascript
// 连接超时
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 120000); // 2分钟超时

// 错误计数和重连提示
let errorCount = 0;

// JSON解析容错
try {
    const e = JSON.parse(raw);
    this.handleSSEEvent(e);
} catch(err) {
    errorCount++;
    if (errorCount > 10) {
        UI.toast('数据流异常，请刷新重试', 'error');
        break;
    }
}
```

### Task 7: PDF导出修复 - WeasyPrint替换

**文件**: `app/services/pdf_generator.py`, `deploy.sh`

7a. 修改pdf_generator.py：
- 将xhtml2pdf替换为weasyprint
- 字体改用系统Noto Sans CJK（通过@font-face或系统安装）
- 配色从紫色改为蓝色系

```python
# 替换 xhtml2pdf 部分
from weasyprint import HTML
# ...
pdf_bytes = HTML(string=html).write_pdf()
return pdf_bytes
```

7b. 字体方案（双保险）：
- 方案A：ECS安装 `apt install -y fonts-noto-cjk`
- 方案B：@font-face嵌入Noto Sans SC TTF文件（~7MB，放static/fonts/）

7c. deploy.sh添加字体安装步骤

7d. requirements.txt：`xhtml2pdf` → `weasyprint`

### Task 8: 自定义SVG Logo设计

**文件**: `static/index.html`

设计一个简洁的研究工具logo（纯SVG inline），替代🧠emoji：
- 风格：线条图形，类似显微镜/望远镜/指南针的抽象化
- 颜色：使用 `var(--accent)` 蓝色
- 尺寸：登录页56px → 缩小为40px，header 20px

---

## 关键文件清单

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `static/app.css` | 修改 | ~200行（变量+响应式+去渐变） |
| `static/app.js` | 修改 | ~80行（图标函数+文案+SSE增强） |
| `static/index.html` | 修改 | ~20行（CDN引入+viewport+emoji替换） |
| `app/services/pdf_generator.py` | 重写 | 全文（xhtml2pdf→weasyprint） |
| `deploy.sh` | 修改 | ~10行（字体安装+依赖变更） |
| `requirements.txt` | 修改 | 1行 |

## 不引入的技术（及理由）

- **React/Vue**：当前vanilla JS架构清晰，引入框架需全面重写，ROI极低
- **Tailwind CSS**：需构建工具链，与CDN直接加载模式冲突
- **Pico.css**：classless风格与现有自定义布局冲突，仅参考设计理念
- **eventsource-parser**：当前SSE解析已可用，引入增加依赖但收益微小
- **PWA/Service Worker**：当前无需离线功能，增加复杂度

## 验证方案

1. **视觉验证**：本地启动，对比改造前后截图，确认无紫色渐变、无emoji图标
2. **移动端验证**：Chrome DevTools iPhone/Android模拟器 + 真机Safari测试
   - 检查safe-area、dvh高度、触摸目标、侧边栏滑出
3. **SSE验证**：发送研究请求，确认流式渲染正常、超时处理生效
4. **PDF验证**：导出含中文的PDF，在ECS上测试WeasyPrint渲染
   - `curl -X POST /api/export/pdf -d '{"message_id":1,"mode":"full"}' -o test.pdf`
   - 确认中文无乱码、排版正确
5. **CDN验证**：检查Lucide和highlight.js CDN加载成功率
   - `document.querySelectorAll('[data-lucide]').length > 0`
   - `typeof hljs !== 'undefined'`
