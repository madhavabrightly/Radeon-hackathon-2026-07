# Screen-AI Memory File

This file provides **fast context loading** for AI agents working on Screen-AI. Read this first before exploring the codebase.

## Quick Facts

- **Project**: Screen-AI (Local AI PC Operator)
- **Track**: Hackathon Track 2 - Agentic AI
- **Platform**: Windows (primary), cross-platform future
- **Hardware Target**: 4GB RAM laptops (low-resource)
- **GPU**: AMD ROCm (cloud), RTX (local dev)
- **Language**: Python (backend), JavaScript (frontend)
- **Database**: SQLite
- **Server**: FastAPI
- **Browser**: Playwright
- **UI Automation**: Windows UIA + OpenCV + OCR

## Core Architecture (30-Second Summary)

```
Mobile Remote (phone)
    ↓ text commands / approvals
Local PC Agent Server (FastAPI)
    ↓
Agent Brain (LLM planner)
    ↓
Risk + Permission Engine
    ↓
Tool Executor
    ↓
File/Browser/App/System/Vault/Passkey/Download/Screen tools
```

## Key Principles

1. **Local-first**: Everything runs on user's PC
2. **Phone approval**: Critical actions need phone confirmation
3. **Quarantine first**: Deletes go to quarantine, not permanent
4. **Log redaction**: Passwords never appear in logs
5. **Tiered models**: Small models for simple tasks, big for complex
6. **Lazy loading**: Heavy models loaded only when needed

## Current Status

### ✅ Working

- Screen scanning (UIA + OpenCV)
- Click-by-text execution
- Screenshot capture
- JSON UI maps
- Debug overlay images

### 🚧 In Progress

- FastAPI server
- Mobile web remote
- Pairing system
- File tools with quarantine

### 📋 Planned

- Password vault
- Passkey flow
- Browser tools
- Local LLM routing

## File Structure (Critical Files)

```
Screen-AI/
├── AGENTS.md              # Agent guide (read first)
├── FUTUREPLANS.md         # Roadmap and future plans
├── MEMORY.md              # This file (fast context)
├── README.md              # Project overview
│
├── screen_element_scanner/
│   ├── scan_screen.py     # Main scanner (UIA + OpenCV)
│   └── uia_scan.ps1       # PowerShell UIA scanner
│
├── hackathon_ui_operator_distill/
│   ├── cloud/             # AMD ROCm training pipeline
│   ├── data/              # Datasets
│   ├── docs/              # Documentation
│   ├── local_runtime/     # Local execution
│   └── native/            # C/C++ native code
│
└── ai_pc_operator/        # NEW - Main product (to be built)
    ├── backend/
    │   └── app/
    │       ├── main.py
    │       ├── agent/
    │       ├── security/
    │       ├── tools/
    │       ├── approvals/
    │       ├── db/
    │       └── logs/
    └── frontend/
        └── src/
```

## Key Commands

### Screen Scanning

```powershell
# Scan current screen
python .\screen_element_scanner\scan_screen.py

# Click by text (dry-run)
python .\hackathon_ui_operator_distill\local_runtime\click_by_text.py "Share" --dry-run

# Collect screenshots for training
python .\hackathon_ui_operator_distill\local_runtime\collect_screenshot.py
```

### Cloud GPU (AMD ROCm)

```bash
# Setup cloud environment
bash cloud/setup_cloud_gpu.sh

# Download OmniParser v2
bash cloud/download_omniparser_v2.sh

# Train YOLO student model
python cloud/train_student_yolo.py --data data/yolo_dataset/ui_dataset.yaml --model yolov8n.pt --epochs 80 --device 0

# Export to INT8 ONNX
python cloud/export_int8_onnx.py --weights runs/ui_student/weights/best.pt --out ui_detector_int8.onnx
```

## Model Stack (4GB RAM)

| Component | Model | RAM | When |
|-----------|-------|-----|------|
| UI Detection | UIA + OpenCV | ~150 MB | Always |
| OCR | PaddleOCR Mobile | ~50 MB | Fallback |
| UI Detector | YOLOv8n INT8 ONNX | ~300 MB | Fallback |
| Action LLM | Qwen2.5-1.5B Q4 | ~1.2 GB | Always |
| Vision LLM | Florence-2-base Q4 | ~1.5 GB | Optional |
| **Total** | | **~3 GB** | |

## Access Levels

| Level | Action | Approval |
|-------|--------|----------|
| 0 | Read status, search | None |
| 1 | Open app/site | None |
| 2 | Download, rename | Maybe |
| 3 | Email, login, install | Phone |
| 4 | Delete, bulk ops | Phone required |
| 5 | Permanent delete, export | Special mode |

## Database Tables

- `commands` - All user commands
- `approvals` - Pending/resolved approvals
- `actions` - Executed tool actions
- `devices` - Paired phones
- `vault_entries` - Encrypted credentials
- `quarantine` - Quarantined files
- `sessions` - Active sessions
- `settings` - User preferences

## Tool List

### File Tools
- `file.list`, `file.scan`, `file.read`
- `file.move`, `file.copy`
- `file.quarantine`, `file.restore`
- `file.delete_permanent`

### System Tools
- `system.status`, `system.disk_usage`
- `system.ram_usage`, `system.processes`
- `system.open_app`, `system.kill_process`
- `system.network_status`, `system.run_command`

### Browser Tools
- `browser.open`, `browser.search`
- `browser.click`, `browser.type`
- `browser.read`, `browser.download`

### Auth Tools
- `auth.password_login`
- `auth.passkey_login`
- `auth.vault_unlock`

### Approval Tools
- `approval.request`
- `approval.resolve`

## Protected Folders

- `C:\Windows`
- `C:\Program Files`
- `C:\Program Files (x86)`
- `AppData`
- Browser credential stores
- SSH keys
- `.env` files
- Wallet files

## Dangerous Extensions

- `.exe`, `.msi`, `.bat`, `.cmd`
- `.ps1`, `.vbs`, `.scr`
- `.jar`, `.js`

## Temperature Settings

| Task | Temperature |
|------|-------------|
| Tool selection | 0.0 |
| Risk classification | 0.0 |
| File operations | 0.0 |
| Login flow | 0.0-0.2 |
| Browser automation | 0.1-0.2 |
| Summarization | 0.2-0.4 |
| Writing messages | 0.4-0.7 |

## Non-Negotiable Rules

1. Critical actions require phone approval
2. Passwords are redacted from logs
3. Destructive actions use quarantine first
4. Emergency stop always works
5. All non-secret actions are logged
6. Login target domain shown before approval
7. Downloaded executables require approval
8. Full access sessions are time-limited
9. Model proposes; tool system executes
10. User can wipe logs, vault, memory, quarantine

## Common Patterns

### Command Flow

```python
# 1. Receive command
command = await receive_command()

# 2. Classify intent
intent = await classify_intent(command)

# 3. Assess risk
risk = await assess_risk(intent)

# 4. Check approval
if risk >= 3:
    approval = await request_phone_approval(intent)
    if not approval.approved:
        return "User rejected"

# 5. Execute tools
result = await execute_tools(intent)

# 6. Verify
verified = await verify_result(result)

# 7. Log
await log_action(command, intent, result)

# 8. Return
return format_response(result)
```

### Quarantine Pattern

```python
# Instead of permanent delete:
def quarantine_file(path):
    quarantine_id = generate_id()
    quarantine_path = f"data/quarantine/{quarantine_id}"
    shutil.move(path, quarantine_path)
    db.insert("quarantine", {
        "id": quarantine_id,
        "original_path": path,
        "quarantine_path": quarantine_path,
        "created_at": now()
    })
    return quarantine_id

def restore_file(quarantine_id):
    record = db.get("quarantine", quarantine_id)
    shutil.move(record.quarantine_path, record.original_path)
    db.update("quarantine", quarantine_id, {"restored_at": now()})
```

### Password Vault Pattern

```python
# Encrypt with AES-256-GCM
def encrypt_password(password, master_key):
    salt = os.urandom(16)
    key = argon2id(master_key, salt)
    nonce = os.urandom(12)
    ciphertext, tag = aes_gcm_encrypt(key, nonce, password)
    return {
        "salt": salt,
        "nonce": nonce,
        "ciphertext": ciphertext,
        "tag": tag
    }

# Decrypt
def decrypt_password(encrypted, master_key):
    key = argon2id(master_key, encrypted.salt)
    return aes_gcm_decrypt(key, encrypted.nonce, encrypted.ciphertext, encrypted.tag)
```

## Troubleshooting

### Common Issues

1. **UIA returns nothing**: App doesn't expose UI Automation
   - Solution: Fall back to OCR + OpenCV

2. **Click misses target**: Coordinates are off
   - Solution: Add verification screenshot after click

3. **Password not working**: Vault not unlocked
   - Solution: Request phone unlock first

4. **Approval timeout**: User didn't respond
   - Solution: Default to reject after 60s

5. **Model too slow**: LLM taking too long
   - Solution: Use smaller model or rule-based fallback

### Performance Tips

- Cache frequent commands
- Summarize old conversations
- Use SQLite for fast lookups
- Lazy-load heavy models
- Stream responses
- Avoid background indexing

## References

- [AGENTS.md](AGENTS.md) - Full agent guide
- [FUTUREPLANS.md](FUTUREPLANS.md) - Roadmap
- [README.md](README.md) - Project overview
- [hackathon_ui_operator_distill/docs/](hackathon_ui_operator_distill/docs/) - Technical docs

## Quick Start for New Agents

1. Read this file (MEMORY.md) - 2 minutes
2. Read AGENTS.md - 10 minutes
3. Read FUTUREPLANS.md - 5 minutes
4. Explore screen_element_scanner/ - 10 minutes
5. Check current issues/todos - 5 minutes
6. Start working on assigned task

**Total onboarding**: ~30 minutes

---

## Latest Run Memory: 2026-07-23 17:03:33 +05:30

Focus: low-memory tuning after review notes about DB connection churn, vault Argon2 spikes, Playwright idle memory, recursive scan cost, regex hot loops, missing DB indexes, screen cache wiring, and dependency bloat.

Changed:

- Added shared SQLite connection lifecycle in `ai_pc_operator/backend/app/db/database.py`.
- Added `db_session()` and migrated router, approvals, pairing, file tools, vault, and history reads to it.
- Added indexes for `approvals.command_id` and `quarantine.command_id`.
- Changed history endpoint to specific columns plus result truncation and limit clamp.
- Added router shutdown and browser close on FastAPI lifespan shutdown.
- Added browser idle unload after 300 seconds.
- Bounded file scan traversal to 5000 files, depth 3, and 10 seconds.
- Precompiled planner/risk/redactor regexes.
- Added vault per-session entry-key cache and lazy cryptography imports.
- Added configurable vault KDF profile for faster tests while keeping production defaults strong.
- Fixed vault `last_used` update and made credential upserts idempotent.
- Added scanner identical-screen cache with `--cache-ttl`.
- Trimmed backend requirements and updated Playwright pin.
- Fixed async smoke tests and ASCII console output.

Verification:

```text
py_compile: pass
backend test_basic.py: pass
screen scanner --quiet: pass
```

Operational note:

If smoke tests time out while using the shared DB, check for stale Python processes holding SQLite locks and stop them before rerunning.

## Latest Run Memory: 2026-07-23 23:41:06 +05:30

Focus: start the real model/tool runtime pipeline.

Implemented:

- Added backend runtime package:
  - `app/runtime/resource_budget.py`
  - `app/runtime/io_pool.py`
  - `app/runtime/model_registry.py`
  - `app/runtime/heatmap.py`
  - `app/runtime/tier_manager.py`
- `AgentRouter` now wires TierManager into real command processing.
- RAM budget is measured at command start.
- Intent classification overlaps with memory measurement.
- Risk assessment overlaps with tier decision and async prefetch.
- Tool heat map records tools used by each intent.
- Hot models/tools can be prefetched without blocking the event loop.
- Sync tools execute through the shared I/O thread pool.
- Browser and auth tools gained safe `prepare()` methods.
- Added `/runtime` endpoint for RAM/model status.

Current model registry uses placeholders:

```text
ocr-mobile
ui-detector-int8
qwen-1.5b-q4
vault-crypto
browser-warmup
```

Next work:

- Replace placeholders with real PaddleOCR/ONNX/GGUF lazy loaders.
- Add model download script and local model manifest.
- Add click-by-text endpoint into `ai_pc_operator`.
- Add runtime tests around `AgentRouter.process_command()`.

**Last Updated**: 2026-07-23 23:41:06 +05:30
**Version**: 1.2.0
**Maintainer**: Screen-AI Team

## Latest Run Memory: 2026-07-24 00:09:12 +05:30

Focus: fix browser/search commands that returned `completed` with `No actions taken`.

Changed:

- Broadened planner intent matching for natural browser commands.
- Added support for:
  - `search ... in chrome`
  - `open YouTube`
  - `open github.com`
  - `close browser`
- Added common site aliases in the planner.
- Cleaned browser hints out of search queries.
- URL-encoded search queries before navigation.
- Added system-browser fallback when Playwright Chromium is unavailable.
- Changed no-step plans to return `unsupported` instead of fake success.
- Added PBKDF2-HMAC-SHA256 fallback when the Windows `cryptography` Argon2 binding is broken.
- Added smoke assertions for search and browser-close planning.
- Installed Playwright Chromium locally for structured browser automation.

Current behavior:

- Browser search/open should now execute through Playwright when available.
- If Playwright browser binaries are missing, the command opens through the Windows default browser.
- Click/type/read still require Playwright to be installed and working.
- Verified `/command` with `search best gaming mouse in chrome` and `close browser`.

Next work:

- Add Playwright install/check endpoint.
- Add screen click-by-text tools into `ai_pc_operator`.
- Replace runtime placeholder models with real OCR/ONNX/GGUF loaders.

**Last Updated**: 2026-07-24 00:09:12 +05:30
**Version**: 1.2.1
**Maintainer**: Screen-AI Team

## Latest Run Memory: 2026-07-24 00:19:07 +05:30

Focus: replace model placeholders with real loader/discovery wiring and connect unused architecture pieces.

Changed:

- Added model artifact discovery:
  - `app/runtime/artifact_store.py`
  - searches `ai_pc_operator/data/models`, hackathon distill outputs, and `SCREEN_AI_MODEL_DIR`
- Added optional real loaders:
  - PaddleOCR for `ocr-mobile`
  - ONNX Runtime for `ui-detector-int8`
  - llama.cpp GGUF for `qwen-1.5b-q4`
  - cryptography warmup for `vault-crypto`
  - Playwright warmup for `browser-warmup`
- Removed `placeholder_loader` from the runtime registry.
- Added `app/agent/llm_planner.py`.
- `LLMPlanner` now imports and uses `SYSTEM_PROMPT` and `USER_PROMPT_TEMPLATE`.
- `AgentRouter` can attempt LLM planning only for unknown intents when RAM allows and a real Qwen GGUF model is loaded.
- Added backend `ScreenCache`:

```text
ai_pc_operator/data/.screen_ai_cache/
  ui_maps/
  ocr_results/
  detector_results/
```

- `AgentRouter` writes redacted plan metadata into the cache.
- `/runtime` now reports:
  - memory budget
  - model registry status
  - artifact inventory
  - screen cache stats
- `LogRedactor` is now used:
  - as a global logging filter
  - when saving commands
  - when saving action input/output JSON
  - when saving memory entries
- Nested list/dict redaction now works.
- Added artifact CLI:

```powershell
python .\ai_pc_operator\backend\scripts\model_artifacts.py inventory
python .\ai_pc_operator\backend\scripts\model_artifacts.py stage-yolo <ui_detector_int8.onnx>
python .\ai_pc_operator\backend\scripts\model_artifacts.py stage-gguf <qwen.gguf>
```

Verification:

```text
py_compile: pass
backend test_basic.py: pass
model_artifacts.py inventory: pass
/runtime: pass
/command search best air coolers in chrome: pass
/command close browser: pass
```

Current artifact inventory:

```text
ocr-mobile: missing
ui-detector-int8: missing
qwen-1.5b-q4: missing
vault-crypto: no artifact required
browser-warmup: no artifact required
```

**Last Updated**: 2026-07-24 00:19:07 +05:30
**Version**: 1.3.0
**Maintainer**: Screen-AI Team

## Latest Run Memory: 2026-07-24 01:50:32 +05:30

Focus: repair the enhanced mobile/PC login flow and stop the stuck test process.

Problems found:

- A stale `python -u ai_pc_operator/backend/test_login_v2.py` process was still running.
- `test_login_v2.py` did not close the shared SQLite connection.
- FastAPI lifespan did not declare `pairing_manager_v2` as global, so V2 endpoints could stay unavailable.
- `/remote/index.html` still used the old `pairing-screen` DOM while `app.js` expected `login-screen`.
- Frontend QR flow depended on browser X25519 WebCrypto support.
- Trusted reconnect returned a token but frontend did not save it.
- QR completion had a bad DB fallback path when the in-memory private key was gone.

Changed:

- Stopped the stale Python process.
- Added DB shutdown to `test_login_v2.py`.
- Fixed FastAPI V2 manager initialization.
- Aligned `index.html` with the enhanced login UI.
- Kept the 6-digit code flow as reliable fallback.
- Made QR scanner fail gracefully when camera/jsQR is unavailable.
- Removed frontend dependency on X25519 for MVP pairing.
- QR pairing and trusted reconnect now return/store usable local session tokens.
- Token rotation records an audit row.

Verification:

```text
py_compile: pass
node --check frontend/app.js: pass
test_login_v2.py: pass
test_basic.py: pass
/pair/qr: pass
/pair/code: pass
/remote/index.html: pass
/pair/qr/complete: pass
/auth/rotate: pass
/pair/trusted: pass
```

Current server:

```text
localhost:8000
PID seen during verification: 22372
```

**Last Updated**: 2026-07-24 01:50:32 +05:30
**Version**: 1.3.1
**Maintainer**: Screen-AI Team
