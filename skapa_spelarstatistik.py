import sqlite3
import requests
import re
import unicodedata
from bs4 import BeautifulSoup
from datetime import datetime


DB = "dif_hockey.db"
SEASON = "2026/27"
TEAM = "Djurgården"

URL = "https://stats.swehockey.se/Players/Statistics/PlayersByTeam/21138"


def namnnyckel(namn):
    """
    Gör om namn till en normaliserad nyckel.

    Exempel:
        Jacob Josefson
        Josefson, Jacob

    blir samma nyckel.
    """

    if not namn:
        return ()

    namn = str(namn).replace("**", "").strip().lower()

    # Ta bort accenter
    namn = unicodedata.normalize("NFKD", namn)
    namn = "".join(
        tecken
        for tecken in namn
        if not unicodedata.combining(tecken)
    )

    # Bara bokstäver
    namn = re.sub(r"[^a-z\s]", " ", namn)

    ord_lista = namn.split()

    return tuple(sorted(ord_lista))


def skapa_tabell(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT NOT NULL,
            player TEXT NOT NULL,
            team TEXT NOT NULL,
            games_played INTEGER,
            goals INTEGER,
            assists INTEGER,
            points INTEGER,
            plus_minus INTEGER,
            penalty_minutes INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(season, player, team)
        )
    """)

    conn.commit()


def aliasnyckel(namn):
    """
    Hanterar namn där Swehockey och vår gamla data använder
    olika förnamnsformer.

    Exempel:
        Joe Snively
        Snively, Joseph
    """

    key = namnnyckel(namn)

    if key == tuple(sorted(["joe", "snively"])):
        return tuple(sorted(["joseph", "snively"]))

    return key


def hamta_statistik():
    print("=" * 70)
    print("DJURGÅRDEN – SPELARSTATISTIK")
    print("=" * 70)
    print()
    print("Källa:")
    print(URL)
    print()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "Chrome/126.0 Safari/537.36"
        )
    }

    response = requests.get(
        URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    tabeller = soup.find_all("table")

    if not tabeller:
        raise RuntimeError(
            "Ingen statistiktabell hittades på sidan."
        )

    hittade = []

    for table in tabeller:

        headers_row = table.find("tr")

        if not headers_row:
            continue

        headers_text = [
            cell.get_text(" ", strip=True)
            for cell in headers_row.find_all(["th", "td"])
        ]

        headers_norm = [
            text.upper()
            for text in headers_text
        ]

        krav = [
            "NAME",
            "TEAM",
            "GP",
            "G",
            "A",
            "TP",
            "PIM"
        ]

        if not all(
            krav_header in headers_norm
            for krav_header in krav
        ):
            continue

        index = {
            namn: headers_norm.index(namn)
            for namn in krav
        }

        rows = table.find_all("tr")

        for row in rows[1:]:

            cells = row.find_all(["td", "th"])

            if not cells:
                continue

            values = [
                cell.get_text(" ", strip=True)
                for cell in cells
            ]

            if len(values) <= max(index.values()):
                continue

            player = values[index["NAME"]].strip()
            team = values[index["TEAM"]].strip()

            if not player:
                continue

            if "djurgården" not in team.lower():
                continue

            def heltal(kolumn):
                try:
                    return int(values[index[kolumn]])
                except (ValueError, TypeError):
                    return 0

            games_played = heltal("GP")
            goals = heltal("G")
            assists = heltal("A")
            points = heltal("TP")
            penalty_minutes = heltal("PIM")

            hittade.append({
                "player": player.replace("**", "").strip(),
                "team": TEAM,
                "games_played": games_played,
                "goals": goals,
                "assists": assists,
                "points": points,
                "penalty_minutes": penalty_minutes
            })

    # Ta bort eventuella dubbla rader från själva källan.
    unika = {}

    for row in hittade:
        key = aliasnyckel(row["player"])
        unika[key] = row

    return list(unika.values())


def hitta_befintliga_spelare(conn, namn):
    """
    Hittar alla befintliga poster som representerar samma spelare.

    Matchar både:
        Jacob Josefson
        Josefson, Jacob

    samt:
        Joe Snively
        Snively, Joseph
    """

    key = aliasnyckel(namn)

    rows = conn.execute("""
        SELECT *
        FROM player_stats
        WHERE season = ?
          AND team = ?
        ORDER BY id
    """, (
        SEASON,
        TEAM
    )).fetchall()

    resultat = []

    for row in rows:
        if aliasnyckel(row["player"]) == key:
            resultat.append(row)

    return resultat


def spara_statistik(conn, statistik):

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    nya = 0
    uppdaterade = 0
    sammanslagna = 0

    for row in statistik:

        befintliga = hitta_befintliga_spelare(
            conn,
            row["player"]
        )

        if befintliga:

            # Behåll den senaste posten.
            behall = max(
                befintliga,
                key=lambda x: x["id"]
            )

            conn.execute("""
                UPDATE player_stats
                SET player=?,
                    games_played=?,
                    goals=?,
                    assists=?,
                    points=?,
                    penalty_minutes=?,
                    updated_at=?
                WHERE id=?
            """, (
                row["player"],
                row["games_played"],
                row["goals"],
                row["assists"],
                row["points"],
                row["penalty_minutes"],
                now,
                behall["id"]
            ))

            uppdaterade += 1

            # Om det fortfarande finns gamla dubbletter,
            # ta bort dem efter att rätt post valts.
            for duplicate in befintliga:

                if duplicate["id"] == behall["id"]:
                    continue

                conn.execute("""
                    DELETE FROM player_stats
                    WHERE id=?
                """, (
                    duplicate["id"],
                ))

                sammanslagna += 1

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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                SEASON,
                row["player"],
                TEAM,
                row["games_played"],
                row["goals"],
                row["assists"],
                row["points"],
                None,
                row["penalty_minutes"],
                now,
                now
            ))

            nya += 1

    conn.commit()

    return nya, uppdaterade, sammanslagna


def main():

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    try:

        skapa_tabell(conn)

        statistik = hamta_statistik()

        print(
            f"DJURGÅRDEN-SPELARE HITTADES: {len(statistik)}"
        )
        print()

        if not statistik:
            print(
                "Ingen Djurgårdsstatistik hittades."
            )
            return

        nya, uppdaterade, sammanslagna = (
            spara_statistik(
                conn,
                statistik
            )
        )

        print(f"Nya spelare:       {nya}")
        print(f"Uppdaterade:       {uppdaterade}")
        print(f"Dubbletter ihop:   {sammanslagna}")
        print()

        print("STATISTIK:")
        print("-" * 70)

        for row in sorted(
            statistik,
            key=lambda x: (
                -x["points"],
                x["player"]
            )
        ):
            print(
                f"{row['player']:25} "
                f"GP {row['games_played']:2} | "
                f"G {row['goals']:2} | "
                f"A {row['assists']:2} | "
                f"TP {row['points']:2} | "
                f"PIM {row['penalty_minutes']:2}"
            )

        print()
        print("=" * 70)
        print("SPELARSTATISTIK KLAR")
        print("=" * 70)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
