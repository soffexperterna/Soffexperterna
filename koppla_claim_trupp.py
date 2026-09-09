import sqlite3
from datetime import datetime


DB = "dif_hockey.db"


def skapa_tabell(conn):

    conn.execute("""
        CREATE TABLE IF NOT EXISTS claim_roster_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id INTEGER NOT NULL,
            player TEXT NOT NULL,
            roster_status TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(claim_id, player),
            FOREIGN KEY(claim_id) REFERENCES claims(id)
        )
    """)

    conn.commit()


def hamta_claimar(conn):

    return conn.execute("""
        SELECT
            c.id,
            c.comment_id,
            c.claim_text,
            c.season,
            co.facebook_time,
            co.first_seen
        FROM claims c
        JOIN comments co
            ON co.id = c.comment_id
        ORDER BY c.id
    """).fetchall()


def hamta_trupp_vid_tidpunkt(conn, datum):

    return conn.execute("""
        SELECT
            player,
            status,
            valid_from,
            valid_to
        FROM roster_history
        WHERE season = '2026/27'
          AND team = 'Djurgården'
          AND valid_from <= ?
          AND (
              valid_to IS NULL
              OR valid_to >= ?
          )
        ORDER BY player
    """, (
        datum,
        datum
    )).fetchall()


def hitta_claim_datum(facebook_time, first_seen):

    if facebook_time:
        text = str(facebook_time)

        if len(text) >= 10:

            datum = text[:10]

            try:
                datetime.strptime(
                    datum,
                    "%Y-%m-%d"
                )

                return datum

            except ValueError:
                pass

    if first_seen:
        text = str(first_seen)

        if len(text) >= 10:

            datum = text[:10]

            try:
                datetime.strptime(
                    datum,
                    "%Y-%m-%d"
                )

                return datum

            except ValueError:
                pass

    return None


def koppla_claim(conn, claim):

    (
        claim_id,
        comment_id,
        claim_text,
        season,
        facebook_time,
        first_seen
    ) = claim

    datum = hitta_claim_datum(
        facebook_time,
        first_seen
    )

    if not datum:

        return 0, "saknar datum"

    trupp = hamta_trupp_vid_tidpunkt(
        conn,
        datum
    )

    if not trupp:

        return 0, "ingen trupp hittades"

    antal = 0

    for player, status, valid_from, valid_to in trupp:

        conn.execute("""
            INSERT OR IGNORE INTO claim_roster_snapshot (
                claim_id,
                player,
                roster_status,
                valid_from,
                valid_to,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            claim_id,
            player,
            status,
            valid_from,
            valid_to,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))

        antal += 1

    return antal, datum


def visa_claim(conn, claim_id, claim_text):

    rader = conn.execute("""
        SELECT
            player,
            roster_status,
            valid_from,
            valid_to
        FROM claim_roster_snapshot
        WHERE claim_id = ?
        ORDER BY player
    """, (
        claim_id,
    )).fetchall()

    print()
    print("-" * 70)
    print(f"CLAIM #{claim_id}")
    print("-" * 70)
    print(f"Påstående: {claim_text}")
    print(
        f"Truppspelare sparade: {len(rader)}"
    )

    if rader:

        print()

        for rad in rader:

            print(
                f"  {rad[0]:<25} "
                f"{rad[1]:<8} "
                f"från {rad[2]}"
            )


def main():

    print("=" * 70)
    print("DIF – KOPPLAR CLAIMS TILL TRUPP")
    print("=" * 70)

    conn = sqlite3.connect(DB)

    skapa_tabell(conn)

    claims = hamta_claimar(conn)

    print()
    print(
        f"Claims att behandla: {len(claims)}"
    )

    lyckade = 0
    misslyckade = 0

    for claim in claims:

        antal, resultat = koppla_claim(
            conn,
            claim
        )

        if antal > 0:

            lyckade += 1

            print(
                f"CLAIM {claim[0]} "
                f"→ {antal} spelare "
                f"({resultat})"
            )

        else:

            misslyckade += 1

            print(
                f"CLAIM {claim[0]} "
                f"→ {resultat}"
            )

    conn.commit()

    print()
    print("=" * 70)
    print("KOPPLING KLAR")
    print("=" * 70)

    print(
        f"Lyckade:      {lyckade}"
    )

    print(
        f"Utan koppling: {misslyckade}"
    )

    print()

    for claim in claims:

        visa_claim(
            conn,
            claim[0],
            claim[2]
        )

    conn.close()

    print()
    print("=" * 70)
    print("KLART")
    print("=" * 70)


if __name__ == "__main__":
    main()
