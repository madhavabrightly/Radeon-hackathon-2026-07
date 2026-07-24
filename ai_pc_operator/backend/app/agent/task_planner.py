"""Higher-level task decomposition for multi-step desktop commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskPlan:
    intent: str
    risk_level: int
    steps: list[dict[str, Any]]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "risk_level": self.risk_level,
            "steps": self.steps,
            "source": "task-planner",
            "reason": self.reason,
        }


class TaskPlanner:
    """Plans compound tasks before falling back to single-intent rules."""

    def plan(self, text: str) -> TaskPlan | None:
        normalized = " ".join(text.strip().split())
        lower = normalized.lower()

        research = self._plan_research_collect(normalized, lower)
        if research:
            return research

        settings = self._plan_settings(normalized, lower)
        if settings:
            return settings

        keep_awake = self._plan_keep_awake(normalized, lower)
        if keep_awake:
            return keep_awake

        return None

    def _plan_research_collect(self, text: str, lower: str) -> TaskPlan | None:
        search_words = r"(search|research|look up|google|find)"
        collect_words = r"(copy|collect|scrape|extract|save|paste|write)"
        if not re.search(search_words, lower) or not re.search(collect_words, lower):
            return None
        if not re.search(r"\b(websites?|pages?|results?|sites?)\b", lower):
            return None

        query = self._extract_research_query(text)
        max_sites = self._extract_count(lower, default=5, upper=10)
        save_dir = self._extract_save_dir(text)
        return TaskPlan(
            intent="research_collect",
            risk_level=2,
            reason="compound browser research task",
            steps=[
                {
                    "tool": "browser.research_collect",
                    "args": {
                        "query": query,
                        "max_sites": max_sites,
                        "save_dir": save_dir,
                    },
                }
            ],
        )

    def _plan_settings(self, text: str, lower: str) -> TaskPlan | None:
        if "settings" not in lower:
            return None
        if "contrast" in lower:
            return TaskPlan(
                intent="open_settings",
                risk_level=1,
                reason="open Windows contrast settings for user-visible adjustment",
                steps=[
                    {
                        "tool": "system.open_settings",
                        "args": {"page": "ms-settings:easeofaccess-highcontrast"},
                    }
                ],
            )
        return TaskPlan(
            intent="open_settings",
            risk_level=1,
            reason="open Windows settings",
            steps=[{"tool": "system.open_settings", "args": {"page": "ms-settings:"}}],
        )

    def _plan_keep_awake(self, text: str, lower: str) -> TaskPlan | None:
        if not re.search(r"\b(keep|prevent|stop)\b.*\b(screen|display|pc|computer)\b.*\b(off|sleep|awake)\b", lower):
            return None
        minutes = self._extract_duration_minutes(lower, default=60, upper=120)
        return TaskPlan(
            intent="keep_awake",
            risk_level=1,
            reason="prevent local PC sleep/display timeout for a bounded duration",
            steps=[{"tool": "system.keep_awake", "args": {"minutes": minutes}}],
        )

    def _extract_research_query(self, text: str) -> str:
        cleaned = re.sub(
            r"\b(open|chrome|browser|and|then|go to|random|websites?|pages?|results?|copy|collect|scrape|extract|all|text|paste|write|save|folder|file|about|on)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\b(search|research|look up|google|find)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b\d+\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;\"'")
        return cleaned or text.strip()

    def _extract_count(self, lower: str, default: int, upper: int) -> int:
        match = re.search(r"\b(\d{1,2})\b\s+(?:random\s+)?(?:websites?|pages?|results?|sites?)", lower)
        if not match:
            return default
        return max(1, min(int(match.group(1)), upper))

    def _extract_duration_minutes(self, lower: str, default: int, upper: int) -> int:
        match = re.search(r"\b(\d{1,3})\s*(hour|hours|hr|hrs|minute|minutes|min|mins)\b", lower)
        if not match:
            return default
        value = int(match.group(1))
        unit = match.group(2)
        minutes = value * 60 if unit.startswith(("hour", "hr")) else value
        return max(1, min(minutes, upper))

    def _extract_save_dir(self, text: str) -> str | None:
        match = re.search(r"([A-Za-z]:\\[^\n\r]+)", text)
        if match:
            return match.group(1).strip().strip("\"'")
        return None
