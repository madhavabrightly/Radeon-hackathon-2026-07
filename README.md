# Screen-AI

Lightweight screen scanning and UI-control foundation for a local Agentic AI PC operator.

## What This Does Now

- Scans the current Windows screen.
- Detects buttons, inputs, tabs, menus, and visual UI candidates.
- Produces exact click endpoints: top-left, bottom-right, and center.
- Writes JSON and debug overlay images.
- Includes a hackathon pipeline for OmniParser-v2 teacher labeling on cloud GPU and tiny YOLO/ONNX student deployment on low-resource laptops.

## Quick Local Test

```powershell
python .\screen_element_scanner\scan_screen.py
python .\hackathon_ui_operator_distill\local_runtime\click_by_text.py "Share" --dry-run
```

## Cloud GPU Direction

Use cloud GPU for the heavy teacher phase:

```text
screenshots -> OmniParser v2 -> teacher labels -> YOLO dataset -> tiny INT8 ONNX model
```

Use laptop for the light runtime:

```text
Windows UI Automation + OpenCV + OCR + tiny detector
```

