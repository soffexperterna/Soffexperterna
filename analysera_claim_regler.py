import sqlite3
import re

DB = "dif_hockey.db"


def analysera_claim(claim_type, target_type, target, text):
    text_lag = text.lower()

    metric = None
    threshold = None
    rule = None

    # --------------------------------------------------
    # KEDJA / FORMATION
    # --------------------------------------------------
    if claim_type == "kedja":
        metric = "kedjans prestation"
        rule = (
            "Bedöm kedjan mot verkliga match- och spelarstatistik "
            "under säsongen. Kräver tillräckligt med matcher för "
            "att kunna avgöra om kedjan faktiskt fungerat bra."
        )

    # --------------------------------------------------
    # LAGBYGGE – SAKNADE PUSSELBITAR
    # --------------------------------------------------
    elif claim_type == "lagbygge" and (
        "saknar" in text_lag
        or "pusselbitar" in text_lag
    ):
        metric = "lagbygge"
        rule = (
            "Kontrollera vilka ytterligare spelare Djurgården "
            "värvar efter påståendet och om truppen senare "
            "kompletteras på de positioner som bedöms saknas."
        )

    # --------------------------------------------------
    # LAGBYGGE – BEHÖVER VÄRVNING
    # --------------------------------------------------
    elif claim_type == "lagbygge" and (
        "behöver" in text_lag
        or "värvning" in text_lag
        or "värva" in text_lag
    ):
        metric = "truppförstärkning"
        rule = (
            "Kontrollera om Djurgården gör ytterligare värvningar "
            "efter påståendet. Påståendet kan inte avgöras enbart "
            "av att en spelare värvas; även sammanhanget måste vägas in."
        )

    # --------------------------------------------------
    # UTVECKLING
    # --------------------------------------------------
    elif claim_type == "utveckling":
        metric = "lagets utveckling"
        rule = (
            "Jämför Djurgårdens prestationer efter påståendet "
            "med prestationerna före påståendet. Kräver flera "
            "matcher för att avgöra utvecklingen."
        )

    # --------------------------------------------------
    # GENERELL LAGKVALITET
    # --------------------------------------------------
    elif claim_type == "lagkvalitet":
        metric = "lagprestation"
        rule = (
            "Bedöm mot resultat, tabellplacering och relevant "
            "matchstatistik under säsongen."
        )

    # --------------------------------------------------
    # SPELARE
    # --------------------------------------------------
    elif target_type == "spelare":
        metric = "spelarprestation"
        rule = (
            "Bedöm mot spelarens faktiska statistik och prestation "
            "under relevant period."
        )

    # --------------------------------------------------
    # FALLBACK
    # --------------------------------------------------
    else:
        metric = "manuell bedömning"
        rule = (
            "Påståendet behöver analyseras manuellt eftersom "
            "ingen tillräckligt tydlig automatisk mätregel finns ännu."
        )

    return metric, threshold, rule


def analysera_alla():
    conn = sqlite3.connect(DB)

    claims = conn.execute("""
        SELECT
            id,
            claim_text,
            claim_type,
            target_type,
            target
        FROM claims
        ORDER BY id
    """).fetchall()

    uppdaterade = 0

    for claim_id, text, claim_type, target_type, target in claims:
        metric, threshold, rule = analysera_claim(
            claim_type,
            target_type,
            target,
            text
        )

        conn.execute("""
            UPDATE claims
            SET
                metric = ?,
                threshold = ?,
                evaluation_rule = ?
            WHERE id = ?
        """, (
            metric,
            threshold,
            rule,
            claim_id
        ))

        uppdaterade += 1

        print()
        print(f"CLAIM {claim_id}")
        print(f"Påstående: {text}")
        print(f"Mätning:   {metric}")
        print(f"Regel:     {rule}")

    conn.commit()

    print()
    print("=" * 50)
    print("ANALYS KLAR")
    print("=" * 50)
    print(f"Claims analyserade: {uppdaterade}")

    conn.close()


if __name__ == "__main__":
    analysera_alla()
