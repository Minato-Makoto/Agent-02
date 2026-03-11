(function () {
    'use strict';

    const refs = {
        chatMessages: document.getElementById('chat-messages'),
        chatContainer: document.getElementById('chat-container'),
        chatInput: document.getElementById('chat-input'),
        btnSend: document.getElementById('btn-send'),
        btnReset: document.getElementById('btn-reset'),
        statusBadge: document.getElementById('status-badge'),
        gatewayPill: document.getElementById('gateway-pill'),
        backendPill: document.getElementById('backend-pill'),
        modelSelect: document.getElementById('model-select'),
        panelModelSelect: document.getElementById('panel-model-select'),
        availableModels: document.getElementById('available-models'),
        welcome: document.getElementById('welcome'),
        modelOverlay: document.getElementById('model-overlay'),
        overlayModelSelect: document.getElementById('overlay-model-select'),
        overlayConfirm: document.getElementById('overlay-confirm'),
        sessionList: document.getElementById('session-list'),
        btnRefreshSessions: document.getElementById('btn-refresh-sessions'),
        btnRefreshChannels: document.getElementById('btn-refresh-channels'),
        btnRefreshPairing: document.getElementById('btn-refresh-pairing'),
        currentSessionTitle: document.getElementById('current-session-title'),
        currentSessionChannel: document.getElementById('current-session-channel'),
        currentSessionMeta: document.getElementById('current-session-meta'),
        settingsGateway: document.getElementById('settings-gateway'),
        settingsBackend: document.getElementById('settings-backend'),
        settingsConnections: document.getElementById('settings-connections'),
        settingsWorkspace: document.getElementById('settings-workspace'),
        sessionDetail: document.getElementById('session-detail'),
        channelCards: document.getElementById('channel-cards'),
        pairingPending: document.getElementById('pairing-pending'),
        pairingApproved: document.getElementById('pairing-approved'),
        btnApplyModel: document.getElementById('btn-apply-model'),
        dockTabs: Array.from(document.querySelectorAll('.dock-tab')),
        dockPanels: Array.from(document.querySelectorAll('.dock-panel')),
    };

    const CHANNELS = ['telegram', 'discord', 'zalo'];
    const TOKEN_FIELDS = { telegram: 'botToken', discord: 'token', zalo: 'botToken' };
    const state = {
        ws: null,
        reconnectAttempts: 0,
        currentSessionKey: 'agent:main:main',
        selectedModelId: '',
        modelRequired: false,
        currentAssistantEl: null,
        currentAssistantTextEl: null,
        currentReasoningEl: null,
        currentReasoningTextEl: null,
        currentStatusEl: null,
        currentToolTextEl: null,
        currentTranscriptSignature: '',
        sessions: [],
        health: null,
        channelStates: {},
        pairing: null,
        streaming: false,
    };
    const MAX_RECONNECT = 10;
    const RECONNECT_DELAY = 2000;
    const TRANSCRIPT_POLL_MS = 6000;
    const SESSIONS_POLL_MS = 10000;
    const HEALTH_POLL_MS = 15000;
    const ADMIN_POLL_MS = 20000;

    function connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        state.ws = new WebSocket(`${protocol}//${location.host}/ws`);

        state.ws.onopen = () => {
            state.reconnectAttempts = 0;
            setStatus('Connected', 'connected');
            send({ type: 'hello', payload: { client_type: 'webui' } });
            attachSession(state.currentSessionKey);
        };

        state.ws.onmessage = (event) => {
            try {
                handleMessage(JSON.parse(event.data));
            } catch (error) {
                console.error('Invalid message:', error);
            }
        };

        state.ws.onclose = () => {
            setStatus('Disconnected', 'error');
            scheduleReconnect();
        };

        state.ws.onerror = () => {
            setStatus('Connection error', 'error');
        };
    }

    function send(message) {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(JSON.stringify(message));
        }
    }

    function scheduleReconnect() {
        if (state.reconnectAttempts >= MAX_RECONNECT) {
            return;
        }
        state.reconnectAttempts += 1;
        setTimeout(connect, RECONNECT_DELAY);
    }

    function handleMessage(message) {
        const type = message.type || '';
        const payload = message.payload || {};

        switch (type) {
            case 'session.snapshot':
                handleSessionSnapshot(payload);
                break;
            case 'models.snapshot':
                renderModels(payload.models || []);
                break;
            case 'assistant.delta':
                appendAssistantToken(payload.token || '');
                break;
            case 'assistant.reasoning':
                appendReasoningToken(payload.token || '');
                break;
            case 'tool.call.start':
                addToolCall(payload.name || 'tool');
                break;
            case 'tool.call.delta':
                appendToolDelta(payload.token || '');
                break;
            case 'tool.call.end':
                state.currentToolTextEl = null;
                break;
            case 'tool.result':
                addToolResult(payload.name || 'tool', payload.result || '');
                break;
            case 'status':
                handleStatusMessage(payload.text || '');
                break;
            case 'assistant.done':
                finalizeStream(payload);
                state.streaming = false;
                resetStreamRefs();
                refreshSessions(true);
                setTimeout(() => fetchTranscript(true), 750);
                break;
            case 'error':
                addErrorMessage(payload.message || 'Unknown error');
                state.streaming = false;
                clearTransientStatus();
                removeEmptyStreamArtifacts();
                resetStreamRefs();
                if (payload.model_required) {
                    showModelOverlay();
                }
                break;
            case 'pong':
                break;
            default:
                console.debug('Unhandled message type:', type, payload);
        }
    }

    function handleSessionSnapshot(payload) {
        state.selectedModelId = payload.selected_model_id || '';
        state.modelRequired = !!payload.model_required;
        refs.currentSessionTitle.textContent = payload.title || 'Main';
        refs.currentSessionChannel.textContent = payload.channel || 'webchat';
        refs.currentSessionMeta.textContent = payload.session_key || state.currentSessionKey;
        refs.sessionDetail.textContent = JSON.stringify(payload, null, 2);
        updateModelSelects(payload.available_model_ids || [], state.selectedModelId);
        refs.btnSend.disabled = false;
        if (state.modelRequired) {
            showModelOverlay();
        } else {
            hideModelOverlay();
        }
        fetchTranscript(true);
        refreshSessions(true);
    }

    function setStatus(text, stateName) {
        refs.statusBadge.textContent = text;
        refs.statusBadge.className = 'header-badge ' + (stateName || '');
    }

    function updateModelSelects(modelIds, selected) {
        [refs.modelSelect, refs.panelModelSelect, refs.overlayModelSelect].forEach((select) => {
            select.innerHTML = '';
            if (!modelIds.length) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'No models available';
                select.appendChild(opt);
                return;
            }
            modelIds.forEach((modelId) => {
                const opt = document.createElement('option');
                opt.value = modelId;
                opt.textContent = modelId;
                if (modelId === selected) {
                    opt.selected = true;
                }
                select.appendChild(opt);
            });
        });
        refs.modelSelect.disabled = modelIds.length === 0;
    }

    function renderModels(models) {
        const ids = models.map((model) => model.id || '').filter(Boolean);
        updateModelSelects(ids, state.selectedModelId);
        refs.availableModels.innerHTML = '';
        if (!ids.length) {
            refs.availableModels.appendChild(renderEmpty('No models reported by llama.cpp.'));
            return;
        }
        ids.forEach((id) => {
            const chip = document.createElement('span');
            chip.className = 'inline-chip';
            chip.textContent = id;
            refs.availableModels.appendChild(chip);
        });
    }

    function showModelOverlay() {
        refs.modelOverlay.style.display = 'flex';
    }

    function hideModelOverlay() {
        refs.modelOverlay.style.display = 'none';
    }

    function createMessage(type, content) {
        if (refs.welcome && refs.welcome.parentNode) {
            refs.welcome.remove();
        }
        const node = document.createElement('div');
        node.className = 'message ' + type;
        if (content) {
            node.textContent = content;
        }
        refs.chatMessages.appendChild(node);
        scrollToBottom();
        return node;
    }

    function addStatusMessage(text) {
        createMessage('status', text);
    }

    function handleStatusMessage(text) {
        if (!text) {
            return;
        }
        if (state.streaming) {
            if (!state.currentStatusEl || !state.currentStatusEl.parentNode) {
                state.currentStatusEl = createMessage('status', text);
                state.currentStatusEl.dataset.streaming = 'true';
                return;
            }
            state.currentStatusEl.textContent = text;
            return;
        }
        addStatusMessage(text);
    }

    function addErrorMessage(text) {
        createMessage('error', text);
    }

    function buildTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.id = 'typing';
        indicator.innerHTML = '<span></span><span></span><span></span>';
        return indicator;
    }

    function ensureAssistantStreamNode() {
        if (!state.currentAssistantEl) {
            state.currentAssistantEl = createMessage('assistant', '');
            state.currentAssistantTextEl = document.createElement('div');
            state.currentAssistantTextEl.className = 'message-body';
            state.currentAssistantEl.appendChild(state.currentAssistantTextEl);
            state.currentAssistantEl.appendChild(buildTypingIndicator());
        }
        return state.currentAssistantEl;
    }

    function removeTypingIndicator() {
        const typing = state.currentAssistantEl.querySelector('#typing');
        if (typing) {
            typing.remove();
        }
    }

    function appendAssistantToken(token) {
        ensureAssistantStreamNode();
        removeTypingIndicator();
        state.currentAssistantTextEl.textContent += token;
        scrollToBottom();
    }

    function ensureReasoningNode() {
        if (!state.currentReasoningEl) {
            state.currentReasoningEl = createMessage('reasoning', '');
            const label = document.createElement('div');
            label.className = 'label';
            label.textContent = 'Reasoning';
            state.currentReasoningTextEl = document.createElement('div');
            state.currentReasoningTextEl.className = 'message-body';
            state.currentReasoningEl.appendChild(label);
            state.currentReasoningEl.appendChild(state.currentReasoningTextEl);
        }
        return state.currentReasoningEl;
    }

    function appendReasoningToken(token) {
        ensureReasoningNode();
        state.currentReasoningTextEl.textContent += token;
        scrollToBottom();
    }

    function addToolCall(name) {
        const el = createMessage('tool-call', '');
        const label = document.createElement('div');
        label.className = 'label';
        label.textContent = 'Tool: ' + name;
        const body = document.createElement('div');
        el.appendChild(label);
        el.appendChild(body);
        state.currentToolTextEl = body;
    }

    function appendToolDelta(token) {
        if (state.currentToolTextEl) {
            state.currentToolTextEl.textContent += token;
            scrollToBottom();
        }
    }

    function addToolResult(name, result) {
        const el = createMessage('tool-result', '');
        const label = document.createElement('div');
        label.className = 'label';
        label.textContent = 'Result: ' + name;
        el.appendChild(label);
        el.appendChild(document.createTextNode(result));
        state.currentToolTextEl = null;
    }

    function submitMessage() {
        const content = refs.chatInput.value.trim();
        if (!content) {
            return;
        }
        createMessage('user', content);
        refs.chatInput.value = '';
        refs.chatInput.style.height = 'auto';
        state.streaming = true;
        state.currentTranscriptSignature = '';
        clearTransientStatus();
        resetStreamRefs();
        state.currentStatusEl = createMessage('status', 'Thinking...');
        state.currentStatusEl.dataset.streaming = 'true';
        ensureAssistantStreamNode();
        send({
            type: 'chat.submit',
            session_key: state.currentSessionKey,
            payload: { content: content },
        });
    }

    function attachSession(sessionKey) {
        state.currentSessionKey = sessionKey;
        send({ type: 'session.attach', session_key: sessionKey });
    }

    async function fetchJson(path, options) {
        const response = await fetch(path, options);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || 'Request failed');
        }
        return payload;
    }

    function shouldPoll(options) {
        const settings = Object.assign(
            {
                allowWhileStreaming: false,
                requireVisible: true,
            },
            options || {}
        );
        if (settings.requireVisible && document.hidden) {
            return false;
        }
        if (!settings.allowWhileStreaming && state.streaming) {
            return false;
        }
        return true;
    }

    async function refreshSessions(force) {
        if (!force && !shouldPoll({ allowWhileStreaming: false })) {
            return;
        }
        try {
            const payload = await fetchJson('/api/sessions');
            state.sessions = payload.sessions || [];
            renderSessions();
        } catch (error) {
            console.error(error);
        }
    }

    async function fetchTranscript(force) {
        if (!force && !shouldPoll({ allowWhileStreaming: false })) {
            return;
        }
        try {
            const payload = await fetchJson('/api/sessions/' + encodeURIComponent(state.currentSessionKey) + '/transcript');
            const signature = JSON.stringify({
                session_id: payload.session_id,
                message_count: payload.message_count,
                updated_at: payload.updated_at,
                preview: payload.preview,
            });
            refs.sessionDetail.textContent = JSON.stringify(payload.snapshot || {}, null, 2);
            refs.currentSessionTitle.textContent = payload.title || 'Main';
            refs.currentSessionChannel.textContent = payload.channel || 'webchat';
            refs.currentSessionMeta.textContent = payload.session_key || state.currentSessionKey;
            if (signature !== state.currentTranscriptSignature) {
                state.currentTranscriptSignature = signature;
                renderTranscript(payload.messages || []);
            }
        } catch (error) {
            console.error(error);
        }
    }

    async function refreshHealth(force) {
        if (!force && !shouldPoll({ allowWhileStreaming: true })) {
            return;
        }
        try {
            const payload = await fetchJson('/health');
            state.health = payload;
            refs.gatewayPill.className = 'mini-pill ' + (payload.gateway ? 'ok' : 'error');
            refs.backendPill.className = 'mini-pill ' + (payload.backend ? 'ok' : 'error');
            refs.settingsGateway.textContent = payload.gateway ? 'Healthy' : 'Unavailable';
            refs.settingsBackend.textContent = payload.backend ? 'Healthy' : 'Unavailable';
            refs.settingsConnections.textContent = String(payload.connections || 0);
            refs.settingsWorkspace.textContent = payload.workspace || 'workspace';
        } catch (error) {
            console.error(error);
        }
    }

    async function refreshChannels(force) {
        if (!force && !shouldPoll({ allowWhileStreaming: true })) {
            return;
        }
        try {
            const payload = await fetchJson('/api/admin/channels');
            const states = payload.channels || [];
            state.channelStates = {};
            states.forEach((item) => {
                state.channelStates[item.channel] = item;
            });
            renderChannelCards(states);
        } catch (error) {
            console.error(error);
        }
    }

    async function refreshPairing(force) {
        if (!force && !shouldPoll({ allowWhileStreaming: true })) {
            return;
        }
        try {
            const payload = await fetchJson('/api/admin/pairing');
            state.pairing = payload.channels || {};
            renderPairing();
        } catch (error) {
            console.error(error);
        }
    }

    function renderSessions() {
        refs.sessionList.innerHTML = '';
        if (!state.sessions.length) {
            refs.sessionList.appendChild(renderEmpty('No sessions yet.'));
            return;
        }
        state.sessions.forEach((session) => {
            const button = document.createElement('button');
            button.className = 'session-item' + (session.session_key === state.currentSessionKey ? ' active' : '');
            button.addEventListener('click', () => {
                state.currentTranscriptSignature = '';
                renderTranscript([]);
                attachSession(session.session_key);
            });

            const meta = document.createElement('div');
            meta.className = 'session-meta';
            const badge = document.createElement('span');
            badge.className = 'channel-badge';
            badge.textContent = session.channel || 'webchat';
            const count = document.createElement('span');
            count.className = 'message-count';
            count.textContent = String(session.message_count || 0) + ' msgs';
            meta.appendChild(badge);
            meta.appendChild(count);

            const title = document.createElement('h3');
            title.textContent = session.title || session.session_key;
            const preview = document.createElement('p');
            preview.textContent = session.preview || session.session_key;

            button.appendChild(meta);
            button.appendChild(title);
            button.appendChild(preview);
            refs.sessionList.appendChild(button);
        });
    }

    function renderTranscript(messages) {
        refs.chatMessages.innerHTML = '';
        resetStreamRefs();
        if (!messages.length) {
            if (refs.welcome) {
                refs.chatMessages.appendChild(refs.welcome);
            } else {
                refs.chatMessages.appendChild(renderEmpty('No messages yet.'));
            }
            return;
        }
        messages.forEach((message) => {
            const role = message.role || 'system';
            if (role === 'assistant' && Array.isArray(message.tool_calls) && message.tool_calls.length) {
                if (message.content) {
                    createMessage('assistant', message.content);
                }
                message.tool_calls.forEach((call) => {
                    const toolNode = createMessage('tool-call', '');
                    const label = document.createElement('div');
                    label.className = 'label';
                    label.textContent = 'Tool: ' + (((call || {}).function || {}).name || 'tool');
                    toolNode.appendChild(label);
                    toolNode.appendChild(document.createTextNode((((call || {}).function || {}).arguments || '').toString()));
                });
                return;
            }
            if (role === 'tool') {
                const node = createMessage('tool-result', '');
                const label = document.createElement('div');
                label.className = 'label';
                label.textContent = 'Tool result';
                node.appendChild(label);
                node.appendChild(document.createTextNode(message.content || ''));
                return;
            }
            if (role === 'system') {
                createMessage('system', message.content || '');
                return;
            }
            createMessage(role === 'assistant' ? 'assistant' : 'user', message.content || '');
        });
        scrollToBottom();
    }

    function clearTransientStatus() {
        if (state.currentStatusEl && state.currentStatusEl.parentNode) {
            state.currentStatusEl.remove();
        }
        state.currentStatusEl = null;
    }

    function removeEmptyStreamArtifacts() {
        if (state.currentAssistantEl && state.currentAssistantEl.parentNode) {
            const assistantText = state.currentAssistantTextEl ? state.currentAssistantTextEl.textContent.trim() : '';
            if (!assistantText) {
                state.currentAssistantEl.remove();
            } else {
                removeTypingIndicator();
            }
        }
        if (state.currentReasoningEl && state.currentReasoningEl.parentNode && state.currentReasoningTextEl) {
            if (!state.currentReasoningTextEl.textContent.trim()) {
                state.currentReasoningEl.remove();
            }
        }
    }

    function resetStreamRefs() {
        state.currentAssistantEl = null;
        state.currentAssistantTextEl = null;
        state.currentReasoningEl = null;
        state.currentReasoningTextEl = null;
        state.currentToolTextEl = null;
    }

    function finalizeStream(payload) {
        const finalContent = String((payload || {}).content || '');
        if (finalContent) {
            ensureAssistantStreamNode();
            removeTypingIndicator();
            if (!state.currentAssistantTextEl.textContent.trim()) {
                state.currentAssistantTextEl.textContent = finalContent;
            }
        }
        clearTransientStatus();
        removeEmptyStreamArtifacts();
    }

    function renderChannelCards(states) {
        refs.channelCards.innerHTML = '';
        states.forEach((stateItem) => {
            const card = document.createElement('div');
            card.className = 'channel-card';

            const title = document.createElement('h4');
            title.textContent = stateItem.channel;
            const status = document.createElement('div');
            status.className = 'channel-status';
            status.textContent = (stateItem.status || 'unknown') + (stateItem.last_error ? ' - ' + stateItem.last_error : '');

            const grid = document.createElement('div');
            grid.className = 'channel-grid';

            const enabled = buildCheckboxField('Enabled', stateItem.enabled, stateItem.channel + '-enabled');
            const requireMention = buildCheckboxField('Require mention', stateItem.requireMention !== false, stateItem.channel + '-requireMention');
            const dmPolicy = buildSelectField('DM policy', ['pairing', 'allowlist', 'open', 'disabled'], stateItem.dmPolicy, stateItem.channel + '-dmPolicy');
            const groupPolicy = buildSelectField('Group policy', ['allowlist', 'open', 'disabled'], stateItem.groupPolicy, stateItem.channel + '-groupPolicy');
            const token = buildInputField('Token', stateItem.channel + '-token', 'password', stateItem.configured ? 'Configured (leave blank to keep current token)' : 'Paste token');
            const allowFrom = buildInputField('DM allowFrom', stateItem.channel + '-allowFrom', 'text', 'id1,id2,*');
            allowFrom.querySelector('input').value = (stateItem.allowFrom || []).join(', ');
            const groupAllowFrom = buildInputField('Group allowFrom', stateItem.channel + '-groupAllowFrom', 'text', 'id1,id2,*');
            groupAllowFrom.querySelector('input').value = (stateItem.groupAllowFrom || []).join(', ');
            const scopeInput = buildTextareaField(stateItem.channel === 'discord' ? 'Guild IDs' : 'Group IDs', stateItem.channel + '-scopes');
            const scopes = stateItem.channel === 'discord' ? (stateItem.guilds || {}) : (stateItem.groups || {});
            scopeInput.querySelector('textarea').value = Object.keys(scopes).filter((key) => key !== '*').join('\n');

            [enabled, requireMention, dmPolicy, groupPolicy, token, allowFrom, groupAllowFrom, scopeInput].forEach((field) => {
                grid.appendChild(field);
            });

            const actions = document.createElement('div');
            actions.className = 'pairing-actions';
            const saveBtn = document.createElement('button');
            saveBtn.className = 'btn btn-primary btn-small';
            saveBtn.textContent = 'Save';
            saveBtn.addEventListener('click', () => saveChannel(stateItem.channel));
            const probeBtn = document.createElement('button');
            probeBtn.className = 'btn btn-ghost btn-small';
            probeBtn.textContent = 'Probe';
            probeBtn.addEventListener('click', () => probeChannel(stateItem.channel));
            actions.appendChild(saveBtn);
            actions.appendChild(probeBtn);

            card.appendChild(title);
            card.appendChild(status);
            card.appendChild(grid);
            card.appendChild(actions);
            refs.channelCards.appendChild(card);
        });
    }

    function renderPairing() {
        refs.pairingPending.innerHTML = '';
        refs.pairingApproved.innerHTML = '';
        const channels = state.pairing || {};
        let pendingCount = 0;
        let approvedCount = 0;

        Object.keys(channels).forEach((channel) => {
            (channels[channel].pending || []).forEach((item) => {
                pendingCount += 1;
                const card = document.createElement('div');
                card.className = 'pairing-item';
                const title = document.createElement('strong');
                title.textContent = channel + ' - ' + (item.sender_name || item.sender_id);
                const code = document.createElement('p');
                code.textContent = 'Code: ' + item.code;
                const actions = document.createElement('div');
                actions.className = 'pairing-actions';
                const approve = document.createElement('button');
                approve.className = 'btn btn-primary btn-small';
                approve.textContent = 'Approve';
                approve.addEventListener('click', () => approvePairing(channel, item.code));
                const reject = document.createElement('button');
                reject.className = 'btn btn-ghost btn-small';
                reject.textContent = 'Reject';
                reject.addEventListener('click', () => rejectPairing(channel, item.code));
                actions.appendChild(approve);
                actions.appendChild(reject);
                card.appendChild(title);
                card.appendChild(code);
                card.appendChild(actions);
                refs.pairingPending.appendChild(card);
            });

            (channels[channel].approved || []).forEach((senderId) => {
                approvedCount += 1;
                const card = document.createElement('div');
                card.className = 'approved-item';
                const label = document.createElement('strong');
                label.textContent = channel + ' - ' + senderId;
                const revoke = document.createElement('button');
                revoke.className = 'btn btn-ghost btn-small';
                revoke.textContent = 'Revoke';
                revoke.addEventListener('click', () => revokeSender(channel, senderId));
                card.appendChild(label);
                card.appendChild(document.createElement('br'));
                card.appendChild(document.createElement('br'));
                card.appendChild(revoke);
                refs.pairingApproved.appendChild(card);
            });
        });

        if (!pendingCount) {
            refs.pairingPending.appendChild(renderEmpty('No pending pairing requests.'));
        }
        if (!approvedCount) {
            refs.pairingApproved.appendChild(renderEmpty('No approved senders.'));
        }
    }

    async function saveChannel(channel) {
        try {
            const patch = buildChannelPatch(channel);
            await fetchJson('/api/admin/channels/' + channel, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(patch),
            });
            addStatusMessage('Saved channel config: ' + channel);
            refreshChannels(true);
        } catch (error) {
            addErrorMessage(error.message);
        }
    }

    async function probeChannel(channel) {
        try {
            const payload = await fetchJson('/api/admin/channels/' + channel + '/probe', { method: 'POST' });
            const probe = payload.probe || {};
            addStatusMessage(channel + ' probe: ' + (probe.ok ? 'ok' : probe.error || 'failed'));
            refreshChannels(true);
        } catch (error) {
            addErrorMessage(error.message);
        }
    }

    async function approvePairing(channel, code) {
        try {
            await fetchJson('/api/admin/pairing/' + channel + '/' + code + '/approve', { method: 'POST' });
            refreshPairing(true);
            refreshChannels(true);
        } catch (error) {
            addErrorMessage(error.message);
        }
    }

    async function rejectPairing(channel, code) {
        try {
            await fetchJson('/api/admin/pairing/' + channel + '/' + code + '/reject', { method: 'POST' });
            refreshPairing(true);
        } catch (error) {
            addErrorMessage(error.message);
        }
    }

    async function revokeSender(channel, senderId) {
        try {
            await fetchJson('/api/admin/pairing/' + channel + '/' + senderId, { method: 'DELETE' });
            refreshPairing(true);
        } catch (error) {
            addErrorMessage(error.message);
        }
    }

    function buildChannelPatch(channel) {
        const patch = {
            enabled: document.getElementById(channel + '-enabled').checked,
            requireMention: document.getElementById(channel + '-requireMention').checked,
            dmPolicy: document.getElementById(channel + '-dmPolicy').value,
            groupPolicy: document.getElementById(channel + '-groupPolicy').value,
            allowFrom: parseCommaList(document.getElementById(channel + '-allowFrom').value),
            groupAllowFrom: parseCommaList(document.getElementById(channel + '-groupAllowFrom').value),
        };
        const tokenField = TOKEN_FIELDS[channel];
        const tokenValue = document.getElementById(channel + '-token').value.trim();
        if (tokenValue) {
            patch[tokenField] = tokenValue;
        }
        const scopeLines = document.getElementById(channel + '-scopes').value
            .split('\n')
            .map((item) => item.trim())
            .filter(Boolean);
        const scopeMap = {};
        scopeLines.forEach((scope) => {
            scopeMap[scope] = { requireMention: patch.requireMention, groupPolicy: patch.groupPolicy };
        });
        if (channel === 'discord') {
            patch.guilds = scopeMap;
        } else {
            patch.groups = scopeMap;
        }
        return patch;
    }

    function parseCommaList(value) {
        return String(value || '')
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function buildInputField(labelText, id, type, placeholder) {
        const field = document.createElement('div');
        field.className = 'field';
        const label = document.createElement('label');
        label.textContent = labelText;
        label.setAttribute('for', id);
        const input = document.createElement('input');
        input.type = type;
        input.id = id;
        input.placeholder = placeholder || '';
        field.appendChild(label);
        field.appendChild(input);
        return field;
    }

    function buildTextareaField(labelText, id) {
        const field = document.createElement('div');
        field.className = 'field full';
        const label = document.createElement('label');
        label.textContent = labelText;
        label.setAttribute('for', id);
        const textarea = document.createElement('textarea');
        textarea.className = 'scope-input';
        textarea.id = id;
        textarea.placeholder = 'One identifier per line';
        field.appendChild(label);
        field.appendChild(textarea);
        return field;
    }

    function buildSelectField(labelText, options, selected, id) {
        const field = document.createElement('div');
        field.className = 'field';
        const label = document.createElement('label');
        label.textContent = labelText;
        label.setAttribute('for', id);
        const select = document.createElement('select');
        select.id = id;
        options.forEach((optionValue) => {
            const option = document.createElement('option');
            option.value = optionValue;
            option.textContent = optionValue;
            if (optionValue === selected) {
                option.selected = true;
            }
            select.appendChild(option);
        });
        field.appendChild(label);
        field.appendChild(select);
        return field;
    }

    function buildCheckboxField(labelText, checked, id) {
        const field = document.createElement('div');
        field.className = 'field inline-toggle';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = id;
        input.checked = !!checked;
        const label = document.createElement('label');
        label.textContent = labelText;
        label.setAttribute('for', id);
        field.appendChild(input);
        field.appendChild(label);
        return field;
    }

    function renderEmpty(text) {
        const node = document.createElement('div');
        node.className = 'empty-state';
        node.textContent = text;
        return node;
    }

    function scrollToBottom() {
        refs.chatContainer.scrollTop = refs.chatContainer.scrollHeight;
    }

    refs.chatInput.addEventListener('input', () => {
        refs.chatInput.style.height = 'auto';
        refs.chatInput.style.height = Math.min(refs.chatInput.scrollHeight, 150) + 'px';
    });

    refs.chatInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submitMessage();
        }
    });

    refs.btnSend.addEventListener('click', submitMessage);
    refs.btnReset.addEventListener('click', () => {
        send({ type: 'session.reset', session_key: state.currentSessionKey });
        state.currentTranscriptSignature = '';
        renderTranscript([]);
        refreshSessions(true);
    });
    refs.modelSelect.addEventListener('change', () => {
        refs.panelModelSelect.value = refs.modelSelect.value;
        refs.btnApplyModel.click();
    });
    refs.btnApplyModel.addEventListener('click', () => {
        const modelId = refs.panelModelSelect.value || refs.modelSelect.value;
        if (!modelId) {
            return;
        }
        state.selectedModelId = modelId;
        send({ type: 'session.model.set', session_key: state.currentSessionKey, payload: { model_id: modelId } });
    });
    refs.overlayConfirm.addEventListener('click', () => {
        const modelId = refs.overlayModelSelect.value;
        if (!modelId) {
            return;
        }
        refs.panelModelSelect.value = modelId;
        refs.modelSelect.value = modelId;
        refs.btnApplyModel.click();
        hideModelOverlay();
    });
    refs.btnRefreshSessions.addEventListener('click', () => refreshSessions(true));
    refs.btnRefreshChannels.addEventListener('click', () => refreshChannels(true));
    refs.btnRefreshPairing.addEventListener('click', () => refreshPairing(true));
    refs.dockTabs.forEach((tab) => {
        tab.addEventListener('click', () => {
            refs.dockTabs.forEach((item) => item.classList.toggle('active', item === tab));
            refs.dockPanels.forEach((panel) => {
                panel.classList.toggle('active', panel.getAttribute('data-panel') === tab.getAttribute('data-tab'));
            });
        });
    });

    setInterval(() => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            send({ type: 'ping' });
        }
    }, 30000);

    setInterval(fetchTranscript, TRANSCRIPT_POLL_MS);
    setInterval(refreshSessions, SESSIONS_POLL_MS);
    setInterval(refreshHealth, HEALTH_POLL_MS);
    setInterval(refreshChannels, ADMIN_POLL_MS);
    setInterval(refreshPairing, ADMIN_POLL_MS);

    refreshSessions(true);
    refreshHealth(true);
    refreshChannels(true);
    refreshPairing(true);
    connect();
})();
