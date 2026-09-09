import sqlite3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

DB = "dif_hockey.db"

URL = "https://stats.swehockey.se/ScheduleAndResults/Schedule/20961"


LAG = [
    "Brynäs IF",
    "Djurgårdens IF",
    "Färjestad BK",
    "Frölunda HC",
    "HV 71",
    "IF Björklöven",
    "IF Malmö Redhawks",
    "Linköping HC",
    "Luleå HF",
    "Rögle BK",
    "Skellefteå AIK",
    "Timrå IK",
    "Växjö Lakers HC",
    "Örebro HK",
]


def hamta_sida():
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(
        URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    return response.text


def normalisera_lag(namn):
    namn = namn.strip().replace("\xa0", " ")

    ersatt = {
        "Djurgårdens IF": "Djurgården",
        "Färjestad BK": "Färjestads BK",
        "IF Malmö Redhawks": "Malmö Redhawks",
        "Linköping HC": "Linköpings HC",
        "HV 71": "HV71",
    }

    return ersatt.get(namn, namn)


def hitta_resultat(text):
    match = re.search(
        r"(?<!\d)(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d)",
        text
    )

    if not match:
        return None

    return (
        int(match.group(1)),
        int(match.group(2))
    )


def hitta_lagpar(text):
    for hemma in LAG:
        for borta in LAG:

            if hemma == borta:
                continue

            monster = (
                re.escape(hemma)
                + r"\s*-\s*"
                + re.escape(borta)
            )

            match = re.search(
                monster,
                text
            )

            if match:
                return (
                    hemma,
                    borta,
                    match.start(),
                    match.end()
                )

    return None


def dela_upp_matcher(text):

    text = text.replace("\xa0", " ")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    matcher = []

    datum_matcher = list(
        re.finditer(
            r"20\d{2}-\d{2}-\d{2}",
            text
        )
    )

    for datum_index, datum_match in enumerate(
        datum_matcher
    ):

        datum = datum_match.group(0)

        start = datum_match.end()

        if datum_index + 1 < len(datum_matcher):
            slut = datum_matcher[
                datum_index + 1
            ].start()
        else:
            slut = len(text)

        block = text[start:slut].strip()

        tider = list(
            re.finditer(
                r"\d{1,2}:\d{2}",
                block
            )
        )

        for tid_index, tid_match in enumerate(tider):

            tid = tid_match.group(0)

            match_start = tid_match.end()

            if tid_index + 1 < len(tider):
                match_slut = tider[
                    tid_index + 1
                ].start()
            else:
                match_slut = len(block)

            match_text = block[
                match_start:match_slut
            ].strip()

            lagpar = hitta_lagpar(
                match_text
            )

            if not lagpar:
                continue

            hemma, borta, _, lag_slut = lagpar

            resten = match_text[
                lag_slut:
            ].strip()

            resultat = hitta_resultat(
                resten
            )

            matcher.append({
                "date": datum,
                "time": tid,
                "home_team": normalisera_lag(hemma),
                "away_team": normalisera_lag(borta),
                "home_score": (
                    resultat[0]
                    if resultat
                    else None
                ),
                "away_score": (
                    resultat[1]
                    if resultat
                    else None
                ),
            })

    return matcher


def hitta_matcher(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    tabell = soup.find("table")

    if not tabell:
        return []

    text = tabell.get_text(
        " ",
        strip=True
    )

    matcher = dela_upp_matcher(text)

    unika = {}

    for match in matcher:

        nyckel = (
            match["date"],
            match["home_team"],
            match["away_team"]
        )

        unika[nyckel] = match

    return list(
        unika.values()
    )


def hitta_db_match(
    cursor,
    datum,
    hemma,
    borta
):

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
            datum,
            hemma,
            borta
        )
    )

    return cursor.fetchone()


def uppdatera_databas(matcher):

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    nya_matcher = 0
    nya_resultat = 0
    redan = 0
    kommande = 0

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    for match in matcher:

        datum = match["date"]
        hemma = match["home_team"]
        borta = match["away_team"]

        db_match = hitta_db_match(
            cursor,
            datum,
            hemma,
            borta
        )

        # MATCHEN FINNS INTE
        if not db_match:

            status = (
                "spelad"
                if (
                    match["home_score"] is not None
                    and
                    match["away_score"] is not None
                )
                else "kommande"
            )

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
                    datum,
                    hemma,
                    borta,
                    match["home_score"],
                    match["away_score"],
                    status,
                    now,
                    "SHL"
                )
            )

            nya_matcher += 1

            if status == "spelad":
                print(
                    f"NY MATCH + RESULTAT: "
                    f"{datum} | "
                    f"{hemma} "
                    f"{match['home_score']}-"
                    f"{match['away_score']} "
                    f"{borta}"
                )
            else:
                print(
                    f"NY MATCH: "
                    f"{datum} | "
                    f"{hemma} - {borta}"
                )

            continue

        (
            match_id,
            gammal_hemma,
            gammal_borta,
            gammal_status
        ) = db_match

        # KOMMANDE MATCH
        if (
            match["home_score"] is None
            or match["away_score"] is None
        ):

            if gammal_status == "kommande":
                redan += 1
            else:
                cursor.execute(
                    """
                    UPDATE matches
                    SET status = 'kommande'
                    WHERE id = ?
                    """,
                    (match_id,)
                )

            kommande += 1

            continue

        # RESULTAT FINNS
        ny_hemma = match["home_score"]
        ny_borta = match["away_score"]

        if (
            gammal_hemma == ny_hemma
            and gammal_borta == ny_borta
            and gammal_status == "spelad"
        ):

            redan += 1

            continue

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
                ny_hemma,
                ny_borta,
                match_id
            )
        )

        print(
            f"RESULTAT: "
            f"{datum} | "
            f"{hemma} "
            f"{ny_hemma}-"
            f"{ny_borta} "
            f"{borta}"
        )

        nya_resultat += 1

    conn.commit()

    # Statistik från hela databasen
    cursor.execute(
        "SELECT COUNT(*) FROM matches"
    )
    totalt = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM matches
        WHERE status = 'spelad'
        """
    )
    spelade = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM matches
        WHERE status = 'kommande'
        """
    )
    kommande_db = cursor.fetchone()[0]

    conn.close()

    return (
        nya_matcher,
        nya_resultat,
        redan,
        kommande,
        totalt,
        spelade,
        kommande_db
    )


def main():

    print("=" * 60)
    print("SHL VERKLIGHETSMOTOR – MATCHRESULTAT")
    print("=" * 60)
    print()
    print("Källa:")
    print(URL)
    print()

    try:
        html = hamta_sida()

    except Exception as e:

        print("FEL VID HÄMTNING:")
        print(e)

        return

    matcher = hitta_matcher(html)

    print()
    print(
        f"Matcher från källan: {len(matcher)}"
    )
    print()

    if not matcher:

        print("INGA MATCHER HITTADE.")
        return

    print("MATCHER FRÅN KÄLLAN:")
    print("-" * 60)

    for match in matcher:

        resultat = "-"

        if (
            match["home_score"] is not None
            and
            match["away_score"] is not None
        ):

            resultat = (
                f"{match['home_score']}-"
                f"{match['away_score']}"
            )

        print(
            f"{match['date']} | "
            f"{match['home_team']} - "
            f"{match['away_team']} | "
            f"{resultat}"
        )

    print()
    print("=" * 60)

    (
        nya_matcher,
        nya_resultat,
        redan,
        kommande,
        totalt,
        spelade,
        kommande_db
    ) = uppdatera_databas(matcher)

    print()
    print("=" * 60)
    print("MATCHSYSTEM KLART")
    print("=" * 60)

    print(
        f"Matcher från källan:   {len(matcher)}"
    )

    print(
        f"Nya matcher:           {nya_matcher}"
    )

    print(
        f"Nya/ändrade resultat:  {nya_resultat}"
    )

    print(
        f"Redan uppdaterade:     {redan}"
    )

    print(
        f"Kommande i körningen:  {kommande}"
    )

    print()
    print(
        f"Totalt i databasen:    {totalt}"
    )

    print(
        f"Spelade:               {spelade}"
    )

    print(
        f"Kommande:              {kommande_db}"
    )


if __name__ == "__main__":
    main()
