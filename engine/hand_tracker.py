"""
Rastreia mãos de poker a partir da sequência de resultados OCR.

Recebe a lista de frames já lidos (com timestamps) e agrupa em mãos
por mesa, detectando início, rua ativa, ações e fim de cada mão.
Infere posições (BTN/SB/BB/etc.) a partir das apostas iniciais.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field


# ── posições ─────────────────────────────────────────────────────────────────

_POSITION_NAMES: dict[int, list[str]] = {
    2: ["BTN/SB", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["BTN", "SB", "BB", "STR"],
    5: ["BTN", "SB", "BB", "STR", "CO"],
    6: ["BTN", "SB", "BB", "STR", "HJ", "CO"],
    7: ["BTN", "SB", "BB", "STR", "MP", "HJ", "CO"],
    8: ["BTN", "SB", "BB", "STR", "UTG+1", "MP", "HJ", "CO"],
    9: ["BTN", "SB", "BB", "STR", "UTG+1", "MP", "LJ", "HJ", "CO"],
}


def _clockwise_order(regions: dict) -> list[str]:
    """Retorna seat_keys ordenados em sentido horário pelo ângulo do centro da mesa."""
    seat_keys = [f"seat_{i}" for i in range(1, 9) if f"seat_{i}" in regions]
    if not seat_keys:
        return seat_keys
    xs = [regions[k][0] + regions[k][2] / 2 for k in seat_keys]
    ys = [regions[k][1] + regions[k][3] / 2 for k in seat_keys]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)

    def cw_angle(k: str) -> float:
        x = regions[k][0] + regions[k][2] / 2 - cx
        y = regions[k][1] + regions[k][3] / 2 - cy
        return math.atan2(x, -y) % (2 * math.pi)

    return sorted(seat_keys, key=cw_angle)


def _find_positions(bets: dict, seat_order: list[str], seats: dict) -> dict[str, str]:
    """
    Infere posições a partir das apostas no início da mão.
    SB = menor aposta, BB = segunda menor, STR = terceira (straddle obrigatório).
    BTN = assento imediatamente antes do SB na ordem horária.
    Demais posições distribuídas em sentido horário a partir do BTN.

    Straddle obrigatório (>= 4 jogadores):
    Quando 4+ assentos ativos e 3 apostas iniciais detectadas, o terceiro blind
    é o STR (straddle = 2BB). Posições: BTN → SB → BB → STR → demais.
    Com 3 ou menos jogadores: apenas SB + BB, sem straddle.
    """
    if not bets or not seat_order:
        return {}

    active = [s for s in seat_order if s in seats]
    if len(active) < 2:
        return {}

    # bet_seats[0] = SB (menor), [1] = BB, [2] = STR se existir
    bet_seats = sorted(bets.items(), key=lambda x: x[1])
    if len(bet_seats) < 2:
        return {}

    sb_seat = bet_seats[0][0]
    if sb_seat not in active:
        return {}

    # Straddle obrigatório: 4+ jogadores ativos E 3 apostas iniciais detectadas.
    # Se len(bets) >= 3 mas len(active) < 4: ignorar straddle (edge case de all-in
    # em mesa curta — apostas extras não representam blind de straddle).
    has_straddle = len(active) >= 4 and len(bet_seats) >= 3

    sb_idx   = active.index(sb_seat)
    btn_idx  = (sb_idx - 1) % len(active)
    btn_seat = active[btn_idx]

    n     = len(active)
    names = _POSITION_NAMES.get(
        n,
        ["BTN", "SB", "BB", "STR"] + [f"P{i}" for i in range(n - 4)]
    )

    btn_abs   = active.index(btn_seat)
    positions = {active[(btn_abs + i) % n]: name for i, name in enumerate(names)}

    # Garante que o assento straddler (terceira aposta) está marcado como "STR".
    if has_straddle:
        str_seat = bet_seats[2][0]
        if str_seat in positions:
            positions[str_seat] = "STR"

    return positions


# ── dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Action:
    seat:      str    # "seat_3"
    player:    str    # "FrankFong"
    position:  str    # "BTN"
    action:    str    # "fold" | "call" | "raise" | "bet" | "check" | "unknown"
    amount_bb: float  # 0.0 para fold/check
    street:    str    # "preflop" | "flop" | "turn" | "river"
    ts:        float  # timestamp do frame


@dataclass
class Hand:
    table_key:   str
    table_id:    str
    hand_number: int
    start_ts:    float
    end_ts:      float      = 0.0
    streets:     dict       = field(default_factory=lambda: {
        "preflop": [], "flop": [], "turn": [], "river": []
    })
    players:     dict       = field(default_factory=dict)
    pot_peak:    float      = 0.0
    positions:   dict       = field(default_factory=dict)
    hero_cards:  list[str]  = field(default_factory=list)
    actions:     list       = field(default_factory=list)   # list[Action]
    winner:      str        = ""

    def duration(self) -> float:
        return self.end_ts - self.start_ts

    def summary(self) -> str:
        dur = self.duration()
        parts = []
        for sk, info in self.players.items():
            if not info.get("name"):
                continue
            pos = self.positions.get(sk, "")
            tag = f"[{pos}]" if pos else ""
            parts.append(f"{info['name']}{tag}({info['stack_start']}→{info['stack_end']} BB)")
        hero = f" hero={self.hero_cards}" if self.hero_cards else ""
        win  = f" vencedor={self.winner}" if self.winner else ""
        return (
            f"Mão #{self.hand_number} [{self.table_id}] "
            f"{self.start_ts:.1f}s-{self.end_ts:.1f}s ({dur:.0f}s) "
            f"pot_peak={self.pot_peak} BB{hero}{win} | {', '.join(parts)}"
        )


# ── inferência de ações ───────────────────────────────────────────────────────

def _infer_actions(prev: dict, curr: dict,
                   positions: dict, players: dict, street: str) -> list[Action]:
    """
    Infere ações comparando dois frames consecutivos da mesma mão.

    Algoritmo conservador:
      - bet aumentou               → raise ou bet
      - bet desapareceu + pot subiu proporcionalmente → call
      - bet desapareceu + pot não subiu              → fold
      - stack caiu sem bet visível → unknown (possível all-in silencioso)
    """
    actions: list[Action] = []
    prev_bets  = prev.get("bets", {})
    curr_bets  = curr.get("bets", {})
    prev_pot   = prev.get("pot") or 0.0
    curr_pot   = curr.get("pot") or 0.0
    pot_delta  = curr_pot - prev_pot
    prev_seats = prev.get("seats", {})
    curr_seats = curr.get("seats", {})
    ts = curr["ts"]

    all_seats = set(prev_seats) | set(curr_seats)
    for sk in sorted(all_seats):
        prev_bet   = prev_bets.get(sk) or 0.0
        curr_bet   = curr_bets.get(sk) or 0.0
        prev_stack = (prev_seats.get(sk) or {}).get("stack")
        curr_stack = (curr_seats.get(sk) or {}).get("stack")
        name = players.get(sk, {}).get("name", "")
        pos  = positions.get(sk, "")

        if curr_bet > prev_bet + 0.05:
            amount = round(curr_bet - prev_bet, 2)
            action_type = "raise" if prev_bet > 0.05 else "bet"
            actions.append(Action(sk, name, pos, action_type, amount, street, ts))

        elif prev_bet > 0.05 and curr_bet < 0.05:
            if pot_delta >= prev_bet * 0.9:
                actions.append(Action(sk, name, pos, "call", round(prev_bet, 2), street, ts))
            else:
                actions.append(Action(sk, name, pos, "fold", 0.0, street, ts))

        elif (prev_bet < 0.05 and curr_bet < 0.05
              and prev_stack is not None and curr_stack is not None):
            stack_drop = round(prev_stack - curr_stack, 2)
            if stack_drop > 0.5:
                actions.append(Action(sk, name, pos, "unknown", stack_drop, street, ts))

    return actions


# ── tracker ───────────────────────────────────────────────────────────────────

class HandTracker:
    """
    Processa uma sequência de resultados OCR e identifica mãos de poker.

    Lógica de detecção:
      - Início:  pot passa de 0/None → valor > 0 (blinds postados)
      - Rua:     número de cartas comunitárias muda (0→3 flop, +1 turn/river)
      - Fim:     pot volta a 0/None após ter sido > 0
      - Posições: inferidas das apostas (bets) no frame de início da mão
      - Ações:   inferidas comparando bets/pot entre frames consecutivos
      - Vencedor: jogador com maior ganho líquido ao fim da mão

    Straddle obrigatório (>= 4 jogadores):
      Quando 4 ou mais assentos ativos e 3 apostas iniciais detectadas, o terceiro
      blind é o STR (straddle = 2BB). Posições: BTN → SB → BB → STR → demais.
      Com 3 ou menos jogadores: apenas SB + BB, sem straddle.
    """

    def __init__(self, cfg: dict | None = None):
        self._seat_orders: dict[str, list[str]] = {}
        if cfg:
            for tk, regs in cfg.get("regions", {}).items():
                self._seat_orders[tk] = _clockwise_order(regs)

    def process_sequence(self, ocr_results: list[dict]) -> list[Hand]:
        """
        ocr_results: [{"timestamp": float, "tables": {tk: {table_id, pot, seats, bets,
                        community_cards, hero_cards, ...}}}, ...]
        Retorna lista de Hand encerradas, ordenadas por timestamp de início.
        """
        all_hands:      list[Hand]              = []
        active:         dict[str, Hand | None]  = {}
        hand_counters:  dict[str, int]          = {}
        prev_pots:      dict[str, float | None] = {}
        prev_n_cards:   dict[str, int]          = {}
        prev_frame_data: dict[str, dict]        = {}   # tk → último frame para inferência de ações

        for entry in ocr_results:
            ts = entry["timestamp"]

            for tk, data in entry["tables"].items():
                if data.get("_from_cache"):
                    continue

                pot             = data.get("pot")
                seats           = data.get("seats", {})
                bets            = data.get("bets", {})
                table_id        = data.get("table_id", "")
                community_cards = data.get("community_cards", [])
                hero_cards      = data.get("hero_cards", [])
                n_cards         = len(community_cards)

                prev_pot = prev_pots.get(tk)
                current  = active.get(tk)

                # frame compacto para inferência de ações
                frame_data = {
                    "ts": ts, "pot": pot, "seats": seats,
                    "bets": bets, "community_cards": community_cards,
                }

                # ── início de mão ────────────────────────────────────────────
                if current is None and pot and pot > 0:
                    hand_counters[tk] = hand_counters.get(tk, 0) + 1
                    current = Hand(
                        table_key=tk,
                        table_id=table_id,
                        hand_number=hand_counters[tk],
                        start_ts=ts,
                    )
                    for sk, info in seats.items():
                        current.players[sk] = {
                            "name":        info.get("name", ""),
                            "stack_start": info.get("stack"),
                            "stack_end":   None,
                        }

                    seat_order = self._seat_orders.get(tk, [])
                    current.positions = _find_positions(bets, seat_order, seats)

                    active[tk]           = current
                    prev_n_cards[tk]     = n_cards
                    prev_frame_data[tk]  = frame_data

                # ── atualiza mão em andamento ─────────────────────────────────
                if current is not None:
                    street = _street_from_cards(n_cards)
                    current.streets[street].append({
                        "ts": ts, "pot": pot, "seats": seats,
                        "bets": bets, "community_cards": community_cards,
                    })

                    if pot and pot > current.pot_peak:
                        current.pot_peak = pot

                    if n_cards != prev_n_cards.get(tk, 0):
                        prev_n_cards[tk] = n_cards

                    # Cartas do hero — captura o primeiro frame onde aparecem
                    if not current.hero_cards and hero_cards:
                        current.hero_cards = hero_cards

                    # Atualiza posições se chegaram apostas num frame subsequente
                    if bets and not current.positions:
                        seat_order = self._seat_orders.get(tk, [])
                        current.positions = _find_positions(bets, seat_order, seats)

                    # Preserva nome anterior se OCR retornou vazio (timebank)
                    for sk, info in seats.items():
                        new_name    = info.get("name", "")
                        cached_name = current.players.get(sk, {}).get("name", "")
                        if not new_name and cached_name:
                            info = {**info, "name": cached_name}
                        current.players[sk] = {
                            "name":        info.get("name", ""),
                            "stack_start": current.players.get(sk, {}).get("stack_start"),
                            "stack_end":   info.get("stack"),
                        }

                    # Inferência de ações entre frames consecutivos
                    if tk in prev_frame_data:
                        new_actions = _infer_actions(
                            prev_frame_data[tk], frame_data,
                            current.positions, current.players, street
                        )
                        current.actions.extend(new_actions)
                    prev_frame_data[tk] = frame_data

                    # ── fim de mão ────────────────────────────────────────────
                    if (pot is None or pot == 0) and prev_pot and prev_pot > 0:
                        current.end_ts = ts
                        for sk, info in seats.items():
                            if sk in current.players:
                                current.players[sk]["stack_end"] = info.get("stack")
                            else:
                                current.players[sk] = {
                                    "name":        info.get("name", ""),
                                    "stack_start": None,
                                    "stack_end":   info.get("stack"),
                                }

                        current.winner = _detect_winner(current.players)
                        all_hands.append(current)
                        active[tk]          = None
                        prev_frame_data.pop(tk, None)

                prev_pots[tk] = pot

        # Fecha mãos ainda abertas no fim do vídeo
        last_ts = ocr_results[-1]["timestamp"] if ocr_results else 0.0
        for tk, hand in active.items():
            if hand is not None:
                hand.end_ts = last_ts
                hand.winner = _detect_winner(hand.players)
                all_hands.append(hand)

        all_hands.sort(key=lambda h: h.start_ts)
        return all_hands


# ── helpers ───────────────────────────────────────────────────────────────────

def _street_from_cards(n_cards: int) -> str:
    if n_cards >= 5:
        return "river"
    if n_cards == 4:
        return "turn"
    if n_cards == 3:
        return "flop"
    return "preflop"


def _detect_winner(players: dict) -> str:
    """
    Identifica o vencedor pela maior variação líquida de stack.
    Retorna "split" se dois ou mais jogadores tiveram ganho igual,
    "" se não houver dados suficientes.
    """
    nets: dict[str, float] = {}
    for sk, info in players.items():
        s_start = info.get("stack_start")
        s_end   = info.get("stack_end")
        if s_start is None or s_end is None:
            continue
        nets[sk] = round(s_end - s_start, 2)

    if not nets:
        return ""

    max_net = max(nets.values())
    if max_net <= 0.05:
        return ""

    winners = [sk for sk, net in nets.items() if abs(net - max_net) < 0.5]
    if len(winners) > 1:
        return "split"
    return players[winners[0]].get("name", "")


def print_summary(hands: list[Hand]) -> None:
    """Imprime resumo das mãos agrupado por mesa."""
    if not hands:
        print("Nenhuma mão detectada.")
        return

    by_table: dict[str, list[Hand]] = {}
    for h in hands:
        by_table.setdefault(h.table_key, []).append(h)

    total_dur = sum(h.duration() for h in hands)
    avg_dur   = total_dur / len(hands) if hands else 0

    print(f"\n{'='*60}")
    print(f"RESUMO: {len(hands)} mãos detectadas  |  duração média: {avg_dur:.0f}s")
    print(f"{'='*60}")

    for tk, tk_hands in sorted(by_table.items()):
        durs    = [h.duration() for h in tk_hands]
        avg     = sum(durs) / len(durs) if durs else 0
        pot_avg = sum(h.pot_peak for h in tk_hands) / len(tk_hands) if tk_hands else 0
        print(f"\n  {tk}: {len(tk_hands)} mãos  |  duração média {avg:.0f}s  |  pot médio {pot_avg:.1f} BB")
        for h in tk_hands:
            n_players = sum(1 for p in h.players.values() if p.get("name"))
            streets   = [s for s, f in h.streets.items() if f]
            pos_str   = " ".join(
                f"{h.positions[s]}:{h.players[s]['name']}"
                for s in sorted(h.positions)
                if s in h.players and h.players[s].get("name")
            ) if h.positions else ""
            hero_str  = f"  hero={h.hero_cards}" if h.hero_cards else ""
            win_str   = f"  vencedor={h.winner}" if h.winner else ""
            print(f"    #{h.hand_number:>3}  {h.start_ts:6.1f}s-{h.end_ts:6.1f}s  "
                  f"pot_peak={h.pot_peak:6.1f} BB  "
                  f"jogadores={n_players}  ruas={'+'.join(streets)}"
                  f"{hero_str}{win_str}"
                  + (f"\n         {pos_str}" if pos_str else ""))
