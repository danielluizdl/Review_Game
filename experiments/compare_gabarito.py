"""
Compara a saída do pipeline com o gabarito para as 3 mãos de referência.

Gabarito: Novo_gabarito_3hands.txt  (HL4017, HL3048, HL2332)
Uso:
  python compare_gabarito.py [arquivo_output.txt]

Se nenhum arquivo for passado, usa o .txt mais recente em output/.

Pontuação por mão (total 100 pts):
  20 - Jogadores nos assentos
  10 - Posições BTN/SB/BB/STR
  20 - Ações preflop
  15 - Ações flop
  15 - Ações turn
  10 - Ações river  (auto-máx se gabarito não tem river)
  10 - Vencedor
Total geral: 300 pts (3 × 100)
"""
import re
import sys
import glob
import os

# Força saída UTF-8 no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GABARITO_PATH = os.path.join(os.path.dirname(__file__), "..", "Novo_gabarito_3hands.txt")
HANDS_TO_COMPARE = ["HL4017", "HL3048", "HL2332"]


# ── parser de hand history PokerStars ─────────────────────────────────────────

def parse_hand(block: str) -> dict:
    """Parseia um bloco de hand history PokerStars em dict estruturado."""
    lines = [l.rstrip() for l in block.strip().splitlines()]
    h = {
        "table_id":   "",
        "btn_seat":   0,
        "seats":      {},
        "positions":  {},
        "antes":      [],
        "blinds":     [],
        "hole_cards": [],
        "actions":    {"preflop": [], "flop": [], "turn": [], "river": []},
        "board":      [],
        "winner":     "",
        "pot":        0.0,
    }

    street = "preflop"

    for line in lines:
        m = re.match(r"Table '(\w+)'.*Seat #(\d+) is the button", line)
        if m:
            h["table_id"] = m.group(1)
            h["btn_seat"] = int(m.group(2))
            continue

        m = re.match(r"Seat (\d+): (.+?) \(\$?([\d.]+) in chips\)", line)
        if m:
            h["seats"][int(m.group(1))] = {"name": m.group(2).strip(),
                                            "stack": float(m.group(3))}
            continue

        m = re.match(r"(.+?): posts the ante \$?([\d.]+)", line)
        if m:
            h["antes"].append({"name": m.group(1), "amount": float(m.group(2))})
            continue

        m = re.match(r"(.+?): posts (small blind|big blind|straddle) \$?([\d.]+)", line)
        if m:
            h["blinds"].append({"name": m.group(1), "type": m.group(2),
                                "amount": float(m.group(3))})
            continue

        m = re.match(r"Dealt to (\S+) \[(.+?)\]", line)
        if m:
            h["hole_cards"] = m.group(2).split()
            continue

        if line.startswith("*** HOLE CARDS ***"):
            street = "preflop"
            continue
        m = re.match(r"\*\*\* FLOP \*\*\* \[(.+?)\]", line)
        if m:
            street = "flop"
            h["board"] = m.group(1).split()
            continue
        m = re.match(r"\*\*\* TURN \*\*\* \[.+?\] \[(.+?)\]", line)
        if m:
            street = "turn"
            h["board"].append(m.group(1).strip())
            continue
        m = re.match(r"\*\*\* RIVER \*\*\* \[.+?\] \[(.+?)\]", line)
        if m:
            street = "river"
            h["board"].append(m.group(1).strip())
            continue
        if line.startswith("*** SUMMARY ***"):
            street = "summary"
            continue
        if line.startswith("*** SHOW DOWN ***"):
            street = "showdown"
            continue

        m = re.match(r"(\S+) collected \$?([\d.]+) from pot", line)
        if m:
            h["winner"] = m.group(1)
            h["pot"]    = float(m.group(2))
            continue
        m = re.match(r"Seat \d+: (.+?) (?:\(.+?\) )?collected \(\$?([\d.]+)\)", line)
        if m:
            h["winner"] = m.group(1).strip()
            h["pot"]    = float(m.group(2))
            continue

        if street == "summary":
            m = re.match(r"Seat \d+: (.+?) \((.+?)\)", line)
            if m:
                name = m.group(1).strip()
                role = m.group(2)
                if "button" in role:
                    h["positions"][name] = "BTN"
                elif "small blind" in role:
                    h["positions"][name] = "SB"
                elif "big blind" in role:
                    h["positions"][name] = "BB"
                elif "straddle" in role:
                    h["positions"][name] = "STR"
            continue

        if street in h["actions"]:
            m = re.match(
                r"(.+?): (folds|checks|calls \$[\d.]+|bets \$[\d.]+|raises \$[\d.]+ to \$[\d.]+)",
                line,
            )
            if m:
                h["actions"][street].append({
                    "player": m.group(1).strip(),
                    "raw":    m.group(2).strip(),
                })
                continue

    for b in h["blinds"]:
        name, btype = b["name"], b["type"]
        if name not in h["positions"]:
            if btype == "small blind":
                h["positions"][name] = "SB"
            elif btype == "big blind":
                h["positions"][name] = "BB"
            elif btype == "straddle":
                h["positions"][name] = "STR"
    for sn, sinfo in h["seats"].items():
        if sn == h["btn_seat"]:
            h["positions"][sinfo["name"]] = "BTN"

    return h


def extract_hand(table_id: str, txt_path: str) -> str | None:
    """Extrai o primeiro bloco de mão de uma mesa específica do arquivo."""
    with open(txt_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    blocks = re.split(r"(?=PokerStars Hand #)", content)
    for block in blocks:
        if table_id in block and block.strip():
            return block.strip()
    return None


# ── comparação e scoring ──────────────────────────────────────────────────────

def _normalize_action(raw: str) -> tuple[str, float]:
    raw = raw.strip().lower()
    if raw == "folds":
        return ("fold", 0.0)
    if raw == "checks":
        return ("check", 0.0)
    m = re.match(r"calls \$?([\d.]+)", raw)
    if m:
        return ("call", float(m.group(1)))
    m = re.match(r"bets \$?([\d.]+)", raw)
    if m:
        return ("bet", float(m.group(1)))
    m = re.match(r"raises \$?([\d.]+) to \$?([\d.]+)", raw)
    if m:
        return ("raise", float(m.group(2)))
    return ("unknown", 0.0)


def _name_match(a: str, b: str) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4:
        return a[:4] == b[:4]
    return False


def _compare_actions(g_acts, o_acts, max_pts, label):
    if not g_acts:
        return max_pts, f"{label} ({max_pts}/{max_pts}): nenhuma ação esperada ✓"

    matched = 0
    diffs = []
    for i in range(max(len(g_acts), len(o_acts))):
        ga = g_acts[i] if i < len(g_acts) else None
        oa = o_acts[i] if i < len(o_acts) else None
        if ga is None:
            diffs.append(f"  extra [{i+1}] output: {oa['player']}: {oa['raw']}")
            continue
        if oa is None:
            diffs.append(f"  faltando [{i+1}]: {ga['player']}: {ga['raw']}")
            continue
        g_type, g_val = _normalize_action(ga["raw"])
        o_type, o_val = _normalize_action(oa["raw"])
        player_ok = _name_match(ga["player"], oa["player"])
        type_ok   = g_type == o_type
        val_ok    = abs(g_val - o_val) < 0.05
        if player_ok and type_ok and val_ok:
            matched += 1
        else:
            parts = []
            if not player_ok:
                parts.append(f"player: '{ga['player']}' vs '{oa['player']}'")
            if not type_ok:
                parts.append(f"tipo: '{g_type}' vs '{o_type}'")
            if not val_ok and g_type not in ("fold", "check"):
                parts.append(f"valor: ${g_val} vs ${o_val}")
            diffs.append(f"  [{i+1}] {'; '.join(parts)}")

    pts = round(max_pts * matched / len(g_acts))
    if not diffs:
        return pts, f"{label} ({pts}/{max_pts}): ✓"
    return pts, f"{label} ({pts}/{max_pts}):\n" + "\n".join(diffs)


def compare_hand(gabarito: dict, output: dict) -> dict:
    """Compara dois parsed-hands. Retorna {score, issues}. Max 100 pts."""
    score = 0
    issues = []

    # ── 1. Jogadores (20 pts) ─────────────────────────────────────────────────
    MAX_PLAYERS = 20
    g_seats = {sn: info["name"] for sn, info in gabarito["seats"].items()}
    o_seats = {sn: info["name"] for sn, info in output["seats"].items()}
    seat_hits = sum(1 for sn in g_seats
                    if sn in o_seats and _name_match(g_seats[sn], o_seats[sn]))
    seat_score = round(MAX_PLAYERS * seat_hits / max(len(g_seats), 1))
    score += seat_score
    if seat_hits < len(g_seats):
        wrong = [f"seat_{sn}: esperado '{g_seats[sn]}' obtido '{o_seats.get(sn,'?')}'"
                 for sn in g_seats
                 if sn not in o_seats or not _name_match(g_seats[sn], o_seats[sn])]
        issues.append(f"JOGADORES ({seat_score}/{MAX_PLAYERS}): {'; '.join(wrong)}")
    else:
        issues.append(f"JOGADORES ({seat_score}/{MAX_PLAYERS}): ✓")

    # ── 2. Posições (10 pts) ──────────────────────────────────────────────────
    MAX_POS = 10
    key_positions = ["BTN", "SB", "BB", "STR"]
    g_pos = {pos: name for name, pos in gabarito["positions"].items() if pos in key_positions}
    o_pos = {pos: name for name, pos in output["positions"].items()  if pos in key_positions}
    pos_hits = sum(1 for pos in g_pos
                   if pos in o_pos and _name_match(g_pos[pos], o_pos[pos]))
    pos_score = round(MAX_POS * pos_hits / max(len(g_pos), 1))
    score += pos_score
    if pos_hits < len(g_pos):
        wrong = [f"{pos}: esperado '{g_pos[pos]}' obtido '{o_pos.get(pos,'?')}'"
                 for pos in g_pos
                 if pos not in o_pos or not _name_match(g_pos[pos], o_pos[pos])]
        issues.append(f"POSIÇÕES ({pos_score}/{MAX_POS}): {'; '.join(wrong)}")
    else:
        issues.append(f"POSIÇÕES ({pos_score}/{MAX_POS}): ✓")

    # ── 3–6. Ações por street ─────────────────────────────────────────────────
    for street, max_pts, label in [
        ("preflop", 20, "PREFLOP"),
        ("flop",    15, "FLOP"),
        ("turn",    15, "TURN"),
        ("river",   10, "RIVER"),
    ]:
        pts, msg = _compare_actions(
            gabarito["actions"][street],
            output["actions"][street],
            max_pts, label,
        )
        score += pts
        issues.append(msg)

    # ── 7. Vencedor (10 pts) ──────────────────────────────────────────────────
    MAX_WIN = 10
    g_win = gabarito["winner"]
    o_win = output["winner"]
    if _name_match(g_win, o_win):
        score += MAX_WIN
        issues.append(f"VENCEDOR ({MAX_WIN}/{MAX_WIN}): ✓ {g_win}")
    else:
        issues.append(f"VENCEDOR (0/{MAX_WIN}): esperado '{g_win}' obtido '{o_win}'")

    return {"score": score, "issues": issues}


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    gabarito_path = os.path.normpath(GABARITO_PATH)
    if not os.path.exists(gabarito_path):
        print(f"Erro: gabarito não encontrado em {gabarito_path}")
        sys.exit(1)

    if len(sys.argv) > 1:
        out_path = sys.argv[1]
    else:
        candidates = sorted(glob.glob("output/hands_*.txt"), key=os.path.getmtime)
        if not candidates:
            print("Nenhum arquivo output/hands_*.txt encontrado. Rode o pipeline primeiro.")
            sys.exit(1)
        out_path = candidates[-1]

    print(f"Output : {out_path}")
    print(f"Gabarito: {gabarito_path}")
    print()

    total_score = 0
    total_max   = len(HANDS_TO_COMPARE) * 100

    for table_id in HANDS_TO_COMPARE:
        gab_block = extract_hand(table_id, gabarito_path)
        if not gab_block:
            print(f"[{table_id}] ERRO: mesa não encontrada no gabarito!")
            continue

        out_block = extract_hand(table_id, out_path)
        if not out_block:
            print(f"[{table_id}] ERRO: mesa não encontrada no output — 0/100")
            print()
            continue

        gab = parse_hand(gab_block)
        out = parse_hand(out_block)
        result = compare_hand(gab, out)

        total_score += result["score"]
        bar = "█" * (result["score"] // 5) + "░" * (20 - result["score"] // 5)
        print(f"{'─'*60}")
        print(f"  {table_id}   {result['score']:3d}/100  [{bar}]")
        print(f"{'─'*60}")
        for issue in result["issues"]:
            print(issue)
        if result["score"] == 100:
            print("  ✓ PERFEITO!")
        else:
            print(f"  Faltam {100 - result['score']} pts.")
        print()

    print("═" * 60)
    bar = "█" * (total_score * 20 // total_max) + "░" * (20 - total_score * 20 // total_max)
    print(f"  TOTAL   {total_score:3d}/{total_max}  [{bar}]")
    print("═" * 60)

    return total_score


if __name__ == "__main__":
    main()
