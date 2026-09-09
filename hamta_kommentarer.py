import hitta_claims
import sqlite3
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

DB = "dif_hockey.db"
HEADLESS = True
TIMEOUT = 30000


# ============================================================
# URL
# ============================================================

def giltig_url(url):
    if not url:
        return False

    url = str(url).strip()

    if not re.match(r"^https?://", url, re.IGNORECASE):
        return False

    if "facebook.com" not in url.lower():
        return False

    return True


# ============================================================
# FACEBOOK UI-TEXT SOM ALDRIG FÅR BLI KOMMENTAR
# ============================================================

def ar_ui_text(text):
    if not text:
        return True

    text = text.replace("\ufeff", "").strip()

    if not text:
        return True

    t = text.lower()

    ui = {
        "mest relevant",
        "visa mer",
        "visa fler",
        "visa fler kommentarer",
        "visa alla",
        "visa alla kommentarer",
        "kommentar",
        "kommentarer",
        "gilla",
        "svara",
        "dela",
        "like",
        "reply",
        "share",
        "follow",
        "följ",
        "reaktioner",
        "alla reaktioner"
    }

    if t in ui:
        return True

    # Bara siffror
    if re.fullmatch(r"\d+", text):
        return True

    # Facebook-tider
    if re.fullmatch(
        r"\d+\s*(sek|sekunder|min|minuter|tim|timmar|h|d|dag|dagar|v|vecka|veckor)",
        t
    ):
        return True

    return False


# ============================================================
# HÄMTA INLÄGG
# ============================================================

def hamta_inlagg(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT id, url, post_text
        FROM posts
        WHERE url IS NOT NULL
          AND TRIM(url) != ''
        ORDER BY id
    """)

    return cur.fetchall()


# ============================================================
# SPARA KOMMENTAR
# ============================================================

def spara_kommentar(
    conn,
    post_id,
    commenter,
    comment_text,
    facebook_time
):

    if ar_ui_text(comment_text):
        return False

    commenter = (commenter or "").strip()
    comment_text = (comment_text or "").strip()
    facebook_time = (facebook_time or "").strip()

    if not commenter:
        commenter = "Okänd"

    if len(comment_text) < 2:
        return False

    # Säkerhetsfilter mot hela inlägg
    if len(comment_text) > 800:
        return False

    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM comments
        WHERE post_id = ?
          AND commenter = ?
          AND comment_text = ?
          AND facebook_time = ?
        LIMIT 1
    """, (
        post_id,
        commenter,
        comment_text,
        facebook_time
    ))

    if cur.fetchone():
        return False

    cur.execute("""
        INSERT INTO comments (
            post_id,
            commenter,
            comment_text,
            facebook_time,
            first_seen
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        post_id,
        commenter,
        comment_text,
        facebook_time,
        datetime.now().isoformat(timespec="seconds")
    ))

    conn.commit()

    return True


# ============================================================
# LADDA FACEBOOK-SIDAN
# ============================================================

def ladda_sida(page):

    # Scrolla så kommentarer kan laddas
    for _ in range(8):

        try:
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(1200)

        except Exception:
            pass

    # Försök öppna fler kommentarer
    knappar = [
        "Visa fler kommentarer",
        "Visa fler",
        "View more comments",
        "View more",
        "Load more comments"
    ]

    for knapp in knappar:

        try:

            loc = page.get_by_text(
                knapp,
                exact=False
            )

            antal = min(loc.count(), 5)

            for i in range(antal):

                try:
                    loc.nth(i).click(timeout=2000)
                    page.wait_for_timeout(1000)

                except Exception:
                    pass

        except Exception:
            pass


# ============================================================
# HITTA KOMMENTARER MED DOM
# ============================================================

def hitta_dom_kommentarer(page):

    resultat = []

    # Facebook använder olika DOM-strukturer.
    selectors = [
        '[role="article"]',
        '[data-testid="UFI2Comment/root_depth_0"]',
        '[data-testid="UFI2Comment/root"]',
        '[data-pagelet*="Comment"]'
    ]

    block = None

    for selector in selectors:

        try:

            loc = page.locator(selector)

            if loc.count() > 0:
                block = loc
                break

        except Exception:
            continue

    if block is None:
        return resultat

    antal = min(block.count(), 100)

    for i in range(antal):

        try:
            element = block.nth(i)

            text = element.inner_text(
                timeout=3000
            ).strip()

        except Exception:
            continue

        if not text:
            continue

        rader = [
            r.strip()
            for r in text.splitlines()
            if r.strip()
        ]

        if len(rader) < 2:
            continue

        # Rensa UI-rader
        rena = [
            r
            for r in rader
            if not ar_ui_text(r)
        ]

        if len(rena) < 2:
            continue

        # Om blocket innehåller tydliga kommentarsknappar
        har_svar = any(
            r.lower() in {"svara", "reply"}
            for r in rader
        )

        har_gilla = any(
            r.lower() in {"gilla", "like"}
            for r in rader
        )

        if not har_svar and not har_gilla:
            continue

        namn = rena[0]

        kommentar_rader = rena[1:]

        kommentar = " ".join(
            kommentar_rader
        ).strip()

        if ar_ui_text(kommentar):
            continue

        if len(kommentar) < 2:
            continue

        if len(kommentar) > 800:
            continue

        # Förhindra att hela Facebook-inlägget blir kommentar
        if kommentar.startswith("· "):
            continue

        resultat.append({
            "commenter": namn,
            "comment_text": kommentar,
            "facebook_time": ""
        })

    return resultat


# ============================================================
# ALTERNATIV DOM-METOD
# ============================================================

def hitta_textbaserade_kommentarer(page):

    resultat = []

    try:

        # Leta specifikt efter element med kommentarrelaterade
        # attribut i stället för hela body-texten.
        selectors = [
            '[aria-label*="Kommentar"]',
            '[aria-label*="comment"]',
            '[data-testid*="comment"]'
        ]

        element = None

        for selector in selectors:

            try:

                loc = page.locator(selector)

                if loc.count() > 0:
                    element = loc
                    break

            except Exception:
                continue

        if element is None:
            return resultat

        antal = min(element.count(), 100)

        for i in range(antal):

            try:

                text = element.nth(i).inner_text(
                    timeout=2000
                ).strip()

            except Exception:
                continue

            if not text:
                continue

            rader = [
                r.strip()
                for r in text.splitlines()
                if r.strip()
            ]

            rader = [
                r
                for r in rader
                if not ar_ui_text(r)
            ]

            if len(rader) < 2:
                continue

            namn = rader[0]
            kommentar = " ".join(rader[1:])

            if ar_ui_text(kommentar):
                continue

            if len(kommentar) < 2:
                continue

            if len(kommentar) > 800:
                continue

            resultat.append({
                "commenter": namn,
                "comment_text": kommentar,
                "facebook_time": ""
            })

    except Exception:
        pass

    return resultat


# ============================================================
# EXTRAHERA
# ============================================================

def extrahera_kommentarer(page):

    ladda_sida(page)

    # Första metoden
    resultat = hitta_dom_kommentarer(page)

    if resultat:
        return resultat

    # Andra metoden
    resultat = hitta_textbaserade_kommentarer(page)

    if resultat:
        return resultat

    # VIKTIGT:
    # Ingen fallback till hela body-texten.
    #
    # Hellre 0 kommentarer än att vi sparar Facebooks
    # gränssnitt eller hela inlägget som en kommentar.

    return []


# ============================================================
# ETT INLÄGG
# ============================================================

def hamta_ett_inlagg(
    page,
    post_id,
    url,
    post_text
):

    print()
    print("=" * 60)
    print(f"INLÄGG: {post_id}")
    print("=" * 60)

    if not giltig_url(url):

        print(
            "SKIPPAR: Ogiltig eller saknad Facebook-URL"
        )

        if url:

            visning = str(url).replace(
                "\n",
                " "
            )

            print(
                f"URL-fält: {visning[:150]}"
            )

        return []

    print(f"URL: {url}")

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=TIMEOUT
        )

        page.wait_for_timeout(4000)

    except Exception as e:

        print(
            "Kunde inte öppna inlägget:"
        )

        print(str(e)[:500])

        return []

    try:

        kommentarer = extrahera_kommentarer(
            page
        )

    except Exception as e:

        print(
            "Fel vid kommentarsextraktion:"
        )

        print(str(e)[:500])

        return []

    rena = []

    for kommentar in kommentarer:

        text = kommentar.get(
            "comment_text",
            ""
        )

        if ar_ui_text(text):
            continue

        rena.append(kommentar)

    print(
        f"Hittade {len(rena)} möjliga kommentarer"
    )

    return rena


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("DIF – HÄMTAR FACEBOOK-KOMMENTARER")
    print("=" * 60)

    conn = sqlite3.connect(DB)

    try:

        inlagg = hamta_inlagg(conn)

        print(
            f"Inlägg med URL i databasen: "
            f"{len(inlagg)}"
        )

        nya = 0
        hoppade_over = 0

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=HEADLESS
            )

            page = browser.new_page()

            page.set_default_timeout(
                TIMEOUT
            )

            for (
                post_id,
                url,
                post_text
            ) in inlagg:

                if not giltig_url(url):
                    hoppade_over += 1

                kommentarer = hamta_ett_inlagg(
                    page,
                    post_id,
                    url,
                    post_text
                )

                for kommentar in kommentarer:

                    sparad = spara_kommentar(
                        conn,
                        post_id,
                        kommentar.get(
                            "commenter"
                        ),
                        kommentar.get(
                            "comment_text"
                        ),
                        kommentar.get(
                            "facebook_time"
                        )
                    )

                    if sparad:

                        nya += 1

                        print(
                            "NY KOMMENTAR: "
                            f"{kommentar.get('commenter')} | "
                            f"{kommentar.get('comment_text')}"
                        )

            browser.close()

        cur = conn.cursor()

        cur.execute(
            "SELECT COUNT(*) FROM comments"
        )

        totalt = cur.fetchone()[0]

        print(
            f"Totalt i databasen: {totalt}"
        )
        print(
            f"Överhoppade URL:    {hoppade_over}"
        )
        print("=" * 60)

        print()
        print("=" * 60)
        print("KÖR CLAIM-FILTER")
        print("=" * 60)

        hitta_claims.kor_claim_filter()

    finally:

        conn.close()


if __name__ == "__main__":
    main()   
