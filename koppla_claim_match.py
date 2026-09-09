import sqlite3
import re
from datetime import datetime, timedelta

DB = "dif_hockey.db"


# ============================================================
# INSTÄLLNINGAR
# ============================================================

DIF = "Djurgården"
DAGAR_FÖRE = 7
DAGAR_EFTER = 7


# ============================================================
# LAGNAMN
# ============================================================

MOTSTÅNDARE = [
    "Björklöven",
    "Rögle",
    "Växjö",
    "Timrå",
    "Färjestad",
    "Frölunda",
    "Örebro",
    "Linköping",
    "Brynäs",
    "Malmö",
    "Skellefteå",
    "Luleå",
    "HV71",
]


def normalisera(text):
    if not text:
        return ""

    text = text.lower()

    ersätt = {
        "ö": "ö",
        "ä": "ä",
        "å": "å",
    }

    for gammalt, nytt in ersätt.items():
        text = text.replace(gammalt, nytt)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# HITTA MOTSTÅNDARE I TEXT
# ============================================================

def hitta_motståndare(text):

    text = normalisera(text)

    for lag in MOTSTÅNDARE:

        if normalisera(lag) in text:
            return lag

    return None


# ============================================================
# DATUM
# ============================================================

def datum_från_post(post_time):

    if not post_time:
        return None

    text = post_time.strip().lower()

    månader = {
        "januari": 1,
        "februari": 2,
        "mars": 3,
        "april": 4,
        "maj": 5,
        "juni": 6,
        "juli": 7,
        "augusti": 8,
        "september": 9,
        "oktober": 10,
        "november": 11,
        "december": 12,
    }

    match = re.search(
        r"(\d{1,2})\s+([a-zåäö]+)",
        text
    )

    if match:

        dag = int(match.group(1))
        månad_text = match.group(2)

        if månad_text in månader:

            månad = månader[månad_text]

            år = datetime.now().year

            try:
                return datetime(
                    år,
                    månad,
                    dag
                ).date()

            except ValueError:
                return None

    # Relativa Facebook-tider
    idag = datetime.now().date()

    if text.startswith("igår"):
        return idag - timedelta(days=1)

    if re.search(r"\d+\s*t", text):
        return idag

    if re.search(r"\d+\s*m", text):
        return idag

    if re.search(r"\d+\s*h", text):
        return idag

    return None


# ============================================================
# HÄMTA MATCHER
# ============================================================

def hämta_matcher(cur):

    cur.execute("""
        SELECT
            id,
            match_date,
            home_team,
            away_team
        FROM matches
        ORDER BY match_date
    """)

    return cur.fetchall()


# ============================================================
# HITTA BÄSTA MATCH
# ============================================================

def hitta_match(post_text, post_time, matcher):

    text = normalisera(post_text)

    post_datum = datum_från_post(post_time)

    motståndare = hitta_motståndare(text)

    kandidater = []

    for match_id, match_date, home_team, away_team in matcher:

        if not match_date:
            continue

        try:
            match_datum = datetime.strptime(
                match_date,
                "%Y-%m-%d"
            ).date()

        except ValueError:
            continue

        # Om vi inte kan hitta postens datum använder vi
        # motståndaren som enda ledtråd.
        if post_datum:

            diff = (match_datum - post_datum).days

            if diff < -DAGAR_FÖRE or diff > DAGAR_EFTER:
                continue

        else:

            diff = 0

        hemma = normalisera(home_team)
        borta = normalisera(away_team)

        motståndare_match = False

        if motståndare:

            if normalisera(motståndare) in hemma:
                motståndare_match = True

            if normalisera(motståndare) in borta:
                motståndare_match = True

        # Utan motståndare är datumkopplingen svag.
        if motståndare_match:
            poäng = 100 - abs(diff)
        elif post_datum and abs(diff) <= 1:
            poäng = 30 - abs(diff)
        else:
            continue

        kandidater.append(
            (
                poäng,
                match_id,
                match_date,
                home_team,
                away_team
            )
        )

    if not kandidater:
        return None

    kandidater.sort(
        reverse=True
    )

    return kandidater[0]


# ============================================================
# KOPPLA POSTS TILL MATCHER
# ============================================================

def koppla_posts():

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    matcher = hämta_matcher(cur)

    cur.execute("""
        SELECT
            posts.id,
            posts.post_text,
            posts.post_time,
            posts.match_id
        FROM posts
        WHERE posts.source_id = 1
        ORDER BY posts.id
    """)

    posts = cur.fetchall()

    kopplade = 0
    redan = 0
    utan_match = 0

    print()
    print("========================================")
    print("       KOPPLAR DIF-INLÄGG TILL MATCH")
    print("========================================")
    print()

    for post_id, post_text, post_time, gammal_match_id in posts:

        if gammal_match_id is not None:
            redan += 1
            continue

        resultat = hitta_match(
            post_text,
            post_time,
            matcher
        )

        if not resultat:

            utan_match += 1

            print(
                f"POST {post_id} → ingen match"
            )

            continue

        poäng, match_id, match_date, home_team, away_team = resultat

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
            f"POST {post_id} → MATCH {match_id} | "
            f"{match_date} | "
            f"{home_team} - {away_team} | "
            f"poäng {poäng}"
        )

    conn.commit()

    # ========================================================
    # KOPPLA CLAIMS VIA DERAS POSTS
    # ========================================================

    print()
    print("Kopplar claims via inlägg...")
    print()

    cur.execute("""
        UPDATE claims
        SET status = CASE
            WHEN status IS NULL OR status = '' THEN 'ny'
            ELSE status
        END
        WHERE comment_id IN (
            SELECT comments.id
            FROM comments
            JOIN posts
                ON posts.id = comments.post_id
            WHERE posts.match_id IS NOT NULL
        )
    """)

    claims_kopplade = cur.rowcount

    conn.commit()

    print()
    print("========================================")
    print("          KOPPLING KLAR")
    print("========================================")
    print(f"DIF-inlägg totalt:       {len(posts)}")
    print(f"Nya matchkopplingar:     {kopplade}")
    print(f"Redan kopplade:          {redan}")
    print(f"Utan match:              {utan_match}")
    print(f"Claims med matchväg:     {claims_kopplade}")
    print("========================================")
    print()

    conn.close()


if __name__ == "__main__":
    koppla_posts()
