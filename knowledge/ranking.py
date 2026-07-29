"""
ranking.py — reorder search results based on learned user preferences.
"""
from __future__ import annotations

import re
from typing import Any

from knowledge.preferences import PreferenceLearner


HOW_TO_PATTERNS = [
    r'\bhow\s+to\b',
    r'\bhow\s+do\s+i\b',
    r'\bhow\s+can\s+I\b',
    r'\blearn\s+how\b',
    r'\bguide\s+to\b',
    r'\btutorial\b',
    r'\bwalkthrough\b',
    r'\bstep\s+by\s+step\b',
    r'\bsetup\b',
    r'\binstall\b',
    r'\bconfigure\b',
    r'\bcreate\s+a\b',
    r'\bset\s+up\b',
]


class PersonalRanker:
    def __init__(self, preference_learner: PreferenceLearner):
        self.preferences = preference_learner

    def rank(self, results: list[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
        if not results:
            return results
        source_bias = {}
        for src in self.preferences.get_ranked_sources():
            source_bias[src["source"].lower()] = src["score"] * src["confidence"]

        is_how_to = any(re.search(p, query.lower()) for p in HOW_TO_PATTERNS)

        scored = []
        for item in results:
            score = 1.0
            source = (item.get("source") or "").lower()
            if source in source_bias:
                score += source_bias[source] * 2.0
            item_type = (item.get("type") or "").lower()
            if item_type in ("repo", "code", "package"):
                score += 0.3
            if item.get("meta"):
                score += 0.1
            if is_how_to:
                score += self._howto_boost(item)
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    def _howto_boost(self, item: dict[str, Any]) -> float:
        boost = 0.0
        title = (item.get("title", "")).lower()
        snippet = (item.get("snippet", "")).lower()
        text = title + " " + snippet

        step_keywords = ["step", "first", "next", "then", "finally", "step 1", "step 2", "guide", "tutorial"]
        for kw in step_keywords:
            if kw in text:
                boost += 0.4

        action_verbs = [
            "click", "type", "open", "run", "install", "select", "enter",
            "find", "go to", "navigate", "set up", "configure", "create",
            "write", "paste", "copy", "save", "download", "launch",
        ]
        for verb in action_verbs:
            if verb in text:
                boost += 0.3
                break

        if any(w in text for w in ["example", "sample", "demo", "template"]):
            boost += 0.2

        return min(boost, 2.0)
