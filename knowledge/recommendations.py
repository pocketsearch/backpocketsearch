"""
recommendations.py — home-page suggestion engine based on learned interests.
"""
from __future__ import annotations

from typing import Optional

from knowledge.learning import InterestLearner
from knowledge.preferences import PreferenceLearner
from knowledge.storage import MemoryStorage
from knowledge.entities import EntityExtractor
from knowledge.memory import SearchMemory


class RecommendationEngine:
    def __init__(
        self,
        storage: MemoryStorage,
        learner: InterestLearner,
        preference_learner: PreferenceLearner,
        memory: SearchMemory,
        extractor: EntityExtractor,
    ):
        self.storage = storage
        self.learner = learner
        self.preferences = preference_learner
        self.memory = memory
        self.extractor = extractor

    def get_recommendations(self, limit: int = 8) -> list[dict]:
        interests = self.learner.get_top_interests(min_score=0.3, limit=limit * 2)
        recs = []
        for item in interests:
            topic = item["topic"]
            query = self._build_query_for_topic(topic)
            recs.append({
                "title": topic.title(),
                "query": query,
                "reason": f"You've shown interest in {topic} (score: {item['effective_score']:.1f})",
                "type": "interest",
            })
            if len(recs) >= limit:
                break
        return recs

    def _build_query_for_topic(self, topic: str) -> str:
        templates = {
            "cybersecurity": "latest CVE vulnerabilities",
            "osint": "OSINT tools and techniques",
            "python": "python tutorials and packages",
            "javascript": "javascript frameworks 2026",
            "linux": "linux news and updates",
            "docker": "docker best practices",
            "git": "github trending repositories",
            "ai": "latest AI research papers",
            "networking": "networking tools",
            "database": "database optimization tips",
            "cloud": "cloud computing trends",
        }
        return templates.get(topic, topic)

    def get_discover_recommendations(self, limit: int = 5) -> list[dict]:
        entities = self.storage.get_entities(limit=100)
        related_queries = []
        seen = set()
        for ent in entities:
            val = ent.get("value", "")
            kind = ent.get("kind", "")
            if not val or val in seen:
                continue
            seen.add(val)
            related_queries.append({
                "title": val,
                "query": val,
                "reason": f"Related to your searches ({kind})",
                "type": "entity",
            })
            if len(related_queries) >= limit:
                break
        return related_queries
