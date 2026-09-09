import sqlite3
from datetime import datetime


DB = "dif_hockey.db"
SASONG = "2026/27"
LAG = "Djurgården"


def skapa_tabell(conn):

    conn.execute("""
        CREATE TABLE IF NOT EXISTS roster_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT NOT NULL,
            team TEXT NOT NULL,
            player TEXT NOT NULL,
            change_type TEXT NOT NULL,
            change_date TEXT NOT NULL,
            source TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(
                season,
                team,
                player,
                change_type,
                change_date
            )
        )
    """)

    conn.commit()


def hamta_aktiva(conn, datum):

    return {
        rad[0]
        for rad in conn.execute("""
            SELECT player
            FROM roster_history
            WHERE season = ?
              AND team = ?
              AND valid_from <= ?
              AND (
                  valid_to IS NULL
                  OR valid_to >= ?
              )
        """, (
            SASONG,
            LAG,
            datum,
            datum
        )).fetchall()
    }


def hamta_datum(conn):

    rader = conn.execute("""
        SELECT DISTINCT valid_from
        FROM roster_history
        WHERE season = ?
          AND team = ?
        ORDER BY valid_from
    """, (
        SASONG,
        LAG
    )).fetchall()

    return [
        rad[0]
        for rad in rader
    ]


def registrera_forandring(
    conn,
    player,
    change_type,
    datum
):

    conn.execute("""
        INSERT OR IGNORE INTO roster_changes (
            season,
            team,
            player,
            change_type,
            change_date,
            source,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        SASONG,
        LAG,
        player,
        change_type,
        datum,
        "DIF trupphistorik",
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))


def jamfor_datum(
    conn,
    tidigare,
    senare
):

    före = hamta_aktiva(
        conn,
        tidigare
    )

    efter = hamta_aktiva(
        conn,
        senare
    )

    tillkomna = efter - före
    borttagna = före - efter

    return tillkomna, borttagna


def analysera(conn):

    datum = hamta_datum(conn)

    if len(datum) < 2:

        print()
        print(
            "Bara ett truppsnapshot finns."
        )

        print(
            "Ingen förändring kan ännu konstateras."
        )

        return

    print()
    print("=" * 70)
    print("TRUPPFÖRÄNDRINGAR")
    print("=" * 70)

    totalt_tillkomna = 0
    totalt_borttagna = 0

    for i in range(1, len(datum)):

        tidigare = datum[i - 1]
        senare = datum[i]

        tillkomna, borttagna = jamfor_datum(
            conn,
            tidigare,
            senare
        )

        print()
        print(
            f"{tidigare} → {senare}"
        )

        if not tillkomna and not borttagna:

            print(
                "  Ingen förändring"
            )

        for player in sorted(tillkomna):

            print(
                f"  + {player}"
            )

            registrera_forandring(
                conn,
                player,
                "tillkommen",
                senare
            )

            totalt_tillkomna += 1

        for player in sorted(borttagna):

            print(
                f"  - {player}"
            )

            registrera_forandring(
                conn,
                player,
                "borttagen",
                senare
            )

            totalt_borttagna += 1

    conn.commit()

    print()
    print("=" * 70)
    print("SAMMANFATTNING")
    print("=" * 70)

    print(
        f"Tillkomna spelare: {totalt_tillkomna}"
    )

    print(
        f"Borttagna spelare: {totalt_borttagna}"
    )


def hitta_claim_datum(
    facebook_time,
    first_seen
):

    for värde in (
        facebook_time,
        first_seen
    ):

        if not värde:
            continue

        text = str(värde)

        if len(text) < 10:
            continue

        datum = text[:10]

        try:

            datetime.strptime(
                datum,
                "%Y-%m-%d"
            )

            return datum

        except ValueError:
            continue

    return None


def visa_claim_relevanta_forandringar(conn):

    claims = conn.execute("""
        SELECT
            c.id,
            c.claim_text,
            co.facebook_time,
            co.first_seen
        FROM claims c
        JOIN comments co
            ON co.id = c.comment_id
        ORDER BY c.id
    """).fetchall()

    print()
    print("=" * 70)
    print("FÖRÄNDRINGAR EFTER CLAIMS")
    print("=" * 70)

    for claim in claims:

        claim_id = claim[0]
        claim_text = claim[1]

        datum = hitta_claim_datum(
            claim[2],
            claim[3]
        )

        print()
        print("-" * 70)
        print(
            f"CLAIM #{claim_id}"
        )

        print(
            f"Påstående: {claim_text}"
        )

        if not datum:

            print(
                "Claim saknar användbart datum."
            )

            continue

        print(
            f"Claimdatum: {datum}"
        )

        förändringar = conn.execute("""
            SELECT
                player,
                change_type,
                change_date
            FROM roster_changes
            WHERE season = ?
              AND team = ?
              AND change_date > ?
            ORDER BY change_date, player
        """, (
            SASONG,
            LAG,
            datum
        )).fetchall()

        if not förändringar:

            print(
                "Inga registrerade truppförändringar "
                "efter claimen."
            )

        else:

            print(
                "Truppförändringar efter claimen:"
            )

            for rad in förändringar:

                if rad[1] == "tillkommen":
                    symbol = "+"
                else:
                    symbol = "-"

                print(
                    f"  {symbol} {rad[0]} "
                    f"({rad[2]})"
                )


def visa_statistik(conn):

    antal = conn.execute("""
        SELECT COUNT(*)
        FROM roster_changes
        WHERE season = ?
          AND team = ?
    """, (
        SASONG,
        LAG
    )).fetchone()[0]

    tillkomna = conn.execute("""
        SELECT COUNT(*)
        FROM roster_changes
        WHERE season = ?
          AND team = ?
          AND change_type = 'tillkommen'
    """, (
        SASONG,
        LAG
    )).fetchone()[0]

    borttagna = conn.execute("""
        SELECT COUNT(*)
        FROM roster_changes
        WHERE season = ?
          AND team = ?
          AND change_type = 'borttagen'
    """, (
        SASONG,
        LAG
    )).fetchone()[0]

    print()
    print("=" * 70)
    print("DATABASSTATUS")
    print("=" * 70)

    print(
        f"Registrerade förändringar: {antal}"
    )

    print(
        f"Tillkomna:                  {tillkomna}"
    )

    print(
        f"Borttagna:                  {borttagna}"
    )


def main():

    print("=" * 70)
    print("DIF – TRUPPFÖRÄNDRINGSMOTOR")
    print("=" * 70)

    conn = sqlite3.connect(DB)

    skapa_tabell(conn)

    analysera(conn)

    visa_claim_relevanta_forandringar(
        conn
    )

    visa_statistik(conn)

    conn.close()

    print()
    print("=" * 70)
    print("KLART")
    print("=" * 70)


if __name__ == "__main__":
    main()
