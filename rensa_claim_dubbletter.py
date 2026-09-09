import sqlite3
import re

DB = "dif_hockey.db"


def normalisera(text):
    """Gör Facebook-varianter av samma kommentar jämförbara."""
    if not text:
        return ""

    text = text.lower()

    # Facebooks "Visa mer"-varianter
    text = re.sub(r"\s*prec…\s*visa mer\s*$", "", text)
    text = re.sub(r"\s*visa mer\s*$", "", text)

    # Ta bort avslutande Facebook-metadata, t.ex. "7"
    text = re.sub(r"\s+\d{1,3}\s*$", "", text)

    # Normalisera mellanslag och skiljetecken
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" .,!?:;-")

    return text


def ar_samma_claim(a, b):
    a = normalisera(a)
    b = normalisera(b)

    if not a or not b:
        return False

    # Exakt samma efter normalisering
    if a == b:
        return True

    # Om den ena är en tydlig trunkering av den andra
    kort, lang = sorted([a, b], key=len)

    if len(kort) >= 80 and lang.startswith(kort):
        return True

    # Facebook kan kapa mitt i texten.
    # Jämför därför de första 100 tecknen.
    if len(kort) >= 100 and kort[:100] == lang[:100]:
        return True

    return False


def rensa_dubbletter():
    conn = sqlite3.connect(DB)

    claims = conn.execute("""
        SELECT
            id,
            comment_id,
            claim_text,
            claim_type,
            target_type,
            target,
            season
        FROM claims
        ORDER BY id
    """).fetchall()

    borttagna = []

    for i in range(len(claims)):
        id1, comment1, text1, type1, target_type1, target1, season1 = claims[i]

        for j in range(i + 1, len(claims)):
            id2, comment2, text2, type2, target_type2, target2, season2 = claims[j]

            # Samma kommentar eller uppenbar Facebook-trunkering
            samma_text = ar_samma_claim(text1, text2)

            if not samma_text:
                continue

            # Behåll den längsta/fullständigaste versionen.
            if len(text1) >= len(text2):
                behall = id1
                ta_bort = id2
            else:
                behall = id2
                ta_bort = id1

            # Säkerhetskoll: flytta eventuell information från
            # den claim som tas bort om den bättre versionen saknar den.
            conn.execute("""
                UPDATE claims
                SET
                    claim_type = COALESCE(claim_type, (
                        SELECT claim_type FROM claims WHERE id = ?
                    )),
                    target_type = COALESCE(target_type, (
                        SELECT target_type FROM claims WHERE id = ?
                    )),
                    target = COALESCE(target, (
                        SELECT target FROM claims WHERE id = ?
                    )),
                    season = COALESCE(season, (
                        SELECT season FROM claims WHERE id = ?
                    ))
                WHERE id = ?
            """, (
                ta_bort,
                ta_bort,
                ta_bort,
                ta_bort,
                behall
            ))

            conn.execute(
                "DELETE FROM claims WHERE id = ?",
                (ta_bort,)
            )

            borttagna.append((ta_bort, behall))

            # Markera den borttagna posten så att den inte behandlas igen
            claims[j] = (
                -1, None, "", None, None, None, None
            )

    conn.commit()

    kvar = conn.execute("""
        SELECT id, claim_type, target_type, target, season, claim_text
        FROM claims
        ORDER BY id
    """).fetchall()

    conn.close()

    print()
    print("=" * 45)
    print("CLAIM-STÄDNING KLAR")
    print("=" * 45)
    print(f"Dubbletter borttagna: {len(borttagna)}")
    print(f"Claims kvar: {len(kvar)}")
    print()

    if borttagna:
        for gammal, behallen in borttagna:
            print(f"  Tog bort claim {gammal} → behöll {behallen}")

    print()
    print("KVARVARANDE CLAIMS:")
    print("-" * 45)

    for row in kvar:
        print(row)


if __name__ == "__main__":
    rensa_dubbletter()
