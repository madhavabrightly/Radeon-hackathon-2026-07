"""Higher-level task decomposition for multi-step desktop commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus


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

        browser_session = self._plan_browser_session(normalized, lower)
        if browser_session:
            return browser_session

        settings = self._plan_settings(normalized, lower)
        if settings:
            return settings

        keep_awake = self._plan_keep_awake(normalized, lower)
        if keep_awake:
            return keep_awake

        return None

    def _plan_browser_session(self, text: str, lower: str) -> TaskPlan | None:
        wants_browser = re.search(
            r"\b(open|launch|start|run|go to|navigate|visit|search|google|find)\b.*\b(browser|chrome|edge|firefox|opera|gx|website|site|url)\b",
            lower,
        ) or re.search(
            r"\b(open|launch|start|run)\b\s+(chrome|edge|firefox|opera|gx|browser)\b",
            lower,
        )
        if not wants_browser:
            return None

        app_name = self._extract_browser_app(lower)
        target_url = self._extract_navigation_target(text, lower)
        minutes = self._extract_duration_minutes(lower, default=60, upper=120)
        wants_awake = bool(
            re.search(r"\b(stay|keep|prevent|stop|idle|awake)\b.*\b(idle|awake|sleep|off|hour|hours|minute|minutes)\b", lower)
            or re.search(r"\bstay\s+idle\b", lower)
        )
        wants_mouse = bool(re.search(r"\b(mouse|cursor)\b.*\b(move|movement|jiggle|shake)\b", lower))

        steps: list[dict[str, Any]] = []
        if app_name and target_url:
            steps.append(
                {
                    "tool": "system.open_app",
                    "args": {"name": app_name, "target": target_url},
                }
            )
        elif app_name:
            steps.append({"tool": "system.open_app", "args": {"name": app_name}})
        elif target_url:
            steps.append({"tool": "browser.open", "args": {"url": target_url}})
        else:
            steps.append({"tool": "browser.open", "args": {"url": "https://www.google.com"}})

        if wants_awake or wants_mouse:
            steps.append({"tool": "system.keep_awake", "args": {"minutes": minutes}})

        if wants_mouse:
            steps.append(
                {
                    "tool": "system.mouse_jiggle",
                    "args": {"minutes": minutes, "interval_seconds": 45},
                }
            )

        if len(steps) == 1 and not target_url and app_name is None:
            return None

        return TaskPlan(
            intent="browser_session",
            risk_level=1,
            reason="compound browser/session command",
            steps=steps,
        )

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

    def _extract_browser_app(self, lower: str) -> str | None:
        phrases = [
            "opera gx browser",
            "opera gx",
            "gx browser",
            "google chrome",
            "chrome",
            "microsoft edge",
            "edge",
            "firefox",
            "opera browser",
            "opera",
        ]
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", lower):
                return phrase
        return None

    def _extract_navigation_target(self, text: str, lower: str) -> str | None:
        url_match = re.search(r"https?://\S+", text)
        if url_match:
            return url_match.group(0).rstrip(".,")

        domain_match = re.search(r"\b([a-zA-Z0-9-]+\.(com|org|net|io|gov|edu|in|ai|dev))\b", text)
        if domain_match:
            return f"https://{domain_match.group(1)}"

        site_aliases = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://github.com",
            "gmail": "https://mail.google.com",
            "chatgpt": "https://chatgpt.com",
            "reddit": "https://www.reddit.com",
            "amazon": "https://www.amazon.com",
        }
        for name, url in site_aliases.items():
            if re.search(rf"\b{name}\b", lower):
                return url

        search_match = re.search(
            r"\b(search|google|find|look up|lookup)\b(?:\s+for)?\s+(.+)",
            text,
            flags=re.IGNORECASE,
        )
        if search_match:
            query = self._clean_search_query(search_match.group(2))
            if query:
                return f"https://www.google.com/search?q={quote_plus(query)}"

        return None

    def _clean_search_query(self, query: str) -> str:
        cleaned = re.sub(
            r"\b(in|on|with|using)\s+(chrome|edge|firefox|opera|gx|browser|google)\b",
            " ",
            query,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(and|then|after that|stay|idle|awake|for|hour|hours|minute|minutes|mouse|movement|move|cursor|jiggle)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\b\d{1,3}\b", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip(" .,:;\"'")

    def _extract_save_dir(self, text: str) -> str | None:
        match = re.search(r"([A-Za-z]:\\[^\n\r]+)", text)
        if match:
            return match.group(1).strip().strip("\"'")
        return None
