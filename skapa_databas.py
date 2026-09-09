import sqlite3
from datetime import datetime

DB = "dif_hockey.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    active INTEGER DEFAULT 1
)
""")

cur.execute("""
CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    facebook_id TEXT NOT NULL,
    url TEXT NOT NULL,
    post_text TEXT,
    post_time TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    is_dif_relevant INTEGER DEFAULT 0,
    match_id INTEGER,
    UNIQUE(source_id, facebook_id),
    FOREIGN KEY(source_id) REFERENCES sources(id)
)
""")

cur.execute("""
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    commenter TEXT NOT NULL,
    comment_text TEXT NOT NULL,
    facebook_time TEXT,
    first_seen TEXT NOT NULL,
    FOREIGN KEY(post_id) REFERENCES posts(id),
    UNIQUE(post_id, commenter, comment_text, facebook_time)
)
""")

cur.execute("""
CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date TEXT,
    home_team TEXT,
    away_team TEXT,
    home_score INTEGER,
    away_score INTEGER,
    status TEXT DEFAULT "unknown",
    created_at TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    commenter TEXT NOT NULL,
    prediction_type TEXT,
    prediction TEXT NOT NULL,
    result TEXT DEFAULT "pending",
    FOREIGN KEY(comment_id) REFERENCES comments(id),
    FOREIGN KEY(match_id) REFERENCES matches(id)
)
""")

cur.execute("""
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    event_time TEXT,
    event_type TEXT NOT NULL,
    team TEXT,
    player TEXT,
    description TEXT,
    FOREIGN KEY(match_id) REFERENCES matches(id)
)
""")

sources = [
    ("Djurgården Hockey", "https://www.facebook.com/difhockeyse"),
    ("TV4 Hockey", "https://www.facebook.com/tv4hockey")
]

for name, url in sources:
    cur.execute("INSERT OR IGNORE INTO sources (name, url, active) VALUES (?, ?, 1)", (name, url))

conn.commit()

print("Databasen är klar.")
print()
print("Källor:")
for row in cur.execute("SELECT id, name, url FROM sources ORDER BY id"):
    print(f"{row[0]}: {row[1]} -> {row[2]}")

print()
print("Tabeller:")
for row in cur.execute("SELECT name FROM sqlite_master WHERE type = ? ORDER BY name", ("table",)):
    print("-", row[0])

conn.close()
