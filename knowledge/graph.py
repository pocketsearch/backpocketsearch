"""
graph.py — knowledge graph linking entities and topics.
"""
from __future__ import annotations

from typing import Optional

from knowledge.storage import MemoryStorage


class KnowledgeGraph:
    def __init__(self, storage: MemoryStorage):
        self.storage = storage

    def link(self, source: str, target: str, relation: str, weight: float = 1.0) -> None:
        self.storage.add_graph_edge(source, target, relation, weight)

    def link_query_entities(self, query: str) -> None:
        entities = self.storage.get_entities(limit=50)
        query_lower = query.lower()
        for ent in entities:
            value = ent.get("value", "")
            if value and value in query_lower:
                for other in entities:
                    other_value = other.get("value", "")
                    if other_value and other_value != value and other_value in query_lower:
                        self.link(value, other_value, "co_occurs", 0.5)

    def get_related(self, entity: str, relation: Optional[str] = None) -> list[dict]:
        return self.storage.get_graph_edges(source=entity, relation=relation)

    def get_graph(self) -> dict:
        edges = self.storage.get_graph_edges()
        nodes: dict[str, dict] = {}
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if src not in nodes:
                nodes[src] = {"id": src, "edges": []}
            if tgt not in nodes:
                nodes[tgt] = {"id": tgt, "edges": []}
            nodes[src]["edges"].append({
                "relation": edge.get("relation"),
                "target": tgt,
                "weight": edge.get("weight", 1),
            })
        return nodes
