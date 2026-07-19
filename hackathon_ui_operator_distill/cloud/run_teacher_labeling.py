from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Teacher labeling wrapper. Runs OmniParser manually or stores placeholder labels."
    )
    parser.add_argument("--screens", default="../data/raw_screenshots", help="Folder with screenshots.")
    parser.add_argument("--out", default="../data/labels_teacher", help="Teacher label output folder.")
    parser.add_argument(
        "--mode",
        choices=["placeholder", "omniparser"],
        default="placeholder",
        help="Use placeholder until OmniParser API integration is adjusted to the installed version.",
    )
    args = parser.parse_args()

    screens = Path(args.screens).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    images = sorted([*screens.glob("*.png"), *screens.glob("*.jpg"), *screens.glob("*.jpeg")])
    if not images:
        raise SystemExit(f"No screenshots found in {screens}")

    if args.mode == "omniparser":
        print("OmniParser mode requested.")
        print("Use the upstream demo/API to produce element boxes, then normalize with this JSON schema:")
        print(json.dumps({
            "image": "screen_001.png",
            "elements": [
                {"class": "button", "text": "Login", "box": [100, 120, 240, 160], "confidence": 0.95}
            ],
        }, indent=2))
        subprocess.run(["python", "OmniParser/gradio_demo.py"], check=False)
        return

    for image in images:
        label_path = out / f"{image.stem}.json"
        payload = {
            "image": str(image),
            "elements": [],
            "note": "Placeholder. Replace with OmniParser v2 output normalized to this schema.",
        }
        label_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {label_path}")


if __name__ == "__main__":
    main()

