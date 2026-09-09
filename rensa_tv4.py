import sqlite3

DB = "dif_hockey.db"


def rensa():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Hämta TV4-källans ID
    row = cur.execute("""
        SELECT id
        FROM sources
        WHERE name = 'TV4 Hockey'
    """).fetchone()

    if not row:
        print("TV4 Hockey finns inte i sources.")
        conn.close()
        return

    tv4_id = row[0]

    # Claims som hör till TV4-kommentarer tas bort först
    cur.execute("""
        DELETE FROM claims
        WHERE comment_id IN (
            SELECT comments.id
            FROM comments
            JOIN posts
                ON posts.id = comments.post_id
            WHERE posts.source_id = ?
        )
    """, (tv4_id,))

    claims_bort = cur.rowcount

    # Därefter kommentarerna
    cur.execute("""
        DELETE FROM comments
        WHERE post_id IN (
            SELECT id
            FROM posts
            WHERE source_id = ?
        )
    """, (tv4_id,))

    kommentarer_bort = cur.rowcount

    # Och slutligen TV4-inläggen
    cur.execute("""
        DELETE FROM posts
        WHERE source_id = ?
    """, (tv4_id,))

    poster_bort = cur.rowcount

    conn.commit()

    print("=" * 45)
    print("TV4-RENSNING KLAR")
    print("=" * 45)
    print(f"Poster borttagna:       {poster_bort}")
    print(f"Kommentarer borttagna:  {kommentarer_bort}")
    print(f"Claims borttagna:       {claims_bort}")
    print("=" * 45)

    conn.close()


if __name__ == "__main__":
    rensa()
