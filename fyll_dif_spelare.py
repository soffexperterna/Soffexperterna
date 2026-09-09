import sqlite3
from datetime import datetime


DB = "dif_hockey.db"

SASONG = "2026/27"
LAG = "Djurgården"


# ============================================================
# AKTUELL DIF-TRUPP 2026/27
#
# VIKTIGT:
# Den här listan används som vårt aktuella spelarregister.
#
# Statistik hämtas INTE från DIF:s gamla statsida här.
# Alla statistikvärden sätts till 0 tills vi har en säker
# officiell 2026/27-källa.
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


def nu():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def skapa_tabell(conn):

    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT NOT NULL,
            player TEXT NOT NULL,
            team TEXT NOT NULL,
            games_played INTEGER DEFAULT 0,
            goals INTEGER DEFAULT 0,
            assists INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            plus_minus INTEGER DEFAULT 0,
            penalty_minutes INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(season, player, team)
        )
    """)

    conn.commit()


def rensa_felaktig_statistik(conn):

    """
    Nollställer all statistik för 2026/27.

    Detta är viktigt eftersom databasen tidigare innehöll
    siffror från en äldre säsong som felaktigt hade kopplats
    till 2026/27.
    """

    conn.execute("""
        UPDATE player_stats
        SET
            games_played = 0,
            goals = 0,
            assists = 0,
            points = 0,
            plus_minus = 0,
            penalty_minutes = 0,
            updated_at = ?
        WHERE season = ?
          AND team = ?
    """, (
        nu(),
        SASONG,
        LAG
    ))

    conn.commit()


def skapa_eller_uppdatera_spelare(conn):

    tid = nu()

    nya = 0
    befintliga = 0

    for spelare in SPELARE:

        rad = conn.execute("""
            SELECT id
            FROM player_stats
            WHERE season = ?
              AND player = ?
              AND team = ?
        """, (
            SASONG,
            spelare,
            LAG
        )).fetchone()

        if rad:

            conn.execute("""
                UPDATE player_stats
                SET
                    games_played = 0,
                    goals = 0,
                    assists = 0,
                    points = 0,
                    plus_minus = 0,
                    penalty_minutes = 0,
                    updated_at = ?
                WHERE id = ?
            """, (
                tid,
                rad[0]
            ))

            befintliga += 1

        else:

            conn.execute("""
                INSERT INTO player_stats (
                    season,
                    player,
                    team,
                    games_played,
                    goals,
                    assists,
                    points,
                    plus_minus,
                    penalty_minutes,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?,
                    0, 0, 0, 0, 0, 0,
                    ?, ?
                )
            """, (
                SASONG,
                spelare,
                LAG,
                tid,
                tid
            ))

            nya += 1

    conn.commit()

    return nya, befintliga


def ta_bort_spelare_som_inte_ar_i_truppen(conn):

    """
    Tar bort gamla spelare från just 2026/27-registret.

    Historiska säsonger påverkas inte.
    """

    placeholders = ",".join(
        "?" for _ in SPELARE
    )

    conn.execute(
        f"""
        DELETE FROM player_stats
        WHERE season = ?
          AND team = ?
          AND player NOT IN ({placeholders})
        """,
        (
            SASONG,
            LAG,
            *SPELARE
        )
    )

    conn.commit()


def visa_spelare(conn):

    rader = conn.execute("""
        SELECT
            player,
            games_played,
            goals,
            assists,
            points,
            plus_minus,
            penalty_minutes
        FROM player_stats
        WHERE season = ?
          AND team = ?
        ORDER BY player
    """, (
        SASONG,
        LAG
    )).fetchall()

    print()
    print("=" * 70)
    print(f"DIF-SPELARE {SASONG}")
    print("=" * 70)

    for rad in rader:

        print(
            f"{rad[0]:<25} "
            f"GP {rad[1]:>2}  "
            f"G {rad[2]:>2}  "
            f"A {rad[3]:>2}  "
            f"P {rad[4]:>2}  "
            f"+/- {rad[5]:>3}  "
            f"Utv {rad[6]:>3}"
        )

    print()
    print(
        f"Totalt: {len(rader)} spelare"
    )

    statistikfel = conn.execute("""
        SELECT COUNT(*)
        FROM player_stats
        WHERE season = ?
          AND team = ?
          AND (
              games_played != 0
              OR goals != 0
              OR assists != 0
              OR points != 0
              OR plus_minus != 0
              OR penalty_minutes != 0
          )
    """, (
        SASONG,
        LAG
    )).fetchone()[0]

    print(
        f"Spelare med statistik: {statistikfel}"
    )


def kontrollera(conn):

    antal = conn.execute("""
        SELECT COUNT(*)
        FROM player_stats
        WHERE season = ?
          AND team = ?
    """, (
        SASONG,
        LAG
    )).fetchone()[0]

    fel = conn.execute("""
        SELECT COUNT(*)
        FROM player_stats
        WHERE season = ?
          AND team = ?
          AND (
              games_played != 0
              OR goals != 0
              OR assists != 0
              OR points != 0
              OR plus_minus != 0
              OR penalty_minutes != 0
          )
    """, (
        SASONG,
        LAG
    )).fetchone()[0]

    print()
    print("=" * 70)
    print("KONTROLL")
    print("=" * 70)

    print(
        f"Förväntade spelare: {len(SPELARE)}"
    )

    print(
        f"Spelare i databasen: {antal}"
    )

    print(
        f"Felaktiga statistikrader: {fel}"
    )

    if antal != len(SPELARE):

        print()
        print(
            "VARNING: Antalet spelare stämmer inte!"
        )

        return False

    if fel != 0:

        print()
        print(
            "VARNING: Någon spelare har fortfarande "
            "icke-noll statistik!"
        )

        return False

    print()
    print(
        "OK: 2026/27-registret är rent."
    )

    return True


def main():

    print("=" * 70)
    print("DIF SPELARREGISTER")
    print("=" * 70)

    print(
        f"Säsong: {SASONG}"
    )

    print(
        f"Spelare i whitelist: {len(SPELARE)}"
    )

    print()
    print(
        "VIKTIGT: Ingen historisk spelarstatistik importeras."
    )

    conn = sqlite3.connect(DB)

    skapa_tabell(conn)

    print()
    print(
        "Nollställer eventuell felaktig 2026/27-statistik..."
    )

    rensa_felaktig_statistik(conn)

    ta_bort_spelare_som_inte_ar_i_truppen(conn)

    nya, befintliga = skapa_eller_uppdatera_spelare(
        conn
    )

    print()
    print("=" * 70)
    print("DATABAS UPPDATERAD")
    print("=" * 70)

    print(
        f"Nya spelare:        {nya}"
    )

    print(
        f"Redan registrerade:  {befintliga}"
    )

    visa_spelare(conn)

    ok = kontrollera(conn)

    conn.close()

    print()
    print("=" * 70)

    if ok:
        print(
            "KLART – 2026/27 ÄR NOLLSTÄLLD OCH REN"
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
