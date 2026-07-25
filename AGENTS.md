# Screen-AI Agent Notes

This file is the future-reference guide for agents working on Screen-AI.

## Project Identity

Screen-AI is a **fully local/offline PC operator AI** with full system access, controlled by your PC and phone, where the phone is the command + approval + unlock device. No sensitive cloud dependency. Text only for now.

The key product is not "chatbot." It is a **local AI control environment**.

Hackathon track:

```text
Track 2: Agentic AI
```

Positioning:

```text
Screen-AI is a local agentic desktop operator accelerated by AMD ROCm for screen perception, model distillation, and lightweight inference.
```

## Final Product Vision

You are building:

```text
Local AI PC Operator
```

It can:

- receive text commands from PC or phone
- search and browse
- open apps
- control mouse/keyboard
- read screen state
- manage files
- download files
- login to websites/apps
- use saved passwords after user unlock
- trigger passkey login flows
- ask mobile approval for dangerous actions
- run offline/local-first
- work on low-resource machines where possible

The system should feel like:

```text
User on phone:
"Open Excel, login if needed, and check my recent sheet."

AI:
Opens Excel.
Detects login.
Requests unlock/approval on phone.
User approves.
AI continues and reports result.
```

## Core Philosophy

Your version is:

```text
My PC
My phone
My AI
My approval
Full local control
```

But build it with strong internal structure:

```text
Model thinks
Tools act
Phone approves
Vault unlocks
Logs record
User controls
```

Do not make one messy AI process do everything. Separate responsibilities.

## 2026-07-25 Model Routing Baseline

The inspected model reports are now encoded in:

```text
ai_pc_operator/backend/app/runtime/model_insights.py
ai_pc_operator/docs/MODEL_INSIGHTS.md
```

Use this policy for future work:

- Qwen2.5 Coder 1.5B Q4 is the local reasoning/planning lane, loaded through llama.cpp with mmap only when RAM budget allows.
- OCR det v3 and OCR rec English are the fast screen perception lane.
- OmniParser v2 icon detect is a teacher/cloud or explicit fallback model, not a default 4GB resident model.
- Browser and vault warmups are tiny dependency lanes, not LLM calls.
- The phone UI can make instant JavaScript worker hints, but the backend remains the safe source of truth.

For a 4GB no-GPU laptop, do not prefetch Qwen or OmniParser. Prefer:

```text
resident rules/native/UIA
warm OCR only when needed
SSD mmap Qwen only for complex/unknown commands
teacher model only in cloud/distillation or explicit fallback
```

## System Architecture

```text
Mobile Remote
  |
  | text commands / approvals / unlocks
  v
Local PC Agent Server
  |
  v
Agent Brain
  |
  v
Risk + Permission Engine
  |
  v
Tool Executor
  |
  +--> File Control
  +--> Browser Control
  +--> App Control
  +--> System Control
  +--> Password Vault
  +--> Passkey Flow Controller
  +--> Download Manager
  +--> Screen/OCR/Vision
```

Everything important runs locally.

## Current Repository State

Important folders:

```text
screen_element_scanner/
  scan_screen.py
  uia_scan.ps1

hackathon_ui_operator_distill/
  cloud/
  data/
  docs/
  local_runtime/
  native/

ai_pc_operator/  (NEW - main product)
  backend/
    app/
      main.py
      agent/
        planner.py
        router.py
        prompts.py
        memory.py
      security/
        risk.py
        permissions.py
        pairing.py
        vault.py
      tools/
        file_tools.py
        system_tools.py
        browser_tools.py
        download_tools.py
        auth_tools.py
      approvals/
        manager.py
      db/
        database.py
        models.py
      logs/
        redactor.py
  frontend/
    src/
      App.jsx
      pages/
        CommandPage.jsx
        ApprovalPage.jsx
        VaultPage.jsx
        HistoryPage.jsx
        SettingsPage.jsx
      api/
        client.js
  data/
    agent.db
    quarantine/
    downloads/
  docs/
    architecture.md
    permissions.md
    vault.md
    roadmap.md
```

Current working prototype:

```powershell
python .\screen_element_scanner\scan_screen.py
python .\hackathon_ui_operator_distill\local_runtime\click_by_text.py "Share" --dry-run
```

The scanner already creates:

- screenshot captures
- Windows UI Automation element maps
- OpenCV visual candidates
- JSON UI maps
- debug overlay images
- exact element endpoints and centers

## Main Components

### A. PC Agent

Runs on your computer.

Responsibilities:

- receive commands
- manage AI reasoning
- execute tools
- control browser/apps
- access filesystem
- communicate with phone
- maintain logs
- enforce approval rules

Recommended stack:

- Python
- FastAPI
- WebSocket
- SQLite
- Playwright
- PowerShell
- PyAutoGUI
- Windows UI Automation

### B. Mobile Remote

Starts as a mobile web app.

Responsibilities:

- send text commands
- approve/reject actions
- unlock password vault
- approve passkey login flow
- emergency stop
- view action history

Later you can convert it to:

- Flutter app
- React Native app
- native Android app

### C. Agent Brain

This converts user text into plans.

Example:

```text
"Delete all files in Downloads"
```

Becomes:

```json
{
  "intent": "delete_files",
  "target": "Downloads",
  "risk": "critical",
  "requires_mobile_approval": true,
  "execution_method": "quarantine"
}
```

### D. Tool Executor

The model should not directly run raw commands. It should request tools.

Example tools:

```text
file.list
file.scan
file.quarantine
file.restore
system.status
browser.open
browser.search
browser.click
browser.type
app.open
download.file
auth.password_login
auth.passkey_login
approval.request
```

### E. Permission Engine

This decides whether the action can run directly or needs phone approval.

### F. Password Vault

Local encrypted password store.

Responsibilities:

- store passwords encrypted
- unlock only when user enters master key
- provide password to automation tool
- remove password from logs
- wipe temporary memory after use

### G. Passkey Flow Controller

For passkeys, the AI should control the login screen and ask the user to approve the passkey challenge.

Passkeys usually cannot be exported like passwords. So the AI flow is:

```text
AI clicks "Sign in with passkey"
Windows/Edge/phone asks for approval
User approves
AI waits
Login succeeds
AI continues
```

## Access Model

Use these access levels.

| Level | Action | Approval |
|-------|--------|----------|
| 0 | read system status, search web | no |
| 1 | open app/site | no |
| 2 | download file, rename/move file | maybe |
| 3 | send email, login, run installer | phone approval |
| 4 | delete files, bulk operations, admin/system changes | phone approval required |
| 5 | permanent delete, credential export, financial action | blocked or explicit special mode |

Since your goal is full control, you can allow Level 5 only through a special mode:

```text
Full Access Session
Time limited: 5-15 minutes
Phone approved
Visible on PC
Emergency stop enabled
All actions logged except secrets
```

## Critical Action Flow

Example:

```text
User:
"Delete everything in Downloads"
```

Flow:

```text
AI parses command
↓
Scans Downloads
↓
Counts affected files and size
↓
Creates approval request
↓
Phone shows exact impact
↓
User approves
↓
AI moves files to quarantine
↓
AI reports result
```

Phone screen:

```text
Critical Action

Delete contents of:
C:\Users\brigh\Downloads

Files affected:
248

Size:
3.2 GB

Method:
Move to quarantine first

[Approve] [Reject]
```

Default should be **quarantine**, not permanent delete.

## Password Login Flow

Your intended password design:

```text
User:
"Login to xyz.com"

AI:
Opens xyz.com
Detects login page
Requests vault unlock on phone

Phone:
"Unlock password for xyz.com?"
User enters master key

Vault:
Decrypts password locally

Automation:
Fills username/password
Submits form

AI:
Continues task after login
```

Important rules:

- passwords can be used by the local AI system
- passwords are deleted/redacted from logs
- screenshots around password entry should be blocked or redacted
- password should not be saved in plain text
- unlock session should expire quickly

Use:

- AES-256-GCM encryption
- Argon2id for deriving key from master password
- SQLite encrypted records
- per-site credential entries
- optional biometric unlock later

Credential record:

```json
{
  "site": "xyz.com",
  "username": "user@example.com",
  "encrypted_password": "...",
  "created_at": "...",
  "last_used": "..."
}
```

## Passkey Login Flow

Passkey flow:

```text
User:
"Login to Microsoft Excel"

AI:
Opens Excel
Detects Microsoft login
Clicks passkey option
Requests user approval

Phone/Windows:
User approves using biometric/PIN/passkey

AI:
Waits for success
Continues inside Excel
```

For passkeys, do not design around extracting the secret. Design around **triggering and approving authentication**.

Works with:

- Windows Hello
- Edge passkeys
- phone passkeys
- hardware security keys
- Microsoft login
- Google login
- app login prompts

## Browser Control Method

Use two browser modes.

### Structured Browser Mode

Use Playwright.

Good for:

- opening pages
- clicking buttons
- filling forms
- downloading files
- reading DOM content

### Human Visual Mode

Use screenshot + OCR + mouse/keyboard.

Good for:

- websites with weird UI
- apps without APIs
- login windows
- popups
- native apps

Tool stack:

- Playwright
- PyAutoGUI
- pytesseract/EasyOCR
- screenshot capture
- Windows UI Automation

## File Control Method

Tools:

```text
file.list(path)
file.scan(path)
file.read(path)
file.move(src, dst)
file.copy(src, dst)
file.quarantine(path)
file.restore(quarantine_id)
file.delete_permanent(path)
```

Rules:

- normal delete means quarantine
- permanent delete requires special approval
- bulk delete requires mobile approval
- system folders need explicit approval

Protected folders by default:

```text
C:\Windows
C:\Program Files
C:\Program Files (x86)
AppData
browser credential stores
SSH keys
.env files
wallet files
```

You can allow them in full access mode, but make it deliberate.

## Download Method

Flow:

```text
User:
"Download VLC"

AI:
Searches official source
Verifies domain
Checks file type
Shows download details
Requests approval if executable
Downloads to AI_Downloads
Optionally scans/hash-checks
Asks again before running
```

Dangerous extensions:

```text
.exe
.msi
.bat
.cmd
.ps1
.vbs
.scr
.jar
.js
```

Never auto-run a downloaded executable unless approved.

## System Control Method

System tools:

```text
system.status
system.disk_usage
system.ram_usage
system.processes
system.open_app
system.kill_process
system.startup_apps
system.network_status
system.run_command
```

`system.run_command` should be high risk.

Admin commands require:

```text
mobile approval + full access session
```

## Local AI Model Strategy

For MVP, you can use local or cloud. But for your stated goal, design local-first.

For 4GB RAM:

Use small quantized models:

```text
Qwen2.5 3B Instruct GGUF Q4
Phi-3.5 Mini GGUF Q4
Gemma 2B Q4
TinyLlama only for very simple commands
```

Runtime:

```text
llama.cpp
Ollama
LM Studio local server
```

Use local model for:

- intent classification
- risk classification
- simple planning
- command rewriting
- summaries

For hard planning, you can later use bigger local models on better hardware.

## Model Routing

Use multiple models, not one.

```text
Small local classifier
  -> detects intent/risk

Main local LLM
  -> creates plan

Tool executor
  -> runs actions

Verifier
  -> checks result
```

Pipeline:

```text
User command
↓
Intent classifier
↓
Risk classifier
↓
Planner
↓
Policy check
↓
Tool call
↓
Observation
↓
Verifier
↓
User response
```

## Temperature Settings

Use low temperature for control.

| Task | Temperature |
|------|-------------|
| tool selection | 0.0 |
| risk classification | 0.0 |
| file operations | 0.0 |
| login flow | 0.0-0.2 |
| browser automation | 0.1-0.2 |
| summarization | 0.2-0.4 |
| writing messages | 0.4-0.7 |

For PC control, randomness is the enemy.

## Compression and Low Resource Design

For 4GB RAM:

- use 3B model, 4-bit quantized
- keep context small
- summarize old conversations
- do not load browser automation until needed
- use SQLite
- use simple rule-based risk engine first
- cache frequent commands
- stream responses
- avoid heavy background indexing

Memory approach:

```text
short-term context: current task
long-term memory: SQLite + embeddings
logs: compressed summaries
```

## Datasets You Need

You do not train a full model first. You create datasets for evaluation and future fine-tuning.

### Intent Dataset

Examples:

```json
{
  "input": "check my storage",
  "intent": "system_status",
  "risk": "low"
}
```

```json
{
  "input": "delete everything on my desktop",
  "intent": "delete_files",
  "risk": "critical"
}
```

Categories:

- search
- browse
- open app
- list files
- read file
- move file
- delete file
- download
- login
- passkey login
- password login
- system check
- terminal command
- email later

Start with 1,000 examples.

### Risk Dataset

```json
{
  "action": "run downloaded exe",
  "risk": "high",
  "approval": "mobile_required"
}
```

Start with 500 examples.

### Tool Calling Dataset

```json
{
  "input": "login to xyz.com and check dashboard",
  "tools": [
    "browser.open",
    "auth.password_login",
    "browser.read",
    "agent.summarize"
  ]
}
```

### Recovery Dataset

```json
{
  "action": "quarantine file",
  "undo": "restore original path"
}
```

## Database Design

Use SQLite.

Tables:

```text
commands
approvals
actions
devices
vault_entries
quarantine
sessions
settings
```

Important fields:

```text
commands:
id, source, input_text, status, result, created_at

approvals:
id, command_id, risk, action_type, target, status, created_at, resolved_at

actions:
id, command_id, tool, input_json, output_json, risk, status

devices:
id, name, token_hash, paired_at, last_seen

vault_entries:
id, site, username, encrypted_password, created_at, last_used

quarantine:
id, original_path, quarantine_path, command_id, created_at, restored_at
```

## Execution Philosophy

The model should not directly run arbitrary commands.

Architecture:

```text
user command
-> parser/planner
-> risk/permission layer
-> tool executor
-> screen/file/browser/system action
-> verification
-> result summary
```

For risky tasks:

```text
plan first
show impact
request phone approval
execute through safe tool
verify
log
```

## Model And Tool Tiers

The project must run on low-resource laptops, including 4 GB RAM machines.

Use a tiered model stack:

```text
Tier 0: always resident
  Windows UI Automation
  OpenCV visual candidate scan
  rule-based command matching
  click executor

Tier 1: warm lazy-loaded models
  PaddleOCR PP-OCRv4 Mobile
  YOLOv8n or YOLO11n INT8 ONNX UI detector

Tier 2: SSD cold parser
  heavier OmniParser/Floorence-style screen parsing modules
  loaded only for difficult screens

Tier 3: AMD cloud GPU
  OmniParser v2 teacher labeling
  tiny model training
  compression/export
  ROCm benchmarks
```

Local runtime priority:

```text
1. UI Automation exact label
2. OCR text match
3. Tiny YOLO/ONNX UI detector
4. OpenCV visual candidates
5. SSD cold parser
6. AMD cloud parser/training
7. ask user if confidence is low
```

## codiii Methodology

Screen-AI borrows systems ideas from `madhavabrightly/codiii` / Colibri:

- do not assume heavy models must be fully resident
- use RAM, SSD, and GPU as a memory hierarchy
- keep a small resident core
- lazy-load heavy modules
- cache hot paths
- prefetch likely next work
- keep quantized artifacts
- enforce RAM budget
- make cold paths acceptable and warm paths fast

For Screen-AI, the equivalent is not MoE expert streaming. It is pipeline tiering:

```text
resident scanner
-> warm OCR/detector
-> SSD cold parser
-> cloud AMD teacher
```

See:

```text
hackathon_ui_operator_distill/docs/codiii_ssd_tiering_strategy.md
```

## AMD / ROCm Strategy

The user has an RTX laptop, but the hackathon is AMD-based. That is fine.

Development split:

```text
RTX/Windows laptop:
  local scanner
  UI control
  screenshot collection
  low-resource demo

AMD cloud GPU:
  ROCm validation
  OmniParser teacher labeling
  YOLO student training
  INT8 ONNX export
  benchmark screenshots
```

Required AMD proof:

```bash
rocm-smi
rocminfo | head
python - <<'PY'
import torch
print(torch.__version__)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no gpu")
PY
```

Benchmark goals:

- CPU screen parse time
- AMD ROCm model/preprocessing time
- end-to-end screenshot parse latency
- memory use

## GPU Backend Methodology

Follow the Colibri-style backend rule:

```text
CPU default
optional CUDA
optional HIP/ROCm
one compatibility shim for vendor differences
```

Vendor-specific code belongs in:

```text
hackathon_ui_operator_distill/native/gpu_compat.h
```

Algorithm code should stay vendor-neutral. Do not scatter CUDA/HIP conditionals throughout the implementation.

See:

```text
hackathon_ui_operator_distill/docs/gpu_backend_methodology.md
```

## Cloud GPU Workflow

If GitHub clone fails from missing CA certificates:

```bash
apt-get update
apt-get install -y ca-certificates git curl wget aria2
update-ca-certificates
```

If HTTPS still fails and the repo is public:

```bash
GIT_SSL_NO_VERIFY=true git clone https://github.com/madhavabrightly/Screen-AI.git
```

Preferred setup:

```bash
cd "/workspace/template-repos/repo-dd2205cfed93/repo/DevZone_Content/Model Fine-Tuning & Training"
python3 -m venv .venv
source .venv/bin/activate

export HF_HOME=/workspace/.cache/huggingface
export PIP_CACHE_DIR=/workspace/.cache/pip
export HF_HUB_ENABLE_HF_TRANSFER=1
mkdir -p "$HF_HOME" "$PIP_CACHE_DIR"

cd hackathon_ui_operator_distill
bash cloud/setup_cloud_gpu.sh
bash cloud/download_omniparser_v2.sh
```

The cloud environment seen earlier did not run SSH server:

```text
service ssh: unrecognized service
service sshd: unrecognized service
```

So prefer GitHub clone/pull inside cloud instead of laptop-to-cloud SSH.

## Data And Training Plan

Collect screenshots locally:

```powershell
python .\hackathon_ui_operator_distill\local_runtime\collect_screenshot.py
```

Cloud pipeline:

```bash
python cloud/run_teacher_labeling.py --screens data/raw_screenshots --out data/labels_teacher --mode placeholder
python cloud/convert_teacher_to_yolo.py --labels data/labels_teacher --out data/yolo_dataset
python cloud/train_student_yolo.py --data data/yolo_dataset/ui_dataset.yaml --model yolov8n.pt --epochs 80 --device 0
python cloud/export_int8_onnx.py --weights runs/ui_student/weights/best.pt --out ui_detector_int8.onnx
```

Target YOLO classes:

```text
button
input
checkbox
radio
dropdown
tab
menu
link
icon
```

## Safety And Boundaries

This project is for user-owned machines and approved automation.

Do not implement stealth, bot-evasion, credential theft, or bypass logic.

Acceptable:

- local screen scanning
- local UI control
- user-approved login flow
- password vault design with redacted logs
- passkey flow coordination through OS/browser
- phone approval for critical actions

Critical actions should require approval:

- deleting files
- running installers
- sending email
- using credentials
- passkey login
- admin/system commands

Destructive operations should use quarantine first, not permanent deletion.

## Non-Negotiable Engineering Rules

Even with full access:

1. Critical actions require phone approval.
2. Passwords are redacted/deleted from logs.
3. Destructive actions use quarantine first.
4. Emergency stop always works.
5. All non-secret actions are logged.
6. Login target domain must be shown before approval.
7. Downloaded executables require approval before running.
8. Full access sessions should be time-limited.
9. Model proposes actions; tool system executes them.
10. User can wipe logs, vault, memory, and quarantine.

## MVP Build Plan

### Phase 1: Local Server

Build:

- FastAPI server
- `/command`
- `/approvals`
- `/status`
- SQLite setup

Goal:

```text
Phone can send text command to PC.
```

### Phase 2: Mobile Web Remote

Build:

- command input
- response display
- approval panel
- emergency stop

Goal:

```text
Phone controls PC locally.
```

### Phase 3: Pairing

Build:

- PC shows pairing code
- phone enters code
- token stored
- only paired phone can control

Goal:

```text
No random device on Wi-Fi can control it.
```

### Phase 4: File Tools

Build:

- list files
- scan folder
- quarantine delete
- restore

Goal:

```text
Delete requires approval and is reversible.
```

### Phase 5: System Tools

Build:

- disk check
- RAM check
- battery
- running processes
- open app

Goal:

```text
"Check my PC" works.
```

### Phase 6: Browser Tools

Build:

- open site
- search web
- click/type with Playwright
- download file

Goal:

```text
"Search and download X" works.
```

### Phase 7: Password Vault

Build:

- add credential
- encrypt credential
- unlock from phone
- autofill login
- redact logs

Goal:

```text
"Login to xyz.com" works using saved password.
```

### Phase 8: Passkey Flow

Build:

- detect login/passkey prompt
- request phone approval
- wait for Windows/browser auth
- continue after login

Goal:

```text
"Login with passkey" works through normal OS/browser approval.
```

### Phase 9: Local Model

Add:

- local LLM
- intent classifier
- tool planner
- risk classifier

Goal:

```text
Natural language commands become tool plans offline.
```

## First Serious MVP Scope

Build this first:

```text
Text-only PC agent
Mobile web remote
Pairing code
Command history
Approval system
Emergency stop
System status
File listing
Quarantine delete
Restore
Open website
Basic browser search
```

Then add:

```text
Password vault
Login automation
Passkey approval flow
Download manager
App control
Local model routing
```

## The First Build Target

Your first concrete target should be:

> A local FastAPI PC agent with a mobile web remote that accepts text commands, checks system status, lists files, and requires mobile approval before deleting by moving files to quarantine.

That is the foundation. After that, password vault and passkey login become modules, not chaos.

## Immediate Next Steps

Build in this order:

1. Set up FastAPI server with SQLite database.
2. Build mobile web remote with command input.
3. Implement pairing code system.
4. Add file tools with quarantine.
5. Add system status tools.
6. Add browser tools with Playwright.
7. Add password vault with encryption.
8. Add passkey flow controller.
9. Add local LLM routing.
10. Add OCR fallback to existing scanner.
11. Add lightweight target confidence scoring.
12. Add screenshot collection workflow for dataset building.
13. Add tiny YOLO ONNX local inference.
14. Add AMD cloud teacher labeling and ROCm benchmark demo.

Keep changes scoped and push after meaningful milestones.

## 2026-07-23 Low-Memory Backend Tuning

The backend was tuned from review notes about 4 GB RAM performance and connection churn.

Implemented:

- SQLite now uses one shared `aiosqlite` connection with WAL mode, `busy_timeout`, and serialized `db_session()` access.
- App shutdown closes browser resources and the shared DB connection.
- Added DB indexes for `approvals.command_id` and `quarantine.command_id`.
- `/history` now selects specific columns, truncates large `result` text, and clamps the limit to 1-200.
- Planner, risk classifier, and log redactor use precompiled regexes.
- File scans are bounded by max files, max depth, and timeout.
- BrowserTools lazy-loads Playwright and can unload Chromium after a 5-minute idle timeout.
- Vault lazy-imports cryptography, supports configurable KDF cost, caches derived entry keys per unlock session, and updates `last_used` correctly.
- Pairing manager uses the shared DB session and `/command` awaits device verification.
- Scanner supports a short identical-screen cache to avoid rerunning UIA/OpenCV repeatedly.
- Backend requirements were trimmed for low-resource installs.
- Smoke tests were made async-correct and ASCII-safe.

Verified:

```powershell
python -m py_compile screen_element_scanner\scan_screen.py ai_pc_operator\backend\app\db\database.py ai_pc_operator\backend\app\agent\planner.py ai_pc_operator\backend\app\security\risk.py ai_pc_operator\backend\app\agent\router.py ai_pc_operator\backend\app\approvals\manager.py ai_pc_operator\backend\app\main.py ai_pc_operator\backend\app\tools\browser_tools.py ai_pc_operator\backend\app\tools\file_tools.py ai_pc_operator\backend\app\security\vault.py ai_pc_operator\backend\app\security\pairing.py ai_pc_operator\backend\app\logs\redactor.py ai_pc_operator\backend\test_basic.py
python -u .\ai_pc_operator\backend\test_basic.py
python .\screen_element_scanner\scan_screen.py --quiet
```

Note: timed-out test runs left stale Python processes holding SQLite locks during development. They were stopped before the final successful test run.

## 2026-07-23 Real Runtime Pipeline

The model/tool runtime is now wired into `AgentRouter`.

Implemented:

- `app/runtime/resource_budget.py`: measures available RAM and creates a model-loading budget.
- `app/runtime/io_pool.py`: shared 2-worker I/O thread pool for blocking disk/model/tool work.
- `app/runtime/model_registry.py`: lazy model registry with async prefetch, idle unload, and placeholder loaders.
- `app/runtime/heatmap.py`: intent-to-tool heat map persisted under runtime memory.
- `app/runtime/tier_manager.py`: RAM-aware tier decisions for resident, OCR, detector, and local LLM modes.
- `AgentRouter` now measures RAM, classifies intent, starts risk assessment, decides tiers, prefetches hot models/tools, records tool heat, and unloads idle resources.
- Browser/Auth tools expose safe `prepare()` warmups that import dependencies without launching Chromium or unlocking vaults.
- `/runtime` endpoint reports current budget, model mode, registered models, loaded models, and pending model prefetches.

Current lazy model names:

```text
ocr-mobile
ui-detector-int8
qwen-1.5b-q4
vault-crypto
browser-warmup
```

These are placeholders until actual OCR/YOLO/GGUF artifacts are downloaded. Do not block the event loop while adding real loaders; use `ModelRegistry` + `IOPool`.

## 2026-07-24 Browser Command Reliability

The command layer now treats common browser requests as first-class actions.

Implemented:

- Planner recognizes commands such as:
  - `search best air coolers in chrome`
  - `open YouTube`
  - `open github.com`
  - `close browser`
- Search query cleanup removes browser hints such as `in chrome`, `on browser`, and `with edge`.
- Site aliases are mapped for common services including YouTube, Google, GitHub, Gmail, Amazon, Reddit, Instagram, LinkedIn, and ChatGPT.
- `browser.search` URL-encodes queries before navigation.
- `browser.open` normalizes bare domains to HTTPS URLs.
- If Playwright Chromium is unavailable, browser open/search falls back to the OS default browser instead of returning a failed command.
- `AgentRouter` now returns `unsupported` for commands with no executable plan instead of `completed` with `No actions taken`.
- Vault key derivation falls back to PBKDF2-HMAC-SHA256 when the local Windows `cryptography` Argon2 binding is broken.

Current limitation:

- The fallback can open/search in the system browser, but DOM click/type automation still needs Playwright browser binaries installed.
- On this machine, Playwright Chromium was installed successfully with `python -m playwright install chromium`.

Recommended next command when Playwright automation is needed:

```powershell
python -m playwright install chromium
```

## 2026-07-24 Real Model Loader Wiring

The runtime model slots are no longer placeholders.

Implemented:

- Added `ArtifactStore` for model discovery in:
  - `ai_pc_operator/data/models`
  - `hackathon_ui_operator_distill/data`
  - `hackathon_ui_operator_distill/runs`
  - `SCREEN_AI_MODEL_DIR`
- Added optional real loaders:
  - `ocr-mobile`: PaddleOCR when installed
  - `ui-detector-int8`: ONNX Runtime with exported INT8 detector
  - `qwen-1.5b-q4`: llama.cpp GGUF loader
  - `vault-crypto`: cryptography warmup
  - `browser-warmup`: Playwright import warmup
- Removed `placeholder_loader` from the model registry path.
- Added `LLMPlanner`, which imports `SYSTEM_PROMPT` and `USER_PROMPT_TEMPLATE` from `prompts.py`.
- `AgentRouter` now only asks the local LLM planner for unknown commands when RAM allows the Qwen tier and a real model is loaded.
- Added backend `ScreenCache` at:

```text
ai_pc_operator/data/.screen_ai_cache/
  ui_maps/
  ocr_results/
  detector_results/
```

- `AgentRouter` writes redacted plan/cache metadata under `ui_maps`.
- `/runtime` reports memory budget, model status, artifact inventory, and cache stats.
- `LogRedactor` now runs as a logging filter and redacts command/action persistence.
- Nested plans/lists are redacted, not just top-level dictionaries.

Artifact CLI:

```powershell
python .\ai_pc_operator\backend\scripts\model_artifacts.py inventory
python .\ai_pc_operator\backend\scripts\model_artifacts.py stage-yolo .\path\to\ui_detector_int8.onnx
python .\ai_pc_operator\backend\scripts\model_artifacts.py stage-gguf .\path\to\qwen.gguf
```

Current artifact status on this machine:

```text
ocr-mobile: not staged
ui-detector-int8: not staged
qwen-1.5b-q4: not staged
vault-crypto: dependency loader available
browser-warmup: dependency loader available
```

## 2026-07-24 Login V2 Repair

Enhanced pairing is additive; do not remove the legacy 6-digit code flow.

Working login layers:

- 6-digit code pairing remains the reliable fallback.
- QR pairing uses short-lived pairing sessions from `/pair/qr`.
- Trusted reconnect uses `/pair/trusted`.
- Token rotation uses `/auth/rotate`.
- Biometric challenge endpoints exist for future sensitive-action gates.

Important implementation notes:

- `pairing_manager_v2` must be declared global in FastAPI lifespan.
- QR pairing private keys are intentionally in-memory only; if the backend restarts, generate a new QR session.
- MVP pairing returns a normal local session token so unsupported mobile WebCrypto/X25519 cannot block login.
- Encrypted token fields may be present when a valid X25519 key is supplied, but the frontend should not require them yet.
- `remote/index.html`, `frontend/app.js`, and `frontend/styles.css` must agree on `login-screen` IDs.
- `test_login_v2.py` must close the shared DB connection or it can leave a stale Python process.

Verified endpoints:

```text
GET /pair/qr
GET /pair/code
POST /pair/qr/complete
POST /auth/rotate
POST /pair/trusted
```

## Model Artifacts: 2026-07-24 02:10:11 +05:30

Runtime model files live in:

```text
ai_pc_operator/data/models/
```

Downloader:

```powershell
python .\ai_pc_operator\backend\scripts\download_models.py
python .\ai_pc_operator\backend\scripts\model_artifacts.py inventory
python .\ai_pc_operator\backend\scripts\model_artifacts.py list-files
```

Selected lightweight artifacts:

- `qwen2.5-coder-1.5b-instruct-q4_0.gguf` from `Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF` for local llama.cpp planning.
- `ocr_det_v3.onnx` and `ocr_rec_english.onnx` from `monkt/paddleocr-onnx` for light ONNX OCR.
- `teachers/omniparser_v2_icon_detect.pt` from `microsoft/OmniParser-v2.0` for cloud teacher/distillation work.

Important:

- Do not commit model binaries. `.gitignore` excludes `*.gguf`, `*.onnx`, and `*.pt`.
- `ui_detector_int8.onnx` is still expected to come from our cloud distillation/export pipeline.
- The OmniParser `.pt` teacher model is saved for cloud use, but the 4 GB laptop runtime should load the exported INT8 ONNX detector.

## Codebase Analysis Fix Pass: 2026-07-24 02:25:43 +05:30

Primary demo path is now:

```text
mobile text command -> AgentRouter -> Planner -> screen.click_text/screen.scan -> Windows UIA/OpenCV -> result
```

New backend tools:

- `screen.scan`: returns visible actionable controls and endpoints.
- `screen.click_text`: fuzzy-matches visible text/accessibility labels and clicks the center point.

Security constraints:

- Do not reintroduce `shell=True` for user-derived app/command text.
- Paired-device endpoints should verify token hashes, not only device ids.
- Frontend must render server-provided strings with `textContent`, not `innerHTML`.
- WebSocket clients should pass `device_id` and `token`; HTTPS pages should use `wss://`.

Cloud detector path:

```bash
python cloud/run_teacher_labeling.py --screens data/raw_screenshots --out data/labels_teacher --mode omniparser
python cloud/convert_teacher_to_yolo.py --labels data/labels_teacher --out data/yolo_dataset
python cloud/train_student_yolo.py --data data/yolo_dataset/ui_dataset.yaml --model yolov8n.pt --epochs 80 --device 0
python cloud/export_int8_onnx.py --weights runs/ui_student/weights/best.pt --out ui_detector_int8.onnx
```

Verified locally:

```text
test_basic.py: pass
test_login_v2.py: pass
ScreenTools.scan: 226 actionable controls
ScreenTools.click_text("Close", dry_run=True): success
```

## 4 GB SSD Tier Runtime: 2026-07-24 02:33:30 +05:30

Screen-AI adapts the `codiii`/colibri memory hierarchy like this:

```text
codiii:
  dense core in RAM -> hot experts pinned -> routed experts streamed from SSD

Screen-AI:
  rules/UIA/OpenCV resident -> OCR/detector warm -> Qwen/teacher artifacts SSD-cold/off -> AMD cloud teacher
```

Runtime knobs:

```powershell
$env:SCREEN_AI_RAM_MB="1200"          # optional low-RAM override/test
$env:SCREEN_AI_MMAP="1"              # mmap GGUF through llama.cpp
$env:SCREEN_AI_PREFETCH="0"          # safest for 4 GB
$env:SCREEN_AI_ALLOW_COLD_LLM="0"    # keep Qwen off unless explicitly enabled
$env:SCREEN_AI_LLM_CTX="512"
$env:SCREEN_AI_LLM_THREADS="2"
```

Rules:

- Large models are never speculative-prefetched.
- Qwen defaults to SSD/off on low RAM.
- OCR/detector are lazy and evictable.
- `/runtime` is the source of truth for current model placement.
- Native C LFRU policy exists under `hackathon_ui_operator_distill/native/ssd_tier_policy.c` for future low-overhead promotion decisions.

## Compound Task Planner: 2026-07-24 19:03:38 +05:30

The agent now has a high-level task planner before the older single-intent rule planner.

Supported compound task families:

- `research_collect`: search web, visit multiple pages, extract text, save report.
- `open_settings`: open Windows settings pages such as contrast settings.
- `keep_awake`: hold Windows awake through `SetThreadExecutionState`.

Important implementation files:

```text
ai_pc_operator/backend/app/agent/task_planner.py
ai_pc_operator/backend/app/tools/browser_tools.py
ai_pc_operator/backend/app/tools/system_tools.py
hackathon_ui_operator_distill/native/endpoint_rank.c
```

Research command example:

```text
open chrome and search about AMD ROCm and go to 10 random websites and copy all text and paste in text file and save it folder
```

Plan:

```text
browser.research_collect(query="AMD ROCm", max_sites=10)
```

Safety rule:

- Keep local automation visible and user-approved. Do not implement stealth, bot-evasion, or hidden-control behavior.

## Mobile Remote UX And Command Code Notes: 2026-07-24 19:24:26 +05:30

The mobile remote should make control state obvious to the user:

- Header connection badge shows `Connected`, `Connecting`, `Reconnecting`, or `Offline`.
- Pairing success uses a short visual transition before opening the command console.
- Command tab shows a progress timeline before and after `/command` returns.
- Emergency stop remains visible in the main header.
- `ai_pc_operator/stop.bat` stops local Screen-AI servers on ports `8000` and `8443`.

Command Code terminal AI can be queried non-interactively when extra planning/research is useful:

```powershell
cmdc -p "Give concise recommendations for Screen-AI mobile UX and local server scripts. No stealth/evasion suggestions." --max-turns 8
```

Implementation boundary:

- Strong local PC automation is allowed for the owner's visible session.
- Do not add stealth, bot-detection bypass, hidden remote control, or anti-forensics.
- Prefer visible status, approvals, logs with redaction, and emergency stop.

## Plan Preview, JS Memory, And Relation Map: 2026-07-24 21:28:08 +05:30

Phone text instructions now have a preview path before execution:

- `POST /command/preview` calls `AgentRouter.preview_plan()`.
- The preview returns interpreted intent, risk level, approval need, runtime tier, SSD tier, and redacted tool steps.
- The mobile app debounces command typing and asks the backend for a plan preview.
- Recent instructions are stored in browser `localStorage` as lightweight JS memory.
- Draft command text is stored in `localStorage` and can be restored.
- Offline commands are saved as drafts only; they are not replayed automatically.

Relation-map notes:

- `relation-map.md` and `ai_pc_operator/relation-map.md` are intentionally identical.
- The router method in the map is `process_command()`, with `preview_plan()` for dry planning.
- Keep the map updated whenever adding endpoint, runtime, database, native, or frontend-worker behavior.
