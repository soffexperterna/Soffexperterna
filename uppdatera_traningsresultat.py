import sqlite3
from datetime import datetime

DB = "dif_hockey.db"

# Försäsongsmatcher som ska hanteras av denna updaterare.
#
# När en match ännu inte har spelats:
#   home_score = None
#   away_score = None
#
# När resultatet är känt fyller vi i siffrorna.

TRANINGSMATCHER = [
    {
        "date": "2026-08-13",
        "home_team": "Djurgården",
        "away_team": "Örebro",
        "home_score": 2,
        "away_score": 3,
    },
    {
        "date": "2026-08-19",
        "home_team": "Djurgården",
        "away_team": "HV71",
        "home_score": 1,
        "away_score": 2,
    },
    {
        "date": "2026-08-27",
        "home_team": "Brynäs",
        "away_team": "Djurgården",
        "home_score": 2,
        "away_score": 1,
    },
    {
        "date": "2026-09-03",
        "home_team": "Djurgården",
        "away_team": "Brynäs",
        "home_score": 4,
        "away_score": 1,
    },
    {
        "date": "2026-09-10",
        "home_team": "Djurgården",
        "away_team": "Malmö Redhawks",
        "home_score": None,
        "away_score": None,
    },
    {
        "date": "2026-09-14",
        "home_team": "HV71",
        "away_team": "Djurgården",
        "home_score": None,
        "away_score": None,
    },
]


def hitta_match(cursor, match):
    cursor.execute(
        """
        SELECT
            id,
            home_score,
            away_score,
            status
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

    return cursor.fetchone()


def uppdatera():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    nya_resultat = 0
    redan_korrekta = 0
    kommande = 0
    saknade = 0

    now = datetime.now().isoformat(timespec="seconds")

    for match in TRANINGSMATCHER:

        db_match = hitta_match(cursor, match)

        # Matchen saknas i databasen
        if db_match is None:

            if (
                match["home_score"] is not None
                and match["away_score"] is not None
            ):
                status = "spelad"
            else:
                status = "kommande"

            cursor.execute(
                """
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match["date"],
                    match["home_team"],
                    match["away_team"],
                    match["home_score"],
                    match["away_score"],
                    status,
                    now,
                    "TRÄNING",
                ),
            )

            print(
                f"NY TRÄNINGSMATCH: "
                f"{match['date']} | "
                f"{match['home_team']} - "
                f"{match['away_team']}"
            )

            continue

        (
            match_id,
            gammal_hemma,
            gammal_borta,
            gammal_status,
        ) = db_match

        # Ingen resultatdata ännu
        if (
            match["home_score"] is None
            or match["away_score"] is None
        ):

            kommande += 1

            if gammal_status != "kommande":
                cursor.execute(
                    """
                    UPDATE matches
                    SET status = 'kommande'
                    WHERE id = ?
                    """,
                    (match_id,),
                )

            continue

        # Resultat finns och matchen är redan korrekt
        if (
            gammal_hemma == match["home_score"]
            and gammal_borta == match["away_score"]
            and gammal_status == "spelad"
        ):
            redan_korrekta += 1
            continue

        # Resultatet har kommit eller ändrats
        cursor.execute(
            """
            UPDATE matches
            SET
                home_score = ?,
                away_score = ?,
                status = 'spelad'
            WHERE id = ?
            """,
            (
                match["home_score"],
                match["away_score"],
                match_id,
            ),
        )

        print(
            f"RESULTAT UPPDATERAT: "
            f"{match['date']} | "
            f"{match['home_team']} "
            f"{match['home_score']}-"
            f"{match['away_score']} "
            f"{match['away_team']}"
        )

        nya_resultat += 1

    conn.commit()

    # Kontrollera DIF:s träningsmatcher
    cursor.execute(
        """
        SELECT
            id,
            match_date,
            home_team,
            away_team,
            home_score,
            away_score,
            status
        FROM matches
        WHERE (
            home_team = 'Djurgården'
            OR away_team = 'Djurgården'
        )
        AND match_date < '2026-09-19'
        ORDER BY match_date
        """
    )

    matcher = cursor.fetchall()

    conn.close()

    print()
    print("=" * 55)
    print("TRÄNINGSRESULTAT KLARA")
    print("=" * 55)
    print(f"Nya resultat:       {nya_resultat}")
    print(f"Redan korrekta:     {redan_korrekta}")
    print(f"Kommande:           {kommande}")
    print(f"Saknade:            {saknade}")
    print()
    print("DIF:S FÖRSÄSONG:")
    
    for row in matcher:
        print(row)


if __name__ == "__main__":
    uppdatera()
