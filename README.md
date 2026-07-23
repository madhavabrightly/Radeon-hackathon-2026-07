# Screen-AI Project README

**Fully local/offline PC operator AI with full system access, controlled by your PC and phone.**

Screen-AI is a local agentic desktop operator accelerated by AMD ROCm for screen perception, model distillation, and lightweight inference. The phone is the command + approval + unlock device.

## Track

```
Track 2: Agentic AI
```

## What This Does

- 📱 **Mobile Remote Control**: Send text commands from your phone to your PC
- 👁️ **Screen Perception**: Scans Windows UI (UIA + OpenCV), detects buttons/inputs/tabs/menus
- 🖱️ **Screen Control**: Click elements by text, scan screen, verify actions
- 🌐 **Browser Automation**: Search, open sites, fill forms, download files (Playwright)
- 🔐 **Password Vault**: AES-256-GCM + Argon2id encrypted credential storage
- ✅ **Phone Approval**: Risky actions require phone approval before execution
- 📁 **File Quarantine**: Delete → quarantine (reversible), not permanent destruction
- 🚨 **Emergency Stop**: One-tap halt of all operations
- 🤖 **LLM Planning**: Local Qwen 1.5B GGUF planner for unknown intents (optional)
- 📊 **Runtime Engine**: RAM-aware tiered model loading for 4GB laptops

## Quick Start

### Windows

```powershell
.\ai_pc_operator\start.bat
```

### Linux/Mac

```bash
./ai_pc_operator/start.sh
```

### HTTPS (for mobile QR camera)

```powershell
python ai_pc_operator/backend/scripts/start_https.py
```

### Download Model Artifacts

```powershell
python ai_pc_operator/backend/scripts/download_models.py
python ai_pc_operator/backend/scripts/download_models.py --skip-llm
```

### Inspect Artifacts

```powershell
python ai_pc_operator/backend/scripts/model_artifacts.py inventory
python ai_pc_operator/backend/scripts/model_artifacts.py list-files
```

## URLs

| URL | Purpose |
|-----|---------|
| `http://localhost:8000/remote/index.html` | Mobile remote (phone opens this) |
| `http://localhost:8000/remote/pair.html` | PC QR pairing page (PC shows this) |
| `https://localhost:8443/remote/...` | HTTPS variant (for camera QR scanning) |

## Architecture

```
Phone → REST/WebSocket → FastAPI Server → Agent Router → Runtime Engine → Tools → Windows PC
                                    ↕            ↕              ↕              ↕
                              Security Layer  Tier Manager  Resource Budget  Screen Scanner
                              (risk/perm/     (RAM-aware    (psutil memory   (UIA + OpenCV)
                               vault/approval) tier select)  measurement)
```

### Three Modules

| Module | Path | Purpose |
|--------|------|---------|
| **Screen Scanner** | `screen_element_scanner/` | UIA + OpenCV screen perception (the "eyes") |
| **Distillation Pipeline** | `hackathon_ui_operator_distill/` | Cloud teacher → local YOLOv8n INT8 ONNX student |
| **AI PC Operator** | `ai_pc_operator/` | FastAPI server + mobile remote + agent brain + runtime engine |

## Runtime Engine

The runtime engine manages RAM-aware model loading on low-memory machines:

- **Tier 0 (Resident)**: UIA, OpenCV, rule planner — always in RAM
- **Tier 1 (Warm)**: OCR, YOLO detector — lazy-loaded when RAM allows
- **Tier 2 (SSD Cold)**: Heavy models — on disk, loaded on demand
- **Tier 3 (SSD Off)**: Too heavy for current RAM profile

Environment variables:

```powershell
$env:SCREEN_AI_RAM_MB="1200"        # Simulate 4GB RAM
$env:SCREEN_AI_MMAP="1"             # Memory-map GGUF files
$env:SCREEN_AI_PREFETCH="0"         # Disable model prefetch
$env:SCREEN_AI_ALLOW_COLD_LLM="0"  # Keep LLM on SSD
$env:SCREEN_AI_LLM_CTX="512"       # Small context window
$env:SCREEN_AI_LLM_THREADS="2"     # Limited CPU threads
```

## 4GB Laptop Recommendations

```text
UIA/OpenCV/rules always available
OCR/detector lazy only if RAM allows
Qwen stays on SSD/off by default
OmniParser/training stays cloud-only
Browser idle-evicts after 120 seconds
```

## Cloud GPU Direction

Cloud GPU for heavy teacher phase:

```
screenshots → OmniParser v2 → teacher labels → YOLO dataset → tiny INT8 ONNX model
```

Laptop for light runtime:

```
Windows UI Automation + OpenCV + OCR + tiny detector + local LLM planner
```

## Tech Stack

**Backend**: Python 3.10+, FastAPI, aiosqlite, psutil, Playwright, cryptography, pyautogui
**Frontend**: Vanilla JS/CSS/HTML, WebSocket, QRCode.js
**ML/Training**: Ultralytics YOLOv8n, ONNX Runtime, llama.cpp (nexa GGUF), PaddleOCR
**Security**: AES-256-GCM, Argon2id, X25519 (QR pairing), HMAC signatures
**Database**: SQLite (WAL mode, serialized access, indexed)
