// Screen-AI Mobile Remote App

const API_BASE = window.location.origin;
const WS_URL = `ws://${window.location.host}/ws`;

// State
let state = {
    deviceId: localStorage.getItem('device_id'),
    token: localStorage.getItem('token'),
    ws: null,
};

// DOM Elements
const pairingScreen = document.getElementById('pairing-screen');
const mainScreen = document.getElementById('main-screen');
const pairingCode = document.getElementById('pairing-code');
const deviceName = document.getElementById('device-name');
const pairButton = document.getElementById('pair-button');
const pairError = document.getElementById('pair-error');

// Initialize
init();

function init() {
    // Check if already paired
    if (state.deviceId && state.token) {
        showMainScreen();
        connectWebSocket();
        loadHistory();
        loadApprovals();
    } else {
        showPairingScreen();
    }

    // Event listeners
    pairButton.addEventListener('click', pairDevice);
    document.getElementById('send-command').addEventListener('click', sendCommand);
    document.getElementById('emergency-stop').addEventListener('click', emergencyStop);
    document.getElementById('unpair-button').addEventListener('click', unpairDevice);

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Auto-format pairing code
    pairingCode.addEventListener('input', (e) => {
        e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6);
    });
}

// Pairing
async function pairDevice() {
    const code = pairingCode.value.trim();
    const name = deviceName.value.trim() || 'Mobile Device';

    if (code.length !== 6) {
        pairError.textContent = 'Please enter a 6-digit code';
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
            pairError.textContent = error.detail || 'Pairing failed';
            return;
        }

        const data = await response.json();

        // Save credentials
        state.deviceId = data.device_id;
        state.token = data.token;
        localStorage.setItem('device_id', data.device_id);
        localStorage.setItem('token', data.token);

        // Show main screen
        showMainScreen();
        connectWebSocket();
        loadHistory();
        loadApprovals();

    } catch (error) {
        pairError.textContent = 'Network error: ' + error.message;
    }
}

function showPairingScreen() {
    pairingScreen.classList.add('active');
    mainScreen.classList.remove('active');
}

function showMainScreen() {
    pairingScreen.classList.remove('active');
    mainScreen.classList.add('active');

    // Update settings
    document.getElementById('device-name-display').textContent =
        localStorage.getItem('device_name') || 'Mobile Device';
    document.getElementById('device-id-display').textContent =
        state.deviceId.substring(0, 8) + '...';
}

// Tabs
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');

    // Load data
    if (tabName === 'history') loadHistory();
    if (tabName === 'approvals') loadApprovals();
}

// Commands
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
            responseDiv.textContent = `⏳ Waiting for approval...\nApproval ID: ${data.approval_id}`;
            loadApprovals();
        } else {
            responseDiv.textContent = JSON.stringify(data, null, 2);
        }

        // Clear input
        document.getElementById('command-text').value = '';

    } catch (error) {
        responseDiv.textContent = 'Error: ' + error.message;
    }
}

// Approvals
async function loadApprovals() {
    try {
        const response = await fetch(`${API_BASE}/approvals/pending?device_id=${state.deviceId}`, {
            headers: { 'Authorization': `Bearer ${state.token}` },
        });

        const data = await response.json();
        const list = document.getElementById('approvals-list');

        if (!data.approvals || data.approvals.length === 0) {
            list.innerHTML = '<p style="color: #888; text-align: center;">No pending approvals</p>';
            return;
        }

        list.innerHTML = data.approvals.map(approval => `
            <div class="approval-card">
                <h3>⚠️ ${approval.action_type}</h3>
                <p class="description">${approval.description}</p>
                ${approval.impact_summary ? `
                    <div class="impact">
                        <strong>Impact:</strong>
                        <pre>${JSON.stringify(JSON.parse(approval.impact_summary || '{}'), null, 2)}</pre>
                    </div>
                ` : ''}
                <div class="approval-actions">
                    <button class="approve-btn" onclick="resolveApproval(${approval.id}, true)">
                        ✓ Approve
                    </button>
                    <button class="reject-btn" onclick="resolveApproval(${approval.id}, false)">
                        ✗ Reject
                    </button>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Failed to load approvals:', error);
    }
}

async function resolveApproval(approvalId, approved) {
    let masterKey = null;

    // Ask for master key if needed
    if (approved) {
        masterKey = prompt('Enter master key (if required):');
    }

    try {
        const response = await fetch(`${API_BASE}/approvals/resolve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.token}`,
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

// History
async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/history?limit=50`);
        const data = await response.json();

        const list = document.getElementById('history-list');

        if (!data.history || data.history.length === 0) {
            list.innerHTML = '<p style="color: #888; text-align: center;">No history yet</p>';
            return;
        }

        list.innerHTML = data.history.map(item => `
            <div class="history-item">
                <div class="command">${item.input_text}</div>
                <div class="status ${item.status}">
                    ${item.status} • ${new Date(item.created_at).toLocaleString()}
                </div>
                ${item.result ? `<div style="margin-top: 8px; font-size: 0.85em; color: #aaa;">${item.result}</div>` : ''}
            </div>
        `).join('');

    } catch (error) {
        console.error('Failed to load history:', error);
    }
}

// Emergency Stop
async function emergencyStop() {
    if (!confirm('🛑 EMERGENCY STOP\n\nThis will halt all operations. Continue?')) {
        return;
    }

    try {
        await fetch(`${API_BASE}/emergency/stop`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${state.token}` },
        });

        alert('🛑 Emergency stop activated');
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// Unpair
function unpairDevice() {
    if (!confirm('Unpair this device? You will need to pair again to use it.')) {
        return;
    }

    localStorage.removeItem('device_id');
    localStorage.removeItem('token');
    state.deviceId = null;
    state.token = null;

    showPairingScreen();
}

// WebSocket
function connectWebSocket() {
    try {
        state.ws = new WebSocket(WS_URL);

        state.ws.onopen = () => {
            console.log('WebSocket connected');
        };

        state.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('WS message:', data);

            if (data.type === 'command_result') {
                // Update UI
                loadHistory();
                loadApprovals();
            }
        };

        state.ws.onclose = () => {
            console.log('WebSocket disconnected');
            // Reconnect after 5 seconds
            setTimeout(connectWebSocket, 5000);
        };

        state.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    } catch (error) {
        console.error('Failed to connect WebSocket:', error);
    }
}
