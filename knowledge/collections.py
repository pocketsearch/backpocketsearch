"""
collections.py — automatic folder/collection generation based on interests and entities.
"""
from __future__ import annotations

from knowledge.storage import MemoryStorage
from knowledge.learning import InterestLearner
from knowledge.entities import EntityExtractor


class AutoCollections:
    def __init__(self, storage: MemoryStorage, learner: InterestLearner, extractor: EntityExtractor):
        self.storage = storage
        self.learner = learner
        self.extractor = extractor

    def build_collections(self) -> list[dict]:
        interests = self.learner.get_top_interests(min_score=1.0, limit=20)
        entities = self.storage.get_entities(limit=200)

        category_map: dict[str, list[str]] = {}
        for interest in interests:
            topic = interest["topic"]
            category_map.setdefault(topic, [])
            for ent in entities:
                val = ent.get("value", "")
                if val and val not in category_map[topic]:
                    category_map[topic].append(val)

        collections = []
        for category, items in category_map.items():
            if len(items) < 2:
                continue
            collection_name = category.title()
            self.storage.create_collection(
                name=collection_name,
                description=f"Auto-generated collection for {category}",
                auto_generated=True,
            )
            for item in items[:20]:
                self.storage.add_to_collection(collection_name, item)
            collections.append({
                "name": collection_name,
                "count": len(items),
            })

        return collections

    def get_collections(self) -> list[dict]:
        return self.storage.get_collections()

    def get_collection_items(self, name: str) -> list[str]:
        return self.storage.get_collection_items(name)
