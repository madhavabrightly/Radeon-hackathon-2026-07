from __future__ import annotations

import argparse
from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic
from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Export trained YOLO model to ONNX and dynamic INT8.")
    parser.add_argument("--weights", default="runs/ui_student/weights/best.pt")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--out", default="ui_detector_int8.onnx")
    args = parser.parse_args()

    weights = Path(args.weights)
    if not weights.exists():
        raise SystemExit(f"Missing weights: {weights}")

    model = YOLO(str(weights))
    exported = model.export(format="onnx", imgsz=args.imgsz, simplify=True)
    onnx_path = Path(exported)

    quantize_dynamic(
        model_input=str(onnx_path),
        model_output=args.out,
        weight_type=QuantType.QInt8,
    )
    print(f"INT8 ONNX written to {args.out}")


if __name__ == "__main__":
    main()

