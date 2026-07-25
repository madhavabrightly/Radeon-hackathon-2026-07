"""Planner - converts user text into executable plans.

This module handles intent classification and action planning.
For MVP, uses rule-based classification. Can be upgraded to LLM later.
"""

from __future__ import annotations

import re
from typing import Dict, Any, List, Optional


class Planner:
    """Command planner."""

    SITE_ALIASES = {
        "amazon": "https://www.amazon.com",
        "bing": "https://www.bing.com",
        "chatgpt": "https://chatgpt.com",
        "edge": "https://www.microsoft.com/edge",
        "facebook": "https://www.facebook.com",
        "gmail": "https://mail.google.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "instagram": "https://www.instagram.com",
        "linkedin": "https://www.linkedin.com",
        "reddit": "https://www.reddit.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "youtube": "https://www.youtube.com",
    }

    def __init__(self):
        """Initialize planner with rule-based patterns."""
        self.intent_patterns = self._load_patterns()

    def _load_patterns(self) -> Dict[str, List[re.Pattern[str]]]:
        """Load intent classification patterns."""
        raw_patterns = {
            "system_status": [
                r"\b(check|show|get)\b.*\b(status|health|info)\b",
                r"\bhow is\b.*\b(pc|computer|laptop)\b",
                r"\bsystem\s+(status|info|check)\b",
            ],
            "disk_usage": [
                r"\b(check|show|get)\b.*\b(storage|disk|drive)\b",
                r"\b(disk|storage|drive)\b.*\b(usage|space|free|full)\b",
                r"\bhow much\b.*\b(space|storage)\b",
            ],
            "ram_usage": [
                r"\b(ram|memory)\b.*\b(usage|used|free)\b",
                r"\bhow much\b.*\b(memory|ram)\b",
            ],
            "list_files": [
                r"\b(list|show)\b.*\b(files|folder|directory)\b",
                r"\bwhat('s| is) in\b",
            ],
            "delete_files": [
                r"\b(delete|remove|clean)\b.*\b(files?|folder|directory)\b",
                r"\bempty\b.*\b(folder|directory|trash)\b",
            ],
            "open_website": [
                r"\b(open|go to|navigate to|visit)\b.*\b(website|url|site)\b",
                r"\b(open|go to|navigate to|visit)\b\s+([a-zA-Z0-9.-]+\.[a-z]{2,}|amazon|bing|chatgpt|facebook|gmail|google|github|instagram|linkedin|reddit|twitter|x|youtube)\b",
                r"\bhttps?://\S+",
            ],
            "search_web": [
                r"\b(search|google|find)\b.*\b(web|internet|online)\b",
                r"\bsearch\b\s+for\b",
                r"\b(search|google|find|look up|lookup)\b.+",
                r"\b(search|google|find|look up|lookup)\b.*\b(in|on|with)\s+(chrome|edge|browser|google|bing)\b",
            ],
            "browser_close": [
                r"\b(close|quit|exit)\b.*\b(browser|chrome|edge|tab)\b",
                r"\b(close|quit|exit)\b\s+(browser|chrome|edge)\b",
            ],
            "open_app": [
                r"\b(open|launch|start|run)\b.*\b(app|application|program)\b",
                r"\bopen\b\s+\w+",
            ],
            "download_file": [
                r"\b(download|get|fetch)\b.*\b(file|program|app)\b",
            ],
            "login": [
                r"\b(login|sign in|log in)\b.*\b(to|on)\b",
                r"\blogin\b\s+to\b",
            ],
            "send_email": [
                r"\b(send|write|compose)\b.*\b(email|mail|message)\b",
            ],
            "run_command": [
                r"\b(run|execute)\b.*\b(command|script|code)\b",
            ],
            "screen_click": [
                r"\b(click|press|tap|select)\b\s+(.+)",
                r"\b(click|press|tap|select)\b.*\b(button|link|tab|field)\b",
            ],
            "screen_scan": [
                r"\b(scan|show|detect|find)\b.*\b(screen|buttons|ui|controls)\b",
                r"\bwhat\b.*\b(on|in)\b.*\b(screen)\b",
            ],
        }
        return {
            intent: [re.compile(pattern) for pattern in patterns]
            for intent, patterns in raw_patterns.items()
        }

    async def classify_intent(self, text: str) -> str:
        """Classify user command intent."""
        text_lower = text.lower().strip()

        # Check each pattern
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if pattern.search(text_lower):
                    return intent

        # Default
        return "unknown"

    async def create_plan(
        self, text: str, intent: str
    ) -> Dict[str, Any]:
        """Create execution plan from intent."""
        text_lower = text.lower().strip()

        if intent == "system_status":
            return {
                "steps": [
                    {"tool": "system.status", "args": {}},
                ]
            }

        elif intent == "disk_usage":
            return {
                "steps": [
                    {"tool": "system.disk_usage", "args": {}},
                ]
            }

        elif intent == "ram_usage":
            return {
                "steps": [
                    {"tool": "system.ram_usage", "args": {}},
                ]
            }

        elif intent == "list_files":
            # Extract path
            path = self._extract_path(text)
            return {
                "steps": [
                    {"tool": "file.list", "args": {"path": path}},
                ]
            }

        elif intent == "delete_files":
            path = self._extract_path(text)
            return {
                "steps": [
                    {"tool": "file.scan", "args": {"path": path}},
                    {"tool": "file.quarantine", "args": {"path": path}},
                ]
            }

        elif intent == "open_app":
            app_name = self._extract_app_name(text)
            return {
                "steps": [
                    {"tool": "system.open_app", "args": {"name": app_name}},
                ]
            }

        elif intent == "open_website":
            url = self._extract_url(text)
            return {
                "steps": [
                    {"tool": "browser.open", "args": {"url": url}},
                ]
            }

        elif intent == "search_web":
            query = self._extract_search_query(text)
            return {
                "steps": [
                    {"tool": "browser.search", "args": {"query": query}},
                ]
            }

        elif intent == "browser_close":
            return {
                "steps": [
                    {"tool": "browser.close", "args": {}},
                ]
            }

        elif intent == "download_file":
            url = self._extract_url(text)
            return {
                "steps": [
                    {"tool": "browser.download", "args": {"url": url}},
                ]
            }

        elif intent == "screen_click":
            return {
                "steps": [
                    {"tool": "screen.click_text", "args": {"text": self._extract_click_text(text)}},
                ]
            }

        elif intent == "screen_scan":
            return {
                "steps": [
                    {"tool": "screen.scan", "args": {}},
                ]
            }

        elif intent == "login":
            site = self._extract_site(text)
            return {
                "steps": [
                    {"tool": "browser.open", "args": {"url": site}},
                    {"tool": "auth.password_login", "args": {"site": site}},
                ]
            }

        else:
            return {
                "steps": [],
                "error": f"Unknown intent: {intent}",
            }

    def _extract_path(self, text: str) -> str:
        """Extract file path from text."""
        # Look for common path patterns
        patterns = [
            r"[Cc]:\\[^\s]+",  # Windows path
            r"/[^\s]+",  # Unix path
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)

        # Default paths
        if "download" in text.lower():
            return "C:\\Users\\brigh\\Downloads"
        elif "desktop" in text.lower():
            return "C:\\Users\\brigh\\Desktop"
        elif "documents" in text.lower():
            return "C:\\Users\\brigh\\Documents"

        return "."

    def _extract_app_name(self, text: str) -> str:
        """Extract application name from text."""
        text_lower = text.lower()
        known_phrases = [
            "opera gx browser",
            "opera gx",
            "gx browser",
            "google chrome",
            "microsoft edge",
            "visual studio code",
            "vs code",
        ]
        for phrase in known_phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", text_lower):
                return phrase

        # Remove common words
        text_clean = re.sub(
            r"\b(open|launch|start|run|app|application|program|browser)\b",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        # Take first word/phrase
        words = text_clean.split()
        return words[0] if words else "unknown"

    def _extract_url(self, text: str) -> str:
        """Extract URL from text."""
        # Look for URL
        url_match = re.search(r"https?://\S+", text)
        if url_match:
            return url_match.group(0)

        # Look for domain
        domain_match = re.search(
            r"\b([a-zA-Z0-9-]+\.(com|org|net|io|gov|edu))\b", text
        )
        if domain_match:
            return f"https://{domain_match.group(0)}"

        text_lower = text.lower()
        for name, url in self.SITE_ALIASES.items():
            if re.search(rf"\b{name}\b", text_lower):
                return url

        return "https://www.google.com"

    def _extract_search_query(self, text: str) -> str:
        """Extract search query from text."""
        # Remove "search for" etc.
        query = re.sub(
            r"\b(search|google|find|look up|lookup|for|on the web|online)\b",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        query = re.sub(
            r"\b(in|on|with)\s+(chrome|edge|browser|google|bing)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()

        query = re.sub(r"\s+", " ", query).strip(" ?.")

        return query or text.strip()

    def _extract_site(self, text: str) -> str:
        """Extract site name from login command."""
        # Look for "to xyz.com" pattern
        match = re.search(r"\bto\s+([a-zA-Z0-9.-]+\.[a-z]{2,})", text)
        if match:
            return f"https://{match.group(1)}"

        return "https://www.google.com"

    def _extract_click_text(self, text: str) -> str:
        """Extract visible UI text from a click/tap command."""
        cleaned = re.sub(
            r"\b(click|press|tap|select|button|link|tab|field|on|the)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:\"'")
        return cleaned or text.strip()
