"""
Serializa mãos rastreadas para o formato PokerStars Hand History (.txt).
Compatível com importação no Hand2Note selecionando "PokerStars" como origem.

Suits das cartas são placeholders ciclicamente distribuídos (detecção real
de suit via OCR é trabalho futuro); análise de equity será imprecisa mas
análise de ação/posição/stack funcionará corretamente.
"""
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from engine.hand_tracker import Hand, Action


# ── suits placeholder ─────────────────────────────────────────────────────────

_SUIT_CYCLE = ["h", "d", "c", "s"]


def _assign_placeholder_suits(cards: list[str],
                               used: set[str] | None = None) -> list[str]:
    """
    Atribui suits ciclicamente aos ranks, evitando combinações rank+suit repetidas.
    Cards que já possuem suit real (len>=2 e card[1] in 'hdcs') são mantidas.
    'used' deve ser compartilhado ao longo de todo o board de uma mão para
    evitar colisões entre flop/turn/river.
    """
    if used is None:
        used = set()
    result: list[str] = []
    suit_idx = 0
    for card in cards:
        rank = card[0] if card else "?"
        # Card already has real suit from color detection — keep it
        if len(card) >= 2 and card[1] in "hdcs":
            used.add(card)
            result.append(card)
            continue
        # Assign placeholder suit cyclically
        placed = False
        for _ in range(4):
            suit = _SUIT_CYCLE[suit_idx % 4]
            suit_idx += 1
            candidate = f"{rank}{suit}"
            if candidate not in used:
                used.add(candidate)
                result.append(candidate)
                placed = True
                break
        if not placed:
            result.append(f"{rank}?")   # fallback improvável com ≤13 cartas
    return result


# ── parsing de blinds ─────────────────────────────────────────────────────────

def parse_blinds(blinds_str: str) -> dict:
    """
    Parseia a string de blinds do OCR para valores monetários reais.
    Tolerante a OCR noise: 'O' isolado → '0'.

    Retorna: {sb, bb, str, ante, currency}

    Exemplos:
        "0.05/0.1/0.2(0.05)" → sb=0.05, bb=0.10, str=0.20, ante=0.05
        "0.5/1/2"             → sb=0.5,  bb=1.0,  str=2.0,  ante=0.5
        "5/10"                → sb=5,    bb=10,   str=None,  ante=5
        "0.05/O.1/0.2(O.05)"  → idem primeiro caso (O→0)
    """
    # Substituir 'O' isolado (rodeado por não-letra) por '0'
    s = re.sub(r"(?<![A-Za-z])O(?![A-Za-z])", "0", blinds_str.strip())

    # Extrair ante dos parênteses, se presente
    ante: float | None = None
    m = re.search(r"\(([0-9.]+)\)", s)
    if m:
        ante = float(m.group(1))
        s = re.sub(r"\([^)]*\)", "", s).strip()

    parts = [p.strip() for p in s.split("/") if p.strip()]
    if len(parts) < 2:
        return {"sb": 0.5, "bb": 1.0, "str": 2.0, "ante": 0.5, "currency": "$"}

    try:
        sb      = float(parts[0])
        bb      = float(parts[1])
        str_val: float | None = float(parts[2]) if len(parts) >= 3 else None
    except ValueError:
        return {"sb": 0.5, "bb": 1.0, "str": 2.0, "ante": 0.5, "currency": "$"}

    if ante is None:
        ante = sb   # ante = SB quando não explicitado

    return {"sb": sb, "bb": bb, "str": str_val, "ante": ante, "currency": "$"}


# ── helpers internos ──────────────────────────────────────────────────────────

def _get_street_cards(frames: list) -> list[str]:
    """Community_cards com mais cartas; em empate, prefere o último frame (pós-animação)."""
    best: list[str] = []
    best_suits = 0
    for frame in frames:
        cards = frame.get("community_cards", [])
        n_suits = sum(1 for c in cards if len(c) >= 2 and c[1] in "hdcs")
        # >= instead of >: last frame with same card count wins, avoiding animation frames
        if len(cards) > len(best) or (len(cards) == len(best) and n_suits >= best_suits):
            best = list(cards)
            best_suits = n_suits
    return best


def _seat_num(sk: str) -> int:
    return int(sk.split("_")[1])


_SUMMARY_LABELS = {
    "BTN": "button",
    "SB":  "small blind",
    "BB":  "big blind",
    "STR": "straddle",
}


def _seat_role(sk: str, h: Hand) -> str:
    label = _SUMMARY_LABELS.get(h.positions.get(sk, ""), "")
    return f"({label}) " if label else ""


def _format_action(action: Action, bb_value: float,
                   currency: str, hero_seat: str = "") -> str:
    """Formata uma Action para o texto PokerStars."""
    player = action.player
    amt    = round(action.amount_bb * bb_value, 2)
    act    = action.action

    if act == "fold":
        return f"{player}: folds"
    if act == "check":
        return f"{player}: checks"
    if act in ("call", "unknown"):
        return f"{player}: calls {currency}{amt:.2f}"
    if act == "bet":
        return f"{player}: bets {currency}{amt:.2f}"
    if act == "raise":
        to_amt = round(action.total_bb * bb_value, 2)
        return f"{player}: raises {currency}{amt:.2f} to {currency}{to_amt:.2f}"
    return ""


# ── conversão de uma mão para bloco PokerStars ────────────────────────────────

def _hand_to_ps(h: Hand) -> str:
    blinds   = parse_blinds(h.blinds)
    bb       = blinds["bb"]
    sb       = blinds["sb"]
    str_val  = blinds["str"]
    ante     = blinds["ante"]
    currency = blinds["currency"]

    # Hero: usa winner_label se disponível; substitui nome real por "Hero" nas actions
    winner    = getattr(h, "winner_label", "") or h.winner
    hero_seat = getattr(h, "hero_seat", "")
    hero_name = h.players.get(hero_seat, {}).get("name", "") if hero_seat else ""

    hand_id = int(h.start_ts * 1000) * 100 + h.hand_number

    # Timestamp: data de hoje + offset igual ao start_ts do vídeo
    today  = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ts_str = (today + timedelta(seconds=h.start_ts)).strftime("%Y/%m/%d %H:%M:%S")

    # Stakes no header — formato GGPoker: ($SB/$BB/$STR(ante))
    ante_str = f"({ante:.2f})" if ante else ""
    if str_val:
        stakes = (f"({currency}{sb:.2f}/{currency}{bb:.2f}"
                  f"/{currency}{str_val:.2f}{ante_str})")
    else:
        stakes = f"({currency}{sb:.2f}/{currency}{bb:.2f}{ante_str})"

    # Assentos ocupados ordenados pelo número
    seat_items = sorted(
        [(sk, info) for sk, info in h.players.items() if info.get("name")],
        key=lambda x: _seat_num(x[0]),
    )

    # Número do assento BTN para o header
    btn_sk  = next((sk for sk, pos in h.positions.items() if pos == "BTN"), None)
    btn_num = (_seat_num(btn_sk) if btn_sk
               else (_seat_num(seat_items[0][0]) if seat_items else 1))

    lines: list[str] = []

    # ── header ────────────────────────────────────────────────────────────────
    lines.append(
        f"PokerStars Hand #{hand_id}: Hold'em No Limit {stakes} - {ts_str} ET"
    )
    lines.append(f"Table '{h.table_id}' 8-max Seat #{btn_num} is the button")

    # ── lista de assentos ─────────────────────────────────────────────────────
    for sk, info in seat_items:
        stack_real = round((info.get("stack_start") or 0.0) * bb, 2)
        lines.append(
            f"Seat {_seat_num(sk)}: {info['name']}"
            f" ({currency}{stack_real:.2f} in chips)"
        )

    # ── antes (todos os jogadores, em ordem de assento) ───────────────────────
    if ante:
        for _, info in seat_items:
            lines.append(f"{info['name']}: posts the ante {currency}{ante:.2f}")

    # ── blinds ────────────────────────────────────────────────────────────────
    for pos_name, label, amount in (
        ("SB",  "small blind", sb),
        ("BB",  "big blind",   bb),
        ("STR", "straddle",    str_val),
    ):
        if not amount:
            continue
        pos_sk = next((sk for sk, p in h.positions.items() if p == pos_name), None)
        if not pos_sk:
            continue
        pinfo = h.players.get(pos_sk)
        if pinfo and pinfo.get("name"):
            lines.append(
                f"{pinfo['name']}: posts {label} {currency}{amount:.2f}"
            )

    # ── hole cards ────────────────────────────────────────────────────────────
    lines.append("*** HOLE CARDS ***")
    if h.hero_cards:
        used_hero: set[str] = set()
        hero_suited = _assign_placeholder_suits(h.hero_cards, used_hero)
        lines.append(f"Dealt to {hero_name or 'Hero'} [{' '.join(hero_suited)}]")

    # ── cartas comunitárias com suits placeholder ─────────────────────────────
    used_board: set[str] = set()

    flop_ranks  = _get_street_cards(h.streets.get("flop", []))
    turn_full   = _get_street_cards(h.streets.get("turn", []))
    river_full  = _get_street_cards(h.streets.get("river", []))

    flop_suited = _assign_placeholder_suits(flop_ranks, used_board) if flop_ranks else []

    # Turn: apenas a 4ª carta (delta em relação ao flop)
    if len(turn_full) >= 4:
        turn_delta = [turn_full[3]]
    elif turn_full and len(turn_full) > len(flop_ranks):
        turn_delta = [turn_full[-1]]
    else:
        turn_delta = []
    turn_suited = _assign_placeholder_suits(turn_delta, used_board) if turn_delta else []

    # River: apenas a 5ª carta (delta em relação ao turn)
    if len(river_full) >= 5:
        river_delta = [river_full[4]]
    elif river_full and len(river_full) > max(len(turn_full), len(flop_ranks)):
        river_delta = [river_full[-1]]
    else:
        river_delta = []
    river_suited = _assign_placeholder_suits(river_delta, used_board) if river_delta else []

    # ── ações por rua ─────────────────────────────────────────────────────────
    def _emit_actions(street_name: str) -> None:
        for action in (a for a in h.actions if a.street == street_name):
            line = _format_action(action, bb, currency, hero_seat)
            if line:
                lines.append(line)

    _emit_actions("preflop")

    if flop_suited:
        lines.append(f"*** FLOP *** [{' '.join(flop_suited)}]")
        _emit_actions("flop")

    if turn_suited:
        lines.append(
            f"*** TURN *** [{' '.join(flop_suited)}] [{' '.join(turn_suited)}]"
        )
        _emit_actions("turn")

    if river_suited:
        lines.append(
            f"*** RIVER *** [{' '.join(flop_suited)}]"
            f" [{' '.join(turn_suited)}] [{' '.join(river_suited)}]"
        )
        _emit_actions("river")

    # ── uncalled bet + winner collect ─────────────────────────────────────────
    uncalled_amt = 0.0
    if h.actions:
        last_agg = next(
            (a for a in reversed(h.actions) if a.action in ("bet", "raise")),
            None,
        )
        if last_agg:
            agg_idx = h.actions.index(last_agg)
            called = any(
                a.action in ("call", "allin")
                for a in h.actions[agg_idx + 1:]
                if a.seat != last_agg.seat
            )
            if not called:
                ubet = round(last_agg.amount_bb * bb, 2)
                if ubet > 0.01:
                    uncalled_amt = ubet
                    lines.append(
                        f"Uncalled bet ({currency}{uncalled_amt:.2f})"
                        f" returned to {last_agg.player}"
                    )

    pot_total = round(h.pot_peak * bb, 2)
    pot_real  = round(pot_total - uncalled_amt, 2)

    if winner and winner != "split":
        lines.append(f"{winner} collected {currency}{pot_real:.2f} from pot")

    # ── showdown / doesn't show ───────────────────────────────────────────────
    # Showdown: river was played AND nobody folded on the river
    river_folds = [a for a in h.actions if a.action == "fold" and a.street == "river"]
    at_showdown = bool(river_suited) and not river_folds

    if winner and winner != "split":
        if at_showdown:
            lines.append("*** SHOW DOWN ***")
            if h.hero_cards and winner == hero_name:
                used_sd: set[str] = set()
                hero_sd = _assign_placeholder_suits(h.hero_cards, used_sd)
                lines.append(f"{hero_name}: shows [{' '.join(hero_sd)}] (a hand)")
            # Non-hero cards at showdown are not detected (accepted limitation)
        else:
            if winner != hero_name:
                lines.append(f"{winner}: doesn't show hand")
            elif h.hero_cards:
                lines.append(f"{hero_name}: doesn't show hand")

    # ── summary ───────────────────────────────────────────────────────────────
    lines.append("*** SUMMARY ***")
    lines.append(f"Total pot {currency}{pot_real:.2f} | Rake {currency}0.00")

    board_all = flop_suited + turn_suited + river_suited
    if board_all:
        lines.append(f"Board [{' '.join(board_all)}]")

    for sk, info in seat_items:
        name = info["name"]
        role = _seat_role(sk, h)

        if winner == name:
            outcome = f"collected ({currency}{pot_real:.2f})"
        elif winner == "split":
            split_amt = round(pot_real / 2, 2)
            outcome = f"collected ({currency}{split_amt:.2f})"
        else:
            folds = [a for a in h.actions if a.player == name and a.action == "fold"]
            if folds:
                s = folds[0].street
                if s == "preflop":
                    voluntary = any(
                        a.player == name and a.action in ("bet", "raise", "call", "allin")
                        for a in h.actions if a.street == "preflop"
                    )
                    suffix  = "" if voluntary else " (didn't bet)"
                    outcome = f"folded before Flop{suffix}"
                else:
                    outcome = f"folded on the {s.capitalize()}"
            else:
                outcome = "folded"

        lines.append(f"Seat {_seat_num(sk)}: {name} {role}{outcome}")

    lines.append("")   # linha em branco separadora entre mãos
    return "\n".join(lines)


# ── API pública ───────────────────────────────────────────────────────────────

def write_hands_ps(hands: list[Hand], video_path: str) -> str:
    """
    Serializa lista de Hand para formato PokerStars .txt.
    Retorna o caminho do arquivo criado.
    """
    stem      = Path(video_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"hands_{stem}_{timestamp}.txt"
    out_path  = os.path.join("output", filename)

    os.makedirs("output", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_hand_to_ps(h) for h in hands))

    return out_path
