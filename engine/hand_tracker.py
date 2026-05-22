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


def _find_positions(bets: dict, seat_order: list[str], seats: dict,
                    dealer_seat: str = "") -> dict[str, str]:
    """
    Infere posições a partir das apostas no início da mão.
    SB = menor aposta, BB = segunda menor, STR = terceira (straddle obrigatório).
    BTN = dealer_seat se detectado visualmente; caso contrário, seat antes do SB.
    Demais posições distribuídas em sentido horário a partir do STR/BB.

    Atribui BTN/SB/BB/STR diretamente dos dados de aposta para evitar
    conflito entre a distribuição horária e o override do straddle.
    """
    if not bets or not seat_order:
        return {}

    active = [s for s in seat_order if s in seats]
    if len(active) < 2:
        return {}

    bet_seats = sorted(bets.items(), key=lambda x: x[1])
    if len(bet_seats) < 2:
        return {}

    sb_seat = bet_seats[0][0]
    bb_seat = bet_seats[1][0]
    if sb_seat not in active or bb_seat not in active:
        return {}

    has_straddle = (len(active) >= 4 and len(bet_seats) >= 3
                    and bet_seats[2][0] in active)
    str_seat = bet_seats[2][0] if has_straddle else None

    sb_idx = active.index(sb_seat)
    # BTN direto da tela (dealer_seat ROI) se disponível; senão infere do SB
    if dealer_seat and dealer_seat in active:
        btn_seat = dealer_seat
    else:
        btn_seat = active[(sb_idx - 1) % len(active)]

    # Atribuição direta das posições cegas — sem risco de dupla atribuição
    positions: dict[str, str] = {btn_seat: "BTN", sb_seat: "SB", bb_seat: "BB"}
    if str_seat:
        positions[str_seat] = "STR"

    # Distribui posições restantes em sentido horário a partir do anchor (STR ou BB)
    anchor     = str_seat if str_seat else bb_seat
    anchor_idx = active.index(anchor)
    n          = len(active)
    n_fixed    = 4 if has_straddle else 3

    pos_names_all = _POSITION_NAMES.get(
        n, ["BTN", "SB", "BB", "STR"] + [f"P{i}" for i in range(n - 4)]
    )
    remaining_names = pos_names_all[n_fixed:]

    remaining_seats = [s for s in active if s not in positions]
    remaining_seats.sort(key=lambda s: (active.index(s) - anchor_idx - 1) % n)

    for i, sk in enumerate(remaining_seats):
        positions[sk] = remaining_names[i] if i < len(remaining_names) else f"P{i}"

    return positions


# ── dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Action:
    seat:      str    # "seat_3"
    player:    str    # "FrankFong"
    position:  str    # "BTN"
    action:    str    # "fold" | "call" | "raise" | "bet" | "check" | "unknown"
    amount_bb: float  # incremento desta ação (0.0 para fold/check)
    street:    str    # "preflop" | "flop" | "turn" | "river"
    ts:        float  # timestamp do frame
    total_bb:  float = 0.0  # total investido pelo jogador nesta rua após a ação


@dataclass
class StreetState:
    """
    Estado de uma rua de apostas, mantido entre frames para classificação correta.
    Uma instância por mesa por rua — resetada quando n_cards muda.
    """
    street:           str
    max_bet:          float = 0.0   # maior bet ativo antes do frame atual
    voluntary_raises: int   = 0     # raises voluntários (não conta posts de blinds)
    last_aggressor:   str   = ""    # seat_key do último raiser/bettor
    invested:         dict  = field(default_factory=dict)  # seat → total investido na rua
    has_acted:        set   = field(default_factory=set)   # seats que já agiram
    limpers:          set   = field(default_factory=set)   # seats que fizeram limp
    straddle_val:     float = 0.0   # valor do straddle postado (GGPoker subtrai do call/raise)


@dataclass
class Hand:
    table_key:    str
    table_id:     str
    hand_number:  int
    start_ts:     float
    end_ts:       float     = 0.0
    streets:      dict      = field(default_factory=lambda: {
        "preflop": [], "flop": [], "turn": [], "river": []
    })
    players:      dict      = field(default_factory=dict)
    pot_peak:     float     = 0.0
    positions:    dict      = field(default_factory=dict)
    hero_cards:   list[str] = field(default_factory=list)
    actions:      list      = field(default_factory=list)   # list[Action]
    winner:       str       = ""
    winner_label: str       = ""   # detectado via ROI — tem prioridade sobre winner
    blinds:       str       = ""   # OCR do título: "0.05/0.1/0.2(0.05)"
    hero_seat:    str       = ""   # seat_key do jogador hero

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
            parts.append(f"{info['name']}{tag}({info['stack_start']}->{info['stack_end']} BB)")
        hero = f" hero={self.hero_cards}" if self.hero_cards else ""
        win  = f" vencedor={self.winner}" if self.winner else ""
        return (
            f"Mão #{self.hand_number} [{self.table_id}] "
            f"{self.start_ts:.1f}s-{self.end_ts:.1f}s ({dur:.0f}s) "
            f"pot_peak={self.pot_peak} BB{hero}{win} | {', '.join(parts)}"
        )


# ── ações por rótulo visual ──────────────────────────────────────────────────

def _actions_from_labels(
    prev_labels: dict,
    curr_labels: dict,
    curr_bets:   dict,
    positions:   dict,
    players:     dict,
    street:      str,
    state:       "StreetState",
    ts:          float,
) -> tuple[list, "StreetState"]:
    """
    Emite ações quando o rótulo de ação de um assento muda entre frames.
    Usa o valor de curr_bets[seat] como montante da ação.
    """
    actions = []
    for sk, label in curr_labels.items():
        if label == prev_labels.get(sk):
            continue  # sem mudança, não é nova ação
        name = players.get(sk, {}).get("name", "")
        pos  = positions.get(sk, "")
        bet  = curr_bets.get(sk, 0.0) or 0.0

        if label == "fold":
            state.has_acted.add(sk)
            actions.append(Action(sk, name, pos, "fold", 0.0, street, ts,
                                  total_bb=state.invested.get(sk, 0.0)))

        elif label == "check":
            state.has_acted.add(sk)
            actions.append(Action(sk, name, pos, "check", 0.0, street, ts))

        elif label == "call":
            already = state.invested.get(sk, 0.0)
            # GGPoker subtracts the straddle value from call/raise increments when the
            # player has already invested more than the straddle (i.e., they raised or
            # called a raise). This matches the native GGPoker hand history format.
            straddle_adj = (state.straddle_val
                            if state.straddle_val > 0 and already > state.straddle_val
                            else 0.0)
            amount = round(max(0.0, state.max_bet - already - straddle_adj), 2)
            state.invested[sk] = round(already + amount, 2)
            state.has_acted.add(sk)
            action = Action(sk, name, pos, "call", amount, street, ts,
                            total_bb=state.invested[sk])
            assert action.total_bb >= action.amount_bb, (
                f"total_bb {action.total_bb} < amount_bb {action.amount_bb}"
            )
            actions.append(action)

        elif label in ("bet", "raise", "allin"):
            total_chip = round(bet, 2)
            prev_max = state.max_bet
            if total_chip < 0.01:
                continue
            # increment = amount above previous max (PS "raises X to Y" convention)
            increment = round(max(0.0, total_chip - prev_max), 2)
            state.invested[sk] = total_chip   # set to total chip (not add to prior invested)
            state.max_bet       = max(state.max_bet, total_chip)
            state.voluntary_raises += 1
            state.last_aggressor    = sk
            state.has_acted.add(sk)
            action_type = "allin" if label == "allin" else ("bet" if prev_max < 0.05 else "raise")
            action = Action(sk, name, pos, action_type, increment, street, ts,
                            total_bb=total_chip)
            assert action.total_bb >= action.amount_bb, (
                f"total_bb {action.total_bb} < amount_bb {action.amount_bb}"
            )
            actions.append(action)

        elif label in ("straddle", "post"):
            amount = round(bet, 2)
            currently = state.invested.get(sk, 0.0)
            if abs(currently - amount) < 0.02:
                # Blind/straddle already counted at hand init via dict(bets) → skip
                pass
            else:
                state.invested[sk] = round(currently + amount, 2)
                actions.append(Action(sk, name, pos, "post", amount, street, ts,
                                      total_bb=state.invested[sk]))

    return actions, state


# ── inferência de ações ───────────────────────────────────────────────────────

def _infer_actions(
    prev: dict,
    curr: dict,
    positions: dict,
    players: dict,
    street: str,
    state: StreetState,
) -> tuple[list[Action], StreetState]:
    """
    Infere ações comparando dois frames consecutivos da mesma mão.
    Retorna (lista de ações, estado da rua atualizado).
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
            already_invested = state.invested.get(sk, 0.0)
            # Suppress blind/straddle chip re-appearing on screen (already counted at init).
            # Condition: chip was absent (prev_bet≈0) and the new chip value matches the
            # already-invested blind/straddle amount → not new money.
            if prev_bet < 0.02 and abs(curr_bet - already_invested) < 0.02:
                continue
            others_max = max((v for k, v in curr_bets.items() if k != sk), default=0.0)
            prev_max   = state.max_bet  # captura antes de atualizar

            if curr_bet <= others_max + 0.02 or curr_bet <= state.max_bet + 0.02:
                action_type = "call"
                amount_bb   = round(curr_bet - prev_bet, 2)  # chips novos adicionados
            elif state.max_bet < 0.05:
                action_type = "bet"
                amount_bb   = round(curr_bet - prev_bet, 2)  # ← CORRETO: incremento sobre prev
                state.max_bet          = curr_bet
                state.voluntary_raises += 1
                state.last_aggressor   = sk
            else:
                action_type = "raise"
                amount_bb   = round(curr_bet - prev_max, 2)  # incremento sobre o max anterior
                state.max_bet          = curr_bet
                state.voluntary_raises += 1
                state.last_aggressor   = sk

            state.invested[sk] = state.invested.get(sk, 0.0) + round(curr_bet - prev_bet, 2)
            state.has_acted.add(sk)
            action = Action(sk, name, pos, action_type, amount_bb, street, ts,
                            total_bb=state.invested[sk])
            assert action.total_bb >= action.amount_bb, (
                f"total_bb {action.total_bb} < amount_bb {action.amount_bb}"
            )
            actions.append(action)

        elif prev_bet > 0.05 and curr_bet < 0.05:
            if pot_delta < 0:
                pass
            elif sk == state.last_aggressor:
                # O chip do aggressor some quando o pot é coletado — não é fold
                pass
            elif pot_delta >= prev_bet * 0.9 and pot_delta <= prev_bet * 3.0:
                # Chip sumiu E pot subiu compatível → call
                already = state.invested.get(sk, 0.0)
                # If player hasn't acted yet and their chip equals their initial blind/straddle
                # posting, the chip is stale — use max_bet - already as the real call amount.
                if (sk not in state.has_acted
                        and abs(prev_bet - already) < 0.02
                        and state.max_bet > already + 0.02):
                    call_amount = round(state.max_bet - already, 2)
                else:
                    call_amount = round(prev_bet, 2)
                if call_amount <= 0:
                    continue  # Zero-amount calls are spurious (player already matched max bet)
                total_bb = already + call_amount
                state.invested[sk] = total_bb
                state.has_acted.add(sk)
                action = Action(sk, name, pos, "call", call_amount,
                                street, ts, total_bb=total_bb)
                assert action.total_bb >= action.amount_bb, (
                    f"total_bb {action.total_bb} < amount_bb {action.amount_bb}"
                )
                actions.append(action)
            elif 0 <= pot_delta < prev_bet * 0.5:
                # Chip sumiu MAS pot não subiu → fold (exceto se pot_delta negativo)
                state.has_acted.add(sk)
                actions.append(Action(sk, name, pos, "fold", 0.0, street, ts,
                                      total_bb=state.invested.get(sk, 0.0)))
            # else: múltiplas ações no intervalo → omitir

        elif (prev_bet < 0.05 and curr_bet < 0.05
              and prev_stack is not None and curr_stack is not None):
            stack_drop = round(prev_stack - curr_stack, 2)
            if stack_drop > 0.5:
                state.has_acted.add(sk)
                actions.append(Action(sk, name, pos, "unknown", stack_drop, street, ts))

    return actions, state


# ── tracker ───────────────────────────────────────────────────────────────────

def _is_antes_frame(pot: float, bets: dict, seats: dict, cfg: dict) -> bool:
    """
    Detecta o frame de coleta de antes: pot > 0, bets vazio, pot ≈ ante_fraction × n_active.

    Quando antes obrigatórios são coletados no GGPoker, o pot sobe mas o dicionário
    de bets ainda está vazio (blinds ainda não foram postados). Esse sinal é usado
    para capturar hero_cards e o timestamp real do início da mão antes dos blinds.

    Retorna False imediatamente se bets não for vazio (blinds já postados) ou pot ≤ 0.
    """
    if not pot or pot <= 0 or bets:
        return False
    n_active = sum(1 for s in seats.values() if s.get("name") or s.get("stack"))
    if n_active < 2:
        return False
    ante_fraction = cfg.get("ante_fraction", 0.5)
    tolerance     = cfg.get("ante_tolerance_bb", 1.0)
    expected      = ante_fraction * n_active
    return abs(pot - expected) <= tolerance


def _derive_hero_seat(regions: dict) -> str:
    """Retorna o seat_key mais próximo da região hero_cards, se configurada."""
    hero_region = regions.get("hero_cards")
    if not hero_region:
        return ""
    hx = hero_region[0] + hero_region[2] / 2
    hy = hero_region[1] + hero_region[3] / 2
    best_sk, best_d = "", float("inf")
    for i in range(1, 9):
        sk = f"seat_{i}"
        if sk not in regions:
            continue
        r  = regions[sk]
        cx = r[0] + r[2] / 2
        cy = r[1] + r[3] / 2
        d  = (cx - hx) ** 2 + (cy - hy) ** 2
        if d < best_d:
            best_d, best_sk = d, sk
    return best_sk


class HandTracker:
    """
    Processa uma sequência de resultados OCR e identifica mãos de poker.

    Máquina de três estados por mesa:
      - IDLE:   pot=0, sem mão ativa → salva idle_seats (stacks pré-ante)
      - ANTES:  pot>0, bets={}, pot≈ante_fraction×n → captura ts e hero_cards reais
      - ACTIVE: pot sobe com blinds → rastreia ações, ruas e fim de mão

    Lógica de detecção:
      - Início real: frame de antes (pot>0, bets={}) — timestamp e hero_cards preservados
      - Início ACTIVE: primeiro frame com bets != {} após o frame de antes
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
        self._hero_seats:  dict[str, str]       = {}
        self._cfg: dict = cfg.get("ante_config", {}) if cfg else {}
        if cfg:
            for tk, regs in cfg.get("regions", {}).items():
                self._seat_orders[tk] = _clockwise_order(regs)
                hs = _derive_hero_seat(regs)
                if hs:
                    self._hero_seats[tk] = hs

    def process_sequence(self, ocr_results: list[dict]) -> list[Hand]:
        """
        ocr_results: [{"timestamp": float, "tables": {tk: {table_id, pot, seats, bets,
                        community_cards, hero_cards, ...}}}, ...]
        Retorna lista de Hand encerradas, ordenadas por timestamp de início.
        """
        all_hands:          list[Hand]              = []
        active:             dict[str, Hand | None]  = {}
        hand_counters:      dict[str, int]          = {}
        prev_pots:          dict[str, float | None] = {}
        prev_n_cards:       dict[str, int]          = {}
        max_n_cards:        dict[str, int]          = {}   # tk → max n_cards visto na mão atual
        known_community:    dict[str, list[str]]    = {}   # tk → cartas comunitárias acumuladas
        prev_frame_data:    dict[str, dict]         = {}   # tk → último frame para inferência
        street_states:      dict[str, StreetState]  = {}   # tk → estado da rua de apostas
        idle_seats:         dict[str, dict]         = {}   # tk → seats do último frame com pot=0 (pré-ante)
        antes_frames:       dict[str, dict]         = {}   # tk → {ts, hero_cards, seats, dealer_seat}
        prev_dealer_seats:  dict[str, str]          = {}   # tk → dealer_seat do frame anterior
        prev_action_labels: dict[str, dict]         = {}   # tk → {seat → último rótulo visto}

        for entry in ocr_results:
            ts = entry["timestamp"]

            for tk, data in entry["tables"].items():
                if data.get("_from_cache"):
                    continue

                pot             = data.get("pot")
                pot_ante        = data.get("pot_ante")
                seats           = data.get("seats", {})
                bets            = data.get("bets", {})
                table_id        = data.get("table_id", "")
                blinds_ocr      = data.get("blinds", "")
                community_cards      = data.get("community_cards", [])
                community_zone_suits  = data.get("community_zone_suits", [])
                community_zone_count = data.get("community_zone_count", 0)
                hero_cards           = data.get("hero_cards", [])
                winner_labels        = data.get("winner_labels", {})
                action_labels        = data.get("action_labels", {})
                dealer_seat     = data.get("dealer_seat", "")
                n_cards         = len(community_cards)

                # Rastreia movimento do dealer (muda quando nova mão começa)
                prev_dealer = prev_dealer_seats.get(tk, "")
                dealer_moved = bool(dealer_seat and prev_dealer and dealer_seat != prev_dealer)
                if dealer_seat:
                    prev_dealer_seats[tk] = dealer_seat

                prev_pot = prev_pots.get(tk)
                current  = active.get(tk)

                # ── IDLE: salva stacks pré-ante; descarta antes obsoleto ──────
                if current is None and (pot is None or pot == 0) and seats:
                    idle_seats[tk] = seats
                    antes_frames.pop(tk, None)

                # ── ANTES: usa pot_ante se calibrado, senão pot ───────────────
                ante_pot = pot_ante if pot_ante is not None else pot
                is_antes = current is None and _is_antes_frame(ante_pot, bets, seats, self._cfg)
                if is_antes:
                    antes_frames[tk] = {
                        "ts":          ts,
                        "hero_cards":  hero_cards,
                        "seats":       seats,
                        "dealer_seat": dealer_seat,
                    }

                # frame compacto para inferência de ações
                frame_data = {
                    "ts": ts, "pot": pot, "seats": seats,
                    "bets": bets, "community_cards": community_cards,
                }

                # ── ACTIVE: início de mão quando blinds aparecem (bets != {}) ──
                if current is None and pot and pot > 0 and not is_antes:
                    antes = antes_frames.pop(tk, None)
                    hand_start_ts = antes["ts"] if antes else ts
                    init_cards    = antes["hero_cards"] if antes else []

                    hand_counters[tk] = hand_counters.get(tk, 0) + 1
                    current = Hand(
                        table_key=tk,
                        table_id=table_id,
                        hand_number=hand_counters[tk],
                        start_ts=hand_start_ts,
                        blinds=blinds_ocr,
                        hero_seat=self._hero_seats.get(tk, ""),
                        hero_cards=init_cards,
                    )

                    # Usa stacks pré-ante (idle) se disponível; caso contrário usa frame atual
                    base = idle_seats.get(tk) or seats
                    for sk in sorted(set(base) | set(seats)):
                        idle_info = base.get(sk, {})
                        curr_info = seats.get(sk, {})
                        name  = curr_info.get("name") or idle_info.get("name", "")
                        stack = idle_info.get("stack") if idle_info else curr_info.get("stack")
                        if stack is None:
                            stack = curr_info.get("stack")
                        current.players[sk] = {
                            "name":        name,
                            "stack_start": stack,
                            "stack_end":   None,
                        }

                    # BTN: usa dealer_seat do frame de antes, ou do frame anterior, ou fallback
                    btn = antes.get("dealer_seat", "") if antes else dealer_seat
                    if not btn:
                        btn = prev_dealer_seats.get(tk, "")
                    seat_order = self._seat_orders.get(tk, [])
                    current.positions = _find_positions(bets, seat_order, seats, btn)

                    # Inicializa StreetState com blinds postados
                    init_max = max(bets.values(), default=0.0)
                    str_seat_init = next(
                        (s for s, p in current.positions.items() if p == "STR"), None
                    )
                    street_states[tk] = StreetState(
                        street="preflop", max_bet=init_max, invested=dict(bets),
                        straddle_val=bets.get(str_seat_init, 0.0) if str_seat_init else 0.0,
                    )

                    # Detect a raise that occurred before the video started.
                    # If exactly one seat has a bet clearly exceeding the max blind
                    # (>= 2× STR/BB), generate the raise action retroactively so that
                    # _infer_preflop_folds does not insert a spurious fold for that player.
                    if len(bets) >= 2:
                        sorted_bet_vals = sorted(bets.values())
                        max_blind = sorted_bet_vals[min(2, len(sorted_bet_vals) - 1)]
                        above = [(sk, v) for sk, v in bets.items()
                                 if v >= max_blind * 2 - 0.01]
                        if len(above) == 1:
                            rsk, rbet = above[0]
                            rname = current.players.get(rsk, {}).get("name", "")
                            rpos  = current.positions.get(rsk, "")
                            increment = round(rbet - max_blind, 2)
                            current.actions.append(Action(
                                rsk, rname, rpos, "raise", increment,
                                "preflop", hand_start_ts, total_bb=round(rbet, 2)
                            ))

                    active[tk]             = current
                    prev_n_cards[tk]       = n_cards
                    max_n_cards[tk]        = n_cards
                    known_community[tk]    = list(community_cards)
                    prev_frame_data[tk]    = frame_data

                # ── atualiza mão em andamento ─────────────────────────────────
                if current is not None:
                    # Acumula cartas comunitárias (nunca remove — evita regressão)
                    # Deduplica por rank (1º char): prefere rank+suit sobre rank só
                    _VALID_RANKS = frozenset("23456789TJQKA")
                    _VALID_SUITS = frozenset("shdc")
                    prev_known = known_community.get(tk, [])
                    merged_community = list(prev_known)
                    for c in community_cards:
                        if not c:
                            continue
                        rank = c[0].upper()
                        if rank not in _VALID_RANKS:
                            continue
                        if len(c) > 1 and c[1].lower() not in _VALID_SUITS:
                            continue
                        existing = next(
                            (j for j, mc in enumerate(merged_community)
                             if mc and mc[0].upper() == rank), -1
                        )
                        if existing == -1:
                            merged_community.append(c)
                        elif len(c) >= len(merged_community[existing]):
                            # >= not >: later frames can overwrite wrong animation-phase suits
                            merged_community[existing] = c
                    merged_community = merged_community[:5]

                    # Cap accumulated cards to the number of visually-present card zones.
                    # Prevents background text ("NEXA POKER") false ranks from inflating
                    # the card count and causing the street to jump from flop to turn.
                    if community_zone_count > 0 and len(merged_community) > community_zone_count:
                        safe_cap = max(community_zone_count, max_n_cards.get(tk, 0))
                        merged_community = merged_community[:safe_cap]

                    # Zone-based suit correction: at stable post-animation frames OCR
                    # may miss a card rank, but colour detection is still correct.
                    # Only correct positions within visible zones (zone_count guard)
                    # to prevent empty-region zone colors from overwriting known suits.
                    for i, mc in enumerate(merged_community):
                        if i >= len(community_zone_suits):
                            break
                        if i >= community_zone_count:
                            break
                        suit = community_zone_suits[i]
                        if suit not in ("?", "s") and len(mc) >= 1:
                            merged_community[i] = mc[0] + suit

                    known_community[tk] = merged_community

                    prev_max = max_n_cards.get(tk, 0)
                    effective_n = max(len(merged_community), prev_max)
                    street = _street_from_cards(effective_n)
                    is_new_street = effective_n > prev_max
                    # Actions inferred on a transition frame (e.g. flop appearing) still
                    # belong to the previous street — they happened before the new cards.
                    action_street = _street_from_cards(prev_max) if is_new_street else street
                    current.streets[street].append({
                        "ts": ts, "pot": pot, "seats": seats,
                        "bets": bets, "community_cards": merged_community,
                    })

                    if pot and pot > current.pot_peak:
                        current.pot_peak = pot

                    # Cartas do hero — mantém a leitura mais completa
                    if len(hero_cards) > len(current.hero_cards):
                        current.hero_cards = hero_cards

                    # Winner por label tem prioridade sobre stack delta
                    if winner_labels:
                        for sk, is_winner in winner_labels.items():
                            if is_winner:
                                name = current.players.get(sk, {}).get("name", "")
                                if name:
                                    current.winner_label = name
                                    break

                    # Atualiza posições se chegaram apostas num frame subsequente
                    if bets and not current.positions:
                        seat_order = self._seat_orders.get(tk, [])
                        current.positions = _find_positions(bets, seat_order, seats, dealer_seat)
                    # Corrige BTN se dealer chip detectado após hand start
                    elif (dealer_seat and dealer_seat in current.players
                          and current.positions.get(dealer_seat) not in ("BTN", "SB", "BB", "STR")):
                        old_btn = next((s for s, p in current.positions.items() if p == "BTN"), "")
                        if old_btn and old_btn != dealer_seat:
                            current.positions[dealer_seat] = "BTN"
                            current.positions.pop(old_btn, None)

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

                    # Detecção de ações — pula o primeiro frame (blinds não são ações)
                    if tk in prev_frame_data and ts != current.start_ts:
                        ss = street_states.get(tk, StreetState(street=action_street))

                        if action_labels:
                            # Primário: rótulos visuais ("Desistir", "Pagar", etc.)
                            prev_labels = prev_action_labels.get(tk, {})
                            new_actions, ss = _actions_from_labels(
                                prev_labels, action_labels, bets,
                                current.positions, current.players, action_street, ss, ts
                            )
                            # Suplementar: captura apostas visíveis na tela mas sem label
                            # (ex: oponente apostou mas label já sumiu no mesmo frame que outro
                            # jogador respondeu com label "Pagar"/"Desistir")
                            if not is_new_street:
                                ss_tmp = StreetState(
                                    street=action_street,
                                    max_bet=ss.max_bet,
                                    invested=dict(ss.invested),
                                    has_acted=set(ss.has_acted),
                                    voluntary_raises=ss.voluntary_raises,
                                    last_aggressor=ss.last_aggressor,
                                    limpers=set(ss.limpers),
                                    straddle_val=ss.straddle_val,
                                )
                                extra_all, _ = _infer_actions(
                                    prev_frame_data[tk], frame_data,
                                    current.positions, current.players, action_street, ss_tmp
                                )
                                label_seats = {a.seat for a in new_actions}
                                pot_now = frame_data.get("pot") or 0.0
                                extra_bets = [
                                    a for a in extra_all
                                    if a.seat not in label_seats
                                    and a.action in ("bet", "raise", "allin")
                                    and a.total_bb <= max(pot_now * 5 + 5.0, 5.0)
                                ]
                                if extra_bets:
                                    for ea in extra_bets:
                                        ss.max_bet = max(ss.max_bet, ea.total_bb)
                                        ss.invested[ea.seat] = round(
                                            ss.invested.get(ea.seat, 0.0) + ea.amount_bb, 2
                                        )
                                        ss.voluntary_raises += 1
                                        ss.last_aggressor = ea.seat
                                    # Apostas suplementares vêm ANTES das respostas (fold/call)
                                    new_actions = extra_bets + new_actions
                                    # Recalcula calls usando max_bet atualizado pós-supplemental
                                    for a in new_actions:
                                        if a.action in ("call", "unknown"):
                                            prior = ss.invested.get(a.seat, 0.0)
                                            sadj = (ss.straddle_val
                                                    if ss.straddle_val > 0 and prior > ss.straddle_val
                                                    else 0.0)
                                            fixed = round(max(0.0, ss.max_bet - prior - sadj), 2)
                                            if fixed > 0.01 and abs(fixed - a.amount_bb) > 0.01:
                                                a.amount_bb = fixed
                                                a.total_bb = round(prior + fixed, 2)
                        elif not is_new_street:
                            # Fallback: inferência por diferença de apostas
                            # Skipped on transition frames: all prev bets clear at once
                            # (collected into pot), pot update lags → false folds otherwise.
                            new_actions, ss = _infer_actions(
                                prev_frame_data[tk], frame_data,
                                current.positions, current.players, action_street, ss
                            )
                        else:
                            new_actions = []

                        street_states[tk] = ss
                        # Filter: skip folds for already-folded players (label + bet-based
                        # can both fire for the same fold on adjacent frames).
                        already_folded = {a.seat for a in current.actions if a.action == "fold"}
                        new_actions = [
                            a for a in new_actions
                            if not (a.action == "fold" and a.seat in already_folded)
                        ]
                        current.actions.extend(new_actions)

                    prev_frame_data[tk]    = frame_data
                    prev_action_labels[tk] = action_labels

                    # Reseta StreetState apenas quando nova rua é detectada (effective_n aumenta)
                    if effective_n > prev_max:
                        max_n_cards[tk]  = effective_n
                        prev_n_cards[tk] = effective_n
                        prev_ss = street_states.get(tk)
                        new_ss  = StreetState(street=street)
                        if prev_ss:
                            new_ss.last_aggressor = prev_ss.last_aggressor
                        street_states[tk] = new_ss

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
                        street_states.pop(tk, None)
                        max_n_cards.pop(tk, None)
                        known_community.pop(tk, None)

                prev_pots[tk] = pot

        # Fecha mãos ainda abertas no fim do vídeo
        last_ts = ocr_results[-1]["timestamp"] if ocr_results else 0.0
        for tk, hand in active.items():
            if hand is not None:
                hand.end_ts = last_ts
                hand.winner = _detect_winner(hand.players)
                all_hands.append(hand)

        all_hands.sort(key=lambda h: h.start_ts)

        # Post-processing: infer silently-missed folds + reconstruct null stacks
        for hand in all_hands:
            _fill_empty_action_names(hand)
            _infer_preflop_folds(hand, self._seat_orders.get(hand.table_key, []))
            _infer_terminal_folds(hand)
            _reconstruct_missing_stacks(hand)

        return all_hands


# ── pós-processamento de folds ────────────────────────────────────────────────

def _fill_empty_action_names(hand: Hand) -> None:
    """
    Fill in missing player names in actions from hand.players.
    Happens when OCR misses a seat name on the frame where the action was detected.
    """
    for action in hand.actions:
        if not action.player and action.seat:
            name = hand.players.get(action.seat, {}).get("name", "")
            if name:
                action.player = name


def _infer_preflop_folds(hand: Hand, seat_order: list[str]) -> None:
    """
    Insere folds para jogadores que estavam na mão mas não têm nenhuma ação
    registrada (ação aconteceu entre frames e não foi capturada).

    Posição correta de inserção: baseada na ordem horária de ação preflop
    (começa depois do STR ou BB, circunda de volta ao STR/BB).
    """
    preflop_actor_seats = {a.seat for a in hand.actions if a.street == "preflop"}
    active_players = {
        sk for sk, info in hand.players.items()
        if info.get("name") and info.get("stack_start") is not None
    }
    missing_seats = active_players - preflop_actor_seats
    if not missing_seats:
        return

    # Calcula ordem de ação preflop (depois do anchor: STR > BB > SB)
    anchor = (next((sk for sk, p in hand.positions.items() if p == "STR"), "")
              or next((sk for sk, p in hand.positions.items() if p == "BB"), "")
              or next((sk for sk, p in hand.positions.items() if p == "SB"), ""))
    if anchor and anchor in seat_order:
        n = len(seat_order)
        anchor_idx = seat_order.index(anchor)
        preflop_order = [seat_order[(anchor_idx + 1 + i) % n] for i in range(n)]
    else:
        preflop_order = seat_order

    def _order_idx(sk: str) -> int:
        try:
            return preflop_order.index(sk)
        except ValueError:
            return len(preflop_order)

    # Índice da PRIMEIRA ação de cada assento no preflop (ignora re-ações)
    first_seen: dict[str, int] = {}
    for i, action in enumerate(hand.actions):
        if action.street != "preflop":
            break
        if action.seat not in first_seen:
            first_seen[action.seat] = i

    for sk in missing_seats:
        name = hand.players[sk].get("name", "")
        if not name:
            continue
        pos    = hand.positions.get(sk, "")
        sk_ord = _order_idx(sk)

        # Insere depois da primeira ação do último assento que age antes de sk
        insert_at = 0
        for sk_other, first_idx in first_seen.items():
            if _order_idx(sk_other) < sk_ord:
                insert_at = max(insert_at, first_idx + 1)

        hand.actions.insert(insert_at,
                            Action(sk, name, pos, "fold", 0.0, "preflop", hand.start_ts))
        # Atualiza first_seen para refletir a inserção
        first_seen[sk] = insert_at
        first_seen = {s: (idx if idx < insert_at else idx + 1)
                      for s, idx in first_seen.items() if s != sk}
        first_seen[sk] = insert_at


def _infer_terminal_folds(hand: Hand) -> None:
    """
    Ao fim da mão, insere fold para jogadores que:
    - Tiveram ação na última rua (check/limp) mas não responderam a uma aposta posterior.
    - Não são o vencedor.

    Cobre o caso de FishGeorge que checkava no turn, Hamster apostou, FishGeorge
    desistiu mas o fold foi capturado após os frames do pipeline.
    """
    if not hand.actions:
        return

    streets_in_order = ["preflop", "flop", "turn", "river"]
    last_street = "preflop"
    for s in streets_in_order:
        if any(a.street == s for a in hand.actions):
            last_street = s

    winner_name = hand.winner_label or hand.winner
    winner_seat = next(
        (sk for sk, info in hand.players.items() if info.get("name") == winner_name), ""
    )

    # Indexa ações da última rua por assento
    for sk in list(hand.players):
        info = hand.players[sk]
        if not info.get("name"):
            continue
        if sk == winner_seat:
            continue

        sk_last_street = [
            (i, a) for i, a in enumerate(hand.actions)
            if a.street == last_street and a.seat == sk
        ]
        if not sk_last_street:
            continue

        last_idx, last_action = sk_last_street[-1]
        if last_action.action in ("fold", "call", "raise", "bet", "allin"):
            # Já respondeu (ou já tem fold)
            continue

        # Verifica se houve aposta/raise DEPOIS da última ação deste assento
        later_aggression = [
            a for a in hand.actions[last_idx + 1:]
            if a.street == last_street and a.action in ("bet", "raise", "allin")
            and a.seat != sk
        ]
        if not later_aggression:
            continue

        pos  = hand.positions.get(sk, "")
        name = info["name"]
        hand.actions.append(Action(sk, name, pos, "fold", 0.0, last_street, hand.end_ts))


# ── reconstrução de stacks ausentes ──────────────────────────────────────────

def _reconstruct_missing_stacks(hand: Hand) -> None:
    """
    Estima stack_start para jogadores onde não foi capturado (idle frame ausente).
    Fórmula: stack_start = stack_end + total_investido + ante (se jogou)
    Para vencedores: desconta o pot ganho.
    """
    import re as _re
    import logging as _log

    # Tenta extrair ante real do string de blinds (ex: "0.05/0.10/0.20" → ante = SB/BB = 0.5 BB)
    # Os valores no string são em real money; dividir pelo BB para converter para unidades de BB.
    ante_bb = 0.5  # fallback: ante padrão GGPoker = 0.5 BB
    if hand.blinds:
        m = _re.match(r"([\d.]+)/([\d.]+)", hand.blinds)
        if m:
            try:
                sb_real = float(m.group(1))
                bb_real = float(m.group(2))
                if bb_real > 0:
                    ante_bb = sb_real / bb_real  # normaliza para BB units (ex: 0.05/0.10 = 0.5 BB)
            except (ValueError, ZeroDivisionError):
                pass

    winner_name = hand.winner_label or hand.winner

    for sk, info in hand.players.items():
        if info.get("stack_start") is not None:
            continue
        stack_end = info.get("stack_end")
        if stack_end is None:
            continue

        # Total investido = soma real de amount_bb por ação (captura investimento real)
        total_invested = sum(a.amount_bb for a in hand.actions if a.seat == sk)
        played         = total_invested > 0  # só posta ante se participou

        if info.get("name") == winner_name:
            # Vencedor recebeu o pot: stack_end já inclui o ganho → desconta
            stack_start = round(
                stack_end - hand.pot_peak + total_invested + (ante_bb if played else 0.0), 2
            )
        else:
            stack_start = round(
                stack_end + total_invested + (ante_bb if played else 0.0), 2
            )

        if stack_start < 0 or stack_start > 500:
            _log.warning(
                "stack_start reconstruído implausível (%.2f) para %s — descartado",
                stack_start, info.get("name", sk)
            )
            info["stack_start"] = None
        else:
            info["stack_start"] = stack_start


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


def validate_hands(hands: list[Hand]) -> tuple[list[Hand], list[dict]]:
    """Separa mãos válidas de inválidas. Retorna (válidas, rejeitadas com motivo)."""
    valid, rejected = [], []
    for h in hands:
        reason = _rejection_reason(h)
        if reason:
            rejected.append({"hand": h.summary(), "reason": reason})
        else:
            valid.append(h)
    return valid, rejected


def _rejection_reason(h: Hand) -> str:
    """Retorna motivo de rejeição, ou '' se a mão é válida."""
    named = [p for p in h.players.values() if p.get("name")]
    if len(named) < 2:
        return "menos de 2 jogadores com nome identificado"
    if h.duration() < 5.0:
        return f"duração muito curta ({h.duration():.1f}s) — provável falso positivo"
    if h.pot_peak < 1.0:
        return f"pot_peak irreal ({h.pot_peak} BB)"
    total_frames = sum(len(f) for f in h.streets.values())
    if total_frames < 2:
        return "apenas 1 frame capturado — dados insuficientes"
    # Reject hands where blind positions couldn't be identified — almost certainly a
    # mid-hand fragment from before the video start (blind-posting was never captured).
    if not any(p in h.positions.values() for p in ("SB", "BB")):
        return "SB/BB não identificados — fragmento de mão (início fora do vídeo)"
    return ""


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
