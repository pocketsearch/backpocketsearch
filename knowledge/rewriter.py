"""
rewriter.py — expand queries based on previous searches and learned interests.
"""
from __future__ import annotations

from typing import Optional

from knowledge.learning import InterestLearner
from knowledge.memory import SearchMemory


class QueryRewriter:
    def __init__(self, memory: SearchMemory, learner: InterestLearner):
        self.memory = memory
        self.learner = learner

    def rewrite(self, query: str) -> str:
        interests = self.learner.get_top_interests(min_score=0.2, limit=10)
        interest_terms = [i["topic"] for i in interests if i["topic"] not in query.lower()]

        recent = self.memory.get_recent_queries(limit=5)
        context_terms: list[str] = []
        for rq in recent:
            for word in rq.lower().split():
                if len(word) > 3 and word not in query.lower() and word not in context_terms:
                    context_terms.append(word)

        expansions = interest_terms[:3] + context_terms[:3]
        if expansions:
            return f"{query} {' '.join(expansions)}"
        return query

    def suggest_related(self, query: str, limit: int = 6) -> list[str]:
        interests = self.learner.get_top_interests(min_score=0.1, limit=limit * 2)
        related = []
        q_lower = query.lower()
        for item in interests:
            topic = item["topic"]
            if topic not in q_lower and topic not in related:
                related.append(topic)
            if len(related) >= limit:
                break
        return related
