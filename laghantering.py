import sqlite3
from datetime import datetime

DB = "/home/robert/dif-kommentarer/dif_hockey.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    short_name TEXT,
    active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
)
""")

now = datetime.now().isoformat(timespec="seconds")

cur.execute("""
INSERT OR IGNORE INTO teams (name, short_name, active, created_at)
VALUES (?, ?, ?, ?)
""", ("Djurgården", "DIF", 1, now))

conn.commit()

print()
print("==============================")
print("       LAGREGISTRET")
print("==============================")
print()

cur.execute("""
SELECT id, name, short_name, active
FROM teams
ORDER BY name
""")

teams = cur.fetchall()

for team_id, name, short_name, active in teams:
    status = "AKTIVT" if active else "INAKTIVT"
    print(f"{team_id:2} | {name:25} | {short_name or '-':5} | {status}")

print()
print(f"Totalt antal lag: {len(teams)}")
print()

conn.close()
