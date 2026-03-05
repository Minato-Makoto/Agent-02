// Agent-02 Web Control UI Logic
// Powered by Vanilla JS & WebSockets

document.addEventListener('DOMContentLoaded', () => {
    // ── DOM Elements ──
    const elements = {
        navItems: document.querySelectorAll('.nav-item'),
        viewSections: document.querySelectorAll('.view-section'),

        // Status & Stats
        wsStatus: document.getElementById('ws-status'),
        statusText: document.querySelector('#ws-status .status-text'),
        sysUptime: document.getElementById('sys-uptime'),
        sysMemory: document.getElementById('sys-memory'),
        sysLlm: document.getElementById('sys-llm'),

        // Logs
        liveLog: document.getElementById('live-log'),
        historyLog: document.getElementById('history-log'),
        btnRefreshLogs: document.getElementById('btn-refresh-logs'),

        // Chat
        chatMessages: document.getElementById('chat-messages'),
        chatInput: document.getElementById('chat-input'),
        btnSendChat: document.getElementById('btn-send-chat'),
        btnStopChat: document.getElementById('btn-stop-chat'),
        btnNewChat: document.getElementById('btn-new-chat'),

        // Sessions
        sessionsList: document.getElementById('sessions-list'),

        // Consents
        consentsContainer: document.getElementById('consents-container'),
        consentBadge: document.getElementById('consent-badge'),
        modalBackdrop: document.getElementById('modal-backdrop'),
        consentModal: document.getElementById('consent-modal'),
        modalSkillName: document.getElementById('modal-skill-name'),
        modalSkillArgs: document.getElementById('modal-skill-args'),
        modalBtnApprove: document.getElementById('modal-btn-approve'),
        modalBtnDeny: document.getElementById('modal-btn-deny'),

        // Settings
        cfgProvider: document.getElementById('cfg-provider'),
        cfgModel: document.getElementById('cfg-model'),
        cfgApikey: document.getElementById('cfg-apikey'),
        cfgBaseurl: document.getElementById('cfg-baseurl'),
        cfgTelegram: document.getElementById('cfg-telegram'),
        cfgDiscord: document.getElementById('cfg-discord'),
        cfgShellEnabled: document.getElementById('cfg-shell-enabled'),
        btnSaveSettings: document.getElementById('btn-save-settings')
    };

    let ws = null;
    let reconnectTimer = null;
    let currentSessionId = localStorage.getItem('agent02_session') || crypto.randomUUID();
    let isStreaming = false;
    let activeConsentId = null;

    // Save session ID so refresh doesn't lose context
    localStorage.setItem('agent02_session', currentSessionId);

    // Set marked.js options for safe rendering
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            breaks: true,
            gfm: true
        });
    }

    // ── Navigation (SPA logic) ──
    function switchView(pageId) {
        // Update nav styling
        elements.navItems.forEach(nav => {
            if (nav.dataset.page === pageId) nav.classList.add('active');
            else nav.classList.remove('active');
        });

        // Switch sections
        elements.viewSections.forEach(section => {
            if (section.id === `view-${pageId}`) section.classList.remove('hidden');
            else section.classList.add('hidden');
        });

        // Trigger data fetches based on view
        if (pageId === 'sessions') fetchSessions();
        if (pageId === 'logs') fetchHistoryLogs();
        if (pageId === 'settings') loadSettings();
        if (pageId === 'chat') {
            elements.chatInput.focus();
            scrollToBottom(elements.chatMessages);
        }
    }

    elements.navItems.forEach(nav => {
        nav.addEventListener('click', (e) => {
            // Find the closest button in case they clicked an inner span
            const btn = e.target.closest('button.nav-item');
            if (btn) switchView(btn.dataset.page);
        });
    });

    // ── WebSocket Connection Manager ──
    function connectWS() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('[WS] Connected to Agent-02');
            elements.wsStatus.classList.remove('status-offline');
            elements.wsStatus.classList.add('status-online');
            elements.statusText.textContent = 'Agent Online';
            appendLog('SYSTEM', 'Neural link established. WebSocket connected.', 'info');

            // Re-fetch consents purely to update badge
            fetchConsents();
            fetchSystemStats();
        };

        ws.onclose = () => {
            console.log('[WS] Disconnected. Reconnecting in 3s...');
            elements.wsStatus.classList.add('status-offline');
            elements.wsStatus.classList.remove('status-online');
            elements.statusText.textContent = 'Disconnected';

            clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(connectWS, 3000);
        };

        ws.onerror = (err) => {
            console.error('[WS] Error:', err);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleSocketMessage(data);
            } catch (err) {
                console.error('[WS] Failed to parse message:', err);
            }
        };
    }

    function handleSocketMessage(msg) {
        switch (msg.type) {
            case 'log':
                appendLog(msg.source, msg.message, msg.level);
                break;
            case 'chat:stream':
                handleChatStream(msg.text, msg.done);
                break;
            case 'chat:error':
                appendChatMessage('System', `Error: ${msg.error}`, 'error');
                uiSetStreaming(false);
                break;
            case 'chat:tool':
                appendToolItem(msg.text);
                break;
            case 'consent:request':
                // The backend asks for permission
                handleConsentRequest(msg.data);
                break;
            default:
                console.log('Unknown WS msg:', msg);
        }
    }

    // ── System Stats ──
    let uptimeStart = Date.now();
    function fetchSystemStats() {
        setInterval(() => {
            // Update Fake Uptime
            const diff = Math.floor((Date.now() - uptimeStart) / 1000);
            const hrs = Math.floor(diff / 3600).toString().padStart(2, '0');
            const mins = Math.floor((diff % 3600) / 60).toString().padStart(2, '0');
            const secs = (diff % 60).toString().padStart(2, '0');
            elements.sysUptime.textContent = `${hrs}:${mins}:${secs}`;

            // Wait for endpoint or use mock memory stats
            if (window.performance && window.performance.memory) {
                const mb = Math.round(window.performance.memory.usedJSHeapSize / (1024 * 1024));
                elements.sysMemory.textContent = `${mb} MB`;
            } else {
                elements.sysMemory.textContent = `${Math.floor(Math.random() * 20 + 85)} MB`; // visual pseudo fallback
            }
        }, 1000);
    }

    // ── Logs ──
    function appendLog(source, message, level = 'info') {
        const time = new Date().toLocaleTimeString();
        const div = document.createElement('div');
        div.className = `log-entry ${level}`;
        div.innerHTML = `
            <span class="log-time">[${time}]</span>
            <span class="log-source">[${source}]</span>
            <span class="log-msg">${formatLogText(message)}</span>
        `;

        elements.liveLog.appendChild(div);

        // Auto-scroll but keep maximum 100 lines
        if (elements.liveLog.children.length > 100) {
            elements.liveLog.removeChild(elements.liveLog.firstChild);
        }
        scrollToBottom(elements.liveLog.parentElement);

        // Also stick to dashboard view if they are there
        const dbStat = document.getElementById('sys-llm');
        if (source === 'llm' && message.includes('Model')) {
            dbStat.textContent = message.split(' ')[0] || 'Active';
        }
    }

    function formatLogText(text) {
        // Simple HTML escape
        const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
        return text.replace(/[&<>"']/g, function (m) { return map[m]; });
    }

    async function fetchHistoryLogs() {
        try {
            elements.historyLog.innerHTML = 'Loading history...';
            const res = await fetch('/api/logs?limit=200');
            const logs = await res.json();

            elements.historyLog.innerHTML = '';
            logs.reverse().forEach(log => {
                const date = new Date(log.timestamp).toLocaleString();
                const div = document.createElement('div');
                div.className = `log-entry ${log.level}`;
                div.innerHTML = `
                    <span class="log-time">[${date}]</span>
                    <span class="log-source">[${log.source}]</span>
                    <span class="log-msg">${formatLogText(log.message)}</span>
                `;
                elements.historyLog.appendChild(div);
            });
            scrollToBottom(elements.historyLog.parentElement);
        } catch (e) {
            elements.historyLog.innerHTML = '<span class="text-danger">Failed to load logs.</span>';
        }
    }
    elements.btnRefreshLogs.addEventListener('click', fetchHistoryLogs);

    // ── Chat Flow ──
    let activeStreamMsgContainer = null;
    let mdRawText = '';

    function uiSetStreaming(isStreamingState) {
        isStreaming = isStreamingState;
        elements.chatInput.disabled = isStreamingState;

        if (isStreamingState) {
            elements.btnSendChat.classList.add('hidden');
            elements.btnStopChat.classList.remove('hidden');
        } else {
            elements.btnSendChat.classList.remove('hidden');
            elements.btnStopChat.classList.add('hidden');
            setTimeout(() => elements.chatInput.focus(), 100);
        }
    }

    async function sendChat() {
        if (isStreaming) return;
        const msg = elements.chatInput.value.trim();
        if (!msg) return;

        // Display user msg
        appendChatMessage('User', msg, 'user');
        elements.chatInput.value = '';

        // Setup UI for incoming stream
        uiSetStreaming(true);
        activeStreamMsgContainer = createIncomingMessageBlock();
        mdRawText = '';

        // Send to backend via REST (or WS). Using REST allows easy streaming response handling via WS
        try {
            // Note: chat goes over socket via API fallback or dedicated WS command?
            // Since backend server.ts doesn't have POST /api/chat anymore, we send via WebSocket!
            ws.send(JSON.stringify({
                type: 'chat',
                userId: currentSessionId,
                sessionId: currentSessionId,
                message: msg
            }));

        } catch (e) {
            console.error('Send error:', e);
            appendChatMessage('System', 'Failed to send message: network error', 'error');
            uiSetStreaming(false);
        }
    }

    function appendChatMessage(sender, text, role) {
        const div = document.createElement('div');
        div.className = `message ${role}-message`;

        let avatar = role === 'user' ? 'U' : '⚡';
        let parsed = role === 'user' ? formatLogText(text) : (typeof marked !== 'undefined' ? marked.parse(text) : text);

        div.innerHTML = `
            <div class="avatar">${avatar}</div>
            <div class="content markdown">${parsed}</div>
        `;
        elements.chatMessages.appendChild(div);
        scrollToBottom(elements.chatMessages);
    }

    function appendToolItem(text) {
        // Just inject a small tool use notification above the active stream
        if (!activeStreamMsgContainer) activeStreamMsgContainer = createIncomingMessageBlock();
        const parent = activeStreamMsgContainer.parentNode;

        const div = document.createElement('div');
        div.className = `message tool-message`;
        div.innerHTML = `🛠 Executing tool: <span style="color:var(--accent-cyan)">${formatLogText(text)}</span>`;
        parent.insertBefore(div, activeStreamMsgContainer);
        scrollToBottom(elements.chatMessages);
    }

    function createIncomingMessageBlock() {
        const div = document.createElement('div');
        div.className = `message system-message`;
        div.innerHTML = `
            <div class="avatar">⚡</div>
            <div class="content markdown"><div class="streaming-cursor"></div></div>
        `;
        elements.chatMessages.appendChild(div);
        scrollToBottom(elements.chatMessages);
        return div.querySelector('.content.markdown');
    }

    function handleChatStream(chunk, isDone) {
        if (!activeStreamMsgContainer) {
            activeStreamMsgContainer = createIncomingMessageBlock();
            mdRawText = '';
        }

        if (chunk) mdRawText += chunk;

        if (isDone) {
            if (typeof marked !== 'undefined') {
                activeStreamMsgContainer.innerHTML = marked.parse(mdRawText);
            } else {
                activeStreamMsgContainer.innerText = mdRawText;
            }
            activeStreamMsgContainer = null;
            uiSetStreaming(false);
        } else {
            // Live render with cursor
            if (typeof marked !== 'undefined') {
                activeStreamMsgContainer.innerHTML = marked.parse(mdRawText) + '<div class="streaming-cursor"></div>';
            } else {
                activeStreamMsgContainer.innerText = mdRawText + '...';
            }
        }
        scrollToBottom(elements.chatMessages);
    }

    function stopChat() {
        if (ws && isStreaming) {
            ws.send(JSON.stringify({ type: 'abort' }));
            uiSetStreaming(false);
            if (activeStreamMsgContainer) {
                const cursor = activeStreamMsgContainer.querySelector('.streaming-cursor');
                if (cursor) cursor.remove();
                activeStreamMsgContainer = null;
            }
            appendLog('SYSTEM', 'Chat generation aborted by user', 'warn');
        }
    }

    elements.btnSendChat.addEventListener('click', sendChat);
    elements.btnStopChat.addEventListener('click', stopChat);
    elements.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChat();
        }
    });
    elements.btnNewChat.addEventListener('click', () => {
        elements.chatMessages.innerHTML = `
            <div class="message system-message">
                <div class="avatar">⚡</div>
                <div class="content markdown"><p>New session started. How can I assist you?</p></div>
            </div>`;
        currentSessionId = crypto.randomUUID();
        localStorage.setItem('agent02_session', currentSessionId);
    });

    // ── Consents Flow ──
    async function fetchConsents() {
        try {
            const res = await fetch('/api/consents');
            const items = await res.json();
            renderConsents(items);

            // Update badge (filter only pending)
            const count = items.length;
            elements.consentBadge.textContent = count;
            if (count > 0) elements.consentBadge.classList.remove('hidden');
            else elements.consentBadge.classList.add('hidden');

        } catch (err) {
            console.error('Fetch consents error:', err);
        }
    }

    function renderConsents(items) {
        elements.consentsContainer.innerHTML = '';
        if (items.length === 0) {
            elements.consentsContainer.innerHTML = '<div class="empty-state">No pending requests.</div>';
            return;
        }

        items.forEach(req => {
            const div = document.createElement('div');
            div.className = 'consent-card glass-panel';
            div.innerHTML = `
                <div class="consent-details">
                    <h4>Action Request #${req.id.substring(0, 8)}</h4>
                    <div class="consent-args">Skill: ${req.toolName}<br>Params: ${JSON.stringify(req.args)}</div>
                </div>
                <div class="consent-actions">
                    <button class="btn btn-outline text-danger btn-deny" data-id="${req.id}">Deny</button>
                    <button class="btn btn-primary btn-approve" data-id="${req.id}">Approve</button>
                </div>
            `;
            elements.consentsContainer.appendChild(div);
        });

        // Bind buttons
        elements.consentsContainer.querySelectorAll('.btn-deny').forEach(b => b.addEventListener('click', (e) => answerConsent(e.target.dataset.id, false)));
        elements.consentsContainer.querySelectorAll('.btn-approve').forEach(b => b.addEventListener('click', (e) => answerConsent(e.target.dataset.id, true)));
    }

    function handleConsentRequest(req) {
        // Pop modal if not already open
        activeConsentId = req.id;
        elements.modalSkillName.textContent = req.toolName;
        elements.modalSkillArgs.textContent = JSON.stringify(req.args, null, 2);

        elements.modalBackdrop.classList.remove('hidden');
        elements.consentModal.classList.remove('hidden');

        // Also background update the list
        fetchConsents();
    }

    async function answerConsent(id, isApproved) {
        try {
            await fetch(`/api/consents/${id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ approved: isApproved })
            });

            // Hide modal if it was this one
            if (activeConsentId === id) {
                elements.modalBackdrop.classList.add('hidden');
                elements.consentModal.classList.add('hidden');
                activeConsentId = null;
            }

            fetchConsents();
        } catch (e) {
            console.error("Failed to answer consent:", e);
        }
    }

    elements.modalBtnApprove.addEventListener('click', () => answerConsent(activeConsentId, true));
    elements.modalBtnDeny.addEventListener('click', () => answerConsent(activeConsentId, false));

    // ── Sessions Flow ──
    async function fetchSessions() {
        try {
            elements.sessionsList.innerHTML = '<tr><td colspan="5" class="text-center p-4">Loading sessions...</td></tr>';
            const res = await fetch('/api/sessions');
            const data = await res.json();

            elements.sessionsList.innerHTML = '';
            if (data.length === 0) {
                elements.sessionsList.innerHTML = '<tr><td colspan="5" class="text-center p-4">No active sessions.</td></tr>';
                return;
            }

            data.forEach(s => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="font-mono text-xs">${s.id}</td>
                    <td><span class="badge ${s.platform === 'web' ? 'badge-secure' : ''}">${s.platform.toUpperCase()}</span></td>
                    <td>${s.userId}</td>
                    <td>${new Date(s.updatedAt).toLocaleString()}</td>
                    <td>
                        <button class="btn btn-outline text-xs" onclick="alert('Viewing session history not implemented in this demo')">View Logs</button>
                    </td>
                `;
                elements.sessionsList.appendChild(tr);
            });
        } catch (e) {
            elements.sessionsList.innerHTML = '<tr><td colspan="5" class="text-danger text-center p-4">Failed to load</td></tr>';
        }
    }

    // ── Settings Flow ──
    async function loadSettings() {
        try {
            const res = await fetch('/api/config');
            const cfg = await res.json();

            elements.cfgProvider.value = cfg.llm?.provider || 'ollama';
            elements.cfgModel.value = cfg.llm?.model || '';
            elements.cfgBaseurl.value = cfg.llm?.baseUrl || '';

            elements.cfgShellEnabled.checked = cfg.skills?.shell === true;

            // Mask keys
            elements.cfgApikey.value = cfg.llm?.apiKey ? '********' : '';
            elements.cfgTelegram.value = cfg.connectors?.telegram?.token ? '********' : '';
            elements.cfgDiscord.value = cfg.connectors?.discord?.token ? '********' : '';
        } catch (err) {
            console.error('Failed to load settings', err);
        }
    }

    elements.btnSaveSettings.addEventListener('click', async () => {
        const btn = elements.btnSaveSettings;
        const oldText = btn.textContent;
        btn.textContent = 'Saving...';
        btn.disabled = true;

        const partialCfg = {
            llm: {
                provider: elements.cfgProvider.value,
                model: elements.cfgModel.value,
            },
            skills: {
                shell: elements.cfgShellEnabled.checked
            }
        };

        if (elements.cfgBaseurl.value) partialCfg.llm.baseUrl = elements.cfgBaseurl.value;
        if (elements.cfgApikey.value && elements.cfgApikey.value !== '********') {
            partialCfg.llm.apiKey = elements.cfgApikey.value;
        }

        // Also connectors if updated
        if ((elements.cfgTelegram.value && elements.cfgTelegram.value !== '********') ||
            (elements.cfgDiscord.value && elements.cfgDiscord.value !== '********')) {
            partialCfg.connectors = {
                telegram: { token: elements.cfgTelegram.value !== '********' ? elements.cfgTelegram.value : undefined },
                discord: { token: elements.cfgDiscord.value !== '********' ? elements.cfgDiscord.value : undefined }
            }
        }

        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(partialCfg)
            });
            btn.textContent = 'Saved!';
            btn.classList.add('btn-success');
            setTimeout(() => {
                btn.textContent = oldText;
                btn.classList.remove('btn-success');
                btn.disabled = false;
            }, 2000);
        } catch (err) {
            btn.textContent = 'Save Failed';
            setTimeout(() => {
                btn.textContent = oldText;
                btn.disabled = false;
            }, 2000);
        }
    });

    // ── Helper ──
    function scrollToBottom(elem) {
        if (!elem) return;
        elem.scrollTop = elem.scrollHeight;
    }

    // ── Boot ──
    connectWS();
    fetchSystemStats();
});
