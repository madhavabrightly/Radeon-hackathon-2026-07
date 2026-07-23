"""Screen scanning and click tools."""

from __future__ import annotations

import asyncio
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List

import pyautogui


ROOT = Path(__file__).resolve().parents[4]
SCANNER_DIR = ROOT / "screen_element_scanner"
if str(SCANNER_DIR) not in sys.path:
    sys.path.insert(0, str(SCANNER_DIR))

from scan_screen import (  # noqa: E402
    actionable_elements,
    capture_screen,
    detect_visual_boxes,
    run_uia_scan,
    valid_bounds,
)


class ScreenTools:
    """Operate on visible desktop UI elements through local scanning."""

    async def scan(
        self,
        max_depth: int = 8,
        max_elements: int = 2500,
        vision_limit: int = 200,
    ) -> Dict[str, Any]:
        """Return visible actionable UI elements."""
        return await asyncio.to_thread(
            self._scan_sync,
            max_depth,
            max_elements,
            vision_limit,
        )

    async def click_text(
        self,
        text: str,
        dry_run: bool = False,
        min_score: float = 0.55,
    ) -> Dict[str, Any]:
        """Click the best visible element matching text."""
        return await asyncio.to_thread(self._click_text_sync, text, dry_run, min_score)

    def _scan_sync(
        self,
        max_depth: int,
        max_elements: int,
        vision_limit: int,
    ) -> Dict[str, Any]:
        screenshot = capture_screen()
        uia_elements = run_uia_scan(max_depth=max_depth, max_elements=max_elements)
        visual_elements = detect_visual_boxes(screenshot, limit=vision_limit)
        elements = [
            item
            for item in [*uia_elements, *visual_elements]
            if "bounds" in item and valid_bounds(item, screenshot.width, screenshot.height)
        ]
        actions = actionable_elements(elements)
        return {
            "status": "success",
            "screen": {"width": screenshot.width, "height": screenshot.height},
            "counts": {
                "uia": len(uia_elements),
                "vision": len(visual_elements),
                "total": len(elements),
                "actionable": len(actions),
            },
            "elements": actions[:120],
        }

    def _click_text_sync(
        self,
        text: str,
        dry_run: bool,
        min_score: float,
    ) -> Dict[str, Any]:
        if not text.strip():
            return {"status": "failed", "error": "No target text provided"}

        scan = self._scan_sync(max_depth=8, max_elements=2500, vision_limit=150)
        target = self._find_best(scan["elements"], text)
        if not target or target["score"] < min_score:
            return {
                "status": "failed",
                "error": f"No visible UI element matched '{text}'",
                "best_match": target,
                "counts": scan["counts"],
            }

        element = target["element"]
        x, y = element["center"]
        if not dry_run:
            pyautogui.click(x, y)

        return {
            "status": "success",
            "clicked": not dry_run,
            "target_text": text,
            "match_score": round(target["score"], 3),
            "element": {
                "role": element.get("role"),
                "label": element.get("label") or element.get("automation_id") or "",
                "source": element.get("source"),
                "bounds": element.get("bounds"),
                "center": element.get("center"),
                "confidence": element.get("confidence"),
            },
        }

    def _find_best(self, elements: List[dict], text: str) -> dict | None:
        query = self._normalize(text)
        best: dict | None = None
        for element in elements:
            labels = [
                element.get("label", ""),
                element.get("automation_id", ""),
                element.get("localized_role", ""),
                element.get("role", ""),
            ]
            haystack = " ".join(item for item in labels if item)
            score = self._score(query, self._normalize(haystack))
            if best is None or score > best["score"]:
                best = {"score": score, "element": element}
        return best

    def _score(self, query: str, label: str) -> float:
        if not query or not label:
            return 0.0
        if query == label:
            return 1.0
        if query in label:
            return 0.9
        words = [word for word in query.split() if word]
        if words and all(word in label for word in words):
            return 0.82
        return SequenceMatcher(None, query, label).ratio()

    def _normalize(self, value: str) -> str:
        return " ".join(value.lower().strip().split())
