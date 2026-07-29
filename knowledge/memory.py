"""
memory.py — record every search and maintain a short-term query history.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from knowledge.entities import EntityExtractor
from knowledge.storage import MemoryStorage


class SearchMemory:
    def __init__(self, storage: MemoryStorage, entity_extractor: EntityExtractor):
        self.storage = storage
        self.entity_extractor = entity_extractor
        self._recent_queries: list[str] = []
        self._max_recent = 20

    def record_search(self, query: str, normalized_query: Optional[str] = None) -> int:
        search_id = self.storage.log_search(query, normalized_query)
        self.entity_extractor.extract_and_store(query)
        self._recent_queries.append(query)
        if len(self._recent_queries) > self._max_recent:
            self._recent_queries.pop(0)
        return search_id

    def get_recent_queries(self, limit: int = 10) -> list[str]:
        return list(reversed(self._recent_queries[-limit:]))

    def get_search_count(self) -> int:
        with self.storage._lock, self.storage._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as c FROM searches").fetchone()
            return row["c"]

    def prune_old_searches(self, days: int = 90) -> None:
        cutoff = datetime.utcnow() - timedelta(days=days)
        with self.storage._lock, self.storage._conn() as conn:
            conn.execute(
                "DELETE FROM searches WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            conn.commit()
