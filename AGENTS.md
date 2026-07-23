# Screen-AI Agent Notes

This file is the future-reference guide for agents working on Screen-AI.

## Project Identity

Screen-AI is a lightweight local Agentic AI desktop operator. Its first goal is to scan the visible Windows screen, identify UI elements, choose accurate click targets from text commands, execute actions, and verify results.

Hackathon track:

```text
Track 2: Agentic AI
```

Positioning:

```text
Screen-AI is a local agentic desktop operator accelerated by AMD ROCm for screen perception, model distillation, and lightweight inference.
```

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

## Core Product Goal

The product should eventually support:

- text commands from PC
- text commands from phone/mobile remote
- screen scanning
- click-by-text
- type-by-target
- browser/app control
- file/system tools
- action verification
- phone approval for risky actions
- local-first operation
- low-resource 4 GB RAM mode
- AMD ROCm acceleration where available

Do not treat this as a chatbot. It is a tool-using desktop operator.

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

## Immediate Next Steps

Build in this order:

1. Reliable `click_by_text` with real click and verification.
2. Add OCR fallback for text not exposed by UI Automation.
3. Add lightweight target confidence scoring.
4. Add screenshot collection workflow for dataset building.
5. Add mobile approval/server layer later.
6. Add tiny YOLO ONNX local inference.
7. Add AMD cloud teacher labeling and ROCm benchmark demo.

Keep changes scoped and push after meaningful milestones.

