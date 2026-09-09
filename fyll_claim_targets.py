import sqlite3
import re

DB = "dif_hockey.db"


def hitta_target(claim_text, claim_type):
    text = claim_text or ""
    lower = text.lower()

    if claim_type == "kedja":
        match = re.search(
            r"kedja(?:n)?\s+(?:i\s+)?(.+?)(?:,?\s+fortsätt|$)",
            text,
            re.IGNORECASE
        )

        if match:
            return "kedja", match.group(1).strip()

    if claim_type == "lagbygge":
        # Påståenden om lagbygget som helhet
        if any(word in lower for word in [
            "värvning",
            "varvning",
            "pusselbitar",
            "lagbygge",
            "trupp",
            "spelande djurgården"
        ]):
            return "lag", "Djurgården"

    if claim_type == "utveckling":
        return "lag", "Djurgården"

    if claim_type == "malskytte":
        return "lag", "Djurgården"

    if claim_type == "sasong":
        return "lag", "Djurgården"

    if claim_type == "spelare":
        return "spelare", None

    return None, None


def main():
    conn = sqlite3.connect(DB)

    rows = conn.execute("""
        SELECT id, claim_text, claim_type
        FROM claims
        ORDER BY id
    """).fetchall()

    uppdaterade = 0

    for claim_id, claim_text, claim_type in rows:
        target_type, target = hitta_target(
            claim_text,
            claim_type
        )

        if target_type is None:
            continue

        conn.execute("""
            UPDATE claims
            SET target_type = ?,
                target = ?
            WHERE id = ?
        """, (
            target_type,
            target,
            claim_id
        ))

        uppdaterade += 1

    conn.commit()

    print()
    print("=" * 70)
    print("DIF – CLAIM TARGETS")
    print("=" * 70)
    print(f"Claims uppdaterade: {uppdaterade}")
    print()

    rows = conn.execute("""
        SELECT id, claim_type, target_type, target, claim_text
        FROM claims
        ORDER BY id
    """).fetchall()

    for row in rows:
        print(
            f"{row[0]} | "
            f"{row[1]} | "
            f"{row[2]} | "
            f"{row[3]} | "
            f"{row[4]}"
        )

    conn.close()


if __name__ == "__main__":
    main()
