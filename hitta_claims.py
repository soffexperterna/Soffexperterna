import sqlite3
import re
from datetime import datetime

DB = "dif_hockey.db"
SEASON = "2026/27"

print("=" * 60)
print("DIF – CLAIM-FILTER v8")
print("=" * 60)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()


def normalisera(text):
    text = text or ""

    # Facebooks "Prec… Visa mer"
    text = re.sub(r"prec….*$", "", text, flags=re.I | re.S)

    # Tidsangivelser som ibland följer med importerade kommentarer
    text = re.sub(
        r"\b\d+\s*(?:sek|min|tim|timm|dag|dagar|vecka|veckor)\b",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(r"\s+", " ", text).strip()
    return text


def utan_citerad_anvandare(text):
    """
    Facebook-svar kan importeras som:
    'Svante Nilson Kör hårt lycka till.'
    eller:
    'Mikael Kähler Bra match'

    Försök ta bort inledande namn så att grundkommentaren
    kan jämföras med originalet.
    """
    text = normalisera(text)

    # Vanliga svenska förnamn/efternamn som följs av resten av kommentaren.
    # Vi använder bara detta för dublettkontroll, inte för att ändra
    # claim_text som sparas i databasen.
    match = re.match(
        r"^[A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){1,2}\s+(.+)$",
        text,
    )

    if match:
        resten = match.group(1).strip()

        # Behåll bara om resten faktiskt ser ut som en kommentar.
        if len(resten) >= 5:
            return resten

    return text


def claim_nyckel(text):
    text = utan_citerad_anvandare(text).lower()

    # Normalisera vanliga variationer
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-zåäö0-9 ]", "", text)

    return text[:250].strip()


IGNORERA = [
    "kör hårt",
    "lycka till",
    "nu kör vi",
    "kämpa",
    "fff",
    "htb",
    "bra match",
    "gick ju bra",
    "ser bra ut",
    "såg riktigt bra ut",
    "snyggt jobbat",
    "gnugga gnugga",
    "easy",
    "stort grattis",
    "synd att jag inte kunde komma",
    "herregud",
    "så jäkla taggad",
    "fixat swiss",
    "visa vilka vi är",
]


def ar_ignorerad(text):
    t = normalisera(text).lower()

    if len(t) < 12:
        return True

    for phrase in IGNORERA:
        if t == phrase or t.startswith(phrase + "."):
            return True

    # Rena resultatgissningar ska inte bli SOFFEXPERT-claims.
    if re.search(
        r"\b(?:vi|dif|djurgården)\s+vinner?\s+med\s+\d+\s*[-–]\s*\d+\b",
        t,
    ):
        return True

    return False


def skapa_claim(comment_id, text, claim_type, target_type=None, target=None):
    cur.execute(
        """
        INSERT INTO claims
        (
            comment_id,
            claim_text,
            claim_type,
            target_type,
            target,
            status,
            verdict,
            created_at,
            season
        )
        VALUES (?, ?, ?, ?, ?, 'ny', 'OKLART', ?, ?)
        """,
        (
            comment_id,
            text,
            claim_type,
            target_type,
            target,
            datetime.now().isoformat(timespec="seconds"),
            SEASON,
        ),
    )


def hitta_claim(text):
    t = normalisera(text)
    l = t.lower()

    if ar_ignorerad(t):
        return None

    # ---------------------------------------------------------
    # KEDJOR
    # ---------------------------------------------------------
    if (
        ("bra kedja" in l or "riktigt bra kedja" in l)
        and ("," in t or " och " in l)
    ):
        return ("kedja", "kedja", t)

    if (
        "kedja" in l
        and any(
            x in l
            for x in [
                "fortsätt",
                "spela ihop",
                "hittat",
                "bra",
                "riktigt bra",
            ]
        )
    ):
        return ("kedja", "kedja", t)

    # ---------------------------------------------------------
    # LAGBYGGE
    # ---------------------------------------------------------
    lagbygge_ord = [
        "saknar viktiga pusselbitar",
        "saknar pusselbitar",
        "behöver en till värvning",
        "behöver en värvning",
        "behöver värva",
        "behöver förstärka",
        "måste värva",
        "måste förstärka",
        "ordinarie lag",
        "spela samman formationer",
        "formationer",
        "truppen behöver",
        "truppen måste",
        "laget behöver",
        "laget måste",
        "lagbygget",
        "lagbygge",
    ]

    if any(x in l for x in lagbygge_ord):
        return ("lagbygge", "lag", "Djurgården")

    # ---------------------------------------------------------
    # TRANSFER
    # ---------------------------------------------------------
    transfer_patterns = [
        r"\bbehöver\s+(?:en\s+)?(?:ny\s+)?värvning\b",
        r"\bbehöver\s+värva\b",
        r"\bmåste\s+värva\b",
        r"\bkommer\s+(?:en\s+)?värvning\b",
        r"\b(?:hoppas|tror)\s+.*\bkommer\b",
        r"\b.*\bkommer\s+snart\b",
        r"\b.*\bansluter\b",
        r"\b.*\bnyförvärv\b",
    ]

    if any(re.search(p, l) for p in transfer_patterns):
        return ("transfer", "spelare", t)

    # ---------------------------------------------------------
    # SPELARE / MÅLVAKT – OBJEKTIVT VERIFIERBARA PÅSTÅENDEN
    # ---------------------------------------------------------
    # Viktigt:
    # Vanliga omdömen som "hittat formen", "spelar bra",
    # "är i form" och "blir viktig" ska INTE automatiskt bli
    # spelarclaims. De är subjektiva och saknar ett tydligt facit.
    #
    # Spelarclaim kräver här ett konkret, verifierbart påstående.
    # Exempel:
    #   "Hellberg håller nollan"
    #   "Hellberg släpper in minst 4 mål"
    #   "Hellberg gör 20 mål"
    #   "Hellberg vinner skytteligan"
    # ---------------------------------------------------------
    player_objective_patterns = [
        r"\b(?:håller|hålla)\s+nollan\b",
        r"\bsläpper\s+in\s+(?:minst\s+)?\d+\b",
        r"\bsläppa\s+in\s+(?:minst\s+)?\d+\b",
        r"\b(?:gör|göra|kommer\s+göra|kommer\s+att\s+göra)\s+\d+\s*(?:mål|poäng|assist|assists)\b",
        r"\b(?:kommer|ska)\s+(?:göra|nå)\s+\d+\b",
        r"\b(?:vinner|vinna|toppar|toppa)\s+(?:skytte|poäng)ligan\b",
        r"\b(?:blir|vara)\s+(?:skytte|poäng)kung\b",
        r"\b(?:gör|göra)\s+flest\s+(?:mål|poäng)\b",
        r"\b(?:får|kommer\s+få|ska\s+få)\s+\d+\s*(?:poäng|mål|assist|minuter)\b",
    ]

    if any(re.search(pattern, l) for pattern in player_objective_patterns):
        names = re.findall(
            r"\b[A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+)?\b",
            t,
        )

        stop = {
            "Allt",
            "Djurgården",
            "Bra",
            "Ser",
            "Det",
            "Och",
            "Nu",
            "Samtidigt",
            "Vi",
            "Han",
            "Hon",
            "Den",
            "Detta",
        }

        names = [
            n for n in names
            if n.split()[0] not in stop
        ]

        if names:
            return ("spelare", "spelare", names[0])

    # ---------------------------------------------------------
    # MÅLSKYTTE / POÄNG
    # ---------------------------------------------------------
    if re.search(
        r"\b(?:gör|göra|göra minst|kommer göra|kommer att göra|"
        r"skjuter|skjuta|producerar|producerar|"
        r"slutar på)\b.*\b\d+\b",
        l,
    ):
        return ("målskytte", "spelare", t)

    if re.search(
        r"\b(?:skytteligan|poängligan|poängkung|skyttekung|"
        r"bästa målskytt|bäste målskytt|bäst poäng|"
        r"toppar poängligan|vinner poängligan)\b",
        l,
    ):
        return ("målskytte", "spelare", t)

    # ---------------------------------------------------------
    # SÄSONG / TABELL / GULD
    # ---------------------------------------------------------
    if any(
        x in l
        for x in [
            "vinner serien",
            "vinner grundserien",
            "tar guld",
            "tar guldet",
            "blir svenska mästare",
            "blir mästare",
            "går till final",
            "går till semifinal",
            "slutar topp",
            "slutar på",
            "hamnar på",
            "tabellplacering",
            "topp 3",
            "topp tre",
            "topp 5",
            "topp fem",
        ]
    ):
        return ("sasong", "lag", "Djurgården")

    # ---------------------------------------------------------
    # MATCH – INTE EXAKT RESULTAT
    # ---------------------------------------------------------
    if any(
        x in l
        for x in [
            "vinner mot",
            "vinner över",
            "tar en vinst",
            "tar hem segern",
            "blir seger",
            "förlorar mot",
            "slår",
        ]
    ):
        return ("match", "lag", "Djurgården")

    # ---------------------------------------------------------
    # UTVECKLING / FRAMTIDA PRESTATION
    # ---------------------------------------------------------
    utveckling_ord = [
        "bättre och bättre",
        "kommer bli bättre",
        "kommer att bli bättre",
        "kan ta oss långt",
        "kan gå långt",
        "kommer gå långt",
        "kommer att gå långt",
        "bara bli bättre",
        "utvecklas",
        "utveckling",
        "fortsätta utvecklas",
        "växa",
        "växer",
        "bli bättre",
    ]

    if any(x in l for x in utveckling_ord):
        return ("utveckling", "lag", "Djurgården")

    # ---------------------------------------------------------
    # PRESTATION – TYDLIGT PÅSTÅENDE
    # ---------------------------------------------------------
    if any(
        x in l
        for x in [
            "visar äntligen vad man kan",
            "ett helt annat djurgården",
            "ett spel som kan",
            "spel som kan",
        ]
    ):
        return ("utveckling", "lag", "Djurgården")

    return None


def kor_claim_filter():
    # -------------------------------------------------------------
    # Läs kommentarer
    # -------------------------------------------------------------
    rows = cur.execute(
        """
        SELECT id, commenter, comment_text
        FROM comments
        ORDER BY id
        """
    ).fetchall()

    print(f"Kommentarer i databasen: {len(rows)}")
    print()

    existing_comment_ids = {
        row[0]
        for row in cur.execute(
            "SELECT comment_id FROM claims WHERE comment_id IS NOT NULL"
        ).fetchall()
    }

    existing_keys = {
        claim_nyckel(row[0])
        for row in cur.execute(
            "SELECT claim_text FROM claims"
        ).fetchall()
    }

    nya = 0
    ignorerade = 0
    utan = 0
    redan = 0
    dublett = 0
    per_typ = {}


    for row in rows:
        comment_id = row["id"]
        commenter = row["commenter"]
        text = row["comment_text"] or ""

        if comment_id in existing_comment_ids:
            redan += 1
            continue

        if ar_ignorerad(text):
            ignorerade += 1
            continue

        key = claim_nyckel(text)

        if key in existing_keys:
            dublett += 1
            continue

        result = hitta_claim(text)

        if not result:
            utan += 1
            continue

        claim_type, target_type, target = result

        skapa_claim(
            comment_id,
            normalisera(text),
            claim_type,
            target_type,
            target,
        )

        existing_keys.add(key)
        nya += 1
        per_typ[claim_type] = per_typ.get(claim_type, 0) + 1

        print(
            f"NY CLAIM #{comment_id} | {commenter} | "
            f"{claim_type} | {normalisera(text)}"
        )


    conn.commit()

    print()
    print("=" * 60)
    print("RESULTAT")
    print("=" * 60)
    print(f"Nya claims:        {nya}")
    print(
        f"Totala claims:     "
        f"{cur.execute('SELECT COUNT(*) FROM claims').fetchone()[0]}"
    )
    print(f"Ignorerade:        {ignorerade}")
    print(f"Utan claim:        {utan}")
    print(f"Redan kommentar:   {redan}")
    print(f"Dublett claim:     {dublett}")

    print()
    print("CLAIMS PER TYP:")

    if per_typ:
        for typ, antal in sorted(per_typ.items()):
            print(f"  {typ}: {antal}")
    else:
        print("  Inga nya claims")

    print()
    print("KLART")
    return nya


if __name__ == "__main__":
    kor_claim_filter()
