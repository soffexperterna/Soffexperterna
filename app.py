from flask import Flask, request, redirect, url_for
import sqlite3
import os
import shutil
from datetime import datetime
from html import escape

app = Flask(__name__)

DB = "dif_hockey.db"
SEED_DB = "render_seed.sqlite"


# ============================================================
# DATABASE
# ============================================================

def ensure_database():
    if not os.path.exists(DB) and os.path.exists(SEED_DB):
        shutil.copyfile(SEED_DB, DB)


ensure_database()

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# FORUM DATABASE
# ============================================================

def setup_forum():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS forum_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS forum_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


setup_forum()


# ============================================================
# HTML
# ============================================================

def page(title, content):

    css = """
    * {
        box-sizing: border-box;
    }

    body {
        margin: 0;
        background: #101214;
        color: #e7e9eb;
        font-family: Arial, Helvetica, sans-serif;
        line-height: 1.6;
    }

    header {
        background: #17191c;
        border-bottom: 1px solid #30343a;
        padding: 14px 20px;
    }

    .header-inner {
        max-width: 1150px;
        margin: auto;
        display: flex;
        align-items: center;
        gap: 28px;
    }

    .logo {
        height: 68px;
        width: auto;
        object-fit: contain;
    }

    nav {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }

    nav a {
        color: #d9dde1;
        text-decoration: none;
        padding: 9px 13px;
        border-radius: 6px;
        font-size: 14px;
    }

    nav a:hover {
        background: #292d32;
    }

    main {
        max-width: 1150px;
        margin: 35px auto;
        padding: 0 18px;
    }

    h1 {
        font-size: 36px;
        line-height: 1.2;
        margin: 0 0 10px;
    }

    h2 {
        line-height: 1.3;
        margin-top: 0;
    }

    h3 {
        margin-bottom: 8px;
    }

    a {
        color: #b8c8d8;
    }

    .subtitle {
        color: #9ca3aa;
        margin-bottom: 28px;
    }

    .hero {
        background: #181b1f;
        border: 1px solid #343940;
        border-radius: 14px;
        padding: 42px 35px;
        text-align: center;
        margin-bottom: 24px;
    }

    .hero-logo {
        max-width: 260px;
        width: 42%;
        height: auto;
        margin: 0 auto 20px;
        display: block;
    }

    .hero-tagline {
        font-size: 24px;
        font-weight: bold;
        letter-spacing: 0.4px;
        margin-bottom: 18px;
    }

    .hero-intro {
        max-width: 760px;
        margin: auto;
        color: #c5c9ce;
        font-size: 17px;
        text-align: left;
    }

    .hero-intro p {
        margin: 0 0 15px;
    }

    .hero-buttons {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 25px;
    }

    .button {
        display: inline-block;
        background: #343a40;
        color: #ffffff;
        border: 1px solid #4b5259;
        border-radius: 7px;
        padding: 10px 17px;
        text-decoration: none;
    }

    .button:hover {
        background: #454c53;
        color: white;
    }

    .section-title {
        margin: 34px 0 14px;
        font-size: 24px;
    }

    .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 18px;
    }

    .grid-three {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 18px;
    }

    .card {
        background: #191c20;
        border: 1px solid #30353b;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 18px;
    }

    .stat {
        text-align: center;
    }

    .stat-number {
        display: block;
        font-size: 31px;
        font-weight: bold;
        margin-bottom: 3px;
    }

    .stat-label {
        color: #969da5;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .claim {
        border-left: 4px solid #626b75;
    }

    .right {
        border-left-color: #4caf50;
    }

    .wrong {
        border-left-color: #e05252;
    }

    .unknown {
        border-left-color: #b5a44d;
    }

    .badge {
        display: inline-block;
        padding: 5px 9px;
        border-radius: 5px;
        font-size: 13px;
        font-weight: bold;
    }

    .badge-right {
        background: #244c2b;
        color: #8ee89a;
    }

    .badge-wrong {
        background: #542727;
        color: #ff9b9b;
    }

    .badge-unknown {
        background: #4d4724;
        color: #e5d878;
    }

    .badge-neutral {
        background: #30353a;
        color: #c7ccd1;
    }

    .expert-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 15px;
        padding: 12px 0;
        border-bottom: 1px solid #30343a;
    }

    .expert-row:last-child {
        border-bottom: 0;
    }

    .expert-name {
        font-weight: bold;
    }

    .expert-stat {
        color: #9ca3aa;
        font-size: 13px;
        white-space: nowrap;
    }

    .claim-mini {
        padding: 14px 0;
        border-bottom: 1px solid #30343a;
    }

    .claim-mini:last-child {
        border-bottom: 0;
    }

    .claim-mini-text {
        font-size: 16px;
        font-weight: bold;
    }

    .meta {
        color: #8e969e;
        font-size: 13px;
    }

    .comment {
        background: #151719;
        border-radius: 7px;
        padding: 15px;
        margin-top: 10px;
    }

    .hall-card {
        min-height: 190px;
    }

    .how-step {
        text-align: center;
    }

    .how-number {
        font-size: 28px;
        font-weight: bold;
        margin-bottom: 8px;
    }

    table {
        width: 100%;
        border-collapse: collapse;
    }

    th,
    td {
        text-align: left;
        padding: 12px;
        border-bottom: 1px solid #303438;
    }

    th {
        color: #aeb5bc;
    }

    button {
        background: #343a40;
        color: white;
        border: 1px solid #4b5259;
        border-radius: 6px;
        padding: 10px 16px;
        cursor: pointer;
    }

    button:hover {
        background: #454c53;
    }

    button.danger {
        background: #542727;
        border-color: #703333;
    }

    button.danger:hover {
        background: #713333;
    }

    button.small {
        padding: 7px 11px;
        font-size: 13px;
    }

    input,
    textarea {
        width: 100%;
        background: #111315;
        color: white;
        border: 1px solid #3a3f44;
        border-radius: 6px;
        padding: 11px;
        margin-top: 6px;
        margin-bottom: 15px;
    }

    textarea {
        resize: vertical;
    }

    .forum-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 14px;
    }

    .action-form {
        display: inline;
        margin: 0;
    }

    footer {
        max-width: 1150px;
        margin: 50px auto;
        padding: 20px 18px;
        border-top: 1px solid #303438;
        color: #777f87;
        font-size: 13px;
    }

    @media (max-width: 800px) {

        .grid,
        .grid-three {
            grid-template-columns: 1fr;
        }

        .header-inner {
            flex-direction: column;
            align-items: flex-start;
        }

        .hero {
            padding: 30px 20px;
        }
    }

    @media (max-width: 500px) {

        .logo {
            height: 58px;
        }

        h1 {
            font-size: 30px;
        }

        .hero-tagline {
            font-size: 20px;
        }

        .hero-intro {
            font-size: 16px;
        }
    }
    """

    return """
<!DOCTYPE html>
<html lang="sv">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>""" + escape(title) + """ – SOFFEXPERTERNA</title>

<style>
""" + css + """
</style>

</head>

<body>

<header>

<div class="header-inner">

<img
    class="logo"
    src="/static/soffexperterna.png"
    alt="SOFFEXPERTERNA"
>

<nav>

<a href="/">Hem</a>
<a href="/claims">Påståenden</a>
<a href="/experter">Soffexperter</a>
<a href="/forum">Forum</a>
<a href="/ideer">Idélådan</a>
<a href="/om">Om sidan</a>

</nav>

</div>

</header>

<main>
""" + content + """
</main>

<footer>
SOFFEXPERTERNA – Vi minns vad du sa.
</footer>

</body>

</html>
"""


# ============================================================
# HEM
# ============================================================

@app.route("/")
def index():

    conn = get_db()

    claims_count = conn.execute(
        "SELECT COUNT(*) FROM claims"
    ).fetchone()[0]

    comments_count = conn.execute(
        "SELECT COUNT(*) FROM comments"
    ).fetchone()[0]

    experts_count = conn.execute("""
        SELECT COUNT(DISTINCT commenter)
        FROM comments
        WHERE commenter IS NOT NULL
          AND commenter != ''
    """).fetchone()[0]

    decided_count = conn.execute("""
        SELECT COUNT(*)
        FROM claims
        WHERE verdict IN ('RÄTT', 'FEL')
    """).fetchone()[0]

    right_count = conn.execute("""
        SELECT COUNT(*)
        FROM claims
        WHERE verdict = 'RÄTT'
    """).fetchone()[0]

    wrong_count = conn.execute("""
        SELECT COUNT(*)
        FROM claims
        WHERE verdict = 'FEL'
    """).fetchone()[0]

    latest_claims = conn.execute("""
        SELECT
            c.*,
            co.commenter
        FROM claims c
        LEFT JOIN comments co
            ON c.comment_id = co.id
        ORDER BY c.id DESC
        LIMIT 5
    """).fetchall()

    ranking = conn.execute("""
        SELECT
            commenter,
            COUNT(claims.id) AS claims,
            SUM(
                CASE
                    WHEN claims.verdict = 'RÄTT'
                    THEN 1
                    ELSE 0
                END
            ) AS right_count,
            SUM(
                CASE
                    WHEN claims.verdict = 'FEL'
                    THEN 1
                    ELSE 0
                END
            ) AS wrong_count
        FROM comments
        LEFT JOIN claims
            ON claims.comment_id = comments.id
        WHERE commenter IS NOT NULL
          AND commenter != ''
        GROUP BY commenter
        HAVING COUNT(claims.id) > 0
        ORDER BY
            CAST(
                SUM(
                    CASE
                        WHEN claims.verdict = 'RÄTT'
                        THEN 1
                        ELSE 0
                    END
                ) AS REAL
            ) / COUNT(claims.id) DESC,
            COUNT(claims.id) DESC
        LIMIT 5
    """).fetchall()

    most_active = conn.execute("""
        SELECT
            commenter,
            COUNT(*) AS comments
        FROM comments
        WHERE commenter IS NOT NULL
          AND commenter != ''
        GROUP BY commenter
        ORDER BY comments DESC
        LIMIT 1
    """).fetchone()

    hall_fame = conn.execute("""
        SELECT
            commenter,
            COUNT(*) AS right_count
        FROM comments
        JOIN claims
            ON claims.comment_id = comments.id
        WHERE commenter IS NOT NULL
          AND commenter != ''
          AND claims.verdict = 'RÄTT'
        GROUP BY commenter
        ORDER BY right_count DESC
        LIMIT 5
    """).fetchall()

    hall_shame = conn.execute("""
        SELECT
            commenter,
            COUNT(*) AS wrong_count
        FROM comments
        JOIN claims
            ON claims.comment_id = comments.id
        WHERE commenter IS NOT NULL
          AND commenter != ''
          AND claims.verdict = 'FEL'
        GROUP BY commenter
        ORDER BY wrong_count DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    # --------------------------------------------------------
    # SENASTE PÅSTÅENDEN
    # --------------------------------------------------------

    latest_html = ""

    if not latest_claims:

        latest_html = """
        <p class="meta">
        Inga påståenden finns ännu.
        </p>
        """

    else:

        for row in latest_claims:

            verdict = row["verdict"] or "OKLART"

            if verdict == "RÄTT":
                badge = '<span class="badge badge-right">RÄTT</span>'

            elif verdict == "FEL":
                badge = '<span class="badge badge-wrong">FEL</span>'

            else:
                badge = '<span class="badge badge-unknown">OKLART</span>'

            commenter = row["commenter"] or "Okänd soffexpert"

            latest_html += """
            <div class="claim-mini">

                <div>
                    """ + badge + """
                </div>

                <div class="claim-mini-text">
                    """ + escape(row["claim_text"]) + """
                </div>

                <div class="meta">
                    """ + escape(commenter) + """
                    · Påstående #""" + str(row["id"]) + """
                </div>

            </div>
            """

    # --------------------------------------------------------
    # RANKING
    # --------------------------------------------------------

    ranking_html = ""

    if not ranking:

        ranking_html = """
        <p class="meta">
        Ranking byggs upp när påståenden får facit.
        </p>
        """

    else:

        position = 1

        for row in ranking:

            claims = row["claims"] or 0
            right = row["right_count"] or 0
            wrong = row["wrong_count"] or 0

            percentage = 0

            if claims:
                percentage = round((right / claims) * 100)

            ranking_html += """
            <div class="expert-row">

                <div>
                    <span class="expert-name">
                        #""" + str(position) + """
                        <a href=\"""" + url_for(
                            "expert",
                            name=row["commenter"]
                        ) + """\">
                            """ + escape(row["commenter"]) + """
                        </a>
                    </span>
                </div>

                <div class="expert-stat">
                    """ + str(percentage) + """%
                    · """ + str(right) + """ rätt
                    · """ + str(wrong) + """ fel
                </div>

            </div>
            """

            position += 1

    # --------------------------------------------------------
    # MEST AKTIV
    # --------------------------------------------------------

    if most_active:

        most_active_html = """
        <strong>""" + escape(
            most_active["commenter"]
        ) + """</strong>

        <p class="meta">
        """ + str(most_active["comments"]) + """
        registrerade kommentarer
        </p>
        """

    else:

        most_active_html = """
        <p class="meta">
        Ingen aktivitet ännu.
        </p>
        """

    # --------------------------------------------------------
    # HALL OF FAME
    # --------------------------------------------------------

    fame_html = ""

    if not hall_fame:

        fame_html = """
        <p class="meta">
        Ingen har fått RÄTT ännu.
        </p>
        """

    else:

        for row in hall_fame:

            fame_html += """
            <div class="expert-row">

                <div>
                    <a href=\"""" + url_for(
                        "expert",
                        name=row["commenter"]
                    ) + """\">
                        """ + escape(row["commenter"]) + """
                    </a>
                </div>

                <div class="expert-stat">
                    """ + str(row["right_count"]) + """ RÄTT
                </div>

            </div>
            """

    # --------------------------------------------------------
    # HALL OF SHAME
    # --------------------------------------------------------

    shame_html = ""

    if not hall_shame:

        shame_html = """
        <p class="meta">
        Ingen har fått FEL ännu.
        </p>
        """

    else:

        for row in hall_shame:

            shame_html += """
            <div class="expert-row">

                <div>
                    <a href=\"""" + url_for(
                        "expert",
                        name=row["commenter"]
                    ) + """\">
                        """ + escape(row["commenter"]) + """
                    </a>
                </div>

                <div class="expert-stat">
                    """ + str(row["wrong_count"]) + """ FEL
                </div>

            </div>
            """

    # --------------------------------------------------------
    # HEMSIDAN
    # --------------------------------------------------------

    content = """

    <section class="hero">

        <img
            class="hero-logo"
            src="/static/soffexperterna.png"
            alt="SOFFEXPERTERNA"
        >

        <div class="hero-tagline">
            Vi minns vad du sa.
        </div>

        <div class="hero-intro">

            <p>
            Jag är ingen journalist, hockeyanalytiker eller expert.
            Jag är bara en vanlig hockeyintresserad kille som
            tröttnat på alla facebookexperter på nätet.
            och ville göra en rolig grej av det.
            </p>

            <p>
            Därför började jag samla de starka påståendena från
            hockeysupportrar och sedan jämföra dem med vad som
            faktiskt händer.
            </p>

            <p>
            För det är ganska lätt att vara expert när ingen
            minns vad man sa.
            </p>

            <p>
            <strong>Det gör vi.</strong>
            </p>

        </div>

        <div class="hero-buttons">

            <a class="button" href="/claims">
                Se påståenden
            </a>

            <a class="button" href="/experter">
                Se soffexperterna
            </a>

            <a class="button" href="/forum">
                Gå till forumet
            </a>

        </div>

    </section>


    <h2 class="section-title">
        SOFFEXPERTERNA just nu
    </h2>

    <div class="grid-three">

        <div class="card stat">
            <span class="stat-number">
                """ + str(comments_count) + """
            </span>

            <span class="stat-label">
                Kommentarer
            </span>
        </div>

        <div class="card stat">
            <span class="stat-number">
                """ + str(claims_count) + """
            </span>

            <span class="stat-label">
                Påståenden
            </span>
        </div>

        <div class="card stat">
            <span class="stat-number">
                """ + str(experts_count) + """
            </span>

            <span class="stat-label">
                Soffexperter
            </span>
        </div>

    </div>


    <div class="grid">

        <div class="card">

            <h2>
                Senaste påståendena
            </h2>

            """ + latest_html + """

            <p>
                <a href="/claims">
                    Visa alla påståenden →
                </a>
            </p>

        </div>


        <div class="card">

            <h2>
                Facit
            </h2>

            <p>
                """ + str(decided_count) + """
                påståenden har fått ett slutgiltigt facit.
            </p>

            <div class="grid-three">

                <div class="stat">
                    <span class="stat-number">
                        """ + str(right_count) + """
                    </span>

                    <span class="stat-label">
                        Rätt
                    </span>
                </div>

                <div class="stat">
                    <span class="stat-number">
                        """ + str(wrong_count) + """
                    </span>

                    <span class="stat-label">
                        Fel
                    </span>
                </div>

                <div class="stat">
                    <span class="stat-number">
                        """ + str(
                            claims_count - decided_count
                        ) + """
                    </span>

                    <span class="stat-label">
                        Pågår
                    </span>
                </div>

            </div>

        </div>

    </div>


    <div class="grid">

        <div class="card">

            <h2>
                Säsongens ranking
            </h2>

            """ + ranking_html + """

            <p>
                <a href="/experter">
                    Visa hela rankingen →
                </a>
            </p>

        </div>


        <div class="card">

            <h2>
                Mest aktiv
            </h2>

            """ + most_active_html + """

        </div>

    </div>


    <h2 class="section-title">
        Hall of Fame & Hall of Shame
    </h2>

    <div class="grid">

        <div class="card hall-card">

            <h2>
                Hall of Fame
            </h2>

            <p class="meta">
                De som faktiskt fick rätt.
            </p>

            """ + fame_html + """

        </div>


        <div class="card hall-card">

            <h2>
                Hall of Shame
            </h2>

            <p class="meta">
                De mest minnesvärda felaktiga påståendena.
            </p>

            """ + shame_html + """

        </div>

    </div>


    <h2 class="section-title">
        Så fungerar SOFFEXPERTERNA
    </h2>

    <div class="grid-three">

        <div class="card how-step">

            <div class="how-number">
                1
            </div>

            <h3>
                Någon säger något
            </h3>

            <p class="meta">
                Ett starkt påstående från en hockeydiskussion
                fångas upp.
            </p>

        </div>


        <div class="card how-step">

            <div class="how-number">
                2
            </div>

            <h3>
                Vi sparar det
            </h3>

            <p class="meta">
                Påståendet dokumenteras tillsammans med
                personen och sammanhanget.
            </p>

        </div>


        <div class="card how-step">

            <div class="how-number">
                3
            </div>

            <h3>
                Verkligheten avgör
            </h3>

            <p class="meta">
                När det går att avgöra får påståendet
                RÄTT, FEL eller OKLART.
            </p>

        </div>

    </div>

    """

    return page("Hem", content)


# ============================================================
# PÅSTÅENDEN
# ============================================================

@app.route("/claims")
def claims():

    conn = get_db()

    rows = conn.execute("""
        SELECT
            c.*,
            co.commenter
        FROM claims c
        LEFT JOIN comments co
            ON c.comment_id = co.id
        ORDER BY c.id DESC
    """).fetchall()

    conn.close()

    query = request.args.get("q", "").strip()
    status = request.args.get("status", "ALL").strip().upper()

    if status not in {"ALL", "RÄTT", "FEL", "OKLART"}:
        status = "ALL"

    filtered_rows = []
    query_lower = query.casefold()

    for row in rows:
        verdict = row["verdict"] or "OKLART"
        commenter = row["commenter"] or "Okänd soffexpert"
        claim_text = row["claim_text"] or ""

        if status != "ALL" and verdict != status:
            continue

        if query_lower:
            searchable = f"{commenter} {claim_text}".casefold()
            if query_lower not in searchable:
                continue

        filtered_rows.append(row)

    selected_all = " selected" if status == "ALL" else ""
    selected_right = " selected" if status == "RÄTT" else ""
    selected_wrong = " selected" if status == "FEL" else ""
    selected_unknown = " selected" if status == "OKLART" else ""
    search_value = escape(query, quote=True)

    html = f"""
<h1>Påståenden</h1>

<div class="subtitle">
Vi minns vad du sa.
</div>

<div class="card" style="margin-top:20px;">
<form method="GET" action="{url_for('claims')}">

<label for="claim-search"><strong>Sök</strong></label>
<input
    id="claim-search"
    type="text"
    name="q"
    value="{search_value}"
    placeholder="Sök på soffexpert eller påstående..."
    style="width:100%; box-sizing:border-box; margin-top:8px;"
>

<label for="claim-status" style="display:block; margin-top:15px;"><strong>Facit</strong></label>
<select
    id="claim-status"
    name="status"
    style="width:100%; box-sizing:border-box; margin-top:8px; padding:10px; border-radius:8px; border:1px solid #444; background:#181818; color:#fff;"
>
    <option value="ALL"{selected_all}>Alla</option>
    <option value="RÄTT"{selected_right}>RÄTT</option>
    <option value="FEL"{selected_wrong}>FEL</option>
    <option value="OKLART"{selected_unknown}>OKLART</option>
</select>

<div style="margin-top:15px; display:flex; gap:10px; flex-wrap:wrap;">
    <button type="submit" class="button">Filtrera</button>
    <a href="{url_for('claims')}" class="button">Rensa</a>
</div>

</form>
</div>

<div class="meta" style="margin:18px 0;">
Visar {len(filtered_rows)} av {len(rows)} påståenden.
</div>
"""

    if not filtered_rows:
        html += """
<div class="card">
<p>Inga påståenden matchar din sökning.</p>
</div>
"""

    for row in filtered_rows:
        verdict = row["verdict"] or "OKLART"

        if verdict == "RÄTT":
            badge = '<span class="badge badge-right">RÄTT</span>'
            cls = "right"
        elif verdict == "FEL":
            badge = '<span class="badge badge-wrong">FEL</span>'
            cls = "wrong"
        else:
            badge = '<span class="badge badge-unknown">OKLART</span>'
            cls = "unknown"

        commenter = row["commenter"] or "Okänd soffexpert"
        claim_text = row["claim_text"] or ""
        evidence = row["evidence"] or ""

        html += f"""
<div class="card claim {cls}" id="claim-{row['id']}">

<div class="meta">
{escape(commenter)}
</div>

<h3>
{badge}
</h3>

<p>
<strong>{escape(claim_text)}</strong>
</p>
"""

        if evidence:
            html += f"""
<p>
<strong>Verkligheten:</strong><br>
{escape(evidence)}
</p>
"""

        html += f"""
<p class="meta">
Påstående #{row['id']}
</p>

</div>
"""

    return page("Påståenden", html)

# ============================================================
# SOFFEXPERTER
# ============================================================

@app.route("/experter")
def experts():

    conn = get_db()

    rows = conn.execute("""
        SELECT
            commenter,
            COUNT(*) AS comments,
            COUNT(claims.id) AS claims,
            SUM(
                CASE
                    WHEN claims.verdict = 'RÄTT' THEN 1
                    ELSE 0
                END
            ) AS right_count,
            SUM(
                CASE
                    WHEN claims.verdict = 'FEL' THEN 1
                    ELSE 0
                END
            ) AS wrong_count
        FROM comments
        LEFT JOIN claims
            ON claims.comment_id = comments.id
        WHERE commenter IS NOT NULL
          AND commenter != ''
        GROUP BY commenter
        ORDER BY claims DESC, commenter
    """).fetchall()

    conn.close()

    html = """
<h1>Soffexperter</h1>

<div class="subtitle">
Personerna bakom påståendena.
</div>

<div class="card">

<table>

<tr>
<th>Namn</th>
<th>Kommentarer</th>
<th>Påståenden</th>
<th>Rätt</th>
<th>Fel</th>
</tr>
"""

    for row in rows:

        name = row["commenter"]

        html += f"""
<tr>

<td>
<a href="{url_for('expert', name=name)}">
<strong>{escape(name)}</strong>
</a>
</td>

<td>{row["comments"] or 0}</td>
<td>{row["claims"] or 0}</td>
<td>{row["right_count"] or 0}</td>
<td>{row["wrong_count"] or 0}</td>

</tr>
"""

    html += """
</table>

</div>
"""

    return page("Soffexperter", html)


# ============================================================
# EXPERTPROFIL
# ============================================================

@app.route("/expert/<path:name>")
def expert(name):

    conn = get_db()

    rows = conn.execute("""
        SELECT
            c.*,
            co.commenter,
            co.comment_text,
            co.facebook_time
        FROM comments co
        LEFT JOIN claims c
            ON c.comment_id = co.id
        WHERE co.commenter = ?
        ORDER BY co.id DESC
    """, (name,)).fetchall()

    conn.close()

    html = f"""
<h1>{escape(name)}</h1>

<div class="subtitle">
Soffexpertprofil
</div>
"""

    if not rows:

        html += """
<div class="card">
<p>Inga kommentarer hittades.</p>
</div>
"""

        return page(name, html)

    total_comments = len(rows)

    claim_rows = [
        row for row in rows
        if row["id"] is not None
    ]

    right = sum(
        1 for row in claim_rows
        if row["verdict"] == "RÄTT"
    )

    wrong = sum(
        1 for row in claim_rows
        if row["verdict"] == "FEL"
    )

    unknown = sum(
        1 for row in claim_rows
        if row["verdict"] not in ("RÄTT", "FEL")
    )

    html += f"""
<div class="card">

<h2>Statistik</h2>

<table>

<tr>
<th>Kommentarer</th>
<td>{total_comments}</td>
</tr>

<tr>
<th>Påståenden</th>
<td>{len(claim_rows)}</td>
</tr>

<tr>
<th>RÄTT</th>
<td>{right}</td>
</tr>

<tr>
<th>FEL</th>
<td>{wrong}</td>
</tr>

<tr>
<th>OKLART</th>
<td>{unknown}</td>
</tr>

</table>

</div>

<h2>Historik</h2>
"""

    for row in rows:

        if row["id"] is None:

            html += f"""
<div class="card">

<div class="meta">
Kommentar
</div>

<p>
{escape(row["comment_text"])}
</p>
"""

            if row["facebook_time"]:

                html += f"""
<div class="meta">
{escape(row["facebook_time"])}
</div>
"""

            html += "</div>"

            continue

        verdict = row["verdict"] or "OKLART"

        if verdict == "RÄTT":

            badge = '<span class="badge badge-right">RÄTT</span>'
            cls = "right"

        elif verdict == "FEL":

            badge = '<span class="badge badge-wrong">FEL</span>'
            cls = "wrong"

        else:

            badge = '<span class="badge badge-unknown">OKLART</span>'
            cls = "unknown"

        html += f"""
<div class="card claim {cls}">

{badge}

<h3>
{escape(row["claim_text"])}
</h3>

<div class="comment">

<strong>Originalkommentar:</strong>

<p>
{escape(row["comment_text"])}
</p>

</div>
"""

        if row["evidence"]:

            html += f"""
<p>
<strong>Vad som faktiskt hände:</strong><br>
{escape(row["evidence"])}
</p>
"""

        html += f"""
<div class="meta">
Påstående #{row["id"]}
</div>

</div>
"""

    return page(name, html)


# ============================================================
# FORUM – STARTSIDA
# ============================================================

@app.route("/forum", methods=["GET", "POST"])
def forum():

    conn = get_db()

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        message = request.form.get(
            "message",
            ""
        ).strip()

        if username and title and message:

            conn.execute("""
                INSERT INTO forum_threads
                (
                    title,
                    username,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                username,
                title,
                message,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ))

            conn.commit()

        conn.close()

        return redirect(url_for("forum"))

    threads = conn.execute("""
        SELECT *
        FROM forum_threads
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    html = """
<h1>Forum</h1>

<div class="subtitle">
Diskutera Djurgården och SOFFEXPERTERNA.
</div>

<div class="card">

<h2>Starta en tråd</h2>

<form method="POST">

<label>Användarnamn</label>

<input
    type="text"
    name="username"
    maxlength="40"
    required
>

<label>Rubrik</label>

<input
    type="text"
    name="title"
    maxlength="120"
    required
>

<label>Meddelande</label>

<textarea
    name="message"
    rows="5"
    maxlength="2000"
    required
></textarea>

<button type="submit">
Starta tråd
</button>

</form>

</div>
"""

    for thread in threads:

        html += f"""
<div class="card">

<h2>
<a href="{url_for('forum_thread', thread_id=thread['id'])}">
{escape(thread["title"])}
</a>
</h2>

<p>
{escape(thread["message"])}
</p>

<div class="meta">
{escape(thread["username"])} · {escape(thread["created_at"])}
</div>

</div>
"""

    return page("Forum", html)


# ============================================================
# REDIGERA TRÅD
# ============================================================

@app.route("/forum/<int:thread_id>/edit", methods=["GET", "POST"])
def edit_thread(thread_id):

    conn = get_db()

    thread = conn.execute("""
        SELECT *
        FROM forum_threads
        WHERE id = ?
    """, (thread_id,)).fetchone()

    if thread is None:

        conn.close()

        return page(
            "Hittades inte",
            """
            <div class="card">
            <h2>Tråden hittades inte.</h2>
            </div>
            """
        ), 404

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        message = request.form.get(
            "message",
            ""
        ).strip()

        if username != thread["username"]:

            conn.close()

            return page(
                "Fel användarnamn",
                """
                <div class="card">
                <h2>Fel användarnamn</h2>
                <p>
                Använd samma användarnamn som användes när
                tråden skapades.
                </p>
                </div>
                """
            ), 403

        if title and message:

            conn.execute("""
                UPDATE forum_threads
                SET title = ?, message = ?
                WHERE id = ?
            """, (
                title,
                message,
                thread_id
            ))

            conn.commit()

        conn.close()

        return redirect(
            url_for(
                "forum_thread",
                thread_id=thread_id
            )
        )

    content = f"""
<h1>Redigera tråd</h1>

<div class="card">

<form method="POST">

<label>Användarnamn</label>

<input
    type="text"
    name="username"
    maxlength="40"
    required
>

<label>Rubrik</label>

<input
    type="text"
    name="title"
    maxlength="120"
    value="{escape(thread["title"])}"
    required
>

<label>Meddelande</label>

<textarea
    name="message"
    rows="7"
    maxlength="2000"
    required
>{escape(thread["message"])}</textarea>

<button type="submit">
Spara ändringar
</button>

</form>

</div>
"""

    conn.close()

    return page("Redigera tråd", content)


# ============================================================
# TA BORT TRÅD
# ============================================================

@app.route(
    "/forum/<int:thread_id>/delete",
    methods=["POST"]
)
def delete_thread(thread_id):

    conn = get_db()

    thread = conn.execute("""
        SELECT *
        FROM forum_threads
        WHERE id = ?
    """, (thread_id,)).fetchone()

    if thread is None:

        conn.close()

        return redirect(url_for("forum"))

    username = request.form.get(
        "username",
        ""
    ).strip()

    if username != thread["username"]:

        conn.close()

        return page(
            "Fel användarnamn",
            """
            <div class="card">
            <h2>Fel användarnamn</h2>
            <p>
            Tråden kunde inte tas bort.
            </p>
            </div>
            """
        ), 403

    conn.execute("""
        DELETE FROM forum_replies
        WHERE thread_id = ?
    """, (thread_id,))

    conn.execute("""
        DELETE FROM forum_threads
        WHERE id = ?
    """, (thread_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("forum"))


# ============================================================
# FORUMTRÅD
# ============================================================

@app.route(
    "/forum/<int:thread_id>",
    methods=["GET", "POST"]
)
def forum_thread(thread_id):

    conn = get_db()

    thread = conn.execute("""
        SELECT *
        FROM forum_threads
        WHERE id = ?
    """, (thread_id,)).fetchone()

    if thread is None:

        conn.close()

        return page(
            "Hittades inte",
            """
            <div class="card">
            <h2>Tråden hittades inte.</h2>
            </div>
            """
        ), 404

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        message = request.form.get(
            "message",
            ""
        ).strip()

        if username and message:

            conn.execute("""
                INSERT INTO forum_replies
                (
                    thread_id,
                    username,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                thread_id,
                username,
                message,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ))

            conn.commit()

        conn.close()

        return redirect(
            url_for(
                "forum_thread",
                thread_id=thread_id
            )
        )

    replies = conn.execute("""
        SELECT *
        FROM forum_replies
        WHERE thread_id = ?
        ORDER BY id ASC
    """, (thread_id,)).fetchall()

    conn.close()

    content = f"""
<h1>{escape(thread["title"])}</h1>

<div class="card">

<p>
{escape(thread["message"])}
</p>

<div class="meta">
Startad av {escape(thread["username"])}
· {escape(thread["created_at"])}
</div>

<div class="forum-actions">

<a href="{url_for('edit_thread', thread_id=thread_id)}">
<button type="button" class="small">
Redigera tråd
</button>
</a>

<form
    class="action-form"
    method="POST"
    action="{url_for('delete_thread', thread_id=thread_id)}"
    onsubmit="return confirm('Vill du verkligen ta bort hela tråden? Alla svar tas också bort.');"
>

<input
    type="text"
    name="username"
    placeholder="Ditt användarnamn"
    maxlength="40"
    required
    style="width:180px;margin:0 5px 0 0;"
>

<button
    type="submit"
    class="danger small"
>
Ta bort tråd
</button>

</form>

</div>

</div>

<h2>Svar</h2>
"""

    if not replies:

        content += """
<div class="card">
<p>
Inga svar ännu.
</p>
</div>
"""

    for reply in replies:

        content += f"""
<div class="card">

<p>
{escape(reply["message"])}
</p>

<div class="meta">
{escape(reply["username"])} · {escape(reply["created_at"])}
</div>

<div class="forum-actions">

<a href="{url_for('edit_reply', reply_id=reply['id'])}">
<button type="button" class="small">
Redigera
</button>
</a>

<form
    class="action-form"
    method="POST"
    action="{url_for('delete_reply', reply_id=reply['id'])}"
    onsubmit="return confirm('Vill du verkligen ta bort detta svar?');"
>

<input
    type="text"
    name="username"
    placeholder="Ditt användarnamn"
    maxlength="40"
    required
    style="width:180px;margin:0 5px 0 0;"
>

<button
    type="submit"
    class="danger small"
>
Ta bort
</button>

</form>

</div>

</div>
"""

    content += """
<div class="card">

<h2>Svara</h2>

<form method="POST">

<label>Användarnamn</label>

<input
    type="text"
    name="username"
    maxlength="40"
    required
>

<label>Meddelande</label>

<textarea
    name="message"
    rows="5"
    maxlength="2000"
    required
></textarea>

<button type="submit">
Svara
</button>

</form>

</div>
"""

    return page(
        thread["title"],
        content
    )


# ============================================================
# REDIGERA SVAR
# ============================================================

@app.route(
    "/forum/reply/<int:reply_id>/edit",
    methods=["GET", "POST"]
)
def edit_reply(reply_id):

    conn = get_db()

    reply = conn.execute("""
        SELECT *
        FROM forum_replies
        WHERE id = ?
    """, (reply_id,)).fetchone()

    if reply is None:

        conn.close()

        return page(
            "Hittades inte",
            """
            <div class="card">
            <h2>Svaret hittades inte.</h2>
            </div>
            """
        ), 404

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        message = request.form.get(
            "message",
            ""
        ).strip()

        if username != reply["username"]:

            conn.close()

            return page(
                "Fel användarnamn",
                """
                <div class="card">
                <h2>Fel användarnamn</h2>
                <p>
                Använd samma användarnamn som användes
                när svaret skapades.
                </p>
                </div>
                """
            ), 403

        if message:

            conn.execute("""
                UPDATE forum_replies
                SET message = ?
                WHERE id = ?
            """, (
                message,
                reply_id
            ))

            conn.commit()

        thread_id = reply["thread_id"]

        conn.close()

        return redirect(
            url_for(
                "forum_thread",
                thread_id=thread_id
            )
        )

    content = f"""
<h1>Redigera svar</h1>

<div class="card">

<form method="POST">

<label>Användarnamn</label>

<input
    type="text"
    name="username"
    maxlength="40"
    required
>

<label>Meddelande</label>

<textarea
    name="message"
    rows="7"
    maxlength="2000"
    required
>{escape(reply["message"])}</textarea>

<button type="submit">
Spara ändringar
</button>

</form>

</div>
"""

    conn.close()

    return page("Redigera svar", content)


# ============================================================
# TA BORT SVAR
# ============================================================

@app.route(
    "/forum/reply/<int:reply_id>/delete",
    methods=["POST"]
)
def delete_reply(reply_id):

    conn = get_db()

    reply = conn.execute("""
        SELECT *
        FROM forum_replies
        WHERE id = ?
    """, (reply_id,)).fetchone()

    if reply is None:

        conn.close()

        return redirect(url_for("forum"))

    username = request.form.get(
        "username",
        ""
    ).strip()

    if username != reply["username"]:

        conn.close()

        return page(
            "Fel användarnamn",
            """
            <div class="card">
            <h2>Fel användarnamn</h2>
            <p>
            Svaret kunde inte tas bort.
            </p>
            </div>
            """
        ), 403

    thread_id = reply["thread_id"]

    conn.execute("""
        DELETE FROM forum_replies
        WHERE id = ?
    """, (reply_id,))

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "forum_thread",
            thread_id=thread_id
        )
    )


# ============================================================
# IDÉLÅDAN
# ============================================================

@app.route("/ideer", methods=["GET", "POST"])
def ideas():

    if request.method == "POST":

        idea = request.form.get(
            "idea",
            ""
        ).strip()

        if idea:

            with open(
                "ideer.txt",
                "a",
                encoding="utf-8"
            ) as f:

                f.write(
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    + " | "
                    + idea
                    + "\n"
                )

        return redirect(url_for("ideas"))

    content = """
<h1>Idélådan</h1>

<div class="subtitle">
Har du en idé på något som borde finnas på sidan?
</div>

<div class="card">

<form method="POST">

<label>Din idé</label>

<textarea
    name="idea"
    rows="6"
    maxlength="3000"
    required
></textarea>

<button type="submit">
Skicka idé
</button>

</form>

</div>
"""

    return page("Idélådan", content)


# ============================================================
# OM SIDAN
# ============================================================

@app.route("/om")
def about():

    content = """
<h1>Om SOFFEXPERTERNA</h1>

<div class="card">

<h2>
Vi minns vad du sa.
</h2>

<p>
Jag är ingen journalist, hockeyanalytiker eller expert.
Jag är bara en vanlig hockeyintresserad kille som tröttnat
på alla tvärsäkra uttalanden på nätet.
</p>

<p>
Därför började jag samla de starka påståendena från
hockeysupportrar och jämföra dem med vad som faktiskt händer.
</p>

<p>
Det handlar inte om att vara bäst på att gissa.
Det handlar om att kunna gå tillbaka och se vad som faktiskt
sades.
</p>

<p>
När verkligheten sedan ger oss ett svar får påståendet ett facit:
<strong>RÄTT</strong>, <strong>FEL</strong> eller <strong>OKLART</strong>.
</p>

<p>
Sidan börjar med Djurgården Hockey men är byggd så att
fler lag kan läggas till senare.
</p>

<h2>Hur träffsäkert är det?</h2>

<p>
SOFFEXPERTERNA är ett hobbyprojekt och ska framför allt vara roligt.
</p>

<p>
Vi försöker vara så noggranna vi kan, men systemet är
<strong>inte 110 % träffsäkert</strong>. Kommentarer kan vara otydliga,
ironi kan missförstås och ett påstående kan ibland tolkas på olika sätt.
</p>

<p>
Därför ska statistiken ses som underhållning och inte som någon
vetenskaplig sanning.
</p>

<p>
<strong>Verkligheten bestämmer facit – men vi kan fortfarande göra fel
när vi tolkar vad som faktiskt sades.</strong>
</p>

</div>
"""

    return page("Om sidan", content)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
