import sqlite3
import subprocess
import sys


DB = "dif_hockey.db"


STEG = [
    ("Spelare", "fyll_dif_spelare.py"),
    ("Matcher", "importera_matcher.py"),
    ("Matchresultat", "uppdatera_matchresultat.py"),
    ("DIF-bevakare", "dif_bevakare.py"),
    ("Kommentarer", "hamta_kommentarer.py"),
    ("Claims", "hitta_claims.py"),
    ("Claim-mål", "fyll_claim_targets.py"),
    ("Claim-regler", "analysera_claim_regler.py"),
    ("Claim-matcher", "koppla_claim_match.py"),
    ("Claim-utvärdering", "utvardera_claims.py"),
]


def kontrollera_databas():
    conn = sqlite3.connect(DB)

    tabeller = {
        "sources",
        "posts",
        "comments",
        "matches",
        "events",
        "player_stats",
        "claims",
        "predictions",
    }

    befintliga = {
        rad[0]
        for rad in conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
        """)
    }

    saknas = tabeller - befintliga

    conn.close()

    if saknas:
        print()
        print("FEL: Följande tabeller saknas:")
        for tabell in sorted(saknas):
            print(f"  - {tabell}")
        return False

    return True


def kör_steg(namn, fil):

    print()
    print("=" * 70)
    print(f"STEG: {namn}")
    print(f"FIL:  {fil}")
    print("=" * 70)

    try:
        resultat = subprocess.run(
            [sys.executable, fil],
            text=True
        )

        if resultat.returncode == 0:
            print()
            print(f"OK: {namn}")
            return True

        print()
        print(
            f"FEL: {namn} avslutades med kod "
            f"{resultat.returncode}"
        )

        return False

    except FileNotFoundError:

        print()
        print(f"FEL: Filen finns inte: {fil}")
        return False

    except Exception as e:

        print()
        print(f"FEL i {namn}: {e}")
        return False


def statistik():

    conn = sqlite3.connect(DB)

    print()
    print("=" * 70)
    print("DATABASSTATUS")
    print("=" * 70)

    tabeller = [
        ("sources", "Källor"),
        ("posts", "Inlägg"),
        ("comments", "Kommentarer"),
        ("matches", "Matcher"),
        ("events", "Händelser"),
        ("player_stats", "Spelarstatistik"),
        ("claims", "Claims"),
        ("predictions", "Predictions"),
    ]

    for tabell, namn in tabeller:

        try:
            antal = conn.execute(
                f"SELECT COUNT(*) FROM {tabell}"
            ).fetchone()[0]

            print(
                f"{namn:<20} {antal}"
            )

        except sqlite3.Error:
            print(
                f"{namn:<20} saknas"
            )

    print()

    claims = conn.execute("""
        SELECT verdict, COUNT(*)
        FROM claims
        GROUP BY verdict
    """).fetchall()

    print("CLAIMS")

    resultat = {
        "RÄTT": 0,
        "FEL": 0,
        "OKLART": 0
    }

    for verdict, antal in claims:

        if verdict in resultat:
            resultat[verdict] = antal

    print(
        f"  RÄTT:   {resultat['RÄTT']}"
    )

    print(
        f"  FEL:    {resultat['FEL']}"
    )

    print(
        f"  OKLART: {resultat['OKLART']}"
    )

    conn.close()


def main():

    print()
    print("=" * 70)
    print("DIF KOMMENTARSBEVAKARE")
    print("HELA PIPELINEN")
    print("=" * 70)

    if not kontrollera_databas():

        print()
        print("Backend stoppad.")
        return 1

    lyckade = 0
    misslyckade = 0

    for namn, fil in STEG:

        if kör_steg(namn, fil):
            lyckade += 1
        else:
            misslyckade += 1

    statistik()

    print()
    print("=" * 70)
    print("BACKEND KLAR")
    print("=" * 70)

    print(
        f"Lyckade steg:    {lyckade}"
    )

    print(
        f"Misslyckade steg: {misslyckade}"
    )

    if misslyckade == 0:

        print()
        print("ALLT KLART – 10/10 STEG LYCKADES")

        return 0

    print()
    print("VARNING – minst ett steg misslyckades.")

    return 1


if __name__ == "__main__":
    sys.exit(main())
