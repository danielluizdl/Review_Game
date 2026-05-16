"""
Calcula estatísticas de jogadores a partir dos JSONs de output.
"""
import json

_BLIND_POSITIONS = {"SB", "BB", "STR"}


def from_json(json_path: str) -> list[dict]:
    """Lê arquivo JSON de output e retorna lista de mãos como dicts."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("hands", [])


def compute_player_stats(hands: list[dict]) -> dict[str, dict]:
    """
    Calcula stats por jogador em todas as mãos fornecidas.

    Retorna dict: nome → {hands_played, vpip, pfr, af, won, net_bb,
                           avg_stack, positions, went_to_showdown}
    """
    accum: dict[str, dict] = {}

    for hand in hands:
        players = hand.get("players", {})
        actions = hand.get("actions", [])
        winner  = hand.get("winner", "")
        streets = hand.get("streets", {})

        for pinfo in players.values():
            name = pinfo.get("name", "")
            if not name:
                continue

            if name not in accum:
                accum[name] = {
                    "hands_played":     0,
                    "vpip_count":       0,
                    "pfr_count":        0,
                    "bet_raise_count":  0,
                    "call_count":       0,
                    "won":              0,
                    "net_bb_sum":       0.0,
                    "stack_starts":     [],
                    "positions":        {},
                    "went_to_showdown": 0,
                }

            s   = accum[name]
            pos = pinfo.get("position", "")
            s["hands_played"] += 1

            # Net BB e stack médio
            s_start = pinfo.get("stack_start")
            s_end   = pinfo.get("stack_end")
            if s_start is not None and s_end is not None:
                s["net_bb_sum"] += s_end - s_start
                s["stack_starts"].append(s_start)

            # Posição
            if pos:
                s["positions"][pos] = s["positions"].get(pos, 0) + 1

            # Vencedor
            if winner == name:
                s["won"] += 1

            # Chegou ao river
            if streets.get("river", {}).get("frames", 0) > 0:
                s["went_to_showdown"] += 1

            # Ações preflop para VPIP / PFR
            preflop = [a for a in actions
                       if a.get("player") == name and a.get("street") == "preflop"]
            is_blind = pos in _BLIND_POSITIONS

            # VPIP: call ou raise voluntário preflop
            # Blinds: só call/raise conta (post é obrigatório)
            vpip_types = ("call", "raise") if is_blind else ("call", "raise", "bet")
            if any(a["action"] in vpip_types for a in preflop):
                s["vpip_count"] += 1

            # PFR: raise voluntário preflop
            pfr_types = ("raise",) if is_blind else ("raise", "bet")
            if any(a["action"] in pfr_types for a in preflop):
                s["pfr_count"] += 1

            # AF: bet+raise vs call em todas as ruas
            all_actions = [a for a in actions if a.get("player") == name]
            s["bet_raise_count"] += sum(
                1 for a in all_actions if a["action"] in ("bet", "raise")
            )
            s["call_count"] += sum(
                1 for a in all_actions if a["action"] == "call"
            )

    # Consolida acumuladores em stats finais
    result: dict[str, dict] = {}
    for name, s in accum.items():
        n = s["hands_played"]
        result[name] = {
            "hands_played":     n,
            "vpip":             round(100 * s["vpip_count"] / n, 1) if n else 0.0,
            "pfr":              round(100 * s["pfr_count"] / n, 1)  if n else 0.0,
            "af":               round(s["bet_raise_count"] / max(1, s["call_count"]), 2),
            "won":              s["won"],
            "net_bb":           round(s["net_bb_sum"], 1),
            "avg_stack":        round(
                sum(s["stack_starts"]) / len(s["stack_starts"]), 1
            ) if s["stack_starts"] else 0.0,
            "positions":        s["positions"],
            "went_to_showdown": s["went_to_showdown"],
        }

    return result


def print_stats(stats: dict[str, dict]) -> None:
    """Imprime tabela de stats no terminal, ordenada por net_bb decrescente."""
    if not stats:
        print("Nenhum dado de jogador encontrado.")
        return

    ordered = sorted(stats.items(), key=lambda x: x[1]["net_bb"], reverse=True)

    header = f"{'Jogador':<20} | {'Mãos':>4} | {'VPIP':>6} | {'PFR':>6} | {'AF':>5} | {'Net BB':>8} | {'Won':>4}"
    sep    = "─" * 20 + "─┼─" + "─" * 4 + "─┼─" + "─" * 6 + "─┼─" + "─" * 6 + "─┼─" + "─" * 5 + "─┼─" + "─" * 8 + "─┼─" + "─" * 4
    print(f"\n{header}")
    print(sep)
    for name, s in ordered:
        net = s["net_bb"]
        net_str = f"{'+' if net >= 0 else ''}{net:.1f}"
        print(
            f"{name:<20} | {s['hands_played']:>4} | "
            f"{s['vpip']:>5.1f}% | {s['pfr']:>5.1f}% | "
            f"{s['af']:>5.2f} | {net_str:>8} | {s['won']:>4}"
        )
