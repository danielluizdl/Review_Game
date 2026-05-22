"""
Serializa mãos rastreadas para JSON persistente em output/.
"""
import json
import os
from datetime import datetime
from pathlib import Path

from engine.hand_tracker import Hand


def write_hands(hands: list[Hand], video_path: str) -> str:
    """
    Serializa lista de Hand para JSON e salva em output/.
    Retorna o caminho do arquivo criado.
    """
    stem      = Path(video_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"hands_{stem}_{timestamp}.json"
    out_path  = os.path.join("output", filename)

    os.makedirs("output", exist_ok=True)

    payload = {
        "video":        video_path,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_hands":  len(hands),
        "hands":        [_serialize_hand(h) for h in hands],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return out_path


# ── serialização ──────────────────────────────────────────────────────────────

def _serialize_hand(h: Hand) -> dict:
    return {
        "hand_number":  h.hand_number,
        "table_key":    h.table_key,
        "table_id":     h.table_id,
        "start_ts":     h.start_ts,
        "end_ts":       h.end_ts,
        "duration_sec": round(h.duration(), 1),
        "pot_peak_bb":  h.pot_peak,
        "blinds":       h.blinds,
        "hero_cards":   h.hero_cards,
        "winner":       h.winner,
        "players":      _serialize_players(h),
        "streets":      _serialize_streets(h),
        "actions":      [_serialize_action(a) for a in h.actions],
    }


def _serialize_players(h: Hand) -> dict:
    result = {}
    for sk, info in h.players.items():
        if not info.get("name"):
            continue
        result[sk] = {
            "name":        info["name"],
            "position":    h.positions.get(sk, ""),
            "stack_start": info.get("stack_start"),
            "stack_end":   info.get("stack_end"),
        }
    return result


def _serialize_streets(h: Hand) -> dict:
    result = {}
    for street_name, frames in h.streets.items():
        entry: dict = {"frames": len(frames)}
        if frames:
            # Cartas do último frame da rua (pega o estado mais recente)
            last_cards = frames[-1].get("community_cards", [])
            if last_cards:
                entry["cards"] = last_cards
        result[street_name] = entry
    return result


def _serialize_action(a) -> dict:
    return {
        "seat":      a.seat,
        "player":    a.player,
        "position":  a.position,
        "action":    a.action,
        "amount_bb": a.amount_bb,
        "total_bb":  a.total_bb,
        "street":    a.street,
        "ts":        a.ts,
    }
