"""
preferences.py — learn user preferences for sources, categories, and formats.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

from knowledge.storage import MemoryStorage


class PreferenceLearner:
    def __init__(self, storage: MemoryStorage, half_life_days: int = 30):
        self.storage = storage
        self.half_life_days = half_life_days

    def record_source_choice(self, source: str, clicked: bool = True) -> None:
        key = f"pref_source:{source.lower()}"
        row = self._get_pref(key)
        if row:
            confidence = min(row.get("confidence", 0.5) + 0.05, 0.99)
            score = (row.get("value", "0.5") if isinstance(row.get("value"), (int, float)) else 0.5)
            if clicked:
                score = min(score + 0.1, 1.0)
            else:
                score = max(score - 0.05, 0.0)
            self.storage.set_preference(key, str(round(score, 3)), confidence)
        else:
            confidence = 0.6
            score = 0.7 if clicked else 0.3
            self.storage.set_preference(key, str(round(score, 3)), confidence)

    def get_ranked_sources(self) -> list[dict]:
        prefs = self.storage.get_preferences()
        sources = []
        for key, data in prefs.items():
            if key.startswith("pref_source:"):
                source = key.split(":", 1)[1]
                try:
                    score = float(data["value"])
                except (ValueError, TypeError):
                    score = 0.5
                sources.append({
                    "source": source,
                    "score": score,
                    "confidence": data.get("confidence", 0.5),
                })
        sources.sort(key=lambda x: x["score"] * x["confidence"], reverse=True)
        return sources

    def get_preferred_sources(self, limit: int = 5) -> list[str]:
        return [s["source"] for s in self.get_ranked_sources()[:limit]]

    def get_source_bias(self, source: str) -> float:
        key = f"pref_source:{source.lower()}"
        val = self.storage.get_preference(key, "0.5")
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.5

    def _get_pref(self, key: str) -> Optional[dict]:
        prefs = self.storage.get_preferences()
        return prefs.get(key)

    def record_category(self, category: str) -> None:
        key = f"pref_category:{category.lower()}"
        row = self._get_pref(key)
        if row:
            try:
                score = float(row.get("value", 0.5)) + 0.05
            except (ValueError, TypeError):
                score = 0.6
            self.storage.set_preference(key, str(min(round(score, 3), 0.99)), min(row.get("confidence", 0.5) + 0.02, 0.99))
        else:
            self.storage.set_preference(key, "0.6", 0.6)

    def get_preferred_categories(self, limit: int = 10) -> list[str]:
        prefs = self.storage.get_preferences()
        cats = []
        for key, data in prefs.items():
            if key.startswith("pref_category:"):
                cat = key.split(":", 1)[1]
                try:
                    score = float(data["value"])
                except (ValueError, TypeError):
                    score = 0.5
                cats.append((cat, score * data.get("confidence", 0.5)))
        cats.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in cats[:limit]]
