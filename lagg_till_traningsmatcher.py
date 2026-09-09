import sqlite3
from datetime import datetime

DB = "dif_hockey.db"

TRANINGSMATCHER = [
    {
        "date": "2026-08-13",
        "home_team": "Djurgården",
        "away_team": "Örebro",
        "home_score": 2,
        "away_score": 3,
        "status": "spelad",
    },
    {
        "date": "2026-08-19",
        "home_team": "Djurgården",
        "away_team": "HV71",
        "home_score": 1,
        "away_score": 2,
        "status": "spelad",
    },
    {
        "date": "2026-08-27",
        "home_team": "Brynäs",
        "away_team": "Djurgården",
        "home_score": 2,
        "away_score": 1,
        "status": "spelad",
    },
    {
        "date": "2026-09-03",
        "home_team": "Djurgården",
        "away_team": "Brynäs",
        "home_score": 4,
        "away_score": 1,
        "status": "spelad",
    },
    {
        "date": "2026-09-10",
        "home_team": "Djurgården",
        "away_team": "Malmö Redhawks",
        "home_score": None,
        "away_score": None,
        "status": "kommande",
    },
    {
        "date": "2026-09-14",
        "home_team": "HV71",
        "away_team": "Djurgården",
        "home_score": None,
        "away_score": None,
        "status": "kommande",
    },
]


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    nya = 0
    uppdaterade = 0
    redan = 0

    for match in TRANINGSMATCHER:
        cur.execute(
            """
            SELECT id, home_score, away_score, status
            FROM matches
            WHERE match_date = ?
              AND home_team = ?
              AND away_team = ?
            """,
            (
                match["date"],
                match["home_team"],
                match["away_team"],
            ),
        )

        row = cur.fetchone()

        if row is None:
            cur.execute(
                """
                INSERT INTO matches
                (
                    match_date,
                    home_team,
                    away_team,
                    home_score,
                    away_score,
                    status,
                    created_at,
                    match_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match["date"],
                    match["home_team"],
                    match["away_team"],
                    match["home_score"],
                    match["away_score"],
                    match["status"],
                    created_at,
                    "TRÄNING",
                ),
            )

            if match["home_score"] is None:
                resultat = "kommande"
            else:
                resultat = f"{match['home_score']}-{match['away_score']}"

            print(
                f"NY TRÄNINGSMATCH: "
                f"{match['date']} | "
                f"{match['home_team']} - {match['away_team']} | "
                f"{resultat}"
            )

            nya += 1
            continue

        match_id, old_home, old_away, old_status = row

        if (
            old_home != match["home_score"]
            or old_away != match["away_score"]
            or old_status != match["status"]
        ):
            cur.execute(
                """
                UPDATE matches
                SET home_score = ?,
                    away_score = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    match["home_score"],
                    match["away_score"],
                    match["status"],
                    match_id,
                ),
            )

            print(
                f"UPPDATERAD: "
                f"{match['date']} | "
                f"{match['home_team']} - {match['away_team']}"
            )

            uppdaterade += 1
        else:
            redan += 1

    conn.commit()

    print()
    print("TRÄNINGSMATCHER KLARA")
    print(f"Nya: {nya}")
    print(f"Uppdaterade: {uppdaterade}")
    print(f"Redan korrekta: {redan}")

    cur.execute(
        """
        SELECT id, match_date, home_team, away_team,
               home_score, away_score, status
        FROM matches
        WHERE home_team = 'Djurgården'
           OR away_team = 'Djurgården'
        ORDER BY match_date
        """
    )

    print()
    print("DIF-MATCHER:")

    for row in cur.fetchall():
        print(row)

    conn.close()


if __name__ == "__main__":
    main()
