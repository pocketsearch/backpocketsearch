"""
tagger.py — automatic tagging for saved results.
"""
from __future__ import annotations

import re
from typing import Optional

from knowledge.learning import InterestLearner
from knowledge.entities import EntityExtractor


class AutoTagger:
    def __init__(self, learner: InterestLearner, extractor: EntityExtractor):
        self.learner = learner
        self.extractor = extractor

    def generate_tags(self, title: str, snippet: str, url: str = "") -> list[str]:
        text = f"{title} {snippet} {url}".lower()
        tags: list[str] = []

        tag_keywords = {
            "security": ["cve", "vulnerability", "exploit", "security", "hacker", "pentest", "malware", "advisory"],
            "ai": ["ai", "ml", "machine learning", "openai", "llm", "gpt", "neural"],
            "python": ["python", "pip", "django", "flask", "pypi"],
            "javascript": ["javascript", "js", "react", "vue", "angular", "node"],
            "linux": ["linux", "ubuntu", "debian", "bash", "kernel"],
            "docker": ["docker", "container", "kubernetes"],
            "git": ["git", "github", "gitlab"],
            "database": ["sql", "mysql", "postgres", "mongodb", "redis"],
            "networking": ["dns", "http", "ssh", "tcp", "vpn", "firewall"],
            "cloud": ["aws", "azure", "gcp", "cloud"],
            "news": ["news", "announcement", "release", "update"],
            "tutorial": ["tutorial", "guide", "how to", "learn"],
            "documentation": ["docs", "documentation", "reference", "api"],
        }

        for tag, keywords in tag_keywords.items():
            if any(kw in text for kw in keywords):
                tags.append(tag)

        entities = self.extractor.extract_from_query(text)
        for ent in entities:
            kind = ent.get("kind")
            value = ent.get("value")
            if kind == "domain" and value:
                tags.append(value)
            elif kind == "github_repo" and value:
                tags.append(value.replace("/", "_"))
            elif kind == "technology" and value:
                if value not in tags:
                    tags.append(value)

        interests = self.learner.get_top_interests(min_score=0.5, limit=10)
        for interest in interests:
            topic = interest.get("topic", "")
            if topic and topic in text and topic not in tags:
                tags.append(topic)

        return tags[:10]
