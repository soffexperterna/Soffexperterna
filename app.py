from flask import Flask, request, redirect, url_for, session
import sqlite3
from datetime import datetime
from html import escape
import re
import secrets
import os
from functools import wraps

app = Flask(__name__)

DB = "dif_hockey.db"


# ============================================================
# ADMIN / MILJÖINSTÄLLNINGAR
# ============================================================

def load_local_env():
    """Läser enkla KEY=VALUE-inställningar från projektets .env."""
    env_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".env"
    )

    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if (
                    len(value) >= 2
                    and value[0] == value[-1]
                    and value[0] in ('"', "'")
                ):
                    value = value[1:-1]

                os.environ.setdefault(key, value)
    except OSError:
        pass


load_local_env()

ADMIN_PASSWORD = os.environ.get("SOFF_ADMIN_PASSWORD", "")
SECRET_KEY = os.environ.get("SOFF_SECRET_KEY", "")

if not ADMIN_PASSWORD or not SECRET_KEY:
    raise RuntimeError(
        "SOFF_ADMIN_PASSWORD och SOFF_SECRET_KEY måste finnas i .env"
    )

app.secret_key = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            next_url = request.full_path
            if next_url.endswith("?"):
                next_url = next_url[:-1]
            return redirect(
                url_for("admin_login", next=next_url)
            )
        return view(*args, **kwargs)

    return wrapped


# ============================================================
# DATABASE
# ============================================================

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
            created_at TEXT NOT NULL,
            edit_token TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS forum_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            edit_token TEXT
        )
    """)

    for table in ("forum_threads", "forum_replies"):
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "edit_token" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN edit_token TEXT")

    conn.commit()
    conn.close()


setup_forum()


def is_admin():
    return bool(session.get("admin_logged_in"))


def can_manage_forum_item(row):
    if is_admin():
        return True

    saved = row["edit_token"] or ""
    if not saved:
        return False

    tokens = session.get("forum_tokens", {})
    token = (
        tokens.get(f"forum_thread:{row['id']}", "")
        or tokens.get(f"forum_reply:{row['id']}", "")
        or tokens.get(str(row['id']), "")
    )

    if token and secrets.compare_digest(token, saved):
        return True

    # Behåll stöd för den äldre cookie-lösningen så befintliga inlägg
    # inte plötsligt tappar sin ägarskapstoken.
    legacy_token = request.cookies.get("forum_author_token", "")
    return bool(
        legacy_token
        and secrets.compare_digest(legacy_token, saved)
    )


def remember_forum_token(item_type, item_id, token):
    tokens = dict(session.get("forum_tokens", {}))
    tokens[f"{item_type}:{item_id}"] = token
    session["forum_tokens"] = tokens
    session.modified = True


def set_forum_token(response, token):
    response.set_cookie(
        "forum_author_token",
        token,
        httponly=True,
        samesite="Lax",
        max_age=60 * 60 * 24 * 365 * 2
    )
    return response


# ============================================================
# SOFFEXPERT-SYSTEM – HJÄLPFUNKTIONER
# ============================================================

MIN_CLAIMS_FOR_RANKING = 3


def season_from_date(value):
    if not value:
        now = datetime.now()
        start_year = now.year if now.month >= 8 else now.year - 1
        return f"{start_year}/{str(start_year + 1)[-2:]}"

    text_value = str(value)

    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text_value)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        start_year = year if month >= 8 else year - 1
        return f"{start_year}/{str(start_year + 1)[-2:]}"

    match = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})", text_value)
    if match:
        first = int(match.group(1))
        second = int(match.group(2))
        year = int(match.group(3))
        month = second if first > 12 else first
        start_year = year if month >= 8 else year - 1
        return f"{start_year}/{str(start_year + 1)[-2:]}"

    return season_from_date(None)


def claim_tag(claim_type, claim_text=""):
    value = f"{claim_type or ''} {claim_text or ''}".casefold()

    groups = [
        ("#transfer", ["värvar", "värva", "värvning", "nyförvärv", "transfer", "kontrakt", "signar", "signering"]),
        ("#målvakt", ["målvakt", "målvakten", "keeper", "målvakter"]),
        ("#tränare", ["tränare", "coach", "tränarn", "ledare"]),
        ("#tabellplacering", ["tabell", "slutspel", "kval", "placering", "etta", "tvåa", "trea", "sist"]),
        ("#mål/poäng", ["mål", "målgörare", "målskytt", "poäng", "assist"]),
        ("#kedja", ["kedja", "formation", "femma", "backpar"]),
        ("#spelare", ["spelare", "floppar", "levererar"]),
    ]

    for tag, words in groups:
        if any(word in value for word in words):
            return tag

    return "#övrigt"


def ranking_stats(rows):
    result = {}

    for row in rows:
        name = row["commenter"] or "Okänd soffexpert"
        verdict = row["verdict"] or "OKLART"

        if name not in result:
            result[name] = {"claims": 0, "right": 0, "wrong": 0, "points": 0}

        if verdict not in ("RÄTT", "FEL"):
            continue

        result[name]["claims"] += 1

        if verdict == "RÄTT":
            result[name]["right"] += 1
            result[name]["points"] += 1
        else:
            result[name]["wrong"] += 1

    ranked = []

    for name, stats in result.items():
        if stats["claims"] < MIN_CLAIMS_FOR_RANKING:
            continue

        stats["name"] = name
        stats["percentage"] = round(stats["right"] / stats["claims"] * 100)
        ranked.append(stats)

    ranked.sort(
        key=lambda item: (
            -item["percentage"],
            -item["right"],
            item["wrong"],
            -item["claims"],
            item["name"].casefold()
        )
    )

    return ranked


# ============================================================
# HTML
# ============================================================

def page(title, content):

    css = """
    * {
        box-sizing: border-box;
    }

    html {
        scroll-behavior: smooth;
    }

    body {
        margin: 0;
        background:
            radial-gradient(circle at 50% -20%, #242930 0, #15181c 34%, #0d0f11 78%);
        color: #e9edf1;
        font-family: Arial, Helvetica, sans-serif;
        line-height: 1.65;
        min-height: 100vh;
    }

    header {
        background: rgba(18, 21, 24, 0.96);
        border-bottom: 1px solid #353a40;
        padding: 12px 20px;
        position: sticky;
        top: 0;
        z-index: 100;
        backdrop-filter: blur(10px);
    }

    .header-inner {
        max-width: 1180px;
        margin: auto;
        display: flex;
        align-items: center;
        gap: 30px;
    }

    .logo {
        height: 62px;
        width: auto;
        object-fit: contain;
        flex: 0 0 auto;
    }

    nav {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        align-items: center;
    }

    nav a {
        color: #cfd5da;
        text-decoration: none;
        padding: 9px 12px;
        border-radius: 8px;
        font-size: 14px;
        transition: background 0.15s ease, color 0.15s ease;
    }

    nav a:hover {
        background: #292e34;
        color: #ffffff;
    }

    main {
        max-width: 1180px;
        margin: 42px auto;
        padding: 0 20px;
    }

    h1 {
        font-size: clamp(30px, 4vw, 42px);
        line-height: 1.15;
        margin: 0 0 10px;
        letter-spacing: -0.6px;
    }

    h2 {
        line-height: 1.3;
        margin-top: 0;
        letter-spacing: -0.2px;
    }

    h3 {
        margin-bottom: 8px;
    }

    a {
        color: #c2d0dc;
        transition: color 0.15s ease;
    }

    a:hover {
        color: #ffffff;
    }

    .subtitle {
        color: #929aa3;
        margin-bottom: 28px;
    }

    .hero {
        background:
            linear-gradient(145deg, rgba(31, 35, 40, 0.98), rgba(21, 24, 28, 0.98));
        border: 1px solid #3a4047;
        border-radius: 18px;
        padding: 48px 38px;
        text-align: center;
        margin-bottom: 28px;
        box-shadow: 0 18px 45px rgba(0, 0, 0, 0.24);
    }

    .hero-logo {
        max-width: 260px;
        width: 42%;
        height: auto;
        margin: 0 auto 22px;
        display: block;
        filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.28));
    }

    .hero-tagline {
        font-size: 25px;
        font-weight: bold;
        letter-spacing: 0.3px;
        margin-bottom: 20px;
    }

    .hero-intro {
        max-width: 760px;
        margin: auto;
        color: #c5cbd1;
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
        margin-top: 28px;
    }

    .button {
        display: inline-block;
        background: linear-gradient(180deg, #3b4148, #30353b);
        color: #ffffff;
        border: 1px solid #515860;
        border-radius: 9px;
        padding: 10px 17px;
        text-decoration: none;
        font-weight: 600;
        transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease;
    }

    .button:hover {
        background: linear-gradient(180deg, #484f57, #383e45);
        color: white;
        border-color: #666e77;
        transform: translateY(-1px);
    }

    .section-title {
        margin: 38px 0 15px;
        font-size: 25px;
    }

    .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 20px;
    }

    .grid-three {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 20px;
    }

    .card {
        background: linear-gradient(145deg, #1a1e23, #16191d);
        border: 1px solid #32383f;
        border-radius: 13px;
        padding: 21px;
        margin-bottom: 20px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
    }

    .card:hover {
        border-color: #414850;
    }

    .stat {
        text-align: center;
        padding: 24px 18px;
    }

    .stat-number {
        display: block;
        font-size: 34px;
        font-weight: bold;
        margin-bottom: 3px;
        letter-spacing: -0.5px;
    }

    .stat-label {
        color: #929aa3;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }

    .claim {
        border-left: 4px solid #68717a;
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
        padding: 5px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: bold;
        letter-spacing: 0.3px;
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
        padding: 13px 0;
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
        padding: 15px 0;
        border-bottom: 1px solid #30343a;
    }

    .claim-mini:last-child {
        border-bottom: 0;
    }

    .claim-mini-text {
        font-size: 16px;
        font-weight: bold;
        margin: 6px 0;
    }

    .meta {
        color: #8e969e;
        font-size: 13px;
    }

    .comment {
        background: #131619;
        border: 1px solid #292e33;
        border-radius: 9px;
        padding: 15px;
        margin-top: 10px;
    }

    .how-step {
        text-align: center;
    }

    .how-number {
        font-size: 29px;
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
        padding: 13px 12px;
        border-bottom: 1px solid #303438;
    }

    th {
        color: #aeb5bc;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.35px;
    }

    tr:last-child td {
        border-bottom: 0;
    }

    button {
        background: linear-gradient(180deg, #3b4148, #30353b);
        color: white;
        border: 1px solid #515860;
        border-radius: 9px;
        padding: 10px 16px;
        cursor: pointer;
        font-weight: 600;
    }

    button:hover {
        background: linear-gradient(180deg, #484f57, #383e45);
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
    textarea,
    select {
        width: 100%;
        background: #101316;
        color: white;
        border: 1px solid #3a4148;
        border-radius: 8px;
        padding: 11px 12px;
        margin-top: 6px;
        margin-bottom: 15px;
        font: inherit;
    }

    input:focus,
    textarea:focus,
    select:focus {
        outline: none;
        border-color: #68727c;
        box-shadow: 0 0 0 3px rgba(104, 114, 124, 0.14);
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
        max-width: 1180px;
        margin: 55px auto 30px;
        padding: 22px 20px;
        border-top: 1px solid #303438;
        color: #777f87;
        font-size: 13px;
        text-align: center;
    }

    @media (max-width: 800px) {
        .grid,
        .grid-three {
            grid-template-columns: 1fr;
        }

        .header-inner {
            flex-direction: column;
            align-items: center;
            gap: 12px;
        }

        nav {
            justify-content: center;
        }

        .hero {
            padding: 34px 22px;
        }

        .hero-logo {
            width: 55%;
        }
    }

    @media (max-width: 500px) {
        header {
            padding: 10px 12px;
        }

        .logo {
            height: 54px;
        }

        nav a {
            padding: 8px 9px;
            font-size: 13px;
        }

        main {
            margin: 28px auto;
            padding: 0 13px;
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

        .hero-logo {
            width: 68%;
        }

        .card {
            padding: 17px;
        }

        table {
            display: block;
            overflow-x: auto;
            white-space: nowrap;
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
<a href="/ranking">Ranking</a>
<a href="/forum">Forum</a>
<a href="/ideer">Idélådan</a>
<a href="/om">Om sidan</a>
<a href="/admin">Admin</a>

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
# ADMININLOGGNING
# ============================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    error = ""
    next_url = request.args.get("next", "")

    if request.method == "POST":

        password = request.form.get("password", "")
        next_url = request.form.get("next", "")

        if secrets.compare_digest(password, ADMIN_PASSWORD):
            forum_tokens = session.get("forum_tokens", {})
            session.clear()
            session["forum_tokens"] = forum_tokens
            session["admin_logged_in"] = True

            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)

            return redirect(url_for("admin"))

        error = "Fel lösenord."

    error_html = ""
    if error:
        error_html = f'<p class="error">{escape(error)}</p>'

    content = f"""
<h1>Admin</h1>

<div class="card">

<h2>Logga in</h2>

{error_html}

<form method="POST">

<input type="hidden" name="next" value="{escape(next_url)}">

<label>Adminlösenord</label>

<input
    type="password"
    name="password"
    autocomplete="current-password"
    required
>

<button type="submit">Logga in</button>

</form>

</div>
"""

    return page("Admin", content)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin():

    conn = get_db()

    claims_total = conn.execute(
        "SELECT COUNT(*) FROM claims"
    ).fetchone()[0]

    claims_decided = conn.execute(
        "SELECT COUNT(*) FROM claims WHERE verdict IN ('RÄTT', 'FEL')"
    ).fetchone()[0]

    threads_total = conn.execute(
        "SELECT COUNT(*) FROM forum_threads"
    ).fetchone()[0]

    replies_total = conn.execute(
        "SELECT COUNT(*) FROM forum_replies"
    ).fetchone()[0]

    conn.close()

    content = f"""
<h1>Adminpanel</h1>

<p class="subtitle">
Här samlas funktioner som bara administratören ska kunna använda.
</p>

<div class="grid">

<div class="card">
<h2>Påståenden</h2>
<p>Totalt: <strong>{claims_total}</strong></p>
<p>Avgjorda: <strong>{claims_decided}</strong></p>
<a href="/claims">Visa påståenden</a>
</div>

<div class="card">
<h2>Forum</h2>
<p>Trådar: <strong>{threads_total}</strong></p>
<p>Svar: <strong>{replies_total}</strong></p>
<a href="/forum">Öppna forumet</a>
</div>

</div>

<div class="card">
<h2>Administration</h2>
<p>
Admininloggningen skyddar framtida funktioner för moderering,
facit och underhåll. Vanliga användare påverkas inte av detta.
</p>

<a href="/admin/logout">Logga ut</a>
</div>
"""

    return page("Adminpanel", content)


# ============================================================
# ADMIN – TA BORT FORUMTRÅD
# ============================================================

@app.route("/admin/forum/<int:thread_id>/delete", methods=["POST"])
@admin_required
def admin_delete_thread(thread_id):

    conn = get_db()

    conn.execute(
        "DELETE FROM forum_replies WHERE thread_id = ?",
        (thread_id,)
    )

    conn.execute(
        "DELETE FROM forum_threads WHERE id = ?",
        (thread_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("forum"))


# ============================================================
# ADMIN – TA BORT FORUMSVAR
# ============================================================

@app.route("/admin/forum/reply/<int:reply_id>/delete", methods=["POST"])
@admin_required
def admin_delete_reply(reply_id):

    conn = get_db()

    reply = conn.execute(
        "SELECT thread_id FROM forum_replies WHERE id = ?",
        (reply_id,)
    ).fetchone()

    if reply is not None:
        thread_id = reply["thread_id"]

        conn.execute(
            "DELETE FROM forum_replies WHERE id = ?",
            (reply_id,)
        )

        conn.commit()
        conn.close()

        return redirect(
            url_for("forum_thread", thread_id=thread_id)
        )

    conn.close()
    return redirect(url_for("forum"))


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
            co.commenter,
            co.facebook_time AS source_time
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
                    """ + escape(row['claim_text']) + """
                </div>

                <div class="meta">
                    """ + escape(commenter) + """
                    · Påstående #""" + str(row['id']) + """
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
            co.commenter,
            co.facebook_time AS source_time
        FROM claims c
        LEFT JOIN comments co
            ON c.comment_id = co.id
        ORDER BY c.id DESC
    """).fetchall()

    conn.close()

    query = request.args.get("q", "").strip()
    status = request.args.get("status", "ALL").strip().upper()
    season = request.args.get("season", "ALL").strip()
    tag = request.args.get("tag", "ALL").strip()

    try:
        current_page = int(request.args.get("page", "1"))
    except (TypeError, ValueError):
        current_page = 1

    if current_page < 1:
        current_page = 1

    if status not in {"ALL", "RÄTT", "FEL", "OKLART"}:
        status = "ALL"

    available_seasons = sorted(
        {season_from_date(row["source_time"]) for row in rows},
        reverse=True
    )

    available_tags = sorted(
        {claim_tag("", row['claim_text']) for row in rows}
    )

    filtered_rows = []
    query_lower = query.casefold()

    for row in rows:
        verdict = row["verdict"] or "OKLART"
        commenter = row["commenter"] or "Okänd soffexpert"
        claim_text = row['claim_text'] or ""
        row_season = season_from_date(row["source_time"])
        row_tag = claim_tag("", claim_text)

        if status != "ALL" and verdict != status:
            continue

        if season != "ALL" and row_season != season:
            continue

        if tag != "ALL" and row_tag != tag:
            continue

        if query_lower:
            searchable = f"{commenter} {claim_text}".casefold()
            if query_lower not in searchable:
                continue

        filtered_rows.append(row)

    claims_per_page = 20
    total_filtered = len(filtered_rows)
    total_pages = max(1, (total_filtered + claims_per_page - 1) // claims_per_page)

    if current_page > total_pages:
        current_page = total_pages

    start_index = (current_page - 1) * claims_per_page
    end_index = start_index + claims_per_page
    page_rows = filtered_rows[start_index:end_index]

    selected_all = " selected" if status == "ALL" else ""
    selected_right = " selected" if status == "RÄTT" else ""
    selected_wrong = " selected" if status == "FEL" else ""
    selected_unknown = " selected" if status == "OKLART" else ""
    search_value = escape(query, quote=True)

    filter_params = {
        "q": query,
        "status": status,
        "season": season,
        "tag": tag
    }

    def page_url(page_number):
        params = dict(filter_params)
        params["page"] = page_number
        return url_for("claims", **params)

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

<label for="claim-season" style="display:block; margin-top:15px;"><strong>Säsong</strong></label>
<select id="claim-season" name="season" style="width:100%; box-sizing:border-box; margin-top:8px; padding:10px; border-radius:8px; border:1px solid #444; background:#181818; color:#fff;">
    <option value="ALL">Alla säsonger</option>
    {"".join(f'<option value="{escape(s)}"{" selected" if season == s else ""}>{escape(s)}</option>' for s in available_seasons)}
</select>

<label for="claim-tag" style="display:block; margin-top:15px;"><strong>Tagg</strong></label>
<select id="claim-tag" name="tag" style="width:100%; box-sizing:border-box; margin-top:8px; padding:10px; border-radius:8px; border:1px solid #444; background:#181818; color:#fff;">
    <option value="ALL">Alla taggar</option>
    {"".join(f'<option value="{escape(t)}"{" selected" if tag == t else ""}>{escape(t)}</option>' for t in available_tags)}
</select>

<div style="margin-top:15px; display:flex; gap:10px; flex-wrap:wrap;">
    <button type="submit" class="button">Filtrera</button>
    <a href="{url_for('claims')}" class="button">Rensa</a>
</div>

</form>
</div>

<div class="meta" style="margin:18px 0;">
Visar {start_index + 1 if total_filtered else 0}–{min(end_index, total_filtered)} av {total_filtered} påståenden.
</div>
"""

    if not page_rows:
        html += """
<div class="card">
<p>Inga påståenden matchar din sökning.</p>
</div>
"""
    else:
        for row in page_rows:
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
            claim_text = row['claim_text'] or ""
            evidence = row['evidence'] or ""

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

<p>
<a class="button" href="{url_for('claim_detail', claim_id=row['id'])}">
Visa påståendet
</a>
</p>

</div>
"""

    if total_pages > 1:
        html += """
<div class="card" style="display:flex; justify-content:center; align-items:center; gap:8px; flex-wrap:wrap;">
"""

        if current_page > 1:
            html += f"""
<a class="button" href="{page_url(current_page - 1)}">← Föregående</a>
"""

        start_page = max(1, current_page - 2)
        end_page_number = min(total_pages, current_page + 2)

        if start_page > 1:
            html += f'<a class="button" href="{page_url(1)}">1</a>'
            if start_page > 2:
                html += '<span class="meta" style="padding:10px 4px;">…</span>'

        for number in range(start_page, end_page_number + 1):
            if number == current_page:
                html += f"""
<span class="button" style="background:#555b61; cursor:default;">
{number}
</span>
"""
            else:
                html += f"""
<a class="button" href="{page_url(number)}">{number}</a>
"""

        if end_page_number < total_pages:
            if end_page_number < total_pages - 1:
                html += '<span class="meta" style="padding:10px 4px;">…</span>'
            html += f'<a class="button" href="{page_url(total_pages)}">{total_pages}</a>'

        if current_page < total_pages:
            html += f"""
<a class="button" href="{page_url(current_page + 1)}">Nästa →</a>
"""

        html += """
</div>
"""

    return page("Påståenden", html)


# ============================================================
# ENSKILT PÅSTÅENDE
# ============================================================

@app.route("/claim/<int:claim_id>")
def claim_detail(claim_id):
    conn = get_db()
    row = conn.execute("""
        SELECT c.*, co.commenter, co.comment_text,
               co.facebook_time AS source_time
        FROM claims c
        LEFT JOIN comments co ON c.comment_id = co.id
        WHERE c.id = ?
    """, (claim_id,)).fetchone()
    conn.close()

    if row is None:
        return page("Påståendet hittades inte", '''
<div class="card"><h2>Påståendet hittades inte.</h2></div>
'''), 404

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
    claim_text = row['claim_text'] or ""
    evidence = row['evidence'] or ""

    content = f'''
<h1>Påstående #{row['id']}</h1>
<div class="card claim {cls}">
<div>{badge}</div>
<h2>{escape(claim_text)}</h2>
<p class="meta">Soffexpert:
<a href="{url_for("expert", name=commenter)}">{escape(commenter)}</a></p>
<p class="meta">{escape(claim_tag("", claim_text))}
 · {escape(season_from_date(row["source_time"]))}</p>
'''

    if row['comment_text']:
        content += f'''
<div class="comment">
<strong>Originalkommentar:</strong>
<p>{escape(row['comment_text'])}</p>
</div>
'''

    if evidence:
        content += f'''
<p><strong>Verkligheten:</strong><br>{escape(evidence)}</p>
'''

    content += '</div>'
    return page(f"Påstående #{row['id']}", content)


# ============================================================
# RANKING
# ============================================================

@app.route("/ranking")
def ranking():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.verdict, co.commenter, co.facebook_time AS source_time
        FROM claims c
        LEFT JOIN comments co ON c.comment_id = co.id
        WHERE co.commenter IS NOT NULL AND co.commenter != ''
    """).fetchall()
    conn.close()

    season = request.args.get("season", "ALL").strip()
    available_seasons = sorted(
        {season_from_date(row["source_time"]) for row in rows},
        reverse=True
    )

    if season not in available_seasons:
        season = "ALL"

    if season != "ALL":
        rows = [row for row in rows
                if season_from_date(row["source_time"]) == season]

    ranked = ranking_stats(rows)

    html = '''
<h1>Ranking</h1>
<div class="subtitle">Vem hade faktiskt rätt?</div>

<div class="card">
<form method="GET">
<label for="ranking-season"><strong>Säsong</strong></label>
<select id="ranking-season" name="season" style="width:100%; box-sizing:border-box; margin-top:8px; padding:10px; border-radius:8px; border:1px solid #444; background:#181818; color:#fff;">
<option value="ALL">Alla säsonger</option>
'''

    for available in available_seasons:
        selected = " selected" if season == available else ""
        html += f'<option value="{escape(available)}"{selected}>{escape(available)}</option>'

    html += '''
</select>
<div style="margin-top:15px;">
<button type="submit">Visa ranking</button>
<a class="button" href="/ranking">Rensa</a>
</div>
</form>
</div>

<div class="card">
<p class="meta">
Minst 3 avgjorda påståenden krävs. RÄTT ger 1 poäng.
FEL ger 0. OKLART påverkar inte träffprocenten.
</p>
<table>
<tr>
<th>#</th><th>Soffexpert</th><th>Avgjorda</th>
<th>Rätt</th><th>Fel</th><th>Träff</th><th>Poäng</th>
</tr>
'''

    if not ranked:
        html += '<tr><td colspan="7">Ingen har tillräckligt många avgjorda påståenden ännu.</td></tr>'

    for position, item in enumerate(ranked, 1):
        html += f'''
<tr>
<td><strong>{position}</strong></td>
<td><a href="{url_for("expert", name=item["name"])}"><strong>{escape(item["name"])}</strong></a></td>
<td>{item["claims"]}</td>
<td>{item["right"]}</td>
<td>{item["wrong"]}</td>
<td><strong>{item["percentage"]} %</strong></td>
<td>{item["points"]}</td>
</tr>
'''

    html += '</table></div>'
    return page("Ranking", html)


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
<th>Träff</th>
</tr>
"""

    for row in rows:

        name = row["commenter"]

        claim_total = row["claims"] or 0
        right_total = row["right_count"] or 0
        wrong_total = row["wrong_count"] or 0
        decided_total = right_total + wrong_total
        percentage = round((right_total / decided_total) * 100) if decided_total else 0

        html += f"""
<tr>

<td>
<a href="{url_for('expert', name=name)}">
<strong>{escape(name)}</strong>
</a>
</td>

<td>{row["comments"] or 0}</td>
<td>{claim_total}</td>
<td>{right_total}</td>
<td>{wrong_total}</td>
<td>{percentage} %</td>

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
        if row['id'] is not None
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

        if row['id'] is None:

            html += f"""
<div class="card">

<div class="meta">
Kommentar
</div>

<p>
{escape(row['comment_text'])}
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
{escape(row['claim_text'])}
</h3>

<div class="comment">

<strong>Originalkommentar:</strong>

<p>
{escape(row['comment_text'])}
</p>

</div>
"""

        if row['evidence']:

            html += f"""
<p>
<strong>Vad som faktiskt hände:</strong><br>
{escape(row['evidence'])}
</p>
"""

        html += f"""
<div class="meta">
Påstående #{row['id']}
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

        edit_token = ""

        if username and title and message:

            edit_token = secrets.token_urlsafe(32)

            conn.execute("""
                INSERT INTO forum_threads
                (
                    title,
                    username,
                    message,
                    created_at,
                    edit_token
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                username,
                title,
                message,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                edit_token
            ))

            conn.commit()
            remember_forum_token("forum_thread", conn.execute("SELECT last_insert_rowid()").fetchone()[0], edit_token)

        conn.close()

        response = redirect(url_for("forum"))
        if edit_token:
            set_forum_token(response, edit_token)
        return response

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
    id="new-thread-message"
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
{escape(thread['title'])}
</a>
</h2>

<p>
{escape(thread['message'])}
</p>

<div class="meta">
{escape(thread['username'])} · {escape(thread['created_at'])}
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

        if not can_manage_forum_item(thread):

            conn.close()

            return page(
                "Ingen behörighet",
                """
                <div class="card">
                <h2>Ingen behörighet</h2>
                <p>Du har inte behörighet att ändra detta inlägg.</p>
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
    value="{escape(thread['title'])}"
    required
>

<label>Meddelande</label>

<textarea
    name="message"
    rows="7"
    maxlength="2000"
    required
>{escape(thread['message'])}</textarea>

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

    if not can_manage_forum_item(thread):

        conn.close()

        return page(
            "Ingen behörighet",
            """
            <div class="card">
            <h2>Ingen behörighet</h2>
            <p>Du har inte behörighet att ändra detta inlägg.</p>
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

        edit_token = ""

        if username and message:

            edit_token = secrets.token_urlsafe(32)

            conn.execute("""
                INSERT INTO forum_replies
                (
                    thread_id,
                    username,
                    message,
                    created_at,
                    edit_token
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                thread_id,
                username,
                message,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                edit_token
            ))

            conn.commit()
            remember_forum_token("forum_reply", conn.execute("SELECT last_insert_rowid()").fetchone()[0], edit_token)

        conn.close()

        response = redirect(
            url_for(
                "forum_thread",
                thread_id=thread_id
            )
        )
        if edit_token:
            set_forum_token(response, edit_token)
        return response

    replies = conn.execute("""
        SELECT *
        FROM forum_replies
        WHERE thread_id = ?
        ORDER BY id ASC
    """, (thread_id,)).fetchall()

    conn.close()

    content = f"""
<h1>{escape(thread['title'])}</h1>

<div class="card">

<p>
{escape(thread['message'])}
</p>

<div class="meta">
Startad av {escape(thread['username'])}
· {escape(thread['created_at'])}
</div>

<div class="forum-actions">

<button
    type="button"
    class="small"
    onclick="window.citera(this)"
    data-username="{escape(thread['username'])}"
    data-message="{escape(thread['message'])}"
>
Citera
</button>

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
{escape(reply['message'])}
</p>

<div class="meta">
{escape(reply['username'])} · {escape(reply['created_at'])}
</div>

<div class="forum-actions">

<button
    type="button"
    class="small"
    onclick="window.citera(this)"
    data-username="{escape(reply['username'])}"
    data-message="{escape(reply['message'])}"
>
Citera
</button>

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
    maxlength="80"
    required
>

<label>Meddelande</label>

<textarea
    id="reply-message"
    name="message"
    rows="5"
    maxlength="2000"
    required
></textarea>

<button type="submit">
Svara
</button>

</form>

<script>
window.citera = function(button) {
    const username = button.getAttribute("data-username") || "";
    const message = button.getAttribute("data-message") || "";
    const textarea = document.getElementById("reply-message");

    if (!textarea) {
        alert("Svarsrutan kunde inte hittas.");
        return;
    }

    const lines = message.split(/\r?\n/);
    const quote = "> " + username + " skrev:\n" +
        lines.map(function(line) { return "> " + line; }).join("\n") +
        "\n\n";

    if (textarea.value.trim()) {
        textarea.value += "\n" + quote;
    } else {
        textarea.value = quote;
    }

    textarea.focus();
    textarea.selectionStart = textarea.value.length;
    textarea.selectionEnd = textarea.value.length;
};
</script>

</div>
"""

    return page(
        thread['title'],
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

        if not can_manage_forum_item(reply):

            conn.close()

            return page(
                "Ingen behörighet",
                """
                <div class="card">
                <h2>Ingen behörighet</h2>
                <p>Du har inte behörighet att ändra detta inlägg.</p>
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
>{escape(reply['message'])}</textarea>

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

    if not can_manage_forum_item(reply):

        conn.close()

        return page(
            "Ingen behörighet",
            """
            <div class="card">
            <h2>Ingen behörighet</h2>
            <p>Du har inte behörighet att ändra detta inlägg.</p>
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
