# Screen-AI Run Change Log

## 2026-07-24 01:50:32 +05:30

Purpose: repair the enhanced mobile/PC login implementation that was left hanging by the previous run.

### Fixed Hanging Test

- Stopped stale `test_login_v2.py` Python processes.
- Updated `test_login_v2.py` to close the shared SQLite connection after completion.
- Verified the login V2 test completes under a hard timeout instead of running indefinitely.

### Backend Pairing V2

- Fixed FastAPI lifespan global state so `pairing_manager_v2` is actually initialized.
- Fixed QR pairing completion when the in-memory private key is missing after restart.
- Committed QR session `used` updates immediately.
- `trust_device()` now reports false when no active device was updated.
- QR pairing now returns a normal local session token for the MVP flow, while keeping encrypted token metadata when possible.
- Trusted reconnect now returns a usable token that the frontend can store.
- Token rotation now records an audit row in `token_rotations`.

### Frontend Login

- Updated `remote/index.html` to use the new `login-screen` DOM expected by `app.js`.
- Kept 6-digit code pairing as the reliable fallback.
- QR scan now fails gracefully if camera APIs or the QR library are unavailable.
- Removed dependency on browser X25519 WebCrypto support for MVP pairing.
- Trusted reconnect now calls `saveSession()` with the returned token.

### Verification

```text
python -m py_compile pairing_v2.py database.py main.py test_login_v2.py : pass
node --check frontend/app.js : pass
python -u ai_pc_operator/backend/test_login_v2.py : pass
python -u ai_pc_operator/backend/test_basic.py : pass
GET /pair/qr : pass
GET /pair/code : pass
GET /remote/index.html : pass
POST /pair/qr/complete : pass
POST /auth/rotate : pass
POST /pair/trusted : pass
```

## 2026-07-24 00:19:07 +05:30

Purpose: address the five missing runtime integrations: model placeholders, unused prompts, missing artifact discovery, unwired screen cache, and unused log redaction.

### Model Loaders

- Added `app/runtime/artifact_store.py`.
- Added `app/runtime/model_loaders.py`.
- Removed `placeholder_loader` from the live registry path.
- Registered real optional loaders for:
  - `ocr-mobile`
  - `ui-detector-int8`
  - `qwen-1.5b-q4`
  - `vault-crypto`
  - `browser-warmup`

The loaders are dependency/artifact aware. They return an unavailable status with a reason instead of crashing on 4 GB machines without the heavy packages installed.

### Prompt / LLM Planning

- Added `app/agent/llm_planner.py`.
- `LLMPlanner` imports and uses:
  - `SYSTEM_PROMPT`
  - `USER_PROMPT_TEMPLATE`
- `AgentRouter` now attempts local LLM planning only when:
  - rule planner returns `unknown`
  - RAM budget allows `qwen-1.5b-q4`
  - the GGUF model loader returns a loaded model

### Artifact Discovery

- Added model staging/inventory CLI:

```powershell
python .\ai_pc_operator\backend\scripts\model_artifacts.py inventory
python .\ai_pc_operator\backend\scripts\model_artifacts.py stage-yolo <ui_detector_int8.onnx>
python .\ai_pc_operator\backend\scripts\model_artifacts.py stage-gguf <qwen.gguf>
```

- Search locations:
  - `ai_pc_operator/data/models`
  - `hackathon_ui_operator_distill/data`
  - `hackathon_ui_operator_distill/runs`
  - `SCREEN_AI_MODEL_DIR`

### Screen Cache

- Added backend `app/runtime/screen_cache.py`.
- Cache hierarchy:

```text
ai_pc_operator/data/.screen_ai_cache/
  ui_maps/
  ocr_results/
  detector_results/
```

- `AgentRouter` now writes redacted plan metadata into the cache.
- `/runtime` reports screen cache stats.

### Log Redaction

- `LogRedactor` is now installed as a logging filter in `main.py`.
- Router redacts:
  - command text saved to DB
  - approval target/description
  - action input JSON
  - action output JSON
  - memory entries
  - action errors
- Nested dict/list redaction now works.

### API

- `/runtime` now returns:
  - memory budget
  - registered/loading/loaded model details
  - artifact inventory
  - screen cache stats

### Verification

```text
python -m py_compile ... : pass
python -u .\ai_pc_operator\backend\test_basic.py : pass
python .\ai_pc_operator\backend\scripts\model_artifacts.py inventory : pass
GET /runtime : pass
POST /command search best air coolers in chrome : pass
POST /command close browser : pass
```

## 2026-07-24 00:09:12 +05:30

Purpose: make browser/search commands actually execute instead of returning `No actions taken`.

### Planner

- Expanded browser intent matching for natural commands:
  - `search best air coolers in chrome`
  - `open YouTube`
  - `open github.com`
  - `close browser`
- Added common site aliases for YouTube, Google, GitHub, Gmail, Amazon, Reddit, Instagram, LinkedIn, ChatGPT, and related services.
- Search query extraction now removes execution hints like `in chrome`, `on browser`, and `with edge`.

### Browser Tool

- Added URL normalization for bare domains.
- Added query URL encoding for search commands.
- Added fallback to the OS default browser when Playwright/Chromium is unavailable.

### Router

- Changed empty/no-step plans to return:

```text
status: unsupported
```

instead of:

```text
status: completed
result: No actions taken
```

This makes planner gaps visible during testing.

### Vault Compatibility

- Added PBKDF2-HMAC-SHA256 fallback when the local Windows `cryptography` package has a broken Argon2 binding.
- Argon2id remains the preferred KDF path when available.

### Tests

- Added smoke assertions for browser search planning and close-browser planning.
- Installed Playwright Chromium with:

```powershell
python -m playwright install chromium
```

- Verified live API commands:

```text
search best gaming mouse in chrome
close browser
```

## 2026-07-23 23:41:06 +05:30

Purpose: start the real RAM-aware model/tool runtime pipeline requested for Screen-AI.

### Runtime Core

- Added `ai_pc_operator/backend/app/runtime/`.
- Added RAM-aware startup/runtime budget:
  - measures available memory
  - caps model budget
  - exposes `tier0-only`, `ocr-only`, `perception-only`, and `balanced` modes
- Added shared I/O thread pool for blocking disk/model/tool work.
- Added lazy `ModelRegistry` with async prefetch and idle unload.
- Added `ToolHeatMap` to learn which tools follow which intents.
- Added `AgentTierManager` to produce tier decisions from intent + RAM budget + heat map.

### AgentRouter Integration

- `AgentRouter` now creates:
  - `ResourceBudget`
  - `IOPool`
  - `ModelRegistry`
  - `ToolHeatMap`
  - `AgentTierManager`
- Command flow now:
  - saves command
  - measures RAM off-loop while classifying intent
  - assesses risk while tier decision and prefetch run
  - records tool heat map after planning
  - executes sync tools through I/O pool
  - unloads idle resources after each command
- Response now includes a `runtime` block with the tier decision.

### Prefetch And Hot Tools

- Registered lazy placeholder model names:
  - `ocr-mobile`
  - `ui-detector-int8`
  - `qwen-1.5b-q4`
  - `vault-crypto`
  - `browser-warmup`
- Added safe tool prefetch:
  - browser warmup imports Playwright only, does not launch Chromium
  - auth warmup imports cryptography only, does not unlock vault

### API

- Added:

```text
GET /runtime
```

Returns:

- available RAM
- model budget
- runtime mode
- OCR/detector/LLM allowance
- registered/loaded/loading models

### Notes

- Real model artifacts are not downloaded yet.
- The pipeline is ready for real PaddleOCR, YOLO ONNX, and GGUF loaders.
- All heavy loaders must go through `ModelRegistry` and `IOPool`, not direct event-loop imports.

## 2026-07-23 17:03:33 +05:30

Purpose: fine-tune Screen-AI for low-memory 4 GB laptop operation using the review notes in the attached text file.

### Backend Performance And Memory

- Reworked SQLite access to use one shared `aiosqlite` connection instead of opening a new DB connection for every helper call.
- Added serialized `db_session()` access, WAL mode, `synchronous=NORMAL`, and `busy_timeout=5000`.
- Added lifecycle shutdown for the shared DB connection.
- Added missing DB indexes:
  - `idx_approvals_command`
  - `idx_quarantine_command`
- Changed command history to avoid `SELECT *`; it now selects only required fields, truncates `result`, and clamps `limit`.

### Command Pipeline

- Confirmed approval waits yield through `asyncio.wait_for`.
- Added `AgentRouter.shutdown()` to release heavy tool resources.
- Fixed `/command` device verification to await the async pairing verifier.

### Browser Memory

- Added lazy Playwright lifecycle tracking.
- Added Chromium idle eviction after 300 seconds through `BrowserTools.unload_idle()`.
- Browser is closed during FastAPI shutdown.

### File Tools

- Replaced unbounded recursive scans with bounded traversal.
- Limits:
  - max files: 5000
  - max depth: 3
  - timeout: 10 seconds
- Protected paths are rejected for scan unless explicitly handled by higher approval policy.
- Quarantine size calculation now uses bounded traversal.
- Quarantine listing now selects explicit columns and limits results.

### Vault

- Removed module-level cryptography imports for lazy loading.
- Added configurable Argon2id KDF profile.
- Added per-unlock-session derived key cache keyed by salt.
- Wipes cached keys on lock.
- Fixed `last_used` update.
- Made credential insert idempotent with SQLite upsert.
- Smoke tests use a lighter KDF profile; production defaults remain stronger.

### Regex And Redaction

- Precompiled planner intent patterns.
- Precompiled risk classifier patterns.
- Precompiled log redactor secret patterns.
- Fixed redactor output so quoted secrets do not leave doubled quotes.

### Scanner

- Added short identical-screen cache to `screen_element_scanner/scan_screen.py`.
- New option:

```powershell
python .\screen_element_scanner\scan_screen.py --cache-ttl 2
```

- Cache files are ignored through `.gitignore`.

### Dependencies

- Trimmed unused backend dependencies:
  - removed `pywinauto`
  - removed `pytesseract`
  - removed `python-jose[cryptography]`
  - removed `passlib[bcrypt]`
- Updated Playwright pin from `1.40.0` to `1.54.0`.

### Tests And Verification

Commands run:

```powershell
python -m py_compile screen_element_scanner\scan_screen.py ai_pc_operator\backend\app\db\database.py ai_pc_operator\backend\app\agent\planner.py ai_pc_operator\backend\app\security\risk.py ai_pc_operator\backend\app\agent\router.py ai_pc_operator\backend\app\approvals\manager.py ai_pc_operator\backend\app\main.py ai_pc_operator\backend\app\tools\browser_tools.py ai_pc_operator\backend\app\tools\file_tools.py ai_pc_operator\backend\app\security\vault.py ai_pc_operator\backend\app\security\pairing.py ai_pc_operator\backend\app\logs\redactor.py ai_pc_operator\backend\test_basic.py
python -u .\ai_pc_operator\backend\test_basic.py
python .\screen_element_scanner\scan_screen.py --quiet
```

Result:

```text
All passed.
```

### Development Notes

- Earlier timed-out test runs left stale Python processes holding the SQLite DB lock. Those processes were stopped before the final successful smoke test.
- `aiosqlite==0.19.0` was installed locally to run the backend smoke test.
