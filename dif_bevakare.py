import sqlite3
import re

from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright


DB = "dif_hockey.db"
MAX_DAGAR = 28

KALLOR = [
    ("Djurgården Hockey", "https://www.facebook.com/difhockeyse"),
    ("TV4 Hockey", "https://www.facebook.com/tv4hockey")
]

MANADER = {
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
    "december": 12
}

DIF_ORD = [
    "djurgården",
    "djurgarden",
    "dif hockey",
    "djurgårdens"
]


def facebook_id(url):

    try:

        query = parse_qs(
            urlparse(url).query
        )

        if "fbid" in query:
            return query["fbid"][0]

    except Exception:
        pass

    match = re.search(
        r"pfbid([A-Za-z0-9]+)",
        url
    )

    if match:
        return "pfbid" + match.group(1)

    return None


def normalisera_url(url):

    if not url:
        return None

    url = url.strip()

    # Ta bort Facebooks interna parametrar
    url = url.split("&__")[0]

    # Gör relativa Facebook-länkar absoluta
    if url.startswith("/"):
        url = "https://www.facebook.com" + url

    return url

def hitta_datum(text):

    if not text:
        return None

    nu = datetime.now()
    text = text.lower()

    match = re.search(
        r"(\d{1,2})\s+"
        r"(januari|februari|mars|april|maj|juni|juli|augusti|"
        r"september|oktober|november|december)"
        r"(?:\s+(\d{4}))?"
        r"(?:\s+kl\.?\s*(\d{1,2}):(\d{2}))?",
        text
    )

    if match:

        dag = int(match.group(1))
        manad = MANADER[match.group(2)]

        if match.group(3):
            ar = int(match.group(3))
        else:
            ar = nu.year

        timme = (
            int(match.group(4))
            if match.group(4)
            else 0
        )

        minut = (
            int(match.group(5))
            if match.group(5)
            else 0
        )

        try:

            datum = datetime(
                ar,
                manad,
                dag,
                timme,
                minut
            )

            if datum > nu + timedelta(days=1):

                datum = datum.replace(
                    year=datum.year - 1
                )

            return datum

        except ValueError:
            pass

    match = re.search(
        r"(\d+)\s*d(?:\s|$)",
        text
    )

    if match:

        return (
            nu -
            timedelta(
                days=int(match.group(1))
            )
        )

    match = re.search(
        r"(\d+)\s*tim",
        text
    )

    if match:

        return (
            nu -
            timedelta(
                hours=int(match.group(1))
            )
        )

    match = re.search(
        r"(\d+)\s*m(?:\s|$)",
        text
    )

    if match:

        return (
            nu -
            timedelta(
                minutes=int(match.group(1))
            )
        )

    match = re.search(
        r"(\d+)\s*min",
        text
    )

    if match:

        return (
            nu -
            timedelta(
                minutes=int(match.group(1))
            )
        )

    if "igår" in text:

        return (
            nu -
            timedelta(days=1)
        )

    return None


def ar_dif_relevant(text):

    text = (text or "").lower()

    for ordet in DIF_ORD:

        if ordet in text:
            return True

    return False


def rensa_posttext(text):

    if not text:
        return ""

    # Facebook lägger ofta in sidans login-rader.
    skräp = [
        "logga in",
        "har du glömt kontot?",
        "har du glömt lösenordet?",
        "e-post eller telefonnummer",
        "lösenord",
        "skapa nytt konto",
        "se mer på facebook"
    ]

    rader = text.splitlines()

    rena = []

    for rad in rader:

        rad = rad.strip()

        if not rad:
            continue

        låg = rad.lower()

        if låg in skräp:
            continue

        rena.append(rad)

    return "\n".join(rena)[:10000]


def hitta_inlaggets_huvudtext(text):

    if not text:
        return ""

    text = rensa_posttext(text)

    # Försök ta bort tydliga Facebook-sektioner
    stopp = [
        "alla reaktioner:",
        "kommentarer",
        "mest relevant",
        "författare",
        "visa fler kommentarer",
        "se mer på facebook",
        "e-post eller telefonnummer"
    ]

    resultat = []

    for rad in text.splitlines():

        låg = rad.lower().strip()

        if any(
            låg.startswith(x)
            for x in stopp
        ):
            break

        resultat.append(rad)

    return "\n".join(resultat).strip()


def hamta_source_id(conn, namn):

    row = conn.execute(
        """
        SELECT id
        FROM sources
        WHERE name=?
        """,
        (namn,)
    ).fetchone()

    if row:
        return row[0]

    return None


def spara_inlagg(
    conn,
    source_id,
    fid,
    url,
    text,
    post_time,
    relevant
):

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    conn.execute(
        """
        INSERT INTO posts
        (
            source_id,
            facebook_id,
            url,
            post_text,
            post_time,
            first_seen,
            last_seen,
            is_dif_relevant
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(source_id, facebook_id)
        DO UPDATE SET

            last_seen=excluded.last_seen,

            post_text=CASE
                WHEN excluded.post_text != ''
                THEN excluded.post_text
                ELSE posts.post_text
            END,

            post_time=COALESCE(
                excluded.post_time,
                posts.post_time
            ),

            is_dif_relevant=excluded.is_dif_relevant
        """,
        (
            source_id,
            fid,
            url,
            text[:10000],
            post_time.isoformat()
            if post_time
            else None,
            now,
            now,
            1 if relevant else 0
        )
    )

    conn.commit()


with sqlite3.connect(DB) as conn:

    cutoff = (
        datetime.now()
        -
        timedelta(days=MAX_DAGAR)
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            locale="sv-SE"
        )

        page.set_default_timeout(
            12000
        )

        for namn, source_url in KALLOR:

            print()
            print("=" * 60)
            print(namn)
            print("=" * 60)

            source_id = hamta_source_id(
                conn,
                namn
            )

            if not source_id:

                print(
                    "Källan finns inte i databasen."
                )

                continue

            try:

                page.goto(
                    source_url,
                    wait_until="domcontentloaded",
                    timeout=20000
                )

                page.wait_for_timeout(3000)

                links = page.locator("a")

                kandidater = {}

                for i in range(
                    links.count()
                ):

                    try:

                        href = (
                            links
                            .nth(i)
                            .get_attribute("href")
                        )

                        if not href:
                            continue

                        if "comment_id=" in href:
                            continue

                        if not any(
                            x in href
                            for x in [
                                "/posts/",
                                "/photos/",
                                "/videos/",
                                "/reel/",
                                "/permalink/",
                                "fbid="
                            ]
                        ):
                            continue

                        if href.startswith("/"):

                            href = (
                                "https://www.facebook.com"
                                + href
                            )

                        url = normalisera_url(
                            href
                        )

                        fid = facebook_id(
                            url
                        )

                        if not fid:
                            continue

                        kandidater[fid] = url

                    except Exception:
                        pass

                print(
                    "Hittade",
                    len(kandidater),
                    "möjliga inlägg på sidan."
                )

                nya = 0
                gamla = 0
                gamla_datum = 0
                relevanta = 0

                for fid, url in kandidater.items():

                    redan = conn.execute(
                        """
                        SELECT id
                        FROM posts
                        WHERE source_id=?
                        AND facebook_id=?
                        """,
                        (
                            source_id,
                            fid
                        )
                    ).fetchone()

                    if redan:

                        conn.execute(
                            """
                            UPDATE posts
                            SET url=?,
                                last_seen=?
                            WHERE id=?
                            """,
                            (
                                url,
                                datetime.now().isoformat(
                                    timespec="seconds"
                                ),
                                redan[0]
                            )
                        )

                        conn.commit()

                        gamla += 1

                        continue

                    try:

                        print(
                            "Öppnar:",
                            fid
                        )

                        page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=20000
                        )

                        page.wait_for_timeout(
                            1200
                        )

                        body = page.locator(
                            "body"
                        ).inner_text(
                            timeout=5000
                        )

                        post_time = hitta_datum(
                            body[:3000]
                        )

                        if (
                            post_time
                            and
                            post_time < cutoff
                        ):

                            gamla_datum += 1

                            print(
                                "  Äldre än 28 dagar - hoppar över"
                            )

                            continue

                        huvudtext = (
                            hitta_inlaggets_huvudtext(
                                body
                            )
                        )

                        # DIF-källan är automatiskt relevant.
                        #
                        # TV4 får ENDAST vara relevant om
                        # själva inläggstexten nämner DIF.
                        if namn == "Djurgården Hockey":

                            relevant = True

                        else:

                            relevant = ar_dif_relevant(
                                huvudtext
                            )

                        spara_inlagg(
                            conn,
                            source_id,
                            fid,
                            url,
                            huvudtext,
                            post_time,
                            relevant
                        )

                        nya += 1

                        if relevant:

                            relevanta += 1

                            print(
                                "  SPARAT - DIF"
                            )

                        else:

                            print(
                                "  SPARAT - ej DIF"
                            )

                    except Exception as e:

                        print(
                            "  FEL:",
                            type(e).__name__,
                            e
                        )

                print()
                print("RESULTAT")
                print("Nya:", nya)
                print(
                    "Redan sparade:",
                    gamla
                )
                print(
                    "Äldre än 28 dagar:",
                    gamla_datum
                )
                print(
                    "DIF-relevanta:",
                    relevanta
                )

            except Exception as e:

                print(
                    "KÄLLFEL:",
                    type(e).__name__,
                    e
                )

        browser.close()


print()
print("BEVAKNING KLAR")
