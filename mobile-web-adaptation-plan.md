# Questra-Search V3 移动端网页适配方案

## 概述

为 Questra-Search V3 网页端添加完整的 iOS/Android 移动浏览器适配，确保在 iPhone SE (375px) 到 iPhone 15 Pro Max (430px) 及各种 Android 设备上均能稳定、流畅地使用。

当前前端为纯 HTML/CSS/JS（index.html 177行 + app.css 506行 + app.js 1063行），仅有 13 行基础响应式代码。

---

## 一、页面稳定性优化

### 1.1 iOS Safari `100vh` 修复

iOS Safari 的 `100vh` 包含地址栏高度，导致布局溢出。

```css
/* 当前（有问题）*/
body { height: 100vh; }
.view { height: 100vh; }
.app-body { height: calc(100vh - 48px); }

/* 修复后 */
body { height: 100vh; height: 100dvh; }
.view { height: 100vh; height: 100dvh; }
.app-body { height: calc(100dvh - var(--header-h) - var(--safe-top) - var(--safe-bottom)); }
```

`100dvh` = dynamic viewport height，iOS Safari 15.4+ 支持，旧版自动降级到 `100vh`。

### 1.2 安全区域适配（刘海/灵动岛/底部横条）

```css
:root {
    --safe-top: env(safe-area-inset-top, 0px);
    --safe-bottom: env(safe-area-inset-bottom, 0px);
    --safe-left: env(safe-area-inset-left, 0px);
    --safe-right: env(safe-area-inset-right, 0px);
    --touch-target: 44px;
    --header-h: 48px;
}
```

viewport 需设置 `viewport-fit=cover`：
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, viewport-fit=cover">
```

### 1.3 过度滚动抑制

```css
body {
    overscroll-behavior: none;           /* 禁止 Chrome pull-to-refresh */
    -webkit-text-size-adjust: 100%;      /* 防止 iOS 横屏自动放大字体 */
}
```

---

## 二、UI 组件兼容性（iOS + Android）

### 2.1 触摸目标尺寸

所有可点击元素最小 44x44px（Apple HIG / Material Design 推荐）：

```css
@media (max-width: 768px) {
    button, .btn, .btn-login, .btn-sm, .btn-danger,
    .hamburger, .btn-account, .session-menu-btn {
        min-height: var(--touch-target);
        min-width: var(--touch-target);
    }
}
```

### 2.2 输入框防缩放

iOS Safari 在 `font-size < 16px` 时会自动缩放页面。输入框和 textarea 必须使用 `font-size: 16px`：

```css
@media (max-width: 768px) {
    .input-row textarea { font-size: 16px; }
    .login-form input { font-size: 16px; padding: 14px 16px; }
}
```

### 2.3 触摸设备菜单按钮

当前 `.session-menu-btn` 使用 `opacity: 0` + `:hover` 显示，触摸设备无法 hover：

```css
@media (max-width: 768px) {
    .session-menu-btn { opacity: 1 !important; }
}
```

### 2.4 Modal 底部 Sheet 样式

移动端 Modal 改为从底部弹出（更符合移动端操作习惯）：

```css
@media (max-width: 768px) {
    .modal-overlay { align-items: flex-end; }
    .modal {
        width: 95%; max-height: 90vh;
        border-radius: 16px 16px 0 0;
    }
}
```

### 2.5 Model 选择器方向修正

当前下拉向上弹出，移动端可能被截断。改为向下弹出：

```css
@media (max-width: 768px) {
    .model-dropdown {
        bottom: auto; top: 100%;
        min-width: calc(100vw - 32px);
        max-height: 50vh; overflow-y: auto;
    }
}
```

### 2.6 代码块和表格横向滚动

触摸设备上必须支持横向滑动：

```css
@media (max-width: 768px) {
    .answer-area pre {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
    .answer-area table {
        display: block; overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
}
```

### 2.7 剪贴板 API 降级

`navigator.clipboard.writeText` 在非 HTTPS 环境和旧版 iOS Safari 中不可用：

```javascript
async function copyText(text, feedbackEl) {
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;left:-9999px;opacity:0';
            document.body.appendChild(ta);
            ta.select();
            ta.setSelectionRange(0, text.length); // iOS 必须
            document.execCommand('copy');
            document.body.removeChild(ta);
        }
        if (feedbackEl) {
            feedbackEl.textContent = '已复制';
            setTimeout(() => feedbackEl.textContent = '复制', 1500);
        }
    } catch(e) { UI.toast('复制失败', 'error'); }
}
```

---

## 三、SSE 流式响应移动端稳定性

### 3.1 ReadableStream 兼容性

当前 SSE 使用 `fetch + ReadableStream + TextDecoder`，兼容性：

| 浏览器 | 最低版本 | 状态 |
|--------|---------|------|
| iOS Safari | 15.0 (2021-09) | 良好 |
| Chrome Android | 85 (2020-08) | 良好 |
| Samsung Internet | 14.0 (2021-05) | 良好 |
| Firefox Android | 85 (2021-01) | 良好 |

**无需修改**，兼容性已足够。

### 3.2 渲染性能节流

移动端 DOM 操作成本更高，`marked.parse()` 频繁调用会卡顿：

```javascript
// 替换 Chat.addContent
addContent(text) {
    this.rawMarkdown += text;
    if (this._renderPending) return;
    this._renderPending = true;
    const delay = window.innerWidth <= 768 ? 100 : 16;
    this._renderTimer = setTimeout(() => {
        if (this.currentAnswerEl) {
            this.currentAnswerEl.innerHTML = marked.parse(this.rawMarkdown);
            $('messages').scrollTop = $('messages').scrollHeight;
        }
        this._renderPending = false;
    }, delay);
}
```

- 移动端：100ms 间隔（~10fps），避免低端机卡顿
- 桌面端：16ms（~60fps）

### 3.3 后台标签页 SSE 恢复

iOS Safari 后台标签页会暂停 SSE 连接，返回时需要恢复：

```javascript
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && App.isStreaming) {
        const msgs = $('messages');
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
    }
});
```

### 3.4 网络状态监控

移动网络不稳定时提供用户反馈：

```javascript
window.addEventListener('online', () => UI.toast('网络已恢复', 'success'));
window.addEventListener('offline', () => {
    if (App.isStreaming) UI.toast('网络已断开，流式响应可能中断', 'error');
});
```

---

## 四、虚拟键盘处理

iOS/Android 键盘弹起时，`position: fixed` 失效，输入框可能被遮挡：

```javascript
const VK = {
    init() {
        if (!window.visualViewport) return;
        const vv = window.visualViewport;
        const inputArea = document.querySelector('.input-area');
        vv.addEventListener('resize', () => {
            const isKeyboardOpen = (window.innerHeight - vv.height) > 150;
            if (isKeyboardOpen) {
                const msgs = $('messages');
                if (msgs) msgs.style.height = (vv.height - inputArea.offsetHeight) + 'px';
                setTimeout(() => { msgs && (msgs.scrollTop = msgs.scrollHeight); }, 100);
            } else {
                const msgs = $('messages');
                if (msgs) msgs.style.height = '';
            }
        });
    }
};
```

---

## 五、自定义对话框（替代 prompt/confirm）

移动端 `prompt()` 和 `confirm()` 体验差（样式不可控、部分浏览器阻止）：

**HTML 新增：**
```html
<div id="confirmDialog" class="modal-overlay" style="display:none">
    <div class="modal confirm-modal">
        <div class="modal-header"><h3 id="confirmTitle">确认</h3></div>
        <div class="modal-body">
            <p id="confirmMessage"></p>
            <div id="confirmInputWrap" style="display:none;margin-top:12px">
                <input type="text" id="confirmInput" class="form-input" autocomplete="off">
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn btn-sm" onclick="UI._confirmCancel()">取消</button>
            <button class="btn btn-sm btn-primary" onclick="UI._confirmOk()">确定</button>
        </div>
    </div>
</div>
```

**JS Promise 化：**
```javascript
// UI 模块新增
async customConfirm(message, { title = '确认', inputDefault = null } = {}) {
    return new Promise(resolve => {
        this._confirmResolve = resolve;
        $('confirmTitle').textContent = title;
        $('confirmMessage').textContent = message;
        // 显示/隐藏输入框
        // 显示对话框
    });
}

// 替换 renameSession（原使用 prompt）
async renameSession(sessionId) {
    const newTitle = await this.customConfirm('请输入新名称:', {
        title: '重命名会话', inputDefault: s.title
    });
    if (newTitle) Sessions.rename(sessionId, newTitle);
}

// 替换 deleteSession（原使用 confirm）
async deleteSession(sessionId) {
    const confirmed = await this.customConfirm('确定删除？');
    if (confirmed) Sessions.delete(sessionId);
}
```

---

## 六、触摸手势

从屏幕左边缘右滑打开侧边栏，打开时左滑关闭：

```javascript
const Touch = {
    SWIPE_THRESHOLD: 40,
    EDGE_ZONE: 30,
    init() {
        const main = $('mainArea');
        main.addEventListener('touchstart', e => {
            if (e.touches[0].clientX < this.EDGE_ZONE && !UI._sidebarOpen) {
                this.swiping = true; this.startX = e.touches[0].clientX;
            }
            if (UI._sidebarOpen) {
                this.swiping = true; this.startX = e.touches[0].clientX;
            }
        }, { passive: true });
        // touchmove: 纵向>横向时放弃
        // touchend: diff > threshold 时触发开关
    }
};
```

---

## 七、三断点 CSS 响应式方案

替换现有 13 行 `@media (max-width: 768px)` 为：

| 断点 | 覆盖 | 关键调整 |
|------|------|---------|
| `≤768px` | 平板+手机 | hamburger、sidebar fixed、安全区域、44px 触摸、modal Sheet |
| `≤480px` | 手机 | 登录卡片收紧、sidebar 宽度调整 |
| `≤375px` | iPhone SE | 最小屏适配 |

**关键变更汇总：**

| 组件 | 改动 |
|------|------|
| Header | `padding-top: var(--safe-top)` |
| Hamburger | 44x44px 触摸目标 |
| Sidebar | `padding-bottom: var(--safe-bottom)` |
| session-menu-btn | `opacity: 1 !important` |
| Messages | `-webkit-overflow-scrolling: touch` |
| Input textarea | `font-size: 16px` 防缩放 |
| Input area | `padding-bottom: calc(8px + var(--safe-bottom))` |
| Model dropdown | 向下弹出 |
| Modal | 底部 Sheet 样式 |
| Toast | 避开刘海安全区域 |
| 所有按钮 | `min-height: 44px` |

---

## 八、HTML 改动 (`static/index.html`)

### 8.1 新增 meta 标签

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0a0a0f">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Questra-Search">
```

### 8.2 input 属性增强

- 邀请码：`inputmode="text" autocapitalize="characters"`
- 用户名：`autocorrect="off" autocapitalize="none"`
- textarea placeholder 简化为 `"输入研究问题..."`

### 8.3 新增确认对话框 HTML

在 `accountModal` 之后添加 `confirmDialog` div。

---

## 九、兼容性问题速查表

| 问题 | 影响 | 解决方案 |
|------|------|---------|
| iOS `100vh` 含地址栏 | 布局溢出 | `100dvh` 降级到 `100vh` |
| iOS `< 16px` 字体缩放 | 输入框放大 | `font-size: 16px` |
| iOS `position:fixed` 键盘失效 | 输入区被推走 | `visualViewport` API |
| iOS `clipboard` 需 HTTPS | 复制失败 | `execCommand('copy')` 降级 |
| iOS 后台 SSE 暂停 | 流中断 | `visibilitychange` 恢复 |
| 触摸设备无 hover | 菜单不可见 | `opacity: 1 !important` |
| 双击缩放 | 意外放大 | viewport `maximum-scale=1.0` + JS 防护 |
| `prompt()`/`confirm()` | 体验差/被阻止 | 自定义 Promise 对话框 |

---

## 十、验证方案

### 测试设备

| 设备 | 分辨率 | 重点 |
|------|--------|------|
| iPhone SE | 375x667 | 最小宽度 |
| iPhone 14 Pro | 393x852 | 刘海安全区域 |
| iPhone 15 Pro Max | 430x932 | 大屏比例 |
| Pixel 7 | 412x915 | Android 典型 |

### 15 项关键场景

```
[1]  登录页 — 卡片居中、输入框不触发缩放
[2]  注册页 — 邀请码大写、375px 所有字段可见
[3]  侧边栏 — 滑入/出流畅、左滑手势打开
[4]  发送消息 — 键盘弹起后输入框可见
[5]  流式响应 — thinking/search/content 无卡顿
[6]  代码块 — 横向可滑动不溢出
[7]  Model 选择器 — 下拉不超出屏幕
[8]  重命名 — 自定义对话框（非 prompt）
[9]  删除确认 — 自定义对话框（非 confirm）
[10] 复制功能 — 非安全上下文也能复制
[11] 账户弹窗 — 底部 Sheet 弹出、可滚动
[12] Toast — 不被刘海遮挡
[13] 后台切换 — SSE 恢复后继续
[14] 断网/恢复 — toast 提示
[15] 横屏 — 布局不崩溃
```

### iOS 真机调试

```
iPhone 设置 > Safari > 高级 > Web 检查器
USB 连 Mac → Mac Safari > 开发 > [iPhone] > 选择页面
```

---

## 十一、实施优先级

| 优先级 | 内容 | 工时 |
|--------|------|------|
| **P0** | CSS 三断点 + 安全区域 + 100dvh + font-size:16px + session-btn 可见 | ~2.5h |
| **P1** | 自定义对话框 + 剪贴板降级 + 滑动手势 + SSE 节流 | ~2h |
| **P2** | 虚拟键盘 + Model 向下弹 + Modal Sheet + Toast 安全区 | ~1.5h |
| **P3** | PWA manifest + Service Worker + 网络提示 | ~1.5h |

**总计 ~7.5h。P0+P1 (4.5h) 即可获得良好的移动端体验。**
