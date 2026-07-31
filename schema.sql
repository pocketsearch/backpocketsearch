CREATE TABLE IF NOT EXISTS roadmaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    deadline TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roadmap_id INTEGER,
    title TEXT NOT NULL,
    description TEXT,
    is_completed BOOLEAN NOT NULL,
    FOREIGN KEY (roadmap_id) REFERENCES roadmaps (id)
);