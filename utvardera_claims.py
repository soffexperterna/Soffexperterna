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
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9åäöéü -]", " ", text)).strip()


def get_claims(conn):
    return conn.execute("""
        SELECT id, comment_id, claim_text, claim_type, target_type, target,
               status, verdict, evidence, evidence_value, season, metric,
               threshold, evaluation_rule
        FROM claims
        ORDER BY id
    """).fetchall()


def count_matches(conn, match_type=None):
    if match_type is None or match_type == "ALLA":
        return conn.execute("""
            SELECT COUNT(*) FROM matches
            WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        """).fetchone()[0]
    return conn.execute("""
        SELECT COUNT(*) FROM matches
        WHERE match_type = ?
          AND home_score IS NOT NULL AND away_score IS NOT NULL
    """, (match_type,)).fetchone()[0]


def get_active_players(conn):
    try:
        return conn.execute("""
            SELECT COUNT(*) FROM roster_history WHERE status = 'aktiv'
        """).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def is_final_verdict(claim):
    return claim["verdict"] in ("RÄTT", "FEL")


def set_result(conn, claim_id, verdict, evidence, evidence_value=None,
               rule=None, status="bedömd"):
    conn.execute("""
        UPDATE claims
        SET verdict=?, evidence=?, evidence_value=?, evaluation_rule=?,
            evaluated_at=?, status=?
        WHERE id=?
    """, (verdict, evidence, evidence_value, rule,
          datetime.now().isoformat(timespec="seconds"), status, claim_id))


def waiting(conn, claim_id, evidence, rule):
    conn.execute("""
        UPDATE claims
        SET verdict='OKLART', evidence=?, evaluation_rule=?,
            evaluated_at=?, status='väntar'
        WHERE id=?
    """, (evidence, rule, datetime.now().isoformat(timespec="seconds"), claim_id))


def evaluate_lagbygge(conn, claim):
    text = norm(claim["claim_text"])
    transfer_words = ["värvning", "värva", "förstärka", "nyförvärv",
                      "kommer snart", "ansluter", "pusselbit", "pusselbitar"]
    if not any(word in text for word in transfer_words):
        waiting(conn, claim["id"],
                "Lagbygge registrerat men inget tillräckligt konkret facit.",
                "Lagbygge kräver konkret och verifierbar truppförändring.")
        return "OKLART"
    try:
        changes = conn.execute("""
            SELECT player_name, change_type, change_date
            FROM roster_changes ORDER BY change_date
        """).fetchall()
    except sqlite3.OperationalError:
        changes = []
    valid_types = {"in", "ny", "addition", "added", "värv", "värvning",
                   "nyförvärv", "ansluten"}
    additions = [r for r in changes if norm(r["change_type"]) in valid_types]
    if additions:
        names = [r["player_name"] for r in additions if r["player_name"]]
        evidence = "Truppförändring registrerad"
        if names:
            evidence += ": " + ", ".join(names[:5])
        set_result(conn, claim["id"], "RÄTT", evidence, len(additions),
                   "Minst en relevant truppförstärkning har registrerats.")
        return "RÄTT"
    waiting(conn, claim["id"],
            "Ingen relevant truppförstärkning har ännu registrerats.",
            "Väntar på konkret facit i trupphistoriken.")
    return "OKLART"


def evaluate_transfer(conn, claim):
    return evaluate_lagbygge(conn, claim)


def evaluate_chain(conn, claim):
    target = claim["target"] or ""
    players = [p.strip() for p in re.split(r",| och ", target) if len(p.strip()) >= 3]
    matches = count_matches(conn, "TRÄNING")
    if matches < MIN_CHAIN_GAMES:
        waiting(conn, claim["id"],
                f"Kedja registrerad. {matches} träningsmatcher spelade, minst {MIN_CHAIN_GAMES} krävs för automatisk bedömning.",
                f"Kedja följs mot träningsmatcher och kräver minst {MIN_CHAIN_GAMES} spelade träningsmatcher.")
        return "OKLART"
    waiting(conn, claim["id"],
            f"{matches} träningsmatcher finns registrerade. Kedjan kan följas men systemet sätter inte RÄTT/FEL på subjektiva omdömen utan verifierbart prestationsfacit.",
            "Kedja kräver verifierbar prestationsdata.")
    return "OKLART"


def find_player(conn, claim):
    target = claim["target"] or ""
    if target:
        try:
            row = conn.execute("""
                SELECT * FROM roster_history
                WHERE player_name LIKE ? ORDER BY id DESC LIMIT 1
            """, (f"%{target}%",)).fetchone()
            if row:
                return row["player_name"]
        except sqlite3.OperationalError:
            pass
    text_norm = norm(claim["claim_text"] or "")
    try:
        rows = conn.execute("SELECT player_name FROM roster_history WHERE status='aktiv'").fetchall()
    except sqlite3.OperationalError:
        rows = []
    for row in rows:
        name = row["player_name"]
        if name and norm(name) in text_norm:
            return name
    try:
        rows = conn.execute("SELECT DISTINCT player FROM player_stats WHERE season=?", (SEASON,)).fetchall()
        for row in rows:
            name = row["player"]
            if name and norm(name) in text_norm:
                return name
    except sqlite3.OperationalError:
        pass
    return None


def player_stats(conn, player):
    try:
        return conn.execute("""
            SELECT * FROM player_stats
            WHERE season=? AND player=?
            ORDER BY games_played DESC, id DESC LIMIT 1
        """, (SEASON, player)).fetchone()
    except sqlite3.OperationalError:
        return None


def evaluate_player(conn, claim):
    player = find_player(conn, claim)
    if not player:
        waiting(conn, claim["id"],
                "Spelaren kunde inte kopplas säkert till en spelare i truppen.",
                "Spelare måste kunna identifieras säkert.")
        return "OKLART"

    stats = player_stats(conn, player)
    if not stats:
        waiting(conn, claim["id"],
                f"{player} finns i truppen, men ingen spelarstatistik finns för säsongen ännu.",
                "Spelarclaim kräver verifierbar spelarstatistik.")
        return "OKLART"

    text = norm(claim["claim_text"])
    games = stats["games_played"] or 0
    goals = stats["goals"] or 0
    assists = stats["assists"] or 0
    points = stats["points"] or 0

    patterns = [
        (r"(?:gor|gjort|gör)\s+(\d+)\s+mal", goals, "mål"),
        (r"har\s+(\d+)\s+mal", goals, "mål"),
        (r"(?:gor|gjort|gör)\s+(\d+)\s+poang", points, "poäng"),
        (r"har\s+(\d+)\s+poang", points, "poäng"),
        (r"(?:gor|gjort|gör)\s+(\d+)\s+assist", assists, "assist"),
        (r"har\s+(\d+)\s+assist", assists, "assist"),
    ]

    for pattern, actual, metric_name in patterns:
        match = re.search(pattern, text)
        if match:
            claimed = int(match.group(1))
            if actual == claimed:
                verdict = "RÄTT"
                result = f"{player} har {actual} {metric_name} efter {games} spelade matcher."
            else:
                verdict = "FEL"
                result = f"{player} har {actual} {metric_name}, inte {claimed}, efter {games} spelade matcher."
            set_result(conn, claim["id"], verdict, result, actual,
                       f"Jämför claimens {metric_name} med player_stats för {SEASON}.")
            return verdict

    waiting(conn, claim["id"],
            f"{player} har statistik: {games} matcher, {goals} mål, {assists} assist och {points} poäng. Påståendet saknar ett numeriskt facit som kan jämföras automatiskt.",
            "Subjektiva spelaromdömen avgörs inte som RÄTT/FEL. Numeriska spelarclaims jämförs mot player_stats.")
    return "OKLART"


def evaluate_scoring(conn, claim):
    matches = count_matches(conn)
    if matches < MIN_SCORING_GAMES:
        waiting(conn, claim["id"],
                f"{matches} matcher spelade. Väntar på minst {MIN_SCORING_GAMES} matcher.",
                f"Mål-/poängclaim kräver minst {MIN_SCORING_GAMES} matcher.")
        return "OKLART"
    waiting(conn, claim["id"],
            "Tillräckligt med matcher finns, men claimen saknar ännu en tillräckligt konkret automatisk jämförelseregel.",
            "Målskytte kräver konkret mål- eller poängfacit.")
    return "OKLART"


def evaluate_match(conn, claim):
    matches = count_matches(conn, "SHL")
    if matches == 0:
        waiting(conn, claim["id"], "Ingen färdig SHL-matchdata finns ännu.", "Matchclaim väntar på SHL-matchresultat.")
        return "OKLART"
    waiting(conn, claim["id"],
            "SHL-matchdata finns, men claimen är inte kopplad till en specifik motståndare/match i databasen.",
            "Matchclaim kräver koppling till specifik match.")
    return "OKLART"


def evaluate_development(conn, claim):
    matches = count_matches(conn, "TRÄNING")
    if matches < MIN_DEVELOPMENT_GAMES:
        waiting(conn, claim["id"],
                f"{matches} träningsmatcher spelade. Väntar på minst {MIN_DEVELOPMENT_GAMES} träningsmatcher.",
                f"Utvecklingsclaim följs mot träningsmatcher och kräver minst {MIN_DEVELOPMENT_GAMES} träningsmatcher.")
        return "OKLART"
    waiting(conn, claim["id"],
            f"{matches} träningsmatcher finns registrerade. Utvecklingspåståendet är registrerat. Systemet kräver ett konkret prestationsmått innan RÄTT/FEL sätts.",
            "Utveckling får inte avgöras genom subjektiv tolkning.")
    return "OKLART"


def evaluate_season(conn, claim):
    waiting(conn, claim["id"],
            "Säsongspåstående. Facit avgörs först när relevant del av säsongen är färdig.",
            "Säsongclaim väntar på säsongsfacit.")
    return "OKLART"


def evaluate_unknown(conn, claim):
    waiting(conn, claim["id"], "Ingen färdig utvärderingsregel för denna claimtyp ännu.", "Okänd claimtyp.")
    return "OKLART"


def evaluate_claim(conn, claim):
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
    if claim_type in ["mal", "målskytte", "poang"]:
        return evaluate_scoring(conn, claim)
    if claim_type == "match":
        return evaluate_match(conn, claim)
    if claim_type == "utveckling":
        return evaluate_development(conn, claim)
    if claim_type in ["sasong", "säsong"]:
        return evaluate_season(conn, claim)
    return evaluate_unknown(conn, claim)


def main():
    print("=" * 70)
    print("DIF – GEMENSAM CLAIM ENGINE v16")
    print("=" * 70)
    print()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    claims = get_claims(conn)
    players = get_active_players(conn)
    matches_all = count_matches(conn)
    matches_shl = count_matches(conn, "SHL")
    matches_training = count_matches(conn, "TRÄNING")
    print(f"Claims att analysera: {len(claims)}")
    print(f"Aktiva spelare:       {players}")
    print(f"Spelade matcher totalt: {matches_all}")
    print(f"Spelade SHL-matcher:    {matches_shl}")
    print(f"Spelade träningsmatcher: {matches_training}")
    print()
    summary = {"RÄTT": 0, "FEL": 0, "OKLART": 0}
    for claim in claims:
        verdict = evaluate_claim(conn, claim)
        if verdict in summary:
            summary[verdict] += 1
        print(f"#{claim['id']} | {claim['claim_type']} | {verdict} | {claim['claim_text']}")
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
