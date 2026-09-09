import sqlite3

DB = "dif_hockey.db"


def skapa_falt():
    conn = sqlite3.connect(DB)

    kolumner = {
        "metric": "TEXT",
        "threshold": "TEXT",
        "evaluation_rule": "TEXT",
    }

    befintliga = {
        row[1]
        for row in conn.execute("PRAGMA table_info(claims)").fetchall()
    }

    tillagda = 0

    for namn, typ in kolumner.items():
        if namn not in befintliga:
            conn.execute(
                f"ALTER TABLE claims ADD COLUMN {namn} {typ}"
            )
            print(f"TILLAGD: {namn}")
            tillagda += 1
        else:
            print(f"FINNS REDAN: {namn}")

    conn.commit()

    print()
    print("=" * 45)
    print("CLAIM-REGLER KLARA")
    print("=" * 45)
    print(f"Nya kolumner: {tillagda}")

    print()
    print("CLAIMS:")
    print("-" * 45)

    claims = conn.execute("""
        SELECT
            id,
            claim_type,
            target_type,
            target,
            season,
            metric,
            threshold,
            evaluation_rule
        FROM claims
        ORDER BY id
    """).fetchall()

    for claim in claims:
        print(claim)

    conn.close()


if __name__ == "__main__":
    skapa_falt()
