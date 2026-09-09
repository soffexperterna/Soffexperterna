import sqlite3
import re
import unicodedata
from datetime import datetime


DB = "dif_hockey.db"
SEASON = "2026/27"
TEAM = "Djurgården"

MIN_CHAIN_GAMES = 5
MIN_DEVELOPMENT_GAMES = 3
MIN_SCORING_GAMES = 5


def norm(text):
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = re.sub(r"[^a-z0-9åäöéü -]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_claims(conn):
    return conn.execute("""
        SELECT
            id,
            comment_id,
            claim_text,
            claim_type,
            target_type,
            target,
            status,
            verdict,
            evidence,
            evidence_value,
            season,
            metric,
            threshold,
            evaluation_rule
        FROM claims
        ORDER BY id
    """).fetchall()


def count_matches(conn, match_type=None):
    if match_type is None or match_type == "ALLA":
        return conn.execute("""
            SELECT COUNT(*)
            FROM matches
            WHERE home_score IS NOT NULL
              AND away_score IS NOT NULL
        """).fetchone()[0]

    return conn.execute("""
        SELECT COUNT(*)
        FROM matches
        WHERE match_type = ?
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
    """, (match_type,)).fetchone()[0]


def get_active_players(conn):
    try:
        return conn.execute("""
            SELECT COUNT(*)
            FROM roster_history
            WHERE status = 'aktiv'
        """).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def is_final_verdict(claim):
    return claim["verdict"] in ("RÄTT", "FEL")


def set_result(
    conn,
    claim_id,
    verdict,
    evidence,
    evidence_value=None,
    rule=None,
    status="bedömd"
):
    conn.execute("""
        UPDATE claims
        SET verdict=?,
            evidence=?,
            evidence_value=?,
            evaluation_rule=?,
            evaluated_at=?,
            status=?
        WHERE id=?
    """, (
        verdict,
        evidence,
        evidence_value,
        rule,
        datetime.now().isoformat(timespec="seconds"),
        status,
        claim_id
    ))


def waiting(conn, claim_id, evidence, rule, evidence_value=None):
    conn.execute("""
        UPDATE claims
        SET verdict='OKLART',
            evidence=?,
            evidence_value=?,
            evaluation_rule=?,
            evaluated_at=?,
            status='väntar'
        WHERE id=?
    """, (
        evidence,
        evidence_value,
        rule,
        datetime.now().isoformat(timespec="seconds"),
        claim_id
    ))


def evaluate_lagbygge(conn, claim):
    text = norm(claim["claim_text"])

    transfer_words = [
        "värvning",
        "värva",
        "förstärka",
        "nyförvärv",
        "kommer snart",
        "ansluter",
        "pusselbit",
        "pusselbitar"
    ]

    relevant = any(word in text for word in transfer_words)

    if not relevant:
        waiting(
            conn,
            claim["id"],
            "Lagbygge registrerat men inget tillräckligt konkret facit.",
            "Lagbygge kräver konkret och verifierbar truppförändring."
        )
        return "OKLART"

    try:
        changes = conn.execute("""
            SELECT
                player_name,
                change_type,
                change_date
            FROM roster_changes
            ORDER BY change_date
        """).fetchall()
    except sqlite3.OperationalError:
        changes = []

    additions = []

    for change in changes:
        change_type = norm(change["change_type"])

        valid_types = [
            "in",
            "ny",
            "addition",
            "added",
            "värv",
            "värvning",
            "nyförvärv",
            "ansluten"
        ]

        if change_type in valid_types:
            additions.append(change)

    if additions:
        names = [
            row["player_name"]
            for row in additions
            if row["player_name"]
        ]

        evidence = "Truppförändring registrerad"

        if names:
            evidence += ": " + ", ".join(names[:5])

        set_result(
            conn,
            claim["id"],
            "RÄTT",
            evidence,
            len(additions),
            "Minst en relevant truppförstärkning har registrerats."
        )

        return "RÄTT"

    waiting(
        conn,
        claim["id"],
        "Ingen relevant truppförstärkning har ännu registrerats.",
        "Väntar på konkret facit i trupphistoriken."
    )

    return "OKLART"


def evaluate_transfer(conn, claim):
    return evaluate_lagbygge(conn, claim)


def evaluate_chain(conn, claim):
    target = claim["target"] or ""

    players = []

    for name in re.split(r",| och ", target):
        name = name.strip()

        if len(name) >= 3:
            players.append(name)

    matches = count_matches(conn, "TRÄNING")

    if matches < MIN_CHAIN_GAMES:
        waiting(
            conn,
            claim["id"],
            (
                f"Kedja registrerad. {matches} träningsmatcher spelade, "
                f"minst {MIN_CHAIN_GAMES} krävs för automatisk bedömning."
            ),
            (
                f"Kedja följs mot träningsmatcher och kräver "
                f"minst {MIN_CHAIN_GAMES} spelade träningsmatcher."
            )
        )

        return "OKLART"

    waiting(
        conn,
        claim["id"],
        (
            f"{matches} träningsmatcher finns registrerade. "
            "Kedjan kan följas men systemet sätter inte RÄTT/FEL "
            "på subjektiva omdömen utan verifierbart prestationsfacit."
        ),
        "Kedja kräver verifierbar prestationsdata."
    )

    return "OKLART"


def find_player(conn, claim):
    target = claim["target"] or ""

    if target:
        try:
            row = conn.execute("""
                SELECT *
                FROM roster_history
                WHERE player_name LIKE ?
                ORDER BY id DESC
                LIMIT 1
            """, (
                f"%{target}%"
            )).fetchone()

            if row:
                return row

        except sqlite3.OperationalError:
            pass

    text = claim["claim_text"] or ""

    try:
        rows = conn.execute("""
            SELECT player_name
            FROM roster_history
            WHERE status='aktiv'
        """).fetchall()
    except sqlite3.OperationalError:
        return None

    text_norm = norm(text)

    for row in rows:
        name = row["player_name"]

        if name and norm(name) in text_norm:
            return row

    return None


def find_player_stats(conn, player_name):
    """
    Hämtar senaste statistik för spelaren från player_stats.
    Matchningen görs även om Swehockey använder efternamn, förnamn.
    """

    if not player_name:
        return None

    target = norm(player_name)

    try:
        rows = conn.execute("""
            SELECT *
            FROM player_stats
            WHERE season = ?
              AND team = ?
            ORDER BY points DESC, goals DESC, assists DESC
        """, (
            SEASON,
            TEAM
        )).fetchall()
    except sqlite3.OperationalError:
        return None

    for row in rows:
        db_name = norm(row["player"])

        if db_name == target:
            return row

        if target in db_name or db_name in target:
            return row

    # Försök matcha namn åt båda hållen.
    target_parts = target.split()

    if len(target_parts) >= 2:
        for row in rows:
            db_parts = norm(row["player"]).split()

            if len(db_parts) >= 2:
                target_set = set(target_parts)
                db_set = set(db_parts)

                if target_set.issubset(db_set) or db_set.issubset(target_set):
                    return row

    return None


def format_player_stats(stats):
    if not stats:
        return None

    return (
        f"GP {stats['games_played']}, "
        f"G {stats['goals']}, "
        f"A {stats['assists']}, "
        f"P {stats['points']}, "
        f"PIM {stats['penalty_minutes']}"
    )


def evaluate_player(conn, claim):
    player = find_player(conn, claim)

    if not player:
        waiting(
            conn,
            claim["id"],
            "Spelaren kunde inte kopplas säkert till en spelare i truppen.",
            "Spelare måste kunna identifieras säkert."
        )

        return "OKLART"

    name = player["player_name"]

    stats = find_player_stats(conn, name)

    if not stats:
        waiting(
            conn,
            claim["id"],
            (
                f"{name} finns i truppen, men ingen spelarstatistik "
                "kunde kopplas till personen ännu."
            ),
            "Spelarclaim väntar på verifierbar spelarstatistik."
        )

        return "OKLART"

    stat_text = format_player_stats(stats)

    evidence = (
        f"{name}: {stat_text}. "
        "Statistiken är hämtad från registrerad officiell "
        "Swehockey-statistik för säsongen 2026/27."
    )

    waiting(
        conn,
        claim["id"],
        evidence,
        "Spelarclaim kopplas till GP, G, A, P och PIM. "
        "Själva påståandet bedöms inte subjektivt.",
        stats["points"]
    )

    return "OKLART"


def evaluate_scoring(conn, claim):
    matches = count_matches(conn)

    if matches < MIN_SCORING_GAMES:
        waiting(
            conn,
            claim["id"],
            (
                f"{matches} matcher spelade. "
                f"Väntar på minst {MIN_SCORING_GAMES} matcher."
            ),
            (
                f"Mål-/poängclaim kräver minst "
                f"{MIN_SCORING_GAMES} spelade matcher."
            )
        )

        return "OKLART"

    waiting(
        conn,
        claim["id"],
        (
            "Tillräckligt med matcher finns, men claimen saknar "
            "ännu en tillräckligt konkret automatisk jämförelseregel."
        ),
        "Målskytte kräver konkret mål- eller poängfacit."
    )

    return "OKLART"


def evaluate_match(conn, claim):
    matches = count_matches(conn, "SHL")

    if matches == 0:
        waiting(
            conn,
            claim["id"],
            "Ingen färdig SHL-matchdata finns ännu.",
            "Matchclaim väntar på SHL-matchresultat."
        )

        return "OKLART"

    waiting(
        conn,
        claim["id"],
        (
            "SHL-matchdata finns, men claimen är inte kopplad "
            "till en specifik motståndare/match i databasen."
        ),
        "Matchclaim kräver koppling till specifik match."
    )

    return "OKLART"


def evaluate_development(conn, claim):
    matches = count_matches(conn, "TRÄNING")

    if matches < MIN_DEVELOPMENT_GAMES:
        waiting(
            conn,
            claim["id"],
            (
                f"{matches} träningsmatcher spelade. "
                f"Väntar på minst {MIN_DEVELOPMENT_GAMES} "
                "träningsmatcher."
            ),
            (
                f"Utvecklingsclaim följs mot träningsmatcher och kräver "
                f"minst {MIN_DEVELOPMENT_GAMES} spelade träningsmatcher."
            )
        )

        return "OKLART"

    waiting(
        conn,
        claim["id"],
        (
            f"{matches} träningsmatcher finns registrerade. "
            "Utvecklingspåståendet är registrerat. "
            "Systemet kräver ett konkret prestationsmått "
            "innan RÄTT/FEL sätts."
        ),
        "Utveckling får inte avgöras genom subjektiv tolkning."
    )

    return "OKLART"


def evaluate_season(conn, claim):
    waiting(
        conn,
        claim["id"],
        (
            "Säsongspåstående. Facit avgörs först när "
            "relevant del av säsongen är färdig."
        ),
        "Säsongclaim väntar på säsongsfacit."
    )

    return "OKLART"


def evaluate_unknown(conn, claim):
    waiting(
        conn,
        claim["id"],
        "Ingen färdig utvärderingsregel för denna claimtyp ännu.",
        "Okänd claimtyp."
    )

    return "OKLART"


def evaluate_claim(conn, claim):
    """
    Viktigt:
    Redan fastställda RÄTT/FEL lämnas helt orörda.
    Endast OKLART claims utvärderas på nytt.
    """

    if is_final_verdict(claim):
        return claim["verdict"]

    claim_type = norm(claim["claim_type"])

    if claim_type == "lagbygge":
        return evaluate_lagbygge(conn, claim)

    if claim_type == "transfer":
        return evaluate_transfer(conn, claim)

    if claim_type == "kedja":
        return evaluate_chain(conn, claim)

    if claim_type == "spelare":
        return evaluate_player(conn, claim)

    if claim_type in ["målskytte", "mal", "poang"]:
        return evaluate_scoring(conn, claim)

    if claim_type == "match":
        return evaluate_match(conn, claim)

    if claim_type == "utveckling":
        return evaluate_development(conn, claim)

    if claim_type in ["sasong", "säsong"]:
        return evaluate_season(conn, claim)

    return evaluate_unknown(conn, claim)


def count_player_stats(conn):
    try:
        return conn.execute("""
            SELECT COUNT(*)
            FROM player_stats
            WHERE season = ?
              AND team = ?
        """, (
            SEASON,
            TEAM
        )).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def main():
    print("=" * 70)
    print("DIF – GEMENSAM CLAIM ENGINE v16")
    print("=" * 70)
    print()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    claims = get_claims(conn)
    players = get_active_players(conn)
    player_stats = count_player_stats(conn)

    matches_all = count_matches(conn)
    matches_shl = count_matches(conn, "SHL")
    matches_training = count_matches(conn, "TRÄNING")

    print(f"Claims att analysera:     {len(claims)}")
    print(f"Aktiva spelare:            {players}")
    print(f"Spelarstatistik:           {player_stats}")
    print(f"Spelade matcher totalt:    {matches_all}")
    print(f"Spelade SHL-matcher:       {matches_shl}")
    print(f"Spelade träningsmatcher:   {matches_training}")
    print()

    summary = {
        "RÄTT": 0,
        "FEL": 0,
        "OKLART": 0
    }

    for claim in claims:
        verdict = evaluate_claim(conn, claim)

        if verdict in summary:
            summary[verdict] += 1

        if is_final_verdict(claim):
            print(
                f"#{claim['id']} | "
                f"{claim['claim_type']} | "
                f"{verdict} | "
                f"BEHÅLLEN tidigare bedömning | "
                f"{claim['claim_text']}"
            )
        else:
            print(
                f"#{claim['id']} | "
                f"{claim['claim_type']} | "
                f"{verdict} | "
                f"{claim['claim_text']}"
            )

    conn.commit()

    print()
    print("=" * 70)
    print("CLAIM-SAMMANFATTNING")
    print("=" * 70)

    print(f"RÄTT:     {summary['RÄTT']}")
    print(f"FEL:      {summary['FEL']}")
    print(f"OKLART:   {summary['OKLART']}")
    print(f"TOTALT:   {len(claims)}")

    print()
    print("CLAIM ENGINE v16 KLAR")

    conn.close()


if __name__ == "__main__":
    main()
