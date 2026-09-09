import sqlite3
import re
from datetime import datetime

DB = "dif_hockey.db"

LAG_ALIAAS = {
    "IF Björklöven": [
        "björklöven",
        "bjorkloven",
        "löven"
    ],
    "Rögle BK": [
        "rögle",
        "rogle"
    ],
    "Växjö Lakers HC": [
        "växjö",
        "vaxjo"
    ],
    "Timrå IK": [
        "timrå",
        "timra"
    ],
    "Färjestads BK": [
        "färjestad",
        "farjestad"
    ],
    "Frölunda HC": [
        "frölunda",
        "frolunda"
    ],
    "Örebro HK": [
        "örebro",
        "orebro"
    ],
    "Linköpings HC": [
        "linköping",
        "linkoping"
    ],
    "Brynäs IF": [
        "brynäs",
        "brynas"
    ],
    "Malmö Redhawks": [
        "malmö",
        "malmo"
    ],
    "Skellefteå AIK": [
        "skellefteå",
        "skelleftea"
    ],
    "Luleå HF": [
        "luleå",
        "lulea"
    ],
    "HV71": [
        "hv71",
        "hv 71"
    ]
}


def normalisera(text):
    if not text:
        return ""

    text = text.lower()
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def hitta_lag(text):
    text = normalisera(text)

    hittade = []

    for lag, alias_lista in LAG_ALIAAS.items():

        for alias in alias_lista:

            if re.search(
                r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
                text
            ):
                hittade.append(lag)
                break

    return hittade


def datum_fran_post(post_time):
    if not post_time:
        return None

    try:
        return datetime.fromisoformat(post_time).date()
    except Exception:
        return None


def datum_fran_match(match_date):
    try:
        return datetime.strptime(
            match_date,
            "%Y-%m-%d"
        ).date()
    except Exception:
        return None


def koppla_inlagg():

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # ENDAST Djurgården Hockey.
    # source_id 1 = Djurgården Hockey
    cur.execute("""
        SELECT
            id,
            post_text,
            post_time,
            match_id
        FROM posts
        WHERE source_id = 1
        ORDER BY id
    """)

    poster = cur.fetchall()

    cur.execute("""
        SELECT
            id,
            match_date,
            home_team,
            away_team
        FROM matches
        ORDER BY match_date
    """)

    matcher = cur.fetchall()

    kopplade = 0
    redan = 0
    inga = 0
    flera = 0

    print("=" * 55)
    print("KOPPLAR DIF-INLÄGG TILL MATCHER")
    print("=" * 55)

    for post_id, post_text, post_time, befintlig_match_id in poster:

        if befintlig_match_id is not None:
            redan += 1
            continue

        post_datum = datum_fran_post(post_time)
        text = normalisera(post_text)

        lag_i_text = hitta_lag(text)

        kandidater = []

        for match_id, match_date, hemma, borta in matcher:

            match_datum = datum_fran_match(match_date)

            if not match_datum or not post_datum:
                continue

            # Inlägget får ligga max 7 dagar från matchen.
            dagar = abs((match_datum - post_datum).days)

            if dagar > 7:
                continue

            motstandare = None

            if normalisera(hemma) == "djurgården":
                motstandare = borta

            elif normalisera(borta) == "djurgården":
                motstandare = hemma

            if not motstandare:
                continue

            if motstandare in lag_i_text:

                kandidater.append(
                    (
                        match_id,
                        match_datum,
                        hemma,
                        borta
                    )
                )

        if len(kandidater) == 1:

            match_id, match_datum, hemma, borta = kandidater[0]

            cur.execute("""
                UPDATE posts
                SET match_id = ?
                WHERE id = ?
            """, (
                match_id,
                post_id
            ))

            kopplade += 1

            print(
                f"POST {post_id} -> MATCH {match_id} | "
                f"{hemma} - {borta}"
            )

        elif len(kandidater) == 0:

            inga += 1

        else:

            flera += 1

            print()
            print(f"POST {post_id} HAR FLERA MÖJLIGA MATCHER:")

            for match in kandidater:

                print(
                    f"  MATCH {match[0]} | "
                    f"{match[1]} | "
                    f"{match[2]} - {match[3]}"
                )

    conn.commit()
    conn.close()

    print()
    print("=" * 55)
    print("KLART")
    print("=" * 55)
    print(f"DIF-inlägg analyserade: {len(poster)}")
    print(f"Nya kopplingar:         {kopplade}")
    print(f"Redan kopplade:         {redan}")
    print(f"Ingen kandidat:         {inga}")
    print(f"Flera kandidater:       {flera}")
    print("=" * 55)


if __name__ == "__main__":
    koppla_inlagg()
