import sqlite3
from datetime import datetime


DB = "dif_hockey.db"

SASONG = "2026/27"
LAG = "Djurgården"


# ============================================================
# AKTUELL DIF-TRUPP
# ============================================================

SPELARE = [
    "Magnus Hellberg",
    "Daniel Marmenlind",
    "Nikolas Brouillard",
    "Lucas Carlsson",
    "Gustav Lindström",
    "Jesper Pettersson",
    "Hugo Blixt",
    "Philip Holm",
    "Liam Pettersson",
    "Colby Sissons",
    "Joe Snively",
    "Noel Gunler",
    "Henrik Eriksson",
    "Emilio Pettersen",
    "Håvard Salsten",
    "Marcus Krüger",
    "Jacob Josefson",
    "Theo Stockselius",
    "Lukas Vejdemo",
    "Albin Grewe",
    "David Blomgren",
    "Charles Hudon",
    "Nils Åman",
    "Sebastian Hartmann",
]


# ============================================================
# DATUM
# ============================================================

def nu():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def dagens_datum():
    return datetime.now().strftime(
        "%Y-%m-%d"
    )


# ============================================================
# SKAPA TABELL
# ============================================================

def skapa_tabell(conn):

    conn.execute("""
        CREATE TABLE IF NOT EXISTS roster_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT NOT NULL,
            team TEXT NOT NULL,
            player TEXT NOT NULL,
            status TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            source TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(season, team, player, valid_from)
        )
    """)

    conn.commit()


# ============================================================
# STÄNG GAMLA POSTER
# ============================================================

def stang_spelare_som_inte_langre_finns(
    conn,
    aktuella
):

    idag = dagens_datum()

    rader = conn.execute("""
        SELECT
            id,
            player,
            valid_from
        FROM roster_history
        WHERE season = ?
          AND team = ?
          AND valid_to IS NULL
    """, (
        SASONG,
        LAG
    )).fetchall()

    stangda = 0

    for rad in rader:

        player = rad[1]

        if player not in aktuella:

            conn.execute("""
                UPDATE roster_history
                SET
                    valid_to = ?
                WHERE id = ?
            """, (
                idag,
                rad[0]
            ))

            stangda += 1

    conn.commit()

    return stangda


# ============================================================
# LÄGG TILL NYA SPELARE
# ============================================================

def lagg_till_nya_spelare(
    conn,
    aktuella
):

    idag = dagens_datum()
    tid = nu()

    nya = 0
    redan = 0

    for player in aktuella:

        rad = conn.execute("""
            SELECT
                id
            FROM roster_history
            WHERE season = ?
              AND team = ?
              AND player = ?
              AND valid_to IS NULL
            LIMIT 1
        """, (
            SASONG,
            LAG,
            player
        )).fetchone()

        if rad:

            redan += 1
            continue

        conn.execute("""
            INSERT INTO roster_history (
                season,
                team,
                player,
                status,
                valid_from,
                valid_to,
                source,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
        """, (
            SASONG,
            LAG,
            player,
            "aktiv",
            idag,
            "DIF:s aktuella spelarregister",
            tid
        ))

        nya += 1

    conn.commit()

    return nya, redan


# ============================================================
# VISA AKTUELL TRUPP
# ============================================================

def visa_aktuell_trupp(conn):

    rader = conn.execute("""
        SELECT
            player,
            valid_from,
            valid_to,
            status
        FROM roster_history
        WHERE season = ?
          AND team = ?
          AND valid_to IS NULL
        ORDER BY player
    """, (
        SASONG,
        LAG
    )).fetchall()

    print()
    print("=" * 70)
    print(f"AKTUELL TRUPP – {SASONG}")
    print("=" * 70)

    for rad in rader:

        print(
            f"{rad[0]:<25} "
            f"från {rad[1]}  "
            f"{rad[3]}"
        )

    print()
    print(
        f"Aktiva spelare: {len(rader)}"
    )


# ============================================================
# VISA HISTORIK
# ============================================================

def visa_historik(conn):

    rader = conn.execute("""
        SELECT
            player,
            valid_from,
            valid_to,
            status
        FROM roster_history
        WHERE season = ?
          AND team = ?
        ORDER BY valid_from, player
    """, (
        SASONG,
        LAG
    )).fetchall()

    print()
    print("=" * 70)
    print("TRUPPHISTORIK")
    print("=" * 70)

    if not rader:

        print("Ingen historik ännu.")
        return

    for rad in rader:

        slut = rad[2] if rad[2] else "pågående"

        print(
            f"{rad[0]:<25} "
            f"{rad[1]} → {slut}  "
            f"{rad[3]}"
        )


# ============================================================
# KONTROLL
# ============================================================

def kontrollera(conn):

    antal = conn.execute("""
        SELECT COUNT(*)
        FROM roster_history
        WHERE season = ?
          AND team = ?
          AND valid_to IS NULL
    """, (
        SASONG,
        LAG
    )).fetchone()[0]

    print()
    print("=" * 70)
    print("KONTROLL")
    print("=" * 70)

    print(
        f"Förväntade aktiva spelare: {len(SPELARE)}"
    )

    print(
        f"Aktiva i historiken:       {antal}"
    )

    if antal != len(SPELARE):

        print()
        print(
            "VARNING: Truppantalet stämmer inte."
        )

        return False

    print()
    print(
        "OK: Trupphistoriken stämmer."
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("DIF – TRUPPHISTORIK")
    print("=" * 70)

    print(
        f"Säsong: {SASONG}"
    )

    print(
        f"Spelare i aktuell trupp: {len(SPELARE)}"
    )

    conn = sqlite3.connect(DB)

    skapa_tabell(conn)

    stangda = stang_spelare_som_inte_langre_finns(
        conn,
        SPELARE
    )

    nya, redan = lagg_till_nya_spelare(
        conn,
        SPELARE
    )

    print()
    print("=" * 70)
    print("SNAPSHOT SPARAD")
    print("=" * 70)

    print(
        f"Nya spelare:        {nya}"
    )

    print(
        f"Redan aktiva:       {redan}"
    )

    print(
        f"Avslutade poster:   {stangda}"
    )

    visa_aktuell_trupp(conn)

    visa_historik(conn)

    ok = kontrollera(conn)

    conn.close()

    print()
    print("=" * 70)

    if ok:

        print(
            "KLART – TRUPPHISTORIKEN ÄR AKTIV"
        )

        return 0

    print(
        "FEL – KONTROLLEN MISSLYCKADES"
    )

    return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
