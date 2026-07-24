# Screen-AI Run Change Log

## 2026-07-24 19:03:38 +05:30

Purpose: make the agent less one-shot and more capable for compound desktop tasks.

### Agent Intelligence

- Added `app/agent/task_planner.py`.
- `AgentRouter` now tries high-level task planning before single-intent rules.
- New compound intents:
  - `research_collect`
  - `open_settings`
  - `keep_awake`
- Example now plans as one real task:

```text
open chrome and search about AMD ROCm and go to 10 random websites and copy all text and paste in text file and save it folder
```

into:

```text
browser.research_collect(query="AMD ROCm", max_sites=10)
```

### Browser Research Tool

- Added `browser.research_collect`.
- It searches, visits up to 10 result pages, extracts visible body text, and saves a `.txt` report under:

```text
ai_pc_operator/data/research/
```

- Added search fallback:
  - browser search result selectors
  - HTTP Bing fallback
  - Bing redirect URL decoding

### System Utilities

- Added `system.open_settings` for Windows settings pages.
- Added `system.keep_awake` using Windows `SetThreadExecutionState` with a 120-minute cap.

### Native Endpoint Intelligence

- Added C endpoint ranking scaffold:
  - `hackathon_ui_operator_distill/native/endpoint_rank.c`
  - `hackathon_ui_operator_distill/native/endpoint_rank.h`
- `screen.click_text` now uses endpoint scoring that mirrors the native policy:

```text
text match + confidence + bounds sanity + UIA source priority
```

### LLM Prompt

- Updated local planner prompt with the richer tool surface:
  - `browser.research_collect`
  - `screen.scan`
  - `screen.click_text`
  - `system.open_settings`
  - `system.keep_awake`

### Verification

```text
py_compile: pass
endpoint_rank.c compile: pass
test_basic.py: pass
browser.research_collect("AMD ROCm", max_sites=1): pass
visited: https://www.amd.com/en/products/software/rocm.html
saved report: ai_pc_operator/data/research/research_AMD_ROCm_*.txt
```

## 2026-07-24 02:33:30 +05:30

Purpose: adapt the `codiii`/colibri SSD-tiering strategy for a 4 GB no-GPU Screen-AI runtime.

### Implemented Strategy

- Added `app/runtime/ssd_tier.py`.
- Runtime now plans model placement as:
  - `resident`: rule planner, UIA scanner, tiny warmups
  - `warm`: OCR/detector when RAM budget allows
  - `ssd-cold`: artifacts stay on SSD and lazy-load only when needed
  - `ssd-off`: too heavy for current RAM profile
- Qwen GGUF now uses llama.cpp `use_mmap=True`, smaller default context, smaller batch, and two CPU threads.
- Qwen is not prefetched and is kept `ssd-off` by default on low-RAM profiles unless `SCREEN_AI_ALLOW_COLD_LLM=1`.
- `SCREEN_AI_RAM_MB` can simulate or force a low-memory budget for testing.
- `/runtime` now reports the SSD tier plan and usage stats.
- `ModelRegistry` records model usage heat and refuses large speculative prefetches.

### codiii Ideas Adapted

- `RAM_GB` equivalent: `SCREEN_AI_RAM_MB`
- `COLI_MMAP` equivalent: `SCREEN_AI_MMAP`
- `PREFETCH` equivalent: `SCREEN_AI_PREFETCH`
- hot-store usage stats: `ai_pc_operator/data/memory/model_usage.json`
- LFRU/hysteresis native policy: `hackathon_ui_operator_distill/native/ssd_tier_policy.c`

### 4 GB Recommended Runtime

```powershell
$env:SCREEN_AI_RAM_MB="1200"
$env:SCREEN_AI_MMAP="1"
$env:SCREEN_AI_PREFETCH="0"
$env:SCREEN_AI_ALLOW_COLD_LLM="0"
$env:SCREEN_AI_LLM_CTX="512"
$env:SCREEN_AI_LLM_THREADS="2"
```

### Result

On a 4 GB no-GPU laptop, the app should run as a lightweight operator:

```text
UIA/OpenCV/rules always available
OCR/detector lazy only if RAM allows
Qwen stays on SSD/off by default
OmniParser/training stays cloud-only
```

## 2026-07-24 02:25:43 +05:30

Purpose: close the unresolved codebase-analysis gaps that could break the hackathon demo or weaken local security.

### Backend Screen Control

- Added `ai_pc_operator/backend/app/tools/screen_tools.py`.
- Registered `screen` tools in `AgentRouter`.
- Added planner support for:
  - `screen.scan`
  - `screen.click_text`
- Commands such as `scan screen buttons` and `click Share` now route through the backend instead of staying as standalone CLI-only behavior.
- `screen.click_text` uses UI Automation/actionable elements with fuzzy text scoring and supports `dry_run`.

### Security Hotfixes

- Removed unsafe `shell=True` app launch/command execution from `system_tools.py`.
- `system.open_app` now resolves sanitized app aliases/executables.
- `system.run_command` now parses argv and runs without a shell.
- Legacy pairing verification now checks the stored token hash instead of only checking device id.
- `/command`, `/history`, `/approvals/pending`, `/approvals/resolve`, `/emergency/stop`, and `/ws` now have paired-device token verification paths.
- `browser.download` now sanitizes filenames and blocks dangerous executable/script extensions.

### Frontend Fixes

- Fixed `loadHistory()` to send Authorization and device id.
- Replaced server-content `innerHTML` rendering for approvals/history with DOM nodes and `textContent`.
- WebSocket now uses `wss://` automatically on HTTPS pages.
- Approval resolve and emergency stop now send authenticated device context.
- Reduced duplicate login surface by making `login.html` redirect to the canonical `index.html`.

### Scanner Reliability

- `scan_screen.py` now tolerates UIA timeout by falling back to vision candidates.
- `uia_scan.ps1` no longer silently swallows every error; it skips broken/unavailable UIA branches per element.
- Verified normal scan on this desktop:

```text
screen: 1920x1080
uia: 459
vision: 35
total: 481
actionable: 226
```

### Cloud Pipeline

- `run_teacher_labeling.py` now runs the OmniParser V2 icon detector through Ultralytics when weights are present.
- `convert_teacher_to_yolo.py` now writes `ui_dataset.yaml`.
- `export_int8_onnx.py` now stages the final `ui_detector_int8.onnx` into `ai_pc_operator/data/models/`.
- README cloud workflow now defaults to `--mode omniparser`.

### Low-Memory Runtime

- Browser idle eviction reduced from 300 seconds to 120 seconds.
- Long-term memory JSONL search/write/delete now runs through `asyncio.to_thread()`.

### Verification

```text
py_compile backend/tools/scanner/cloud scripts: pass
node --check frontend/app.js: pass
python -u ai_pc_operator/backend/test_basic.py: pass
python -u ai_pc_operator/backend/test_login_v2.py: pass
ScreenTools.scan normal depth: pass, 226 actionable controls found
ScreenTools.click_text("Close", dry_run=True): pass
```

### Still Not Fully Complete

- Mobile vault unlock UI is still not built.
- Passkey approval UI is still not built.
- Full Access Session UI is still not built.
- Actual `ui_detector_int8.onnx` still requires running the cloud training/export workflow.

## 2026-07-24 02:10:11 +05:30

Purpose: install/save project model artifacts and make the model folder reproducible.

### Changes

- Added `ai_pc_operator/backend/scripts/download_models.py`.
- Downloader saves active local models under:

```text
ai_pc_operator/data/models/
```

- Added a generated `models_manifest.json` describing source URLs, roles, and file paths.
- Added `model_artifacts.py list-files`.
- Tightened OCR artifact discovery so OCR does not accidentally pick unrelated ONNX detector files.
- OCR loader now loads ONNX OCR artifacts through ONNX Runtime before falling back to PaddleOCR.
- Added optional runtime dependencies:
  - `onnxruntime`
  - `llama-cpp-python`

### Selected Artifacts

- Qwen2.5 Coder 1.5B GGUF Q4_0 for local planning.
- PaddleOCR ONNX detection and English recognition files for OCR.
- OmniParser V2 icon detector `.pt` as a teacher/cloud artifact for later INT8 ONNX distillation.

### Important Note

`ui_detector_int8.onnx` is still produced by our cloud distillation/export pipeline. The public OmniParser detector is PyTorch `.pt`, so it is saved as a teacher artifact instead of being mislabelled as the laptop INT8 ONNX runtime model.

### Verification

```text
download_models.py: downloaded Qwen GGUF, OCR ONNX files, OmniParser teacher files
py_compile artifact/model scripts and loaders: pass
model_artifacts.py inventory: pass
model_artifacts.py list-files: pass
OCR ONNX loader smoke test: pass
Qwen llama.cpp loader smoke test: pass
```

## 2026-07-24 02:01:49 +05:30

Purpose: fix mobile `Camera API unavailable` by adding a local HTTPS server.

### Why

Phone browsers block `getUserMedia()` on plain LAN HTTP URLs such as:

```text
http://10.211.40.102:8000/remote/index.html
```

Camera scanning needs HTTPS or localhost.

### Changes

- Added `ai_pc_operator/backend/scripts/start_https.py`.
- The script generates a local self-signed certificate under ignored runtime data:

```text
ai_pc_operator/data/certs/
```

- HTTPS server runs on:

```text
https://localhost:8443/remote/pair.html
https://10.211.40.102:8443/remote/index.html
```

### Verification

```text
python -m py_compile ai_pc_operator/backend/scripts/start_https.py : pass
GET https://localhost:8443/remote/pair.html : pass with certificate check skipped
GET https://localhost:8443/remote/index.html : pass with certificate check skipped
```

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
## 2026-07-24 01:55:28 +05:30

Purpose: add the missing PC QR display page and make the pairing links obvious.

### Links

- PC QR display page:

```text
http://localhost:8000/remote/pair.html
```

- Mobile remote/scanner page:

```text
http://localhost:8000/remote/index.html
```

### Changes

- Added `ai_pc_operator/frontend/pair.html`.
- The PC page fetches:
  - `GET /pair/qr`
  - `GET /pair/code`
- The PC page renders:
  - scan-ready QR code
  - fallback 6-digit code
  - mobile remote link
  - raw QR payload for debugging
- The root endpoint now advertises:
  - `pc_pairing_page`
  - `mobile_remote`
  - `pairing_code_api`
  - `pairing_qr_api`

### Important Note

The MVP QR pairing does not require mobile browser X25519 support. It returns a local session token, while encrypted token metadata remains optional.

### Verification

```text
python -m py_compile ai_pc_operator/backend/app/main.py : pass
node --check ai_pc_operator/frontend/app.js : pass
GET /remote/pair.html : pass
GET /remote/index.html : pass
GET /pair/qr : pass
GET / : pass
```

## 2026-07-24 19:24:26 +05:30

Purpose: improve mobile pairing/connected UX and add a Windows stop script.

### Changes

- Added mobile header connection badge with WebSocket-driven states.
- Added pairing success transition before opening the command console.
- Added command progress timeline for command received, planning/risk/model budget, approval, execution, and error states.
- Hardened WebSocket reconnect behavior so unpairing cancels reconnect timers.
- Cleaned `login.html` into a styled redirect fallback to `index.html`.
- Added `ai_pc_operator/stop.bat` to kill local servers listening on `8000` and `8443`.
- Used `cmdc -p ... --max-turns 8` for terminal AI recommendations and implemented the safe local-automation UX pieces.

### Verification

```text
node --check ai_pc_operator/frontend/app.js : pass
```

### Notes

- Did not implement stealth, bot-evasion, hidden control, or anti-detection behavior.
- Stop script was not executed because the local Screen-AI server was still being used.
