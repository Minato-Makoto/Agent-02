document.addEventListener('DOMContentLoaded', () => {
    const elements = {
        navItems: document.querySelectorAll('.nav-item'),
        viewSections: document.querySelectorAll('.view-section'),
        wsStatus: document.getElementById('ws-status'),
        statusText: document.querySelector('#ws-status .status-text'),
        sysUptime: document.getElementById('sys-uptime'),
        sysMemory: document.getElementById('sys-memory'),
        sysLlm: document.getElementById('sys-llm'),
        runtimeSummary: document.getElementById('runtime-summary'),
        liveLog: document.getElementById('live-log'),
        historyLog: document.getElementById('history-log'),
        btnRefreshLogs: document.getElementById('btn-refresh-logs'),
        chatMessages: document.getElementById('chat-messages'),
        chatInput: document.getElementById('chat-input'),
        btnSendChat: document.getElementById('btn-send-chat'),
        btnStopChat: document.getElementById('btn-stop-chat'),
        btnNewChat: document.getElementById('btn-new-chat'),
        sessionsList: document.getElementById('sessions-list'),
        consentsContainer: document.getElementById('consents-container'),
        consentBadge: document.getElementById('consent-badge'),
        modalBackdrop: document.getElementById('modal-backdrop'),
        consentModal: document.getElementById('consent-modal'),
        modalSkillName: document.getElementById('modal-skill-name'),
        modalSkillArgs: document.getElementById('modal-skill-args'),
        modalBtnApprove: document.getElementById('modal-btn-approve'),
        modalBtnDeny: document.getElementById('modal-btn-deny'),
        cfgProvider: document.getElementById('cfg-provider'),
        cfgModel: document.getElementById('cfg-model'),
        cfgBaseurl: document.getElementById('cfg-baseurl'),
        cfgLocalModel: document.getElementById('cfg-local-model'),
        cfgApikey: document.getElementById('cfg-apikey'),
        cfgSystemPrompt: document.getElementById('cfg-system-prompt'),
        cfgTelegramEnabled: document.getElementById('cfg-telegram-enabled'),
        cfgTelegram: document.getElementById('cfg-telegram'),
        cfgDiscordEnabled: document.getElementById('cfg-discord-enabled'),
        cfgDiscord: document.getElementById('cfg-discord'),
        cfgShellEnabled: document.getElementById('cfg-shell-enabled'),
        cfgWorkdir: document.getElementById('cfg-workdir'),
        runtimeHint: document.getElementById('runtime-hint'),
        btnSaveSettings: document.getElementById('btn-save-settings'),
    };

    const state = {
        ws: null,
        reconnectTimer: null,
        statusTimer: null,
        currentSessionId: localStorage.getItem('agent02_session') || crypto.randomUUID(),
        activeStreamContainer: null,
        streamBuffer: '',
        reasoningBuffer: '',
        isStreaming: false,
        activeConsentId: null,
        runtimeInfo: null,
        loadedConfig: null,
    };

    localStorage.setItem('agent02_session', state.currentSessionId);

    if (typeof marked !== 'undefined') {
        marked.setOptions({
            breaks: true,
            gfm: true,
            headerIds: false,
            mangle: false,
        });
    }

    function escapeHtml(text) {
        return String(text ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;',
        }[char]));
    }

    function renderMarkdown(text) {
        const source = String(text ?? '');
        const thinkMatch = source.match(/<think>\s*([\s\S]*?)\s*<\/think>\s*([\s\S]*)/i);
        if (thinkMatch) {
            return renderAssistantContent(thinkMatch[2] || '', thinkMatch[1] || '');
        }

        return renderMarkdownBody(source);
    }

    function renderMarkdownBody(text) {
        const safeInput = escapeHtml(text);
        if (typeof marked !== 'undefined') {
            return marked.parse(safeInput);
        }

        return safeInput.replace(/\n/g, '<br>');
    }

    function renderReasoningBlock(text) {
        if (!text || !text.trim()) return '';
        return `
            <div class="think-block">
                <div class="think-label">Thinking</div>
                <div class="think-text">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
            </div>
        `;
    }

    function renderAssistantContent(content, reasoning = '', includeCursor = false) {
        const reasoningHtml = renderReasoningBlock(reasoning);
        const contentHtml = renderMarkdownBody(content || '');
        const cursorHtml = includeCursor ? '<div class="streaming-cursor"></div>' : '';
        return `${reasoningHtml}${contentHtml}${cursorHtml}`;
    }

    function scrollToBottom(element) {
        if (!element) return;
        element.scrollTop = element.scrollHeight;
    }

    function formatDate(value) {
        if (!value) return 'Unknown';
        const normalized = String(value).replace(' ', 'T');
        const date = new Date(normalized);
        return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString();
    }

    function formatBytes(bytes) {
        return `${Math.round(bytes / (1024 * 1024))} MB`;
    }

    function formatUptime(seconds) {
        const total = Math.max(0, Math.floor(seconds));
        const hours = Math.floor(total / 3600).toString().padStart(2, '0');
        const minutes = Math.floor((total % 3600) / 60).toString().padStart(2, '0');
        const secs = (total % 60).toString().padStart(2, '0');
        return `${hours}:${minutes}:${secs}`;
    }

    function getFileNameFromPath(filePath) {
        if (!filePath) return '';
        return String(filePath).split(/[\\/]/).pop() || '';
    }

    function switchView(pageId) {
        elements.navItems.forEach((nav) => {
            nav.classList.toggle('active', nav.dataset.page === pageId);
        });

        elements.viewSections.forEach((section) => {
            section.classList.toggle('hidden', section.id !== `view-${pageId}`);
        });

        if (pageId === 'sessions') fetchSessions();
        if (pageId === 'logs') fetchHistoryLogs();
        if (pageId === 'consents') fetchConsents();
        if (pageId === 'settings') loadSettings();
        if (pageId === 'chat') {
            elements.chatInput.focus();
            scrollToBottom(elements.chatMessages);
        }
    }

    elements.navItems.forEach((nav) => {
        nav.addEventListener('click', () => switchView(nav.dataset.page));
    });

    function setConnectionState(connected) {
        elements.wsStatus.classList.toggle('status-online', connected);
        elements.wsStatus.classList.toggle('status-offline', !connected);
        elements.statusText.textContent = connected ? 'Agent Online' : 'Disconnected';
    }

    function appendLog(source, message, level = 'info') {
        const line = document.createElement('div');
        line.className = `log-entry ${level}`;
        line.innerHTML = `
            <span class="log-time">[${new Date().toLocaleTimeString()}]</span>
            <span class="log-source">[${escapeHtml(source)}]</span>
            <span class="log-msg">${escapeHtml(message)}</span>
        `;

        elements.liveLog.appendChild(line);
        while (elements.liveLog.children.length > 120) {
            elements.liveLog.removeChild(elements.liveLog.firstChild);
        }
        scrollToBottom(elements.liveLog.parentElement);
    }

    function appendChatMessage(role, text) {
        const wrapper = document.createElement('div');
        wrapper.className = `message ${role === 'user' ? 'user-message' : 'system-message'}`;
        wrapper.innerHTML = `
            <div class="avatar">${role === 'user' ? 'U' : '⚡'}</div>
            <div class="content markdown">${role === 'user' ? escapeHtml(text) : renderMarkdown(text)}</div>
        `;
        elements.chatMessages.appendChild(wrapper);
        scrollToBottom(elements.chatMessages);
        return wrapper.querySelector('.content');
    }

    function appendToolMessage(title, payload) {
        const card = document.createElement('div');
        card.className = 'message tool-message';
        card.innerHTML = `${escapeHtml(title)} <span style="color:var(--accent-cyan)">${escapeHtml(payload)}</span>`;
        elements.chatMessages.appendChild(card);
        scrollToBottom(elements.chatMessages);
    }

    function beginAssistantStream() {
        state.activeStreamContainer = appendChatMessage('assistant', '');
        state.activeStreamContainer.innerHTML = renderAssistantContent('', '', true);
        state.streamBuffer = '';
        state.reasoningBuffer = '';
    }

    function finishAssistantStream(finalText, finalReasoning = '') {
        if (!state.activeStreamContainer) return;
        state.activeStreamContainer.innerHTML = renderAssistantContent(finalText || '(no response)', finalReasoning);
        state.activeStreamContainer = null;
        state.streamBuffer = '';
        state.reasoningBuffer = '';
        setStreaming(false);
    }

    function handleChatStream(payload) {
        if (payload.sessionId !== state.currentSessionId) return;
        if (!state.activeStreamContainer) beginAssistantStream();

        if (payload.token) {
            if (payload.channel === 'reasoning') {
                state.reasoningBuffer += payload.token;
            } else {
                state.streamBuffer += payload.token;
            }
            state.activeStreamContainer.innerHTML = renderAssistantContent(state.streamBuffer, state.reasoningBuffer, true);
            scrollToBottom(elements.chatMessages);
        }

        if (payload.done) {
            finishAssistantStream(state.streamBuffer, state.reasoningBuffer);
        }
    }

    function setStreaming(value) {
        state.isStreaming = value;
        elements.chatInput.disabled = value;
        elements.btnSendChat.classList.toggle('hidden', value);
        elements.btnStopChat.classList.toggle('hidden', !value);
    }

    function connectWS() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws`;
        state.ws = new WebSocket(url);

        state.ws.addEventListener('open', () => {
            setConnectionState(true);
            appendLog('SYSTEM', 'WebSocket connected.');
            fetchConsents();
            fetchStatus();
        });

        state.ws.addEventListener('close', () => {
            setConnectionState(false);
            clearTimeout(state.reconnectTimer);
            state.reconnectTimer = setTimeout(connectWS, 3000);
        });

        state.ws.addEventListener('message', (event) => {
            try {
                handleSocketMessage(JSON.parse(event.data));
            } catch (error) {
                console.error('Failed to parse WebSocket payload', error);
            }
        });
    }

    function handleSocketMessage(message) {
        switch (message.type) {
            case 'log':
                appendLog(message.data?.source || 'system', message.data?.message || '', message.data?.level || 'info');
                break;
            case 'error':
                appendLog(message.data?.source || 'system', message.data?.error || 'Unknown error', 'error');
                break;
            case 'tool:call':
                if (message.data?.sessionId === state.currentSessionId) {
                    appendToolMessage(`Tool requested: ${message.data.name}`, JSON.stringify(message.data.args || {}));
                }
                break;
            case 'tool:result':
                if (message.data?.sessionId === state.currentSessionId) {
                    appendToolMessage('Tool result:', message.data.result || '');
                }
                break;
            case 'consent:request':
                openConsentModal(message.data);
                fetchConsents();
                break;
            case 'consent:resolve':
                if (state.activeConsentId === (message.data?.id || message.data?.consentId)) {
                    closeConsentModal();
                }
                fetchConsents();
                break;
            case 'chat:stream':
                handleChatStream(message.data || {});
                break;
            case 'chat:error':
                appendLog('CHAT', message.error || 'Unknown chat error', 'error');
                setStreaming(false);
                break;
            default:
                break;
        }
    }

    async function fetchStatus() {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();
            elements.sysUptime.textContent = formatUptime(status.uptime || 0);
            elements.sysMemory.textContent = formatBytes(status.memory?.rss || 0);
            elements.sysLlm.textContent = status.llm?.provider ? `${status.llm.provider} • ${status.llm.model || 'default'}` : 'Not configured';
            const runtime = status.runtime || {};
            elements.runtimeSummary.textContent = `${runtime.localModelCount || 0} local GGUF model(s) detected • workspace: ${runtime.workspace || 'unknown'}`;
        } catch (error) {
            elements.runtimeSummary.textContent = 'Failed to read runtime status';
        }
    }

    function startStatusPolling() {
        fetchStatus();
        clearInterval(state.statusTimer);
        state.statusTimer = setInterval(fetchStatus, 5000);
    }

    async function fetchHistoryLogs() {
        try {
            const response = await fetch('/api/logs?limit=200');
            const logs = await response.json();
            elements.historyLog.innerHTML = '';

            logs.forEach((entry) => {
                const line = document.createElement('div');
                line.className = `log-entry ${entry.level || 'info'}`;
                line.innerHTML = `
                    <span class="log-time">[${formatDate(entry.created_at)}]</span>
                    <span class="log-source">[${escapeHtml(entry.source || 'system')}]</span>
                    <span class="log-msg">${escapeHtml(entry.message || '')}</span>
                `;
                elements.historyLog.appendChild(line);
            });

            scrollToBottom(elements.historyLog.parentElement);
        } catch (error) {
            elements.historyLog.innerHTML = '<span class="text-danger">Failed to load logs.</span>';
        }
    }

    async function sendChat() {
        if (state.isStreaming) return;

        const message = elements.chatInput.value.trim();
        if (!message) return;

        if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
            appendLog('CHAT', 'Connection is not ready yet.', 'warn');
            return;
        }

        appendChatMessage('user', message);
        elements.chatInput.value = '';
        beginAssistantStream();
        setStreaming(true);

        state.ws.send(JSON.stringify({
            type: 'chat',
            sessionId: state.currentSessionId,
            text: message,
        }));
    }

    function stopChat() {
        if (!state.ws || state.ws.readyState !== WebSocket.OPEN || !state.isStreaming) {
            return;
        }

        state.ws.send(JSON.stringify({
            type: 'stop',
            sessionId: state.currentSessionId,
        }));
        appendLog('CHAT', 'Generation stopped by user.', 'warn');
        finishAssistantStream(state.streamBuffer, state.reasoningBuffer);
    }

    async function fetchConsents() {
        try {
            const response = await fetch('/api/consents');
            const consents = await response.json();
            renderConsents(consents);
        } catch (error) {
            console.error('Failed to load consents', error);
        }
    }

    function renderConsents(items) {
        elements.consentsContainer.innerHTML = '';
        const count = items.length;
        elements.consentBadge.textContent = String(count);
        elements.consentBadge.classList.toggle('hidden', count === 0);

        if (count === 0) {
            elements.consentsContainer.innerHTML = '<div class="empty-state">No pending approvals.</div>';
            return;
        }

        items.forEach((item) => {
            const card = document.createElement('div');
            card.className = 'consent-card glass-panel';
            card.innerHTML = `
                <div class="consent-details">
                    <h4>${escapeHtml(item.skillName || 'Unknown skill')}</h4>
                    <div class="consent-args">Session: ${escapeHtml(item.sessionId || '')}<br>Args: ${escapeHtml(JSON.stringify(item.args || {}, null, 2))}</div>
                </div>
                <div class="consent-actions">
                    <button class="btn btn-outline text-danger btn-deny">Deny</button>
                    <button class="btn btn-primary btn-approve">Approve</button>
                </div>
            `;

            card.querySelector('.btn-deny').addEventListener('click', () => answerConsent(item.id, false));
            card.querySelector('.btn-approve').addEventListener('click', () => answerConsent(item.id, true));
            elements.consentsContainer.appendChild(card);
        });
    }

    function openConsentModal(consent) {
        state.activeConsentId = consent.id || consent.consentId;
        elements.modalSkillName.textContent = consent.skillName || 'Unknown skill';
        elements.modalSkillArgs.textContent = JSON.stringify(consent.args || {}, null, 2);
        elements.modalBackdrop.classList.remove('hidden');
        elements.consentModal.classList.remove('hidden');
    }

    function closeConsentModal() {
        state.activeConsentId = null;
        elements.modalBackdrop.classList.add('hidden');
        elements.consentModal.classList.add('hidden');
    }

    async function answerConsent(id, approved) {
        try {
            await fetch(`/api/consents/${id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ approved }),
            });
            closeConsentModal();
            fetchConsents();
        } catch (error) {
            appendLog('CONSENT', 'Failed to submit approval.', 'error');
        }
    }

    async function fetchSessions() {
        try {
            const response = await fetch('/api/sessions');
            const sessions = await response.json();
            elements.sessionsList.innerHTML = '';

            if (sessions.length === 0) {
                elements.sessionsList.innerHTML = '<tr><td colspan="6" class="text-center p-4">No sessions yet.</td></tr>';
                return;
            }

            sessions.forEach((session) => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td class="font-mono text-xs">${escapeHtml(session.id)}</td>
                    <td>${escapeHtml((session.platform || '').toUpperCase())}</td>
                    <td>${escapeHtml(session.displayName || session.userId || 'Unknown')}</td>
                    <td>${escapeHtml(String(session.messageCount || 0))}</td>
                    <td>${escapeHtml(formatDate(session.updatedAt))}</td>
                    <td><button class="btn btn-outline text-xs">Continue Here</button></td>
                `;

                row.querySelector('button').addEventListener('click', () => openSession(session.id));
                elements.sessionsList.appendChild(row);
            });
        } catch (error) {
            elements.sessionsList.innerHTML = '<tr><td colspan="6" class="text-danger text-center p-4">Failed to load sessions.</td></tr>';
        }
    }

    async function openSession(sessionId) {
        try {
            const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
            const messages = await response.json();
            state.currentSessionId = sessionId;
            localStorage.setItem('agent02_session', state.currentSessionId);
            elements.chatMessages.innerHTML = '';

            messages.forEach((message) => {
                if (message.role === 'tool') {
                    appendToolMessage('Tool result:', message.content);
                    return;
                }

                if (message.role === 'assistant' || message.role === 'system') {
                    appendChatMessage('assistant', message.content);
                    return;
                }

                appendChatMessage('user', message.content);
            });

            if (messages.length === 0) {
                appendChatMessage('assistant', 'This session is empty.');
            }

            switchView('chat');
        } catch (error) {
            appendLog('SESSIONS', 'Failed to open the selected session.', 'error');
        }
    }

    function fillLocalModels(runtimeInfo, selectedPath) {
        elements.cfgLocalModel.innerHTML = '<option value="">Choose a detected model</option>';

        const models = runtimeInfo?.localModels || [];
        if (models.length === 0) {
            elements.cfgLocalModel.innerHTML = '<option value="">No GGUF models found</option>';
            return;
        }

        models.forEach((model) => {
            const option = document.createElement('option');
            option.value = model.path;
            option.textContent = `${model.name} • ${(model.sizeBytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
            option.selected = model.path === selectedPath;
            elements.cfgLocalModel.appendChild(option);
        });
    }

    function updateProviderUI() {
        const provider = elements.cfgProvider.value;
        const isLlamaCpp = provider === 'llamacpp';
        const isCloud = !['llamacpp', 'ollama'].includes(provider);

        elements.cfgLocalModel.disabled = !isLlamaCpp;
        elements.cfgApikey.placeholder = isLlamaCpp
            ? 'Path to a .gguf model file'
            : isCloud
                ? 'Paste your API key'
                : 'Leave empty unless your provider needs a token';

        if (isLlamaCpp && elements.cfgLocalModel.value) {
            elements.cfgApikey.value = elements.cfgLocalModel.value;
            if (!elements.cfgModel.value.trim()) {
                elements.cfgModel.value = getFileNameFromPath(elements.cfgLocalModel.value);
            }
        }
    }

    async function loadSettings() {
        try {
            const [configResponse, runtimeResponse] = await Promise.all([
                fetch('/api/config'),
                fetch('/api/runtime'),
            ]);

            state.loadedConfig = await configResponse.json();
            state.runtimeInfo = await runtimeResponse.json();

            const cfg = state.loadedConfig;
            elements.cfgProvider.value = cfg.llm.provider || 'llamacpp';
            const localModelName = getFileNameFromPath(cfg.llm.ggufPath || '');
            elements.cfgModel.value = cfg.llm.model || (cfg.llm.provider === 'llamacpp' ? localModelName : '');
            elements.cfgBaseurl.value = cfg.llm.baseUrl || '';
            elements.cfgApikey.value = cfg.llm.provider === 'llamacpp' ? (cfg.llm.ggufPath || '') : '';
            elements.cfgApikey.dataset.maskedValue = cfg.llm.apiKeyMasked || '';
            elements.cfgSystemPrompt.value = cfg.llm.systemPrompt || '';
            elements.cfgTelegramEnabled.checked = !!cfg.connectors.telegram.enabled;
            elements.cfgTelegram.value = '';
            elements.cfgTelegram.placeholder = cfg.connectors.telegram.tokenMasked || 'Telegram bot token';
            elements.cfgDiscordEnabled.checked = !!cfg.connectors.discord.enabled;
            elements.cfgDiscord.value = '';
            elements.cfgDiscord.placeholder = cfg.connectors.discord.tokenMasked || 'Discord bot token';
            elements.cfgShellEnabled.checked = !!cfg.skills.shellEnabled;
            elements.cfgWorkdir.value = cfg.security.allowedWorkDir || '';

            fillLocalModels(state.runtimeInfo, cfg.llm.ggufPath);
            updateProviderUI();

            elements.runtimeHint.innerHTML = `
                llama.cpp folder: ${escapeHtml(state.runtimeInfo.llamaCppDir || 'not found')}<br>
                Models folder: ${escapeHtml(state.runtimeInfo.modelsDir || 'not found')}<br>
                Messenger connector changes may require an app restart.
            `;
        } catch (error) {
            elements.runtimeHint.textContent = 'Failed to load settings.';
        }
    }

    async function saveSettings() {
        const payload = {
            llm: {
                provider: elements.cfgProvider.value,
                model: elements.cfgModel.value.trim(),
                baseUrl: elements.cfgBaseurl.value.trim(),
                systemPrompt: elements.cfgSystemPrompt.value.trim(),
            },
            connectors: {
                telegram: {
                    enabled: elements.cfgTelegramEnabled.checked,
                },
                discord: {
                    enabled: elements.cfgDiscordEnabled.checked,
                },
            },
            skills: {
                shellEnabled: elements.cfgShellEnabled.checked,
            },
            security: {
                allowedWorkDir: elements.cfgWorkdir.value.trim(),
            },
        };

        const provider = payload.llm.provider;
        const enteredKeyOrPath = elements.cfgApikey.value.trim();
        const selectedLocalModel = elements.cfgLocalModel.value;

        if (provider === 'llamacpp') {
            payload.llm.ggufPath = enteredKeyOrPath || selectedLocalModel || state.loadedConfig?.llm?.ggufPath || '';
            payload.llm.model = payload.llm.model || getFileNameFromPath(payload.llm.ggufPath);
        } else if (enteredKeyOrPath) {
            payload.llm.apiKey = enteredKeyOrPath;
        }

        const telegramToken = elements.cfgTelegram.value.trim();
        const discordToken = elements.cfgDiscord.value.trim();
        if (telegramToken) payload.connectors.telegram.token = telegramToken;
        if (discordToken) payload.connectors.discord.token = discordToken;

        const button = elements.btnSaveSettings;
        const originalLabel = button.textContent;
        button.textContent = 'Saving...';
        button.disabled = true;

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const result = await response.json();
            state.loadedConfig = result.config || state.loadedConfig;
            button.textContent = 'Saved';
            appendLog('SETTINGS', 'Configuration updated.', 'info');
            await loadSettings();
            await fetchStatus();
        } catch (error) {
            button.textContent = 'Save Failed';
            appendLog('SETTINGS', 'Failed to save configuration.', 'error');
        } finally {
            setTimeout(() => {
                button.textContent = originalLabel;
                button.disabled = false;
            }, 1200);
        }
    }

    elements.btnRefreshLogs.addEventListener('click', fetchHistoryLogs);
    elements.btnSendChat.addEventListener('click', sendChat);
    elements.btnStopChat.addEventListener('click', stopChat);
    elements.btnNewChat.addEventListener('click', () => {
        state.currentSessionId = crypto.randomUUID();
        localStorage.setItem('agent02_session', state.currentSessionId);
        elements.chatMessages.innerHTML = '';
        appendChatMessage('assistant', 'New session started. Ask anything.');
    });
    elements.chatInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendChat();
        }
    });
    elements.modalBtnApprove.addEventListener('click', () => state.activeConsentId && answerConsent(state.activeConsentId, true));
    elements.modalBtnDeny.addEventListener('click', () => state.activeConsentId && answerConsent(state.activeConsentId, false));
    elements.cfgProvider.addEventListener('change', updateProviderUI);
    elements.cfgLocalModel.addEventListener('change', () => {
        if (elements.cfgProvider.value === 'llamacpp' && elements.cfgLocalModel.value) {
            elements.cfgApikey.value = elements.cfgLocalModel.value;
            elements.cfgModel.value = getFileNameFromPath(elements.cfgLocalModel.value);
        }
    });
    elements.btnSaveSettings.addEventListener('click', saveSettings);

    connectWS();
    startStatusPolling();
    fetchHistoryLogs();
    fetchConsents();
});
