import sqlite3

DB = "dif_hockey.db"

MATCHER = [
    ("2026-09-19", "Djurgården", "IF Björklöven"),
    ("2026-09-22", "Rögle BK", "Djurgården"),
    ("2026-09-24", "Djurgården", "Växjö Lakers HC"),
    ("2026-09-26", "Timrå IK", "Djurgården"),
    ("2026-10-01", "Djurgården", "Färjestads BK"),
    ("2026-10-03", "Frölunda HC", "Djurgården"),
    ("2026-10-08", "Djurgården", "Örebro HK"),
    ("2026-10-10", "Djurgården", "Linköpings HC"),
    ("2026-10-15", "Brynäs IF", "Djurgården"),
    ("2026-10-17", "Djurgården", "Malmö Redhawks"),
    ("2026-10-20", "Frölunda HC", "Djurgården"),
    ("2026-10-22", "Skellefteå AIK", "Djurgården"),
    ("2026-10-24", "Luleå HF", "Djurgården"),
    ("2026-10-29", "Djurgården", "HV71"),
    ("2026-10-31", "Djurgården", "Brynäs IF"),
    ("2026-11-12", "Färjestads BK", "Djurgården"),
    ("2026-11-14", "Örebro HK", "Djurgården"),
    ("2026-11-19", "Djurgården", "Skellefteå AIK"),
    ("2026-11-21", "Djurgården", "Luleå HF"),
    ("2026-11-26", "Växjö Lakers HC", "Djurgården"),
    ("2026-11-28", "Malmö Redhawks", "Djurgården"),
    ("2026-12-03", "IF Björklöven", "Djurgården"),
    ("2026-12-05", "Djurgården", "Timrå IK"),
    ("2026-12-17", "Linköpings HC", "Djurgården"),
    ("2026-12-19", "Djurgården", "Rögle BK"),
    ("2026-12-28", "Djurgården", "HV71"),
    ("2026-12-30", "Brynäs IF", "Djurgården"),
    ("2027-01-02", "Djurgården", "Malmö Redhawks"),
    ("2027-01-05", "Djurgården", "Växjö Lakers HC"),
    ("2027-01-07", "Skellefteå AIK", "Djurgården"),
    ("2027-01-09", "Luleå HF", "Djurgården"),
    ("2027-01-14", "Djurgården", "Linköpings HC"),
    ("2027-01-16", "Rögle BK", "Djurgården"),
    ("2027-01-21", "Djurgården", "Örebro HK"),
    ("2027-01-23", "IF Björklöven", "Djurgården"),
    ("2027-01-26", "Färjestads BK", "Djurgården"),
    ("2027-01-28", "Djurgården", "Timrå IK"),
    ("2027-01-30", "HV71", "Djurgården"),
    ("2027-02-02", "Djurgården", "Frölunda HC"),
    ("2027-02-06", "Djurgården", "IF Björklöven"),
    ("2027-02-16", "Djurgården", "Frölunda HC"),
    ("2027-02-18", "HV71", "Djurgården"),
    ("2027-02-20", "Timrå IK", "Djurgården"),
    ("2027-02-25", "Djurgården", "Rögle BK"),
    ("2027-02-27", "Djurgården", "Färjestads BK"),
    ("2027-03-02", "Linköpings HC", "Djurgården"),
    ("2027-03-04", "Djurgården", "Skellefteå AIK"),
    ("2027-03-06", "Djurgården", "Brynäs IF"),
    ("2027-03-09", "Örebro HK", "Djurgården"),
    ("2027-03-11", "Malmö Redhawks", "Djurgården"),
    ("2027-03-13", "Djurgården", "Luleå HF"),
    ("2027-03-16", "Växjö Lakers HC", "Djurgården"),
]


def importera():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    nya = 0
    redan = 0

    for match_date, home, away in MATCHER:

        cur.execute("""
            SELECT id
            FROM matches
            WHERE match_date = ?
              AND home_team = ?
              AND away_team = ?
        """, (match_date, home, away))

        if cur.fetchone():
            redan += 1
            continue

        cur.execute("""
            INSERT INTO matches (
                match_date,
                home_team,
                away_team,
                home_score,
                away_score,
                status,
                created_at,
                match_type
            )
            VALUES (
                ?,
                ?,
                ?,
                NULL,
                NULL,
                'kommande',
                datetime('now'),
                'SHL'
            )
        """, (match_date, home, away))

        nya += 1

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM matches")
    totalt = cur.fetchone()[0]

    conn.close()

    print("=" * 40)
    print("MATCHIMPORT KLAR")
    print("=" * 40)
    print(f"Matcher i schemat: {len(MATCHER)}")
    print(f"Nya matcher:       {nya}")
    print(f"Redan fanns:       {redan}")
    print(f"Totalt i databasen: {totalt}")
    print("=" * 40)


if __name__ == "__main__":
    importera()
