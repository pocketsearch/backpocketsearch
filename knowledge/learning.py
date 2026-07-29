"""
learning.py — interest scoring with time-based decay.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

from knowledge.storage import MemoryStorage


class InterestLearner:
    def __init__(self, storage: MemoryStorage, half_life_days: int = 14):
        self.storage = storage
        self.half_life_days = half_life_days

    def record_interest(self, topic: str, score_delta: float = 1.0) -> None:
        self.storage.add_interest(topic, score_delta)

    def record_from_query(self, query: str) -> None:
        topics = self._extract_topics(query)
        for topic in topics:
            self.record_interest(topic, 1.0)

    def record_from_click(self, source: str, category: Optional[str] = None) -> None:
        self.record_interest(source, 2.0)
        if category:
            self.record_interest(category, 1.5)

    def get_top_interests(self, min_score: float = 0.5, limit: int = 20) -> list[dict]:
        raw = self.storage.get_interests(min_score=min_score, limit=limit * 2)
        now = datetime.utcnow()
        scored = []
        for item in raw:
            last_text = item.get("last_updated") or item.get("updated_at")
            if not last_text:
                age_days = 999
            else:
                try:
                    last = datetime.fromisoformat(last_text)
                    age_days = (now - last).days
                except Exception:
                    age_days = 999
            decay_factor = 0.5 ** (age_days / self.half_life_days)
            effective_score = item.get("score", 0) * decay_factor
            if effective_score >= min_score:
                scored.append({
                    "topic": item.get("topic") or item.get("key"),
                    "raw_score": item.get("score", 0),
                    "effective_score": round(effective_score, 3),
                    "age_days": age_days,
                })
        scored.sort(key=lambda x: x["effective_score"], reverse=True)
        return scored[:limit]

    def decay_all(self) -> None:
        self.storage.decay_interests(self.half_life_days)

    def _extract_topics(self, query: str) -> list[str]:
        text = query.lower()
        topics: list[str] = []

        topic_keywords = {
            "cybersecurity": ["cve", "vulnerability", "exploit", "hacker", "pentest", "security", "malware"],
            "osint": ["osint", "reconnaissance", "footprinting", "whois", "dns"],
            "python": ["python", "pip", "django", "flask", "fastapi", "pypi"],
            "javascript": ["javascript", "js", "react", "vue", "angular", "node"],
            "linux": ["linux", "ubuntu", "debian", "bash", "shell", "kernel"],
            "docker": ["docker", "container", "kubernetes", "k8s"],
            "git": ["git", "github", "gitlab", "commit"],
            "ai": ["ai", "ml", "machine learning", "openai", "llm", "gpt"],
            "networking": ["dns", "http", "ssh", "tcp", "udp", "vpn", "firewall"],
            "database": ["sql", "mysql", "postgres", "mongodb", "redis"],
            "cloud": ["aws", "azure", "gcp", "cloud"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in text for kw in keywords):
                topics.append(topic)

        return topics
