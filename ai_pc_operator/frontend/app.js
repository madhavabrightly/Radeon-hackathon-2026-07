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
    cameraStream: null,
    qrScanInterval: null,
};

// Browser entropy helper. Do not depend on X25519 WebCrypto support for MVP
// pairing; many mobile browsers still do not expose it consistently.
const browserCrypto = window.crypto || window.msCrypto;

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

        setStatus('qr-status', 'Paired successfully!', 'success');

        setTimeout(() => {
            showMainScreen();
            connectWebSocket();
            loadHistory();
            loadApprovals();
        }, 1000);

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

        showMainScreen();
        connectWebSocket();
        loadHistory();
        loadApprovals();

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

        setStatus('trusted-status', 'Re-paired successfully!', 'success');

        setTimeout(() => {
            showMainScreen();
            connectWebSocket();
            loadHistory();
            loadApprovals();
        }, 1000);

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
    document.getElementById('login-screen').classList.add('active');
    document.getElementById('main-screen').classList.remove('active');
}

function showMainScreen() {
    document.getElementById('login-screen').classList.remove('active');
    document.getElementById('main-screen').classList.add('active');

    document.getElementById('device-name-display').textContent = getDeviceName();
    document.getElementById('device-id-display').textContent =
        state.deviceId ? state.deviceId.substring(0, 8) + '...' : '-';
    checkTrustStatus();
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
    responseDiv.textContent = 'Processing...';

    try {
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

        if (data.requires_approval) {
            responseDiv.textContent = `Waiting for approval...\nApproval ID: ${data.approval_id}`;
            loadApprovals();
        } else {
            responseDiv.textContent = JSON.stringify(data, null, 2);
        }

        document.getElementById('command-text').value = '';

    } catch (error) {
        responseDiv.textContent = 'Error: ' + error.message;
    }
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

        const list = document.getElementById('history-list');
        clearNode(list);

        if (!data.history || data.history.length === 0) {
            list.appendChild(emptyMessage('No history yet'));
            return;
        }

        data.history.forEach(item => {
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
            list.appendChild(row);
        });

    } catch (error) {
        console.error('Failed to load history:', error);
    }
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

    showLoginScreen();
}

// ============================================================
// WebSocket
// ============================================================

function connectWebSocket() {
    try {
        const params = new URLSearchParams({
            device_id: state.deviceId || '',
            token: state.token || '',
        });
        state.ws = new WebSocket(`${WS_SCHEME}//${window.location.host}/ws?${params.toString()}`);

        state.ws.onopen = () => {
            console.log('WebSocket connected');
        };

        state.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('WS message:', data);

            if (data.type === 'command_result') {
                loadHistory();
                loadApprovals();
            }
        };

        state.ws.onclose = () => {
            console.log('WebSocket disconnected');
            setTimeout(connectWebSocket, 5000);
        };

        state.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    } catch (error) {
        console.error('Failed to connect WebSocket:', error);
    }
}
