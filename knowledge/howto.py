"""
howto.py — step-by-step result generation for how-to questions.

HowToProcessor detects how-to / procedural queries, organizes search
results into numbered steps, adapts complexity for any audience level,
and enriches each step with duration estimates, prerequisites, and tips.
"""
from __future__ import annotations

import re
from typing import Optional

from knowledge.storage import MemoryStorage
from knowledge.entities import EntityExtractor


HOW_TO_PATTERNS = [
    r'\bhow\s+to\b',
    r'\bhow\s+do\s+i\b',
    r'\bhow\s+can\s+I\b',
    r'\bhow\s+should\s+I\b',
    r'\bsteps?\s+to\b',
    r'\bguide\s+to\b',
    r'\btutorial\b',
    r'\bwalkthrough\b',
    r'\bsetup\b.*\bfor\b',
    r'\binstall\b.*\bfor\b',
    r'\bconfigure\b.*\bfor\b',
    r'\bbuild\b.*\bfrom\b',
    r'\bcreate\s+a\b',
    r'\bset\s+up\b',
    r'\bget\s+started\b',
    r'\blearn\s+how\b',
    r'\bstep\s+by\s+step\b',
    r'\bfirst\s+step\b',
    r'\bwhat\s+are\s+the\s+steps\b',
    r'\bhow\s+do\s+you\b',
    r'\bhow\s+can\s+you\b',
    r'\bwhat\s+is\s+the\s+process\b',
    r'\bprocedure\s+for\b',
    r'\binsructions?\s+for\b',
]

DIFFICULTY_LEVELS = ["child", "high_school", "college", "engineer", "researcher"]

DIFFICULTY_KEYWORDS = {
    "child": ["simple", "easy", "explain", "for kids", "basics", "beginner", "what is"],
    "high_school": ["explain", "introduction", "basic", "overview", "beginner"],
    "college": ["detailed", "comprehensive", "guide", "tutorial", "step-by-step"],
    "engineer": ["implementation", "code", "configure", "technical", "architecture", "api"],
    "researcher": ["research", "study", "paper", "methodology", "analysis", "experimental"],
}

EASY_WORDS = {
    "use": "use", "click": "click", "open": "open", "go": "go",
    "find": "find", "look": "look", "type": "type", "press": "press",
    "enter": "enter", "select": "select", "choose": "choose", "pick": "pick",
    "start": "start", "run": "run", "install": "install", "save": "save",
    "write": "write", "copy": "copy", "paste": "paste", "drag": "drag",
    "drop": "drop", "right": "right", "click": "click", "next": "next",
    "finish": "finish", "done": "done", "ready": "ready",
}


class HowToProcessor:
    def __init__(self, storage: MemoryStorage, entity_extractor: EntityExtractor):
        self.storage = storage
        self.entity_extractor = entity_extractor

    def is_how_to_query(self, query: str) -> bool:
        q = query.lower().strip()
        for pattern in HOW_TO_PATTERNS:
            if re.search(pattern, q):
                return True
        return False

    def detect_difficulty(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        scores = {level: 0.0 for level in DIFFICULTY_LEVELS}

        for level, keywords in DIFFICULTY_KEYWORDS.items():
            for kw in keywords:
                if kw in q:
                    scores[level] += 1.0

        for item in results:
            snippet = (item.get("snippet", "") + " " + item.get("title", "")).lower()
            for level, keywords in DIFFICULTY_KEYWORDS.items():
                for kw in keywords:
                    if kw in snippet:
                        scores[level] += 0.5

        for word in EASY_WORDS:
            if f" {word} " in f" {q} " or f" {word} " in " ".join(
                item.get("snippet", "").lower().split()[:20]
                for item in results[:3]
            ):
                scores["child"] += 0.3

        best = max(scores, key=scores.get)
        if scores[best] < 0.5:
            best = "college"
        return best

    def generate_steps(
        self,
        results: list[dict],
        query: str,
        difficulty: Optional[str] = None,
    ) -> list[dict]:
        if difficulty is None:
            difficulty = self.detect_difficulty(query, results)

        steps = self._extract_steps(results, query)
        steps = self._add_step_metadata(steps, query, difficulty)
        steps = self._simplify_language(steps, difficulty)
        steps = self._add_prerequisites(steps, query, difficulty)
        steps = self._add_tips(steps, query, difficulty)
        return steps

    def _extract_steps(self, results: list[dict], query: str) -> list[dict]:
        steps = []
        step_num = 0
        seen_titles: set[str] = set()

        for item in results:
            title = item.get("title", "").strip()
            snippet = item.get("snippet", "").strip()
            url = item.get("url", "")
            source = item.get("source", "")

            if not title:
                continue

            clean_title = re.sub(r'\s+', ' ', title).strip()
            if clean_title.lower() in seen_titles:
                continue
            seen_titles.add(clean_title.lower())

            sentences = self._split_sentences(snippet) if snippet else [title]
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence or len(sentence) < 10:
                    continue
                step_num += 1
                steps.append({
                    "step_number": step_num,
                    "step_title": clean_title[:120],
                    "step_description": sentence[:300],
                    "url": url,
                    "source": source,
                    "type": item.get("type", "result"),
                })
                if step_num >= 20:
                    return steps

        if not steps and results:
            for item in results[:5]:
                step_num += 1
                steps.append({
                    "step_number": step_num,
                    "step_title": item.get("title", "Step")[:120],
                    "step_description": item.get("snippet", "")[:300],
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                    "type": item.get("type", "result"),
                })

        return steps

    def _split_sentences(self, text: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    def _add_step_metadata(
        self, steps: list[dict], query: str, difficulty: str
    ) -> list[dict]:
        base_duration = {"child": 2, "high_school": 3, "college": 5, "engineer": 10, "researcher": 15}
        minutes = base_duration.get(difficulty, 5)
        total_steps = len(steps)

        for i, step in enumerate(steps):
            step["difficulty"] = difficulty
            step["level_index"] = DIFFICULTY_LEVELS.index(difficulty)
            step["estimated_minutes"] = minutes
            step["total_steps"] = total_steps
            step["progress_pct"] = round((i + 1) / max(total_steps, 1) * 100)
            step["step_verb"] = self._extract_verb(step["step_description"])
            step["step_number_label"] = f"Step {step['step_number']} of {total_steps}"

        return steps

    def _extract_verb(self, text: str) -> str:
        imperative_verbs = [
            "install", "configure", "run", "open", "click", "select", "type",
            "paste", "copy", "save", "download", "create", "build", "set",
            "enable", "disable", "restart", "connect", "navigate", "go to",
            "find", "look for", "check", "verify", "test", "run", "execute",
            "write", "edit", "delete", "add", "remove", "update", "upgrade",
            "prepare", "launch", "access", "enter", "submit", "choose", "pick",
            "drag", "drop", "resize", "move", "rename", "organize",
        ]
        lower = text.lower()
        for verb in imperative_verbs:
            if lower.startswith(verb):
                return verb
        for verb in imperative_verbs:
            if verb in lower:
                return verb
        return "complete"

    def _simplify_language(self, steps: list[dict], difficulty: str) -> list[dict]:
        if difficulty == "child":
            for step in steps:
                step["step_description"] = self._simplify_to_child(step["step_description"])
                step["step_title"] = self._simplify_to_child(step["step_title"], title=True)
        elif difficulty == "high_school":
            for step in steps:
                step["step_description"] = self._simplify_to_highschool(step["step_description"])
                step["step_title"] = self._simplify_to_highschool(step["step_title"], title=True)
        return steps

    def _simplify_to_child(self, text: str, title: bool = False) -> str:
        replacements = {
            "install": "put in", "configuration": "settings", "configured": "set up",
            "execute": "run", "utilize": "use", "navigate": "go to",
            "initialize": "start", "terminate": "stop", "commence": "begin",
            "proceed": "continue", "implement": "build", "verify": "check",
            "demonstrate": "show", "subsequently": "then", "therefore": "so",
            "additionally": "also", "however": "but", "furthermore": "also",
            "approximately": "about", "previously": "before", "subsequently": "after",
            "document": "write down", "directory": "folder", "environment": "setup",
        }
        for complex_word, simple in replacements.items():
            text = re.sub(r'\b' + re.escape(complex_word) + r'\b', simple, text, flags=re.IGNORECASE)
        return text

    def _simplify_to_highschool(self, text: str, title: bool = False) -> str:
        replacements = {
            "utilize": "use", "demonstrate": "show", "subsequently": "then",
            "therefore": "so", "additionally": "also", "however": "but",
            "furthermore": "also", "approximately": "about", "implement": "build",
            "initialize": "start", "terminate": "stop", "execute": "run",
            "configuration": "settings", "directory": "folder",
        }
        for complex_word, simple in replacements.items():
            text = re.sub(r'\b' + re.escape(complex_word) + r'\b', simple, text, flags=re.IGNORECASE)
        return text

    def _add_prerequisites(
        self, steps: list[dict], query: str, difficulty: str
    ) -> list[dict]:
        if difficulty == "child":
            default_prereqs = ["A computer or device", "An adult to help if needed"]
        elif difficulty == "high_school":
            default_prereqs = ["A computer or device", "Basic understanding of the topic"]
        elif difficulty == "college":
            default_prereqs = ["A computer or device", "Internet connection", "Basic knowledge of the subject"]
        elif difficulty == "engineer":
            default_prereqs = ["A computer with admin access", "Internet connection", "Terminal or command-line access"]
        else:
            default_prereqs = ["Research environment set up", "Access to tools and datasets", "Domain knowledge"]

        for step in steps:
            step["prerequisites"] = list(default_prereqs)
            if step["step_number"] > 1:
                step["prerequisites"].append(f"Completed steps 1 through {step['step_number'] - 1}")

        return steps

    def _add_tips(self, steps: list[dict], query: str, difficulty: str) -> list[dict]:
        tip_pool = {
            "child": [
                "Take your time — there is no rush.",
                "If something feels confusing, read the step again slowly.",
                "Ask a friend or adult if you get stuck.",
            ],
            "high_school": [
                "Read each step fully before acting on it.",
                "If a step fails, check that you completed the previous one correctly.",
                "Take notes as you go — it helps you remember.",
            ],
            "college": [
                "Follow the steps in order — skipping ahead can cause errors.",
                "If a command fails, copy the error message and search for it.",
                "Test your work after completing all steps.",
            ],
            "engineer": [
                "Read the official documentation before starting.",
                "Use version control to track your changes.",
                "Automate repetitive steps with scripts where possible.",
            ],
            "researcher": [
                "Document every step for reproducibility.",
                "Compare results across multiple sources before concluding.",
                "Note any deviations from the standard procedure.",
            ],
        }
        tips = tip_pool.get(difficulty, tip_pool["college"])

        for i, step in enumerate(steps):
            tip_index = i % len(tips)
            step["tips"] = [tips[tip_index]]

        return steps

    def generate_summary(self, query: str, steps: list[dict]) -> dict:
        total = len(steps)
        total_minutes = sum(s.get("estimated_minutes", 5) for s in steps)
        return {
            "query": query,
            "total_steps": total,
            "total_estimated_minutes": total_minutes,
            "difficulty": steps[0].get("difficulty", "college") if steps else "college",
            "summary": f"This guide has {total} steps and takes about {total_minutes} minutes to complete.",
            "prerequisites": steps[0].get("prerequisites", []) if steps else [],
        }