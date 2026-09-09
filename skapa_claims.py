import sqlite3
from datetime import datetime

DB = "dif_hockey.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INTEGER NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT,
    target_type TEXT,
    target TEXT,
    status TEXT DEFAULT 'ny',
    verdict TEXT,
    evidence TEXT,
    evidence_value TEXT,
    evaluated_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (comment_id) REFERENCES comments(id),
    UNIQUE(comment_id, claim_text)
)
""")

conn.commit()
conn.close()

print("Claims-tabellen är klar.")
print("Databasen är inte ändrad i övrigt.")
