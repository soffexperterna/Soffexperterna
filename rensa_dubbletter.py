import sqlite3
import re

DB = "dif_hockey.db"


def normalisera(text):
    if not text:
        return ""

    text = text.lower()

    # Ta bort Facebooks numeriska metadata längst bak
    text = re.sub(r"\s+\d{1,3}\s*$", "", text)

    # Normalisera whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def rensa():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Hämta alla kommentarer
    cur.execute("""
        SELECT
            id,
            post_id,
            commenter,
            comment_text,
            facebook_time
        FROM comments
        ORDER BY id
    """)

    kommentarer = cur.fetchall()

    grupper = {}

    for row in kommentarer:

        comment_id = row[0]
        post_id = row[1]
        commenter = row[2] or ""
        comment_text = row[3] or ""
        facebook_time = row[4] or ""

        nyckel = (
            post_id,
            commenter.strip().lower(),
            normalisera(comment_text)
        )

        grupper.setdefault(
            nyckel,
            []
        ).append(row)

    dubletter = []

    for nyckel, rows in grupper.items():

        if len(rows) <= 1:
            continue

        # Behåll äldsta kommentaren
        rows.sort(key=lambda x: x[0])

        behall = rows[0]

        for duplicate in rows[1:]:

            dubletter.append(
                (
                    behall[0],
                    duplicate[0]
                )
            )

    print("=" * 50)
    print("DUBLETTRÄNSNING")
    print("=" * 50)

    if not dubletter:

        print("Inga dubbletter hittades.")

        conn.close()
        return

    print(
        f"Hittade {len(dubletter)} dubbletter."
    )

    claims_bort = 0
    kommentarer_bort = 0

    for behall_id, duplicate_id in dubletter:

        # Ta bort claims som pekar på dubletten
        cur.execute("""
            DELETE FROM claims
            WHERE comment_id = ?
        """, (duplicate_id,))

        claims_bort += cur.rowcount

        # Ta bort själva kommentaren
        cur.execute("""
            DELETE FROM comments
            WHERE id = ?
        """, (duplicate_id,))

        kommentarer_bort += cur.rowcount

        print(
            f"Behåller kommentar {behall_id} "
            f"-> tar bort {duplicate_id}"
        )

    conn.commit()

    cur.execute(
        "SELECT COUNT(*) FROM comments"
    )

    totalt_kommentarer = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM claims"
    )

    totalt_claims = cur.fetchone()[0]

    conn.close()

    print()
    print("=" * 50)
    print("KLART")
    print("=" * 50)
    print(
        f"Kommentarer borttagna: {kommentarer_bort}"
    )
    print(
        f"Claims borttagna:      {claims_bort}"
    )
    print(
        f"Kommentarer kvar:      {totalt_kommentarer}"
    )
    print(
        f"Claims kvar:           {totalt_claims}"
    )
    print("=" * 50)


if __name__ == "__main__":
    rensa()
