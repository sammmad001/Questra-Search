/**
 * Questra-Search - Frontend
 */

// ===== Config =====
const basePath = window.__BASE_PATH__ || '';

// ===== Global State =====
const App = {
    token: localStorage.getItem('questra_search_token') || null,
    user: null,
    sessions: [],
    activeSessionId: null,
    activeModel: 'mirothinker-1-7-deepresearch',
    models: [],
    isStreaming: false,
    currentRequestId: null,
    startTime: 0,
    elapsedInterval: null,
};

// ===== DOM Refs =====
const $ = id => document.getElementById(id);

// ===== Configure marked + highlight.js =====
marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function(code, lang) {
        if (typeof hljs !== 'undefined') {
            if (lang && hljs.getLanguage(lang)) {
                try { return hljs.highlight(code, { language: lang }).value; } catch(e) {}
            }
            try { return hljs.highlightAuto(code).value; } catch(e) {}
        }
        return code;
    }
});

// ===== Utility =====
function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }

// Lucide icon helper - returns inline SVG string
function ico(name, size) {
    size = size || 14;
    if (typeof lucide !== 'undefined' && lucide.icons && lucide.icons[name]) {
        // Direct SVG from lucide icon data
        const iconData = lucide.icons[name];
        const attrs = iconData[1] || {};
        let svg = '<svg xmlns="http://www.w3.org/2000/svg" width="'+size+'" height="'+size+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">';
        // Parse children
        const children = iconData[2] || [];
        if (typeof children === 'string') {
            svg += children;
        } else if (Array.isArray(children)) {
            children.forEach(function(child) {
                if (Array.isArray(child) && child.length >= 2) {
                    var tag = child[0];
                    var cAttrs = child[1] || {};
                    var attrStr = '';
                    for (var k in cAttrs) { if (cAttrs.hasOwnProperty(k)) attrStr += ' ' + k + '="' + cAttrs[k] + '"'; }
                    svg += '<' + tag + attrStr + '/>';
                }
            });
        }
        svg += '</svg>';
        return svg;
    }
    // Fallback: use <i> tag + createIcons
    return '<i data-lucide="'+name+'" style="width:'+size+'px;height:'+size+'px;display:inline-block;vertical-align:-2px"></i>';
}
function renderIcons(container) {
    if (typeof lucide !== 'undefined' && lucide.createIcons) {
        lucide.createIcons({ nameAttr: 'data-lucide', attrs: {}, icons: lucide.icons });
    }
}

// ===== API Module =====
const API = {
    async request(method, path, body) {
        const headers = { 'Content-Type': 'application/json' };
        if (App.token) headers['Authorization'] = 'Bearer ' + App.token;
        const opts = { method, headers };
        if (body) opts.body = JSON.stringify(body);
        const resp = await fetch(basePath + path, opts);
        if (resp.status === 401) { Auth.logout(); throw new Error('Unauthorized'); }
        return resp;
    },
    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },
    put(path, body) { return this.request('PUT', path, body); },
    patch(path, body) { return this.request('PATCH', path, body); },
    del(path) { return this.request('DELETE', path); },
    async json(resp) { return resp.json(); },
};

// ===== Auth Module =====
const Auth = {
    async init() {
        if (App.token) {
            try {
                const resp = await API.get('/api/auth/me');
                if (resp.ok) {
                    App.user = await resp.json();
                    this.showApp();
                    return;
                }
            } catch(e) {}
        }
        this.showLogin();
    },

    async login() {
        const username = $('loginUser').value.trim();
        const password = $('loginPass').value.trim();
        const errorEl = $('loginError');
        errorEl.textContent = '';

        if (!username || !password) { errorEl.textContent = '请输入用户名和密码'; return; }

        try {
            const resp = await API.post('/api/auth/login', { username, password });
            const data = await resp.json();
            if (!data.ok) {
                let msg = '登录失败';
                if (typeof data.detail === 'string') msg = data.detail;
                else if (Array.isArray(data.detail)) msg = data.detail.map(e => e.msg || JSON.stringify(e)).join('; ');
                errorEl.textContent = msg;
                return;
            }

            App.token = data.token;
            App.user = data.user;
            localStorage.setItem('questra_search_token', data.token);
            this.showApp();
        } catch(e) {
            errorEl.textContent = '连接失败';
        }
    },

    async register() {
        const username = $('regUsername').value.trim();
        const password = $('regPassword').value;
        const password2 = $('regPassword2').value;
        const displayName = $('regDisplayName').value.trim();
        const email = $('regEmail').value.trim();
        const inviteCode = $('regInviteCode').value.trim().toUpperCase();
        const errorEl = $('regError');
        errorEl.textContent = '';

        // 前端校验
        if (!username || !password || !inviteCode) {
            errorEl.textContent = '用户名、密码和邀请码为必填项'; return;
        }
        if (username.length < 3 || username.length > 20) {
            errorEl.textContent = '用户名长度需在 3-20 个字符之间'; return;
        }
        if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(username)) {
            errorEl.textContent = '用户名只能包含字母、数字、下划线或中文'; return;
        }
        if (password.length < 6) {
            errorEl.textContent = '密码长度至少 6 个字符'; return;
        }
        if (password !== password2) {
            errorEl.textContent = '两次输入的密码不一致'; return;
        }
        // 邮箱格式前端预检（选填，但填了就必须合法）
        if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
            errorEl.textContent = '邮箱格式不正确'; return;
        }

        try {
            const resp = await API.post('/api/auth/register', {
                username, password, display_name: displayName, email, invite_code: inviteCode,
            });
            const data = await resp.json();
            if (!data.ok) {
                // 处理 Pydantic 验证错误 (422) 和业务错误
                let msg = '注册失败';
                if (typeof data.detail === 'string') {
                    msg = data.detail;
                } else if (Array.isArray(data.detail)) {
                    msg = data.detail.map(e => e.msg || JSON.stringify(e)).join('; ');
                } else if (data.detail) {
                    msg = String(data.detail);
                }
                errorEl.textContent = msg;
                return;
            }

            // 注册成功，自动登录
            App.token = data.token;
            App.user = data.user;
            localStorage.setItem('questra_search_token', data.token);
            this.showApp();
            UI.toast('注册成功！欢迎 ' + (data.user.display_name || data.user.username), 'success');
        } catch(e) {
            errorEl.textContent = '连接失败，请检查网络';
        }
    },

    logout() {
        App.token = null; App.user = null;
        localStorage.removeItem('questra_search_token');
        // 清空表单
        $('loginUser').value = ''; $('loginPass').value = '';
        $('loginError').textContent = '';
        // 调用后端清 cookie
        API.post('/api/auth/logout').catch(() => {});
        this.showLogin();
    },

    showLogin() {
        $('loginView').style.display = 'flex';
        $('registerView').style.display = 'none';
        $('appView').style.display = 'none';
        $('accountModal').style.display = 'none';
    },

    showRegister() {
        $('loginView').style.display = 'none';
        $('registerView').style.display = 'flex';
        $('appView').style.display = 'none';
    },

    showApp() {
        $('loginView').style.display = 'none';
        $('registerView').style.display = 'none';
        $('appView').style.display = 'block';
        $('userName').textContent = App.user.display_name || App.user.username;
        Sessions.load();
        Models.load();
    },
};

// ===== Account Module =====
const Account = {
    _menuVisible: false,

    toggleMenu() {
        const dd = $('accountDropdown');
        this._menuVisible = !this._menuVisible;
        dd.style.display = this._menuVisible ? 'block' : 'none';
        if (this._menuVisible) {
            setTimeout(() => {
                document.addEventListener('click', function close() {
                    dd.style.display = 'none';
                    Account._menuVisible = false;
                    document.removeEventListener('click', close);
                }, { once: true });
            }, 10);
        }
    },

    async openModal() {
        $('accountDropdown').style.display = 'none';
        this._menuVisible = false;

        // 加载账户信息
        try {
            const resp = await API.get('/api/auth/me');
            if (!resp.ok) { UI.toast('加载账户信息失败', 'error'); return; }
            const info = await resp.json();

            // 填充表单
            $('acctUsername').value = info.username || '';
            $('acctDisplayName').value = info.display_name || '';
            $('acctEmail').value = info.email || '';
            $('acctOldPass').value = '';
            $('acctNewPass').value = '';

            // 统计卡片
            $('accountStats').innerHTML = `
                <div class="stat-card">
                    <div class="stat-value">${info.total_sessions || 0}</div>
                    <div class="stat-label">会话数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${info.total_messages || 0}</div>
                    <div class="stat-label">消息数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${(info.total_tokens || 0).toLocaleString()}</div>
                    <div class="stat-label">总 Tokens</div>
                </div>
            `;
        } catch(e) { UI.toast('加载账户信息失败', 'error'); }

        // 加载邀请码列表
        this.loadInviteCodes();

        $('accountModal').style.display = 'flex';
    },

    closeModal() {
        $('accountModal').style.display = 'none';
    },

    async saveProfile() {
        const displayName = $('acctDisplayName').value.trim();
        const email = $('acctEmail').value.trim();

        try {
            const resp = await API.put('/api/auth/profile', { display_name: displayName, email });
            const data = await resp.json();
            if (data.ok) {
                UI.toast('资料已保存', 'success');
                // 更新 header 显示
                if (App.user) {
                    App.user.display_name = displayName;
                    App.user.email = email;
                    $('userName').textContent = displayName || App.user.username;
                }
            } else {
                UI.toast(data.detail || '保存失败', 'error');
            }
        } catch(e) { UI.toast('保存失败', 'error'); }
    },

    async changePassword() {
        const oldPass = $('acctOldPass').value;
        const newPass = $('acctNewPass').value;

        if (!oldPass || !newPass) { UI.toast('请填写旧密码和新密码', 'error'); return; }
        if (newPass.length < 6) { UI.toast('新密码至少 6 个字符', 'error'); return; }

        try {
            const resp = await API.post('/api/auth/change-password', { old_password: oldPass, new_password: newPass });
            const data = await resp.json();
            if (data.ok) {
                UI.toast('密码已修改', 'success');
                $('acctOldPass').value = '';
                $('acctNewPass').value = '';
            } else {
                UI.toast(data.detail || '修改失败', 'error');
            }
        } catch(e) { UI.toast('修改失败', 'error'); }
    },

    async generateInviteCode() {
        try {
            const resp = await API.post('/api/auth/invite-codes', { count: 1 });
            const data = await resp.json();
            if (data.ok && data.codes) {
                UI.toast('邀请码已生成: ' + data.codes[0], 'success');
                this.loadInviteCodes();
            }
        } catch(e) { UI.toast('生成失败', 'error'); }
    },

    async loadInviteCodes() {
        try {
            const resp = await API.get('/api/auth/invite-codes');
            const data = await resp.json();
            const list = $('inviteCodesList');
            if (!data.items || data.items.length === 0) {
                list.innerHTML = '<div style="color:var(--dim);font-size:12px;">暂无邀请码</div>';
                return;
            }
            list.innerHTML = data.items.map(item => `
                <div class="invite-code-item">
                    <span class="invite-code-value">${esc(item.code)}</span>
                    <span class="invite-code-status ${item.used ? 'used' : 'unused'}">
                        ${item.used ? '已使用' : '可用'}
                    </span>
                    ${!item.used ? `<button class="invite-code-copy" onclick="Account.copyCode('${item.code}',this)">复制</button>` : ''}
                </div>
            `).join('');
        } catch(e) {}
    },

    copyCode(code, btn) {
        navigator.clipboard.writeText(code).then(() => {
            btn.textContent = '已复制';
            setTimeout(() => btn.textContent = '复制', 1500);
        });
    },
};

// ===== Models Module =====
const Models = {
    async load() {
        try {
            const resp = await API.get('/api/models');
            const data = await resp.json();
            App.models = data.models || [];
            this.renderSelector();
            // 默认选旗舰模型
            if (App.models.length > 0) {
                App.activeModel = App.models[0].id;
                this.updateDisplay();
            }
        } catch(e) {}
    },

    renderSelector() {
        const dd = $('modelDropdown');
        dd.innerHTML = App.models.map(m => `
            <div class="model-option ${m.id === App.activeModel ? 'active' : ''}"
                 data-model="${m.id}" onclick="Models.select('${m.id}')">
                <div class="model-option-name">
                    ${esc(m.name)}
                    <span class="model-option-badge ${m.id.includes('mini') ? 'fast' : 'flagship'}">${m.badge}</span>
                </div>
                <div class="model-option-desc">${esc(m.description)}</div>
                <div class="model-option-meta">输入: ${m.input_price} | 上下文: ${m.context_window} | 工具调用: ${m.max_tool_calls}次</div>
            </div>
        `).join('');
    },

    select(modelId) {
        App.activeModel = modelId;
        this.updateDisplay();
        $('modelDropdown').style.display = 'none';
        this.renderSelector();
    },

    updateDisplay() {
        const m = App.models.find(m => m.id === App.activeModel);
        $('currentModelName').textContent = m ? m.name : App.activeModel;
        $('modelName').textContent = m ? m.badge : '';
    },
};

// ===== Sessions Module =====
const Sessions = {
    async load() {
        try {
            const resp = await API.get('/api/sessions');
            const data = await resp.json();
            App.sessions = data.items || [];
            this.render();
        } catch(e) {}
    },

    async create() {
        try {
            const resp = await API.post('/api/sessions', {
                title: '新研究',
                model: App.activeModel,
            });
            const session = await resp.json();
            App.sessions.unshift(session);
            this.render();
            this.switchTo(session.id);
        } catch(e) { UI.toast('创建会话失败', 'error'); }
    },

    async switchTo(sessionId) {
        // 切换会话前取消正在进行的流式传输
        if (App.isStreaming) {
            Chat.cancel();
            App.isStreaming = false;
            Chat.stopElapsed();
            $('sendBtn').disabled = false;
            $('sendBtn').textContent = '发送';
            $('cancelBtn').classList.remove('visible');
            Chat._abortController = null;
        }

        App.activeSessionId = sessionId;
        this.render();
        $('headerTitle').textContent = (App.sessions.find(s => s.id === sessionId) || {}).title || 'Questra-Search 研究平台';

        // 隐藏 header 导出按钮（新会话加载前重置）
        Chat._lastAssistantMsgId = null;
        const exportBtn = $('btnHeaderExport');
        if (exportBtn) exportBtn.style.display = 'none';

        // 加载消息
        const messagesEl = $('messages');
        messagesEl.innerHTML = '';

        try {
            const resp = await API.get(`/api/sessions/${sessionId}`);
            const data = await resp.json();
            if (data.messages) {
                data.messages.forEach(msg => {
                    if (msg.role === 'user') {
                        Chat.renderUserMsg(msg.content, msg.created_at);
                    } else {
                        Chat.renderAssistantMsg(msg, data.messages);
                    }
                });
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }
        } catch(e) {}

        $('emptyState') && ($('emptyState').style.display = App.activeSessionId ? 'none' : 'block');
        // 移动端自动关闭侧边栏
        UI.closeSidebar();
    },

    async rename(sessionId, title) {
        try {
            await API.patch(`/api/sessions/${sessionId}`, { title });
            const s = App.sessions.find(s => s.id === sessionId);
            if (s) s.title = title;
            this.render();
            if (App.activeSessionId === sessionId) {
                $('headerTitle').textContent = title;
            }
        } catch(e) { UI.toast('重命名失败', 'error'); }
    },

    async delete(sessionId) {
        try {
            await API.del(`/api/sessions/${sessionId}`);
            App.sessions = App.sessions.filter(s => s.id !== sessionId);
            this.render();
            if (App.activeSessionId === sessionId) {
                App.activeSessionId = null;
                $('messages').innerHTML = '<div class="empty-state"><div class="empty-logo">'+ico('globe',48)+'</div><h2>Questra-Search 研究平台</h2><p>输入问题开始研究</p></div>';
                renderIcons($('messages'));
                $('headerTitle').textContent = 'Questra-Search 研究平台';
            }
        } catch(e) { UI.toast('删除失败', 'error'); }
    },

    filter(query) {
        const items = document.querySelectorAll('.session-item');
        const q = query.toLowerCase();
        items.forEach(el => {
            const title = el.querySelector('.session-title').textContent.toLowerCase();
            el.style.display = title.includes(q) ? '' : 'none';
        });
    },

    render() {
        const list = $('sessionList');
        list.innerHTML = App.sessions.map(s => `
            <div class="session-item ${s.id === App.activeSessionId ? 'active' : ''}"
                 data-id="${s.id}" onclick="Sessions.switchTo(${s.id})">
                <div class="session-info">
                    <div class="session-title">${esc(s.title)}</div>
                    <div class="session-time">${s.updated_at ? s.updated_at.replace('T',' ').substring(5,16) : ''}</div>
                </div>
                <button class="session-menu-btn" onclick="event.stopPropagation();UI.showSessionMenu(${s.id},this)">⋮</button>
            </div>
        `).join('');
    },

    async autoTitle(sessionId, userMsg) {
        // 首条消息时，用前30字作为标题
        const s = App.sessions.find(s => s.id === sessionId);
        if (s && (s.title === '新对话' || s.title === '新研究')) {
            const title = userMsg.substring(0, 30).replace(/\n/g, ' ') + (userMsg.length > 30 ? '...' : '');
            s.title = title;
            if (App.activeSessionId === sessionId) {
                $('headerTitle').textContent = title;
            }
            this.render();
            // 后台更新
            API.patch(`/api/sessions/${sessionId}`, { title }).catch(() => {});
        }
    },
};

// ===== Chat Module =====
const Chat = {
    currentThinkingEl: null,
    currentAnswerEl: null,
    currentPhaseType: null,
    rawMarkdown: '',
    currentMsgEl: null,   // 当前正在流式渲染的 assistant 消息
    phasesEl: null,       // 当前推理 phases 容器
    _lastAssistantMsgId: null,  // 最后一条 assistant 消息 ID，供 header 导出按钮使用
    phaseCount: 0,
    searchCount: 0,

    async send() {
        const input = $('input');
        const msg = input.textContent.trim();
        if (!msg || App.isStreaming) return;

        // 如果没有活跃会话，先创建
        if (!App.activeSessionId) {
            try {
                const resp = await API.post('/api/sessions', { title: '新研究', model: App.activeModel });
                const session = await resp.json();
                App.sessions.unshift(session);
                App.activeSessionId = session.id;
                Sessions.render();
                $('headerTitle').textContent = session.title;
            } catch(e) { UI.toast('创建会话失败', 'error'); return; }
        }

        // 记录正在流式传输的会话 ID，用于流结束后判断是否需要重新加载
        const streamSessionId = App.activeSessionId;

        App.isStreaming = true;
        $('sendBtn').disabled = true;
        $('sendBtn').textContent = '分析中...';
        $('cancelBtn').classList.add('visible');
        input.innerHTML = '';
        this.rawMarkdown = '';
        this.currentThinkingEl = null;
        this.currentAnswerEl = null;
        this.currentPhaseType = null;
        this.phaseCount = 0;
        this.searchCount = 0;

        // 渲染用户消息
        this.renderUserMsg(msg);
        Sessions.autoTitle(App.activeSessionId, msg);

        // 创建 assistant 消息占位
        this._createAssistantPlaceholder();

        // 开始计时
        this.startElapsed();

        // 创建 AbortController 用于取消
        this._abortController = new AbortController();

        try {
            const resp = await fetch(basePath + '/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + App.token,
                },
                body: JSON.stringify({
                    message: msg,
                    model: App.activeModel,
                    session_id: App.activeSessionId,
                }),
                signal: this._abortController.signal,
            });

            // 从响应头获取 session_id（自动创建时）
            const sid = resp.headers.get('X-Session-Id');
            if (sid && !App.activeSessionId) {
                App.activeSessionId = parseInt(sid);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();

            // Use eventsource-parser if available, otherwise fallback
            let parser = null;
            if (typeof eventSourceParser !== 'undefined' && eventSourceParser.createParser) {
                parser = eventSourceParser.createParser({
                    onEvent(evt) {
                        if (!evt.data || evt.data === '[DONE]') return;
                        try {
                            const e = JSON.parse(evt.data);
                            Chat.handleSSEEvent(e);
                        } catch(err) {}
                    },
                    onError(err) {
                        console.warn('SSE parse error:', err);
                    }
                });
            }

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });

                if (parser) {
                    parser.feed(chunk);
                } else {
                    // Fallback: manual SSE parsing
                    const lines = chunk.split('\n');
                    for (const line of lines) {
                        if (line.startsWith(':') || !line.startsWith('data: ')) continue;
                        const raw = line.slice(6).trim();
                        if (raw === '[DONE]') continue;
                        try {
                            const e = JSON.parse(raw);
                            this.handleSSEEvent(e);
                        } catch(err) {}
                    }
                }
            }
        } catch(e) {
            if (e.name === 'AbortError') {
                this.addContent('\n\n> 任务已取消');
            } else {
                this.addContent('\n\n> 连接失败: ' + esc(e.message));
            }
        }

        this._finalizeAssistantMsg();
        this.stopElapsed();
        App.isStreaming = false;
        $('sendBtn').disabled = false;
        $('sendBtn').textContent = '发送';
        $('cancelBtn').classList.remove('visible');
        App.currentRequestId = null;
        this._abortController = null;

        // 刷新会话列表（updated_at 排序）
        Sessions.load();

        // 重新加载会话消息（仅在未切换到其他会话时）
        if (App.activeSessionId === streamSessionId) {
            await Sessions.switchTo(App.activeSessionId);
        }
    },

    cancel() {
        // 中断前端 SSE 流
        if (this._abortController) {
            this._abortController.abort();
        }
        // 通知后端取消任务
        if (App.currentRequestId) {
            API.post('/api/cancel', { request_id: App.currentRequestId })
                .catch(() => {});
        }
    },

    handleSSEEvent(e) {
        switch (e.type) {
            case 'start':
                App.currentRequestId = e.request_id;
                break;
            case 'thinking':
                this.addThinking(e.content);
                break;
            case 'search':
                this.addSearch(e.keywords, e.results);
                break;
            case 'fetch':
                this.addFetch(e.content);
                break;
            case 'python':
                this.addPython(e.content);
                break;
            case 'command':
                this.addCommand(e.content);
                break;
            case 'tool_start':
            case 'tool_call':
                this.addToolStart(e.name);
                break;
            case 'tool_done': {
                const args = e.arguments;
                if (typeof args === 'string') {
                    try { e.arguments = JSON.parse(args); } catch(ex) {}
                }
                const argObj = e.arguments || {};
                if (argObj.query || argObj.keywords || argObj.search_query) {
                    const kws = (argObj.query || argObj.keywords || argObj.search_query || '').split(/[,，\s]+/).filter(Boolean);
                    this.addSearch(kws, []);
                }
                break;
            }
            case 'content':
                this.addContent(e.content);
                break;
            case 'done':
                this.addUsage(e);
                break;
            case 'error':
                this.addContent('\n\n> ' + esc(e.content));
                break;
        }
    },

    // --- Rendering helpers ---

    renderUserMsg(text, time) {
        const msgs = $('messages');
        // 清除空状态
        const es = msgs.querySelector('.empty-state');
        if (es) es.remove();

        const div = document.createElement('div');
        div.className = 'msg msg-user';
        div.innerHTML = `<div class="msg-bubble">${esc(text)}</div>`;
        if (time) {
            const t = document.createElement('div');
            t.className = 'msg-time'; t.textContent = time.substring(11, 16);
            div.appendChild(t);
        }
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    },

    renderAssistantMsg(msg, allMsgs) {
        const msgs = $('messages');
        const div = document.createElement('div');
        div.className = 'msg msg-assistant';

        // 推理过程
        const events = msg.tool_events || [];
        const thinking = msg.thinking_text || '';
        const hasPhases = thinking || events.length > 0;

        if (hasPhases) {
            const toggle = document.createElement('div');
            toggle.className = 'phases-toggle';
            toggle.innerHTML = '<span class="arrow">\u25b6</span> '+ico('chevron-right',12)+' 展开处理过程 ('+events.length+' 步)';
            toggle.onclick = function() {
                this.classList.toggle('expanded');
                const c = this.nextElementSibling;
                c.classList.toggle('collapsed');
            };
            div.appendChild(toggle);

            const container = document.createElement('div');
            container.className = 'phases-container collapsed';

            if (thinking) {
                const p = document.createElement('div'); p.className = 'phase';
                p.innerHTML = '<div class="phase-header thinking">'+ico('lightbulb',14)+' 思考</div>';
                const box = document.createElement('div'); box.className = 'thinking-box';
                box.textContent = thinking.substring(0, 500);
                p.appendChild(box); container.appendChild(p);
            }

            events.forEach(evt => {
                const p = document.createElement('div'); p.className = 'phase';
                if (evt.type === 'search') {
                    p.innerHTML = '<div class="phase-header search">'+ico('search',14)+' 搜索</div>';
                    const tags = document.createElement('div'); tags.className = 'search-tags';
                    (evt.keywords || []).forEach(k => {
                        const t = document.createElement('span'); t.className = 'search-tag'; t.textContent = k; tags.appendChild(t);
                    });
                    p.appendChild(tags);
                } else if (evt.type === 'fetch') {
                    p.innerHTML = '<div class="phase-header fetch">'+ico('file-text',14)+' 读取: ' + esc((evt.content||'').substring(0,80)) + '</div>';
                } else if (evt.type === 'tool_start' || evt.type === 'tool_call') {
                    p.innerHTML = '<div class="phase-header tool">'+ico('wrench',14)+' ' + esc(evt.name||'工具') + '</div>';
                }
                if (p.innerHTML) container.appendChild(p);
            });

            div.appendChild(container);
        }

        // 回答
        const answer = document.createElement('div');
        answer.className = 'answer-area';
        answer.innerHTML = marked.parse(msg.content || '');
        div.appendChild(answer);

        // 操作按钮
        const actions = document.createElement('div');
        actions.className = 'msg-actions';
        actions.innerHTML = `
            <button class="msg-action-btn" onclick="Chat.copyContent(this)" data-content="${esc(msg.content||'').replace(/"/g, '&quot;')}">复制</button>
            <button class="msg-action-btn" onclick="Export.showMenu(${msg.id}, this)">导出</button>
        `;
        div.appendChild(actions);

        // 用量
        if (msg.total_tokens) {
            const usage = document.createElement('div');
            usage.className = 'usage-bar';
            usage.innerHTML = `
                <span><span class="label">输入:</span> ${msg.prompt_tokens}</span>
                <span><span class="label">输出:</span> ${msg.completion_tokens}</span>
                <span><span class="label">总计:</span> ${msg.total_tokens}</span>
                ${msg.duration_ms ? '<span><span class="label">耗时:</span> ' + (msg.duration_ms/1000).toFixed(1) + 's</span>' : ''}
            `;
            div.appendChild(usage);
        }

        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;

        // 更新 header 导出按钮的目标消息
        Chat._lastAssistantMsgId = msg.id;
        const btn = $('btnHeaderExport');
        if (btn) btn.style.display = 'flex';
    },

    _createAssistantPlaceholder() {
        const msgs = $('messages');
        const div = document.createElement('div');
        div.className = 'msg msg-assistant';
        div.id = 'currentMsg';

        // phases toggle
        const toggle = document.createElement('div');
        toggle.className = 'phases-toggle expanded';
        toggle.id = 'phasesToggle';
        toggle.innerHTML = '<span class="arrow">\u25b6</span> '+ico('loader',12)+' 处理中...';
        toggle.onclick = function() {
            this.classList.toggle('expanded');
            const c = this.nextElementSibling;
            c.classList.toggle('collapsed');
        };
        div.appendChild(toggle);

        // phases container
        const phasesContainer = document.createElement('div');
        phasesContainer.className = 'phases-container';
        phasesContainer.id = 'phasesContainer';
        div.appendChild(phasesContainer);

        // answer area
        const answer = document.createElement('div');
        answer.className = 'answer-area typing-cursor';
        answer.id = 'currentAnswer';
        div.appendChild(answer);

        // elapsed
        const elapsed = document.createElement('div');
        elapsed.className = 'elapsed'; elapsed.id = 'elapsed';
        div.appendChild(elapsed);

        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;

        this.currentMsgEl = div;
        this.phasesEl = phasesContainer;
        this.currentAnswerEl = answer;
    },

    _finalizeAssistantMsg() {
        // 移除 typing cursor
        const answer = $('currentAnswer');
        if (answer) answer.classList.remove('typing-cursor');

        // 更新 toggle 文本
        const toggle = $('phasesToggle');
        if (toggle && this.phaseCount > 0) {
            toggle.innerHTML = '<span class="arrow">\u25b6</span> '+ico('chevron-right',12)+' 处理过程 ('+this.phaseCount+' 步, '+this.searchCount+' 次搜索)';
            toggle.classList.remove('expanded');
            const container = $('phasesContainer');
            if (container) container.classList.add('collapsed');
        } else if (toggle) {
            toggle.style.display = 'none';
        }

        // 移除 ID 避免冲突
        if (this.currentMsgEl) {
            this.currentMsgEl.removeAttribute('id');
        }
    },

    addThinking(text) {
        this.phaseCount++;
        const phases = this.phasesEl;
        if (this.currentPhaseType === 'thinking' && this.currentThinkingEl) {
            this.currentThinkingEl.textContent += text;
            this.currentThinkingEl.scrollTop = this.currentThinkingEl.scrollHeight;
            return;
        }
        this.currentPhaseType = 'thinking';
        const p = document.createElement('div'); p.className = 'phase';
        p.innerHTML = '<div class="phase-header thinking">'+ico('lightbulb',14)+' 思考中</div>';
        const box = document.createElement('div'); box.className = 'thinking-box'; box.textContent = text;
        p.appendChild(box); phases.appendChild(p);
        this.currentThinkingEl = box;
        $('messages').scrollTop = $('messages').scrollHeight;
    },

    addSearch(keywords, results) {
        this.phaseCount++; this.searchCount++;
        this.currentPhaseType = 'search';
        this.currentThinkingEl = null;
        const phases = this.phasesEl;
        const p = document.createElement('div'); p.className = 'phase';
        const h = document.createElement('div'); h.className = 'phase-header search';
        h.innerHTML = ico('search',14)+' 搜索';
        p.appendChild(h);
        const tags = document.createElement('div'); tags.className = 'search-tags';
        (keywords || []).forEach(k => { const t = document.createElement('span'); t.className = 'search-tag'; t.textContent = k; tags.appendChild(t); });
        p.appendChild(tags);
        phases.appendChild(p);
        $('messages').scrollTop = $('messages').scrollHeight;
    },

    addFetch(url) {
        this.phaseCount++;
        this.currentPhaseType = 'fetch';
        this.currentThinkingEl = null;
        const phases = this.phasesEl;
        const p = document.createElement('div'); p.className = 'phase';
        p.innerHTML = '<div class="phase-header fetch">'+ico('file-text',14)+' 读取: ' + esc((url||'').substring(0,80)) + '</div>';
        phases.appendChild(p);
        $('messages').scrollTop = $('messages').scrollHeight;
    },

    addPython(code) {
        this.phaseCount++;
        this.currentPhaseType = 'python';
        this.currentThinkingEl = null;
        const phases = this.phasesEl;
        const p = document.createElement('div'); p.className = 'phase';
        p.innerHTML = '<div class="phase-header python">'+ico('terminal',14)+' 执行 Python</div>';
        const box = document.createElement('div'); box.className = 'thinking-box'; box.textContent = code;
        p.appendChild(box); phases.appendChild(p);
        $('messages').scrollTop = $('messages').scrollHeight;
    },

    addCommand(cmd) {
        this.phaseCount++;
        this.currentPhaseType = 'command';
        this.currentThinkingEl = null;
        const phases = this.phasesEl;
        const p = document.createElement('div'); p.className = 'phase';
        p.innerHTML = '<div class="phase-header command">'+ico('zap',14)+' 执行命令</div>';
        const box = document.createElement('div'); box.className = 'thinking-box'; box.textContent = cmd;
        p.appendChild(box); phases.appendChild(p);
        $('messages').scrollTop = $('messages').scrollHeight;
    },

    addToolStart(name) {
        this.phaseCount++;
        this.currentPhaseType = 'tool';
        this.currentThinkingEl = null;
        const phases = this.phasesEl;
        const p = document.createElement('div'); p.className = 'phase';
        p.innerHTML = '<div class="phase-header tool">'+ico('wrench',14)+' '+esc(name)+'</div>';
        const box = document.createElement('div'); box.className = 'tool-box';
        box.innerHTML = `<div class="tool-name">${esc(name)}</div><div>执行中...</div>`;
        p.appendChild(box); phases.appendChild(p);
        $('messages').scrollTop = $('messages').scrollHeight;
    },

    addContent(text) {
        this.rawMarkdown += text;
        if (this.currentAnswerEl) {
            this.currentAnswerEl.innerHTML = marked.parse(this.rawMarkdown);
            $('messages').scrollTop = $('messages').scrollHeight;
        }
    },

    addUsage(info) {
        const usage = info.usage || {};
        const items = [];
        if (usage.prompt_tokens) items.push(`<span><span class="label">输入:</span> ${usage.prompt_tokens}</span>`);
        if (usage.completion_tokens) items.push(`<span><span class="label">输出:</span> ${usage.completion_tokens}</span>`);
        if (usage.total_tokens) items.push(`<span><span class="label">总计:</span> ${usage.total_tokens}</span>`);

        if (items.length && this.currentMsgEl) {
            const bar = document.createElement('div'); bar.className = 'usage-bar';
            bar.innerHTML = items.join(' ');
            // 插入到 elapsed 之前
            const elapsed = this.currentMsgEl.querySelector('.elapsed');
            if (elapsed) this.currentMsgEl.insertBefore(bar, elapsed);
            else this.currentMsgEl.appendChild(bar);
        }
    },

    startElapsed() {
        App.startTime = Date.now();
        clearInterval(App.elapsedInterval);
        App.elapsedInterval = setInterval(() => {
            const el = $('elapsed');
            if (!el) return;
            const s = Math.floor((Date.now() - App.startTime) / 1000);
            const m = Math.floor(s / 60);
            el.textContent = m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
        }, 1000);
    },

    stopElapsed() { clearInterval(App.elapsedInterval); },

    copyContent(btn) {
        const content = btn.getAttribute('data-content');
        navigator.clipboard.writeText(content).then(() => {
            btn.textContent = '已复制';
            setTimeout(() => btn.textContent = '复制', 1500);
        });
    },
};

// ===== Export Module =====
const Export = {
    async toPDF(messageId, mode) {
        try {
            const resp = await API.post('/api/export/pdf', { message_id: messageId, mode });
            if (!resp.ok) { UI.toast('导出失败', 'error'); return; }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = `questra_search_export_${mode}.pdf`;
            a.click(); URL.revokeObjectURL(url);
        } catch(e) { UI.toast('导出失败: ' + e.message, 'error'); }
    },

    showMenu(messageId, btn) {
        // 移除已有菜单
        document.querySelectorAll('.export-dropdown').forEach(e => e.remove());

        const dd = document.createElement('div');
        dd.className = 'export-dropdown';
        dd.innerHTML = `
            <button onclick="Export.toPDF(${messageId},'answer');this.parentElement.remove()">仅答案</button>
            <button onclick="Export.toPDF(${messageId},'full');this.parentElement.remove()">完整分析</button>
        `;
        btn.parentElement.style.position = 'relative';
        btn.parentElement.appendChild(dd);

        // 点击外部关闭
        setTimeout(() => {
            document.addEventListener('click', function close() {
                dd.remove(); document.removeEventListener('click', close);
            }, { once: true });
        }, 10);
    },

    showHeaderMenu(event) {
        event.stopPropagation();
        const msgId = Chat._lastAssistantMsgId;
        if (!msgId) { UI.toast('暂无消息可导出', 'error'); return; }

        document.querySelectorAll('.export-dropdown').forEach(e => e.remove());

        const btn = $('btnHeaderExport');
        const dd = document.createElement('div');
        dd.className = 'export-dropdown header-export-dropdown';
        dd.innerHTML = `<button onclick="Export.toPDF(${msgId},'answer');this.parentElement.remove()">仅答案</button>`
            + `<button onclick="Export.toPDF(${msgId},'full');this.parentElement.remove()">完整分析</button>`;
        btn.parentElement.style.position = 'relative';
        btn.parentElement.appendChild(dd);

        setTimeout(() => {
            document.addEventListener('click', function close() {
                dd.remove(); document.removeEventListener('click', close);
            }, { once: true });
        }, 10);
    },
};

// ===== UI Module =====
const UI = {
    toggleSidebar() {
        $('sidebar').classList.toggle('open');
        $('sidebarOverlay').classList.toggle('open');
    },

    closeSidebar() {
        $('sidebar').classList.remove('open');
        $('sidebarOverlay').classList.remove('open');
    },

    toggleModelMenu() {
        const dd = $('modelDropdown');
        dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
    },

    showSessionMenu(sessionId, btn) {
        // 移除已有菜单
        document.querySelectorAll('.session-menu').forEach(e => e.remove());

        const menu = document.createElement('div');
        menu.className = 'session-menu';
        menu.innerHTML = `
            <button onclick="UI.renameSession(${sessionId});this.parentElement.remove()">重命名</button>
            <button class="danger" onclick="UI.deleteSession(${sessionId});this.parentElement.remove()">删除</button>
        `;
        btn.parentElement.appendChild(menu);

        setTimeout(() => {
            document.addEventListener('click', function close() {
                menu.remove(); document.removeEventListener('click', close);
            }, { once: true });
        }, 10);
    },

    renameSession(sessionId) {
        const s = App.sessions.find(s => s.id === sessionId);
        if (!s) return;
        const newTitle = prompt('新名称:', s.title);
        if (newTitle && newTitle.trim()) {
            Sessions.rename(sessionId, newTitle.trim());
        }
    },

    deleteSession(sessionId) {
        if (confirm('确定删除这个会话？')) {
            Sessions.delete(sessionId);
        }
    },

    toast(msg, type) {
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();
        const el = document.createElement('div');
        el.className = 'toast' + (type ? ' ' + type : '');
        el.textContent = msg;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    },
};

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    const inputEl = $('input');

    // --- IME-safe Enter-to-send using contenteditable ---
    // contenteditable's beforeinput distinguishes IME Enter (insertFromComposition)
    // from regular Enter (insertParagraph), unlike textarea where both are insertLineBreak.

    // Auto-scroll when content grows
    inputEl.addEventListener('input', function() {
        this.scrollTop = this.scrollHeight;
    });

    // Strip formatting on paste (plain text only)
    inputEl.addEventListener('paste', e => {
        e.preventDefault();
        const text = (e.clipboardData || window.clipboardData).getData('text/plain');
        document.getSelection().deleteFromDocument();
        document.getSelection().getRangeAt(0).insertNode(document.createTextNode(text));
        // Move cursor to end of pasted text
        const sel = window.getSelection();
        sel.collapseToEnd();
    });

    // --- Enter-to-send with IME safety ---
    // contenteditable's beforeinput gives distinct inputType:
    //   insertParagraph/insertLineBreak = regular Enter → send
    //   insertFromComposition/insertCompositionText = IME → ignore
    let enterHandled = false;

    inputEl.addEventListener('beforeinput', e => {
        if (e.inputType === 'insertParagraph' || e.inputType === 'insertLineBreak') {
            if (e.shiftKey || e.isComposing) return; // Shift+Enter or IME: let through
            enterHandled = true;
            e.preventDefault();
            Chat.send();
        }
        // insertFromComposition / insertCompositionText / insertText: let through
    });

    // keydown fallback: block IME Enter, handle send if beforeinput didn't fire
    inputEl.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey && !e.metaKey && !e.ctrlKey) {
            if (e.isComposing || e.keyCode === 229) { e.preventDefault(); return; }
            if (enterHandled) { enterHandled = false; e.preventDefault(); return; }
            // beforeinput didn't fire (old browser) — send directly
            e.preventDefault();
            Chat.send();
        }
    });
    // Login enter
    $('loginPass').addEventListener('keydown', e => {
        if (e.key === 'Enter') Auth.login();
    });
    // Register enter on last field
    $('regInviteCode').addEventListener('keydown', e => {
        if (e.key === 'Enter') Auth.register();
    });
    // Close model dropdown on outside click
    document.addEventListener('click', e => {
        if (!e.target.closest('.model-selector')) {
            $('modelDropdown').style.display = 'none';
        }
    });

    // 启动
    Auth.init();
});
