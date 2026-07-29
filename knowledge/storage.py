"""
storage.py — SQLite persistence for the PocketSearch memory system.
"""
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional


class MemoryStorage:
    def __init__(self, db_path: str = "pocketsearch_memory.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    normalized_query TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    value TEXT NOT NULL,
                    context TEXT,
                    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(kind, value)
                );

                CREATE TABLE IF NOT EXISTS interests (
                    topic TEXT PRIMARY KEY,
                    score REAL NOT NULL DEFAULT 0,
                    last_updated TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER,
                    tag TEXT NOT NULL,
                    FOREIGN KEY(item_id) REFERENCES saved_items(id) ON DELETE CASCADE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_item_tag ON tags(item_id, tag);

                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1,
                    last_updated TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(source, target, relation)
                );

                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    auto_generated INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS collection_items (
                    collection_id INTEGER NOT NULL,
                    entity TEXT NOT NULL,
                    PRIMARY KEY(collection_id, entity),
                    FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE
                );
            """)

    def log_search(self, query: str, normalized_query: Optional[str] = None) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO searches (query, normalized_query) VALUES (?, ?)",
                (query, normalized_query or query.lower().strip()),
            )
            conn.commit()
            return cur.lastrowid

    def upsert_entity(self, kind: str, value: str, context: str = "") -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO entities (kind, value, context, last_seen)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(kind, value) DO UPDATE SET
                     last_seen = excluded.last_seen,
                     context = excluded.context""",
                (kind, value.lower().strip(), context),
            )
            conn.commit()

    def get_entities(self, kind: Optional[str] = None, limit: int = 100):
        with self._lock, self._conn() as conn:
            if kind:
                rows = conn.execute(
                    "SELECT * FROM entities WHERE kind = ? ORDER BY last_seen DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM entities ORDER BY last_seen DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def add_interest(self, topic: str, score_delta: float = 1.0) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO interests (topic, score, last_updated)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(topic) DO UPDATE SET
                     score = score + ?,
                     last_updated = excluded.last_updated""",
                (topic, score_delta, score_delta),
            )
            conn.commit()

    def get_interests(self, min_score: float = 0.0, limit: int = 50):
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT topic, score FROM interests WHERE score >= ? ORDER BY score DESC LIMIT ?",
                (min_score, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def decay_interests(self, half_life_days: int = 14) -> None:
        cutoff = datetime.utcnow() - timedelta(days=half_life_days * 2)
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT topic, score, last_updated FROM interests WHERE last_updated < ?",
                (cutoff.isoformat(),),
            ).fetchall()
            for row in rows:
                last = datetime.fromisoformat(row["last_updated"])
                age_days = (datetime.utcnow() - last).days
                decay_factor = 0.5 ** (age_days / half_life_days)
                new_score = round(row["score"] * decay_factor, 4)
                conn.execute(
                    "UPDATE interests SET score = ?, last_updated = ? WHERE topic = ?",
                    (new_score, datetime.utcnow().isoformat(), row["topic"]),
                )
            conn.commit()

    def add_tag(self, item_id: int, tag: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tags (item_id, tag) VALUES (?, ?)",
                (item_id, tag.lower().strip()),
            )
            conn.commit()

    def get_tags(self, item_id: int):
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT tag FROM tags WHERE item_id = ?", (item_id,)
            ).fetchall()
            return [r["tag"] for r in rows]

    def set_preference(self, key: str, value: str, confidence: float = 1.0) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO preferences (key, value, confidence, updated_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value,
                     confidence = excluded.confidence,
                     updated_at = excluded.updated_at""",
                (key, value, confidence),
            )
            conn.commit()

    def get_preference(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM preferences WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def get_preferences(self) -> dict:
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT key, value, confidence FROM preferences").fetchall()
            return {r["key"]: {"value": r["value"], "confidence": r["confidence"]} for r in rows}

    def add_graph_edge(self, source: str, target: str, relation: str, weight: float = 1.0) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO graph_edges (source, target, relation, weight, last_updated)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(source, target, relation) DO UPDATE SET
                     weight = weight + ?,
                     last_updated = excluded.last_updated""",
                (source, target, relation, weight, weight),
            )
            conn.commit()

    def get_graph_edges(self, source: Optional[str] = None, relation: Optional[str] = None):
        with self._lock, self._conn() as conn:
            query = "SELECT * FROM graph_edges WHERE 1=1"
            params = []
            if source:
                query += " AND source = ?"
                params.append(source)
            if relation:
                query += " AND relation = ?"
                params.append(relation)
            query += " ORDER BY weight DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def create_collection(self, name: str, description: str = "", auto_generated: bool = True) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO collections (name, description, auto_generated) VALUES (?, ?, ?)",
                (name, description, 1 if auto_generated else 0),
            )
            conn.commit()
            if cur.lastrowid:
                return cur.lastrowid
            row = conn.execute("SELECT id FROM collections WHERE name = ?", (name,)).fetchone()
            return row["id"]

    def add_to_collection(self, collection_name: str, entity: str) -> None:
        collection_id = self.create_collection(collection_name)
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO collection_items (collection_id, entity) VALUES (?, ?)",
                (collection_id, entity.lower().strip()),
            )
            conn.commit()

    def get_collections(self):
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, description, auto_generated, created_at FROM collections ORDER BY name"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_collection_items(self, collection_name: str):
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM collections WHERE name = ?", (collection_name,)
            ).fetchone()
            if not row:
                return []
            rows = conn.execute(
                "SELECT entity FROM collection_items WHERE collection_id = ?", (row["id"],)
            ).fetchall()
            return [r["entity"] for r in rows]
