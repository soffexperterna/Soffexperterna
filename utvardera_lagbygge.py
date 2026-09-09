import sqlite3
import re
import unicodedata
from datetime import datetime

DB = "dif_hockey.db"


def normalisera(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    return text.strip()


def hamta_claim_datum(conn, claim_id):
    rad = conn.execute(
        """
        SELECT c.facebook_time, c.first_seen
        FROM claims cl
        JOIN comments c ON c.id = cl.comment_id
        WHERE cl.id = ?
        """,
        (claim_id,)
    ).fetchone()

    if not rad:
        return None

    datum = rad[0] or rad[1]

    if not datum:
        return None

    datum = str(datum)

    # Försök läsa vanliga datumformat
    format_lista = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in format_lista:
        try:
            return datetime.strptime(datum[:26], fmt)
        except ValueError:
            pass

    # Om bara datum finns
    try:
        return datetime.strptime(datum[:10], "%Y-%m-%d")
    except ValueError:
        return None


def hitta_nya_spelare(conn, claim_id):
    """
    Hittar spelare som tillkommit efter claimets datum.
    """

    claim_datum = hamta_claim_datum(conn, claim_id)

    if not claim_datum:
        return []

    # Alla spelare som fanns på claimets datum
    gamla = conn.execute(
        """
        SELECT player
        FROM roster_history
        WHERE season = '2026/27'
          AND team = 'Djurgården'
          AND valid_from <= ?
          AND (valid_to IS NULL OR valid_to >= ?)
        """,
        (
            claim_datum.strftime("%Y-%m-%d"),
            claim_datum.strftime("%Y-%m-%d"),
        )
    ).fetchall()

    gamla_namn = {
        normalisera(rad[0]).lower()
        for rad in gamla
    }

    # Senaste aktiva trupp
    nya = conn.execute(
        """
        SELECT player, valid_from
        FROM roster_history
        WHERE season = '2026/27'
          AND team = 'Djurgården'
          AND status = 'active'
        ORDER BY valid_from, player
        """
    ).fetchall()

    resultat = []

    for player, valid_from in nya:
        if normalisera(player).lower() not in gamla_namn:
            if valid_from > claim_datum.strftime("%Y-%m-%d"):
                resultat.append((player, valid_from))

    return resultat


def klassificera_lagbygge(text):
    """
    Försöker avgöra vilken typ av lagbygge-påstående det är.
    """

    t = normalisera(text).lower()

    if re.search(
        r"\bbehöver\b.*\b(värvning|värvas|spelare|förstärkning)\b",
        t
    ):
        return "behöver_värvning"

    if re.search(
        r"\bkan behöva\b.*\b(värvning|spelare|förstärkning)\b",
        t
    ):
        return "behöver_värvning"

    if re.search(
        r"\b(saknar|saknas)\b.*\b(pusselbitar|förstärkning|spelare)\b",
        t
    ):
        return "saknar_pusselbitar"

    if re.search(
        r"\bbehöver\b.*\b(förstärka|förstärkas)\b",
        t
    ):
        return "behöver_förstärkning"

    if re.search(
        r"\bsvagt lagbygge\b|\bdåligt lagbygge\b|\bsvag trupp\b",
        t
    ):
        return "negativt_lagbygge"

    if re.search(
        r"\bbra lagbygge\b|\bstarkt lagbygge\b|\bbra trupp\b",
        t
    ):
        return "positivt_lagbygge"

    return "okänd"


def utvärdera_claim(conn, claim_id, text):
    typ = klassificera_lagbygge(text)

    nya_spelare = hitta_nya_spelare(conn, claim_id)

    if typ == "behöver_värvning":
        if nya_spelare:
            namn = ", ".join(player for player, _ in nya_spelare)

            return (
                "utvärderad",
                "RÄTT",
                f"Efter påståendet tillkom följande DIF-spelare: {namn}.",
                f"nya_spelare={len(nya_spelare)};spelare={namn}"
            )

        return (
            "väntar_data",
            "OKLART",
            "Påståendet säger att DIF behöver ytterligare förstärkning. "
            "Ingen ny spelare efter påståendet kan ännu konstateras.",
            "nya_spelare=0"
        )

    if typ == "saknar_pusselbitar":
        if nya_spelare:
            namn = ", ".join(player for player, _ in nya_spelare)

            return (
                "underlag_klar",
                "OKLART",
                "Efter påståendet tillkom spelare till truppen: "
                f"{namn}. Detta ger underlag för att följa om de saknade "
                "pusselbitarna faktiskt förstärktes.",
                f"nya_spelare={len(nya_spelare)};spelare={namn}"
            )

        return (
            "väntar_data",
            "OKLART",
            "Påståendet gäller lagbyggets kvalitet. "
            "Det finns ännu ingen senare truppförändring att jämföra med.",
            "nya_spelare=0"
        )

    if typ == "behöver_förstärkning":
        if nya_spelare:
            namn = ", ".join(player for player, _ in nya_spelare)

            return (
                "underlag_klar",
                "OKLART",
                "Efter påståendet tillkom spelare till truppen: "
                f"{namn}. Den faktiska effekten behöver senare bedömas.",
                f"nya_spelare={len(nya_spelare)};spelare={namn}"
            )

        return (
            "väntar_data",
            "OKLART",
            "Ingen senare truppförändring kan ännu konstateras.",
            "nya_spelare=0"
        )

    if typ in (
        "negativt_lagbygge",
        "positivt_lagbygge"
    ):
        return (
            "väntar_data",
            "OKLART",
            "Subjektivt påstående om lagbyggets kvalitet. "
            "Det kräver senare sportsligt underlag för att kunna bedömas.",
            "nya_spelare=" + str(len(nya_spelare))
        )

    return (
        "väntar_regel",
        "OKLART",
        "Ingen specifik regel för detta lagbygge-påstående ännu.",
        "typ=" + typ
    )


def kör():
    conn = sqlite3.connect(DB)

    claims = conn.execute(
        """
        SELECT id, claim_text, claim_type
        FROM claims
        WHERE claim_type IN (
            'lagbygge',
            'truppförstärkning'
        )
        ORDER BY id
        """
    ).fetchall()

    print("=" * 70)
    print("DIF – LAGBYGGE / VÄRVNINGSMOTOR")
    print("=" * 70)
    print()
    print(f"Claims att analysera: {len(claims)}")
    print()

    rätt = 0
    fel = 0
    oklart = 0

    for claim_id, claim_text, claim_type in claims:

        status, verdict, evidence, evidence_value = utvärdera_claim(
            conn,
            claim_id,
            claim_text
        )

        conn.execute(
            """
            UPDATE claims
            SET status = ?,
                verdict = ?,
                evidence = ?,
                evidence_value = ?,
                evaluated_at = ?
            WHERE id = ?
            """,
            (
                status,
                verdict,
                evidence,
                evidence_value,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                claim_id,
            )
        )

        if verdict == "RÄTT":
            rätt += 1
        elif verdict == "FEL":
            fel += 1
        else:
            oklart += 1

        print("-" * 70)
        print(f"CLAIM #{claim_id}")
        print("-" * 70)
        print(f"Påstående: {claim_text}")
        print(f"Typ:       {claim_type}")
        print(f"Status:    {status}")
        print(f"Dom:       {verdict}")
        print(f"Underlag:  {evidence}")
        print(f"Värde:     {evidence_value}")
        print()

    conn.commit()

    print("=" * 70)
    print("SAMMANFATTNING")
    print("=" * 70)
    print(f"RÄTT:     {rätt}")
    print(f"FEL:      {fel}")
    print(f"OKLART:   {oklart}")
    print("=" * 70)
    print("LAGBYGGE-MOTOR KLAR")
    print("=" * 70)

    conn.close()


if __name__ == "__main__":
    kör()
