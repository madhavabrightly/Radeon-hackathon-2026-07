// Screen-AI Mobile Remote App - Enhanced with QR + Trust + Rotation

const API_BASE = window.location.origin;
const WS_SCHEME = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

// State
let state = {
    deviceId: sessionStorage.getItem('device_id'),
    token: sessionStorage.getItem('token'),
    devicePublicKey: localStorage.getItem('device_public_key'),
    trustUntil: localStorage.getItem('trust_until'),
    ws: null,
    wsReconnectTimer: null,
    cameraStream: null,
    qrScanInterval: null,
};

// Browser entropy helper. Do not depend on X25519 WebCrypto support for MVP
// pairing; many mobile browsers still do not expose it consistently.
const browserCrypto = window.crypto || window.msCrypto;

// ============================================================
// PWA + Service Worker + Web Worker + IndexedDB
// ============================================================

let swRegistration = null;
let appWorker = null;
let previewTimer = null;
const COMMAND_MEMORY_KEY = 'screenai_command_memory_v1';
const COMMAND_DRAFT_KEY = 'screenai_command_draft_v1';
const RUNTIME_SNAPSHOT_KEY = 'screenai_runtime_snapshot_v1';

// Register Service Worker for PWA / offline
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/remote/sw.js', { scope: '/remote/' })
        .then((reg) => {
            swRegistration = reg;
            console.log('[ScreenAI] Service Worker registered, scope:', reg.scope);
        })
        .catch((err) => console.warn('[ScreenAI] SW registration failed:', err));

    // Listen for service-worker cache status. Commands are never auto-executed
    // from offline state; they remain drafts until the user presses Send again.
    navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data?.type === 'COMMAND_DRAFT_SAVED') {
            console.log('[ScreenAI] Offline command draft saved:', event.data.id);
        }
    });
}

// Initialize Web Worker for off-main-thread operations
if (typeof Worker !== 'undefined') {
    try {
        appWorker = new Worker('/remote/worker.js');
        appWorker.onmessage = (e) => {
            const { type, id, result, error } = e.data;
            if (error) {
                console.warn(`[Worker] ${type} failed:`, error);
            }
            // Dispatch results to waiting handlers
            const handler = _workerHandlers.get(id);
            if (handler) {
                _workerHandlers.delete(id);
                handler(result, error);
            }
        };
        console.log('[ScreenAI] Web Worker initialized');
    } catch (err) {
        console.warn('[ScreenAI] Worker init failed:', err);
    }
}

const _workerHandlers = new Map();
let _workerIdCounter = 0;

function postToWorker(type, payload, timeout = 5000) {
    return new Promise((resolve, reject) => {
        if (!appWorker) { resolve(null); return; }
        const id = ++_workerIdCounter;
        const timer = setTimeout(() => {
            _workerHandlers.delete(id);
            resolve(null); // Graceful timeout — don't block UI
        }, timeout);
        _workerHandlers.set(id, (result, error) => {
            clearTimeout(timer);
            error ? resolve(null) : resolve(result);
        });
        appWorker.postMessage({ type, id, payload });
    });
}

// IndexedDB caching for offline command drafts and history
const IDB_NAME = 'screenai-cache';
const IDB_VERSION = 1;

function openIDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(IDB_NAME, IDB_VERSION);
        req.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv');
            if (!db.objectStoreNames.contains('offline_command_drafts')) {
                db.createObjectStore('offline_command_drafts', { keyPath: 'id', autoIncrement: true });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function cacheForOffline(key, value) {
    try {
        const db = await openIDB();
        const tx = db.transaction('kv', 'readwrite');
        tx.objectStore('kv').put(value, key);
    } catch (err) {
        console.warn('[ScreenAI] IDB cache failed:', err);
    }
}

async function readFromCache(key) {
    try {
        const db = await openIDB();
        const tx = db.transaction('kv', 'readonly');
        const req = tx.objectStore('kv').get(key);
        return new Promise((resolve) => {
            req.onsuccess = () => resolve(req.result || null);
            req.onerror = () => resolve(null);
        });
    } catch {
        return null;
    }
}

async function saveOfflineCommandDraft(text) {
    try {
        const db = await openIDB();
        const tx = db.transaction('offline_command_drafts', 'readwrite');
        tx.objectStore('offline_command_drafts').add({
            text,
            device_id: state.deviceId,
            queued_at: Date.now(),
        });
    } catch (err) {
        console.warn('[ScreenAI] Failed to save offline command draft:', err);
    }
}

// ============================================================
// Initialization
// ============================================================

init();

async function init() {
    // Check if already paired (sessionStorage - clears on tab close)
    if (state.deviceId && state.token) {
        showMainScreen();
        connectWebSocket();
        loadHistory();
        loadApprovals();
        checkTrustStatus();
        scheduleTokenRotation();
    } else {
        showLoginScreen();
        setConnectionState('offline', 'Offline');
    }

    // Event listeners
    setupEventListeners();
}

function setupEventListeners() {
    // Login method tabs
    document.querySelectorAll('.method-tab').forEach(tab => {
        tab.addEventListener('click', () => switchLoginMethod(tab.dataset.method));
    });

    // QR scanner
    document.getElementById('start-camera')?.addEventListener('click', startQRScanner);
    document.getElementById('stop-camera')?.addEventListener('click', stopQRScanner);

    // Code entry
    document.getElementById('pair-button')?.addEventListener('click', pairWithCode);

    // Trusted device
    document.getElementById('check-trusted')?.addEventListener('click', checkTrustedDevice);

    // Main screen
    document.getElementById('send-command')?.addEventListener('click', sendCommand);
    document.getElementById('preview-command')?.addEventListener('click', previewCurrentCommand);
    document.getElementById('restore-draft')?.addEventListener('click', restoreCommandDraft);
    document.getElementById('emergency-stop')?.addEventListener('click', emergencyStop);
    document.getElementById('unpair-button')?.addEventListener('click', unpairDevice);
    document.getElementById('rotate-token-btn')?.addEventListener('click', rotateTokenNow);

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Auto-format pairing code
    const codeInput = document.getElementById('pairing-code');
    if (codeInput) {
        codeInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6);
        });
    }

    const commandText = document.getElementById('command-text');
    if (commandText) {
        commandText.value = localStorage.getItem(COMMAND_DRAFT_KEY) || '';
        commandText.addEventListener('input', () => {
            const value = commandText.value;
            localStorage.setItem(COMMAND_DRAFT_KEY, value);
            renderCommandMemory(value);
            renderLocalRouteHint(value);
            clearTimeout(previewTimer);
            if (value.trim().length >= 8) {
                previewTimer = setTimeout(previewCurrentCommand, 650);
            } else {
                renderPlanPreview(null);
            }
        });
        renderCommandMemory(commandText.value);
        renderLocalRouteHint(commandText.value);
    }
}

// ============================================================
// Login Methods
// ============================================================

function switchLoginMethod(method) {
    document.querySelectorAll('.method-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.method-content').forEach(t => t.classList.remove('active'));

    document.querySelector(`[data-method="${method}"]`).classList.add('active');
    document.getElementById(`${method}-method`).classList.add('active');

    // Stop camera if switching away from QR
    if (method !== 'qr') {
        stopQRScanner();
    }
}

// ============================================================
// QR Code Pairing (primary, instant)
// ============================================================

async function startQRScanner() {
    try {
        if (typeof jsQR === 'undefined') {
            setStatus('qr-status', 'QR scanner library did not load. Use Enter Code fallback.', 'error');
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            setStatus('qr-status', 'Camera API unavailable. Use Enter Code fallback.', 'error');
            return;
        }

        const video = document.createElement('video');
        video.setAttribute('playsinline', '');
        video.setAttribute('autoplay', '');

        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment' }
        });

        state.cameraStream = stream;
        video.srcObject = stream;

        const qrFrame = document.querySelector('.qr-frame');
        qrFrame.innerHTML = '';
        qrFrame.appendChild(video);

        const canvas = document.createElement('canvas');
        canvas.style.display = 'none';
        qrFrame.appendChild(canvas);

        document.getElementById('start-camera').classList.add('hidden');
        document.getElementById('stop-camera').classList.remove('hidden');

        // Scan loop
        state.qrScanInterval = setInterval(() => scanQRCode(video, canvas), 500);

        setStatus('qr-status', 'Camera started. Point at QR code.', 'info');
    } catch (error) {
        setStatus('qr-status', `Camera error: ${error.message}`, 'error');
    }
}

function stopQRScanner() {
    if (state.cameraStream) {
        state.cameraStream.getTracks().forEach(track => track.stop());
        state.cameraStream = null;
    }
    if (state.qrScanInterval) {
        clearInterval(state.qrScanInterval);
        state.qrScanInterval = null;
    }

    const qrFrame = document.querySelector('.qr-frame');
    if (qrFrame) {
        qrFrame.innerHTML = `
            <div class="qr-corner tl"></div>
            <div class="qr-corner tr"></div>
            <div class="qr-corner bl"></div>
            <div class="qr-corner br"></div>
            <p class="qr-hint">Point camera at QR code on PC</p>
        `;
    }

    document.getElementById('start-camera')?.classList.remove('hidden');
    document.getElementById('stop-camera')?.classList.add('hidden');
}

function scanQRCode(video, canvas) {
    if (video.readyState !== video.HAVE_ENOUGH_DATA) return;
    if (typeof jsQR === 'undefined') return;

    const ctx = canvas.getContext('2d');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const code = jsQR(imageData.data, imageData.width, imageData.height);

    if (code) {
        stopQRScanner();
        handleQRData(code.data);
    }
}

async function handleQRData(qrData) {
    try {
        const payload = JSON.parse(qrData);

        // Validate payload
        if (payload.v !== 1 || !payload.pid || !payload.pk) {
            setStatus('qr-status', 'Invalid QR code', 'error');
            return;
        }

        // Check expiry
        if (payload.exp && payload.exp < Date.now() / 1000) {
            setStatus('qr-status', 'QR code expired', 'error');
            return;
        }

        setStatus('qr-status', 'QR code scanned! Pairing...', 'info');

        const devicePublicKey = getOrCreateDevicePublicKey();

        // Complete pairing
        const response = await fetch(`${API_BASE}/pair/qr/complete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pairing_id: payload.pid,
                device_public_key: devicePublicKey,
                device_name: getDeviceName(),
                trust_device: true,  // QR pairing defaults to trusted
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            setStatus('qr-status', `Pairing failed: ${error.detail}`, 'error');
            return;
        }

        const data = await response.json();

        const sessionToken = data.token;
        if (!sessionToken) {
            setStatus('qr-status', 'Pairing response did not include a session token', 'error');
            return;
        }

        // Save credentials (sessionStorage - clears on tab close)
        saveSession(data.device_id, sessionToken, devicePublicKey, data.trust_until);

        setStatus('qr-status', 'Paired successfully. Opening command console...', 'pair-success');
        openRemoteConsoleAfterPair();

    } catch (error) {
        setStatus('qr-status', `Error: ${error.message}`, 'error');
    }
}

// ============================================================
// Code Entry Pairing (fallback)
// ============================================================

async function pairWithCode() {
    const code = document.getElementById('pairing-code').value.trim();
    const name = document.getElementById('device-name').value.trim() || 'Mobile Device';
    const trust = document.getElementById('trust-device')?.checked || false;

    if (code.length !== 6) {
        document.getElementById('pair-error').textContent = 'Please enter a 6-digit code';
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/pair`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, device_name: name }),
        });

        if (!response.ok) {
            const error = await response.json();
            document.getElementById('pair-error').textContent = error.detail || 'Pairing failed';
            return;
        }

        const data = await response.json();

        // Save credentials
        saveSession(data.device_id, data.token, getOrCreateDevicePublicKey(), null);

        // If user wants to trust, mark as trusted
        if (trust) {
            await fetch(`${API_BASE}/pair/trust?device_id=${data.device_id}&days=30`, {
                method: 'POST',
            });
            localStorage.setItem('trust_until', new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString());
        }

        document.getElementById('pair-error').textContent = '';
        setStatus('pair-error', 'Paired successfully. Opening command console...', 'pair-success');
        openRemoteConsoleAfterPair(500);

    } catch (error) {
        document.getElementById('pair-error').textContent = 'Network error: ' + error.message;
    }
}

// ============================================================
// Trusted Device Re-Pairing
// ============================================================

async function checkTrustedDevice() {
    const deviceId = localStorage.getItem('last_device_id');
    const devicePublicKey = localStorage.getItem('device_public_key');

    if (!deviceId || !devicePublicKey) {
        setStatus('trusted-status', 'No trusted device found. Pair first.', 'error');
        return;
    }

    setStatus('trusted-status', 'Checking trust status...', 'info');

    try {
        const response = await fetch(`${API_BASE}/pair/trusted`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: deviceId,
                device_public_key: devicePublicKey,
            }),
        });

        if (!response.ok) {
            setStatus('trusted-status', 'Device not trusted or key mismatch', 'error');
            return;
        }

        const data = await response.json();
        if (!data.token) {
            setStatus('trusted-status', 'Trusted reconnect did not return a token', 'error');
            return;
        }
        saveSession(
            data.device_id,
            data.token,
            devicePublicKey,
            data.trust_until || localStorage.getItem('trust_until')
        );

        setStatus('trusted-status', 'Re-paired successfully. Opening command console...', 'pair-success');
        openRemoteConsoleAfterPair();

    } catch (error) {
        setStatus('trusted-status', `Error: ${error.message}`, 'error');
    }
}

// ============================================================
// Device Key Helper
// ============================================================

function getOrCreateDevicePublicKey() {
    let key = localStorage.getItem('device_public_key');
    if (key) return key;

    const bytes = new Uint8Array(32);
    if (browserCrypto?.getRandomValues) {
        browserCrypto.getRandomValues(bytes);
    } else {
        for (let i = 0; i < bytes.length; i++) {
            bytes[i] = Math.floor(Math.random() * 256);
        }
    }

    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    key = btoa(binary);
    localStorage.setItem('device_public_key', key);
    return key;
}

// ============================================================
// Session Management
// ============================================================

function saveSession(deviceId, token, publicKey, trustUntil) {
    // Use sessionStorage (clears on tab close - more secure than localStorage)
    sessionStorage.setItem('device_id', deviceId);
    sessionStorage.setItem('token', token);

    // Keep device_id and public_key in localStorage for trusted re-pairing
    localStorage.setItem('last_device_id', deviceId);
    if (publicKey) {
        localStorage.setItem('device_public_key', publicKey);
    }
    if (trustUntil) {
        localStorage.setItem('trust_until', trustUntil);
    }

    state.deviceId = deviceId;
    state.token = token;
    state.devicePublicKey = publicKey;
    state.trustUntil = trustUntil;
}

function getDeviceName() {
    const ua = navigator.userAgent;
    if (/iPhone/.test(ua)) return 'iPhone';
    if (/iPad/.test(ua)) return 'iPad';
    if (/Android/.test(ua)) return 'Android Phone';
    return 'Mobile Device';
}

function setStatus(elementId, message, type) {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = message;
        el.className = `status ${type}`;
    }
}

function setConnectionState(status, label) {
    const badge = document.getElementById('connection-badge');
    const text = document.getElementById('connection-label');
    if (!badge || !text) return;
    badge.dataset.state = status;
    text.textContent = label;
}

function authHeaders(extra = {}) {
    return {
        ...extra,
        ...(state.token ? { 'Authorization': `Bearer ${state.token}` } : {}),
    };
}

function clearNode(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
}

function emptyMessage(text) {
    const p = document.createElement('p');
    p.className = 'empty-message';
    p.textContent = text;
    return p;
}

function appendChatMessage(direction, text, label = '') {
    const thread = document.getElementById('chat-thread');
    if (!thread || !text) return null;
    const row = document.createElement('div');
    row.className = `message-row ${direction === 'outgoing' ? 'outgoing' : 'incoming'}`;
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    appendText(bubble, 'div', text, 'message-text');
    appendText(bubble, 'div', label || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), 'message-time');
    row.appendChild(bubble);
    thread.appendChild(row);
    scrollChatToBottom();
    return row;
}

function scrollChatToBottom() {
    const thread = document.getElementById('chat-thread');
    if (!thread) return;
    requestAnimationFrame(() => {
        thread.scrollTop = thread.scrollHeight;
    });
}

function appendText(parent, tag, text, className = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = text ?? '';
    parent.appendChild(el);
    return el;
}

function parseJsonSafe(value) {
    if (!value) return null;
    try {
        return JSON.parse(value);
    } catch {
        return value;
    }
}

function loadCommandMemory() {
    try {
        return JSON.parse(localStorage.getItem(COMMAND_MEMORY_KEY) || '[]');
    } catch {
        return [];
    }
}

function saveCommandToMemory(text) {
    const normalized = " ".concat(text || "").trim();
    if (!normalized) return;
    const memory = loadCommandMemory().filter(item => item.text !== normalized);
    memory.unshift({ text: normalized, used_at: Date.now() });
    localStorage.setItem(COMMAND_MEMORY_KEY, JSON.stringify(memory.slice(0, 12)));
    renderCommandMemory('');
}

function renderCommandMemory(filterText = '') {
    const box = document.getElementById('command-memory');
    if (!box) return;
    const lower = (filterText || '').toLowerCase().trim();
    const memory = loadCommandMemory()
        .filter(item => !lower || item.text.toLowerCase().includes(lower) || fuzzyMemoryScore(lower, item.text) > 0.32)
        .slice(0, 6);
    clearNode(box);
    if (memory.length === 0) {
        box.classList.add('hidden');
        return;
    }
    appendText(box, 'div', 'Recent instruction memory', 'memory-title');
    const list = document.createElement('div');
    list.className = 'memory-list';
    memory.forEach(item => {
        const btn = document.createElement('button');
        btn.className = 'memory-item';
        btn.type = 'button';
        btn.textContent = item.text;
        btn.addEventListener('click', () => {
            const input = document.getElementById('command-text');
            input.value = item.text;
            localStorage.setItem(COMMAND_DRAFT_KEY, item.text);
            previewCurrentCommand();
        });
        list.appendChild(btn);
    });
    box.appendChild(list);
    box.classList.remove('hidden');
}

function fuzzyMemoryScore(query, target) {
    if (!query || !target) return 0;
    const q = query.toLowerCase();
    const t = target.toLowerCase();
    if (t.includes(q)) return 1;
    let qi = 0;
    for (let i = 0; i < t.length && qi < q.length; i++) {
        if (t[i] === q[qi]) qi++;
    }
    return qi / Math.max(1, q.length);
}

function restoreCommandDraft() {
    const draft = localStorage.getItem(COMMAND_DRAFT_KEY) || '';
    const input = document.getElementById('command-text');
    input.value = draft;
    renderCommandMemory(draft);
    if (draft.trim()) previewCurrentCommand();
}

// ============================================================
// Token Rotation (security)
// ============================================================

async function rotateTokenNow() {
    if (!state.deviceId || !state.token) return;

    try {
        const response = await fetch(`${API_BASE}/auth/rotate`, {
            method: 'POST',
            headers: authHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
                device_id: state.deviceId,
                old_token: state.token,
            }),
        });

        if (!response.ok) {
            alert('Token rotation failed');
            return;
        }

        const data = await response.json();
        sessionStorage.setItem('token', data.new_token);
        state.token = data.new_token;

        alert('Token rotated successfully');
        checkTrustStatus();
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

function scheduleTokenRotation() {
    // Auto-rotate every 24 hours
    const lastRotation = localStorage.getItem('last_token_rotation');
    const now = Date.now();

    if (!lastRotation || now - parseInt(lastRotation) > 24 * 60 * 60 * 1000) {
        setTimeout(() => {
            rotateTokenNow();
            localStorage.setItem('last_token_rotation', now.toString());
        }, 5000);  // Rotate 5 seconds after page load
    }
}

async function checkTrustStatus() {
    const trustUntil = localStorage.getItem('trust_until');
    const display = document.getElementById('trust-status-display');

    if (trustUntil) {
        const expiry = new Date(trustUntil);
        const now = new Date();
        if (expiry > now) {
            const days = Math.ceil((expiry - now) / (1000 * 60 * 60 * 24));
            display.textContent = `Trusted (${days} days left)`;
            display.style.color = '#00aa44';
        } else {
            display.textContent = 'Expired';
            display.style.color = '#ff4444';
        }
    } else {
        display.textContent = 'Not trusted';
        display.style.color = '#888';
    }

    // Token expiry (24h from last rotation)
    const lastRotation = localStorage.getItem('last_token_rotation');
    if (lastRotation) {
        const expiry = new Date(parseInt(lastRotation) + 24 * 60 * 60 * 1000);
        document.getElementById('token-expiry-display').textContent = expiry.toLocaleString();
    }
}

// ============================================================
// Screen Navigation
// ============================================================

function showLoginScreen() {
    const login = document.getElementById('login-screen');
    const main = document.getElementById('main-screen');
    login.classList.add('active', 'entering');
    main.classList.remove('active', 'entering', 'leaving');
    setConnectionState('offline', 'Offline');
    setTimeout(() => login.classList.remove('entering'), 320);
}

function showMainScreen() {
    const login = document.getElementById('login-screen');
    const main = document.getElementById('main-screen');
    login.classList.remove('active', 'entering');
    main.classList.add('active', 'entering');
    setTimeout(() => main.classList.remove('entering'), 320);

    document.getElementById('device-name-display').textContent = getDeviceName();
    document.getElementById('device-id-display').textContent =
        state.deviceId ? state.deviceId.substring(0, 8) + '...' : '-';
    checkTrustStatus();
}

function openRemoteConsoleAfterPair(delayMs = 900) {
    setTimeout(() => {
        showMainScreen();
        setConnectionState('connecting', 'Connecting');
        connectWebSocket();
        loadHistory();
        loadApprovals();
        scheduleTokenRotation();
    }, delayMs);
}

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');

    if (tabName === 'history') loadHistory();
    if (tabName === 'approvals') loadApprovals();
    if (tabName === 'settings') checkTrustStatus();
}

// ============================================================
// Commands
// ============================================================

async function sendCommand() {
    const text = document.getElementById('command-text').value.trim();
    if (!text) return;

    const responseDiv = document.getElementById('command-response');
    const startTime = performance.now();
    responseDiv.textContent = 'Working...';
    appendChatMessage('outgoing', text);
    const workingMessage = appendChatMessage('incoming', 'Working on it...', 'Screen-AI');
    renderProgress([
        { label: 'Command received from phone', status: 'success' },
        { label: 'Planning, risk check, and model budget selection', status: 'running' },
        { label: 'Waiting for tool execution result', status: 'pending' },
    ]);

    try {
        // Check online status — queue offline commands
        if (!navigator.onLine) {
            await saveOfflineCommandDraft(text);
            renderProgress([
                { label: 'Command received from phone', status: 'success' },
                { label: 'Saved as draft for manual resend', status: 'pending' },
            ]);
            const offlineText = 'Offline. I saved this as a draft, but I will not auto-run it later. Reconnect and press Send again.';
            responseDiv.textContent = offlineText;
            if (workingMessage) workingMessage.querySelector('.message-text').textContent = offlineText;
            scrollChatToBottom();
            return;
        }

        const response = await fetch(`${API_BASE}/command`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.token}`,
            },
            body: JSON.stringify({
                text,
                device_id: state.deviceId,
            }),
        });

        const data = await response.json();
        const elapsed = Math.round(performance.now() - startTime);

        if (data.requires_approval) {
            renderProgress([
                { label: 'Command received from phone', status: 'success' },
                { label: 'Risk check requires mobile approval', status: 'running' },
                { label: `Approval request ${data.approval_id}`, status: 'pending' },
            ]);
            const approvalText = `Waiting for approval...\nApproval ID: ${data.approval_id}`;
            responseDiv.textContent = approvalText;
            if (workingMessage) workingMessage.querySelector('.message-text').textContent = approvalText;
            scrollChatToBottom();
            loadApprovals();
        } else {
            const doneStatus = response.ok && data.status !== 'failed' ? 'success' : 'failed';

            // Build rich progress with telemetry
            const progressSteps = [
                { label: 'Command received from phone', status: 'success' },
                { label: summarizeRuntime(data), status: 'success' },
            ];

            // Add telemetry timing if available
            const telemetry = data?.telemetry;
            if (telemetry) {
                progressSteps.push({
                    label: `⚡ ${telemetry.pipeline_ms || elapsed}ms · ${telemetry.tools_succeeded || 0}/${telemetry.tools_executed || 0} tools`,
                    status: 'success',
                });
            }

            progressSteps.push({ label: `Tool execution finished (${elapsed}ms)`, status: doneStatus });
            renderProgress(progressSteps);

            // Format response with metadata
            let responseText = data.result || JSON.stringify(data, null, 2);
            if (telemetry) {
                responseText += `\n\n── Telemetry ──`;
                responseText += `\nPipeline: ${telemetry.pipeline_ms}ms`;
                responseText += `\nTools: ${telemetry.tools_succeeded}/${telemetry.tools_executed} succeeded`;
                const strategy = telemetry.strategy;
                if (strategy?.circuit_breaker && Object.keys(strategy.circuit_breaker).length > 0) {
                    responseText += `\nCircuit: ${Object.keys(strategy.circuit_breaker).length} tool(s) had issues`;
                }
            }
            responseDiv.textContent = responseText;
            if (workingMessage) workingMessage.querySelector('.message-text').textContent = responseText;
            scrollChatToBottom();
        }

        document.getElementById('command-text').value = '';
        localStorage.removeItem(COMMAND_DRAFT_KEY);
        saveCommandToMemory(text);
        renderPlanPreview(null);

        // Cache command in IndexedDB for offline history
        cacheForOffline(`last_command_${Date.now()}`, {
            text, result: data.result, status: data.status, time: Date.now()
        });

    } catch (error) {
        const elapsed = Math.round(performance.now() - startTime);

        // Try queuing for background sync when offline
        if (!navigator.onLine) {
            await saveOfflineCommandDraft(text);
            renderProgress([
                { label: 'Command received from phone', status: 'success' },
                { label: 'Saved as draft for manual resend', status: 'pending' },
            ]);
            const offlineText = 'Offline. Draft saved locally; reconnect and press Send again.';
            responseDiv.textContent = offlineText;
            if (workingMessage) workingMessage.querySelector('.message-text').textContent = offlineText;
            scrollChatToBottom();
        } else {
            renderProgress([
                { label: 'Command received from phone', status: 'success' },
                { label: `Network error after ${elapsed}ms`, status: 'failed' },
            ]);
            const errorText = 'Error: ' + error.message;
            responseDiv.textContent = errorText;
            if (workingMessage) workingMessage.querySelector('.message-text').textContent = errorText;
            scrollChatToBottom();
        }
    }
}

async function previewCurrentCommand() {
    const input = document.getElementById('command-text');
    const text = input?.value.trim();
    if (!text || !state.deviceId || !state.token) {
        renderPlanPreview(null);
        return;
    }
    renderLocalRouteHint(text);
    if (!navigator.onLine) {
        renderPlanPreview({ status: 'offline', message: 'Offline. Plan preview needs the local PC server.' });
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/command/preview`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.token}`,
            },
            body: JSON.stringify({ text, device_id: state.deviceId }),
        });
        const data = await response.json();
        cacheRuntimeSnapshot(data);
        renderPlanPreview(data);
    } catch (error) {
        renderPlanPreview({ status: 'failed', message: error.message });
    }
}

async function renderLocalRouteHint(text) {
    const clean = (text || '').trim();
    if (!clean || clean.length < 3) return;
    const hint = await postToWorker('MODEL_ROUTE_HINT', {
        text: clean,
        memory: loadCommandMemory(),
    }, 650);
    if (!hint) return;
    renderPlanPreview({
        status: 'local',
        intent: 'typing',
        risk_level: 0,
        requires_approval: false,
        step_count: 0,
        message: 'Local phone memory is preparing the model route...',
        model_plan: {
            budget_mode: 'phone-preview',
            model_budget_mb: 0,
            recommended: hint.recommended,
            lanes: hint.lanes,
            prefetch: [],
            teacher_fallback: {
                enabled_by_default: false,
                why: 'server decides teacher fallback after budget check',
            },
        },
        memory_matches: hint.memory_matches,
    });
}

function cacheRuntimeSnapshot(data) {
    if (!data) return;
    const snapshot = {
        cached_at: Date.now(),
        runtime: data.runtime || null,
        ssd_tier: data.ssd_tier || null,
        model_plan: data.model_plan || null,
    };
    localStorage.setItem(RUNTIME_SNAPSHOT_KEY, JSON.stringify(snapshot));
    cacheForOffline(RUNTIME_SNAPSHOT_KEY, snapshot);
}

function renderPlanPreview(data) {
    const box = document.getElementById('plan-preview');
    if (!box) return;
    clearNode(box);
    if (!data) {
        box.classList.add('hidden');
        return;
    }
    const meta = document.createElement('div');
    meta.className = 'meta';
    const risk = Number(data.risk_level || 0);
    const riskClass = risk >= 3 ? 'risk-high' : (risk >= 2 ? 'risk-medium' : 'risk-low');
    [
        `intent: ${data.intent || data.status || 'unknown'}`,
        `risk: ${risk}`,
        data.requires_approval ? 'mobile approval needed' : 'no approval needed',
        `${data.step_count || 0} step(s)`,
    ].forEach((label, index) => {
        const chip = document.createElement('span');
        chip.className = `plan-chip ${index === 1 ? riskClass : ''}`;
        chip.textContent = label;
        meta.appendChild(chip);
    });
    box.appendChild(meta);
    appendText(box, 'div', data.message || 'Plan preview ready.');
    if (data.plan) {
        const pre = document.createElement('pre');
        pre.textContent = JSON.stringify(data.plan, null, 2);
        box.appendChild(pre);
    }
    if (data.model_plan) {
        const plan = data.model_plan;
        const modelBox = document.createElement('div');
        modelBox.className = 'model-route';
        appendText(modelBox, 'div', 'Model route', 'memory-title');
        const chips = document.createElement('div');
        chips.className = 'meta';
        [
            `budget: ${plan.budget_mode || 'auto'}`,
            `model MB: ${plan.model_budget_mb || 0}`,
            ...(plan.recommended || []).slice(0, 6).map(name => `model: ${name}`),
        ].forEach(label => {
            const chip = document.createElement('span');
            chip.className = 'plan-chip';
            chip.textContent = label;
            chips.appendChild(chip);
        });
        modelBox.appendChild(chips);
        (plan.lanes || []).forEach(lane => {
            const row = document.createElement('div');
            row.className = 'progress-step pending';
            const laneModels = (lane.models || []).join(' + ');
            row.textContent = `${lane.lane || 'lane'}: ${laneModels} (${lane.mode || 'auto'})`;
            modelBox.appendChild(row);
        });
        if (plan.teacher_fallback) {
            appendText(
                modelBox,
                'div',
                `Teacher fallback: ${plan.teacher_fallback.enabled_by_default ? 'on' : 'off'} - ${plan.teacher_fallback.why || ''}`,
                'empty-message'
            );
        }
        box.appendChild(modelBox);
    }
    if (data.memory_matches?.length) {
        const memoryBox = document.createElement('div');
        memoryBox.className = 'command-memory';
        appendText(memoryBox, 'div', 'Parallel memory matches', 'memory-title');
        data.memory_matches.slice(0, 3).forEach(item => {
            appendText(memoryBox, 'div', item.text || item.command || item.input_text || '', 'memory-item');
        });
        box.appendChild(memoryBox);
    }
    box.classList.remove('hidden');
    scrollChatToBottom();
}

function summarizeRuntime(data) {
    const runtime = data?.runtime;
    const telemetry = data?.telemetry;
    if (!runtime && !telemetry) return 'Planning and safety checks finished';

    let parts = [];
    if (runtime) {
        const tier = runtime.tier || runtime.mode || 'auto';
        const reason = runtime.reason || '';
        parts.push(reason ? `${tier}: ${reason}` : tier);
    }
    if (telemetry) {
        parts.push(`${telemetry.pipeline_ms || 0}ms`);
    }
    const ssdTier = data?.ssd_tier;
    if (ssdTier?.mode) {
        parts.push(`placement: ${ssdTier.mode}`);
    }
    return parts.join(' · ') || 'Planning and safety checks finished';
}

function renderProgress(steps) {
    const box = document.getElementById('command-progress');
    if (!box) return;
    clearNode(box);
    if (!steps || steps.length === 0) {
        box.classList.add('hidden');
        return;
    }
    steps.forEach(step => {
        const row = document.createElement('div');
        row.className = `progress-step ${step.status || 'pending'}`;
        row.textContent = step.label || '';
        box.appendChild(row);
    });
    box.classList.remove('hidden');
    scrollChatToBottom();
}

// ============================================================
// Approvals
// ============================================================

async function loadApprovals() {
    try {
        const response = await fetch(`${API_BASE}/approvals/pending?device_id=${state.deviceId}`, {
            headers: authHeaders(),
        });

        const data = await response.json();
        const list = document.getElementById('approvals-list');
        clearNode(list);

        if (!data.approvals || data.approvals.length === 0) {
            list.appendChild(emptyMessage('No pending approvals'));
            return;
        }

        data.approvals.forEach(approval => {
            const card = document.createElement('div');
            card.className = 'approval-card';
            appendText(card, 'h3', approval.action_type);
            appendText(card, 'p', approval.description, 'description');

            if (approval.impact_summary) {
                const impact = document.createElement('div');
                impact.className = 'impact';
                appendText(impact, 'strong', 'Impact:');
                appendText(
                    impact,
                    'pre',
                    JSON.stringify(parseJsonSafe(approval.impact_summary), null, 2)
                );
                card.appendChild(impact);
            }

            const actions = document.createElement('div');
            actions.className = 'approval-actions';
            const approve = document.createElement('button');
            approve.className = 'approve-btn';
            approve.textContent = 'Approve';
            approve.addEventListener('click', () => resolveApproval(approval.id, true));
            const reject = document.createElement('button');
            reject.className = 'reject-btn';
            reject.textContent = 'Reject';
            reject.addEventListener('click', () => resolveApproval(approval.id, false));
            actions.append(approve, reject);
            card.appendChild(actions);
            list.appendChild(card);
        });

    } catch (error) {
        console.error('Failed to load approvals:', error);
    }
}

async function resolveApproval(approvalId, approved) {
    let masterKey = null;

    if (approved) {
        masterKey = prompt('Enter master key (if required):');
    }

    try {
        const response = await fetch(`${API_BASE}/approvals/resolve?device_id=${encodeURIComponent(state.deviceId)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...authHeaders(),
            },
            body: JSON.stringify({
                approval_id: approvalId,
                approved,
                master_key: masterKey,
            }),
        });

        if (response.ok) {
            loadApprovals();
        }
    } catch (error) {
        console.error('Failed to resolve approval:', error);
    }
}

// ============================================================
// History
// ============================================================

async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/history?limit=50&device_id=${encodeURIComponent(state.deviceId)}`, {
            headers: authHeaders(),
        });
        const data = await response.json();
        state.history = data.history || [];

        renderHistory(state.history);

    } catch (error) {
        console.error('Failed to load history:', error);
        // Try IndexedDB cache for offline history
        try {
            const cached = await readFromCache('last_history');
            if (cached) renderHistory(cached);
        } catch {}
    }
}

function renderHistory(items) {
    const list = document.getElementById('history-list');
    clearNode(list);

    if (!items || items.length === 0) {
        list.appendChild(emptyMessage('No history yet'));
        return;
    }

    // Add search box for fuzzy filtering
    const searchBox = document.createElement('input');
    searchBox.type = 'text';
    searchBox.placeholder = '🔍 Search history...';
    searchBox.className = 'history-search';
    searchBox.style.cssText = 'width:100%;padding:8px 12px;margin-bottom:8px;background:#1a1a1a;border:1px solid #333;border-radius:6px;color:#e0e0e0;font-size:0.85rem;';
    let searchTimer = null;
    searchBox.addEventListener('input', (e) => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(async () => {
            const q = e.target.value.trim();
            if (!q) { renderHistory(state.history); return; }
            // Offload fuzzy search to web worker
            const filtered = await postToWorker('FUZZY_SEARCH', {
                query: q,
                items: items.map(h => ({ ...h, input_text: h.input_text || h.command || '' })),
            }, 2000);
            if (filtered && filtered.length > 0) {
                renderHistoryList(list, filtered);
            } else {
                // Fallback: client-side substring
                const lower = q.toLowerCase();
                const fallback = items.filter(h =>
                    (h.input_text || '').toLowerCase().includes(lower) ||
                    (h.result || '').toLowerCase().includes(lower)
                );
                renderHistoryList(list, fallback);
            }
        }, 250);
    });
    list.appendChild(searchBox);

    renderHistoryList(list, items);
}

function renderHistoryList(container, items) {
    // Clear everything except the search box
    const searchBox = container.querySelector('.history-search');
    container.innerHTML = '';
    if (searchBox) container.appendChild(searchBox);

    items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'history-item';
        appendText(row, 'div', item.input_text, 'command');
        appendText(
            row,
            'div',
            `${item.status} - ${new Date(item.created_at).toLocaleString()}`,
            `status ${item.status}`
        );
        if (item.result) {
            appendText(row, 'div', item.result, 'history-result');
        }
        if (item._score !== undefined) {
            appendText(row, 'div', `Relevance: ${Math.round(item._score * 100)}%`, 'history-score');
        }
        container.appendChild(row);
    });
}

// ============================================================
// Emergency Stop
// ============================================================

async function emergencyStop() {
    if (!confirm('EMERGENCY STOP\n\nThis will halt all operations. Continue?')) {
        return;
    }

    try {
        await fetch(`${API_BASE}/emergency/stop?device_id=${encodeURIComponent(state.deviceId)}`, {
            method: 'POST',
            headers: authHeaders(),
        });

        alert('Emergency stop activated');
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// ============================================================
// Unpair
// ============================================================

function unpairDevice() {
    if (!confirm('Unpair this device? You will need to pair again to use it.')) {
        return;
    }

    sessionStorage.removeItem('device_id');
    sessionStorage.removeItem('token');
    localStorage.removeItem('last_device_id');
    localStorage.removeItem('device_public_key');
    localStorage.removeItem('trust_until');

    state.deviceId = null;
    state.token = null;
    state.devicePublicKey = null;
    state.trustUntil = null;

    if (state.ws) {
        state.ws.onclose = null;
        state.ws.close();
        state.ws = null;
    }
    if (state.wsReconnectTimer) {
        clearTimeout(state.wsReconnectTimer);
        state.wsReconnectTimer = null;
    }
    renderProgress([]);

    showLoginScreen();
}

// ============================================================
// WebSocket
// ============================================================

function connectWebSocket() {
    if (!state.deviceId || !state.token) {
        setConnectionState('offline', 'Offline');
        return;
    }
    if (state.wsReconnectTimer) {
        clearTimeout(state.wsReconnectTimer);
        state.wsReconnectTimer = null;
    }
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
        return;
    }

    try {
        setConnectionState('connecting', 'Connecting');
        const params = new URLSearchParams({
            device_id: state.deviceId || '',
            token: state.token || '',
        });
        state.ws = new WebSocket(`${WS_SCHEME}//${window.location.host}/ws?${params.toString()}`);

        state.ws.onopen = () => {
            console.log('WebSocket connected');
            setConnectionState('online', 'Connected');
        };

        state.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('WS message:', data);

            if (data.type === 'command_result') {
                renderProgress([
                    { label: 'Realtime command event received', status: 'success' },
                    { label: 'History and approvals refreshed', status: 'success' },
                ]);
                loadHistory();
                loadApprovals();
            } else if (data.type === 'progress') {
                renderProgress(data.steps || [{ label: data.message || 'Agent progress update', status: data.status || 'running' }]);
            }
        };

        state.ws.onclose = () => {
            console.log('WebSocket disconnected');
            state.ws = null;
            if (!state.deviceId || !state.token) {
                setConnectionState('offline', 'Offline');
                return;
            }
            setConnectionState('connecting', 'Reconnecting');
            state.wsReconnectTimer = setTimeout(connectWebSocket, 5000);
        };

        state.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            setConnectionState('offline', 'Socket error');
        };
    } catch (error) {
        console.error('Failed to connect WebSocket:', error);
        setConnectionState('offline', 'Offline');
    }
}
