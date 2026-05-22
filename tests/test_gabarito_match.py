"""
Compara a saída do pipeline contra o gabarito da mão HL3048 (FishGeorge vs Hamster813).

Faz dois tipos de verificação:
  1. Unit: constrói uma Hand mockada com dados conhecidos e verifica que
     hh_writer_ps._hand_to_ps() produz os campos corretos.
  2. File: se o arquivo de saída mais recente existir, verifica os campos
     extraídos diretamente do texto gerado.

O teste unitário NÃO requer o vídeo e pode ser rodado a qualquer momento.
O teste de arquivo é skippado se nenhum output recente for encontrado.
"""
import re
import os
import glob
import unittest
from dataclasses import dataclass, field

from engine.hand_tracker import Hand, Action
from output.hh_writer_ps import _hand_to_ps, parse_blinds


# ── dados do gabarito ─────────────────────────────────────────────────────────

GABARITO = {
    "title_stakes":  "$0.05/$0.10/$0.20(0.05)",   # issue #1
    "fish_stack":    50.20,                         # issue #2 — $50.20 ± 0.10
    "hero_cards":    ["2c", "6s"],                  # issue #3 (placeholder ou detecção)
    "flop":          ["Kd", "Ad", "9d"],            # issues #4-6
    "turn_card":     "8d",
    "board":         ["Kd", "Ad", "9d", "8d"],
    "winner":        "Hamster813",
    "pot":           11.38,
}

# ── helper para construir uma Hand sintética equivalente à do gabarito ────────

def _make_gabarito_hand() -> Hand:
    """
    Reconstrói a mão HL3048 com dados conhecidos para teste do HH writer.
    Stacks são aproximados; o que testamos é a formatação dos campos críticos.
    """
    h = Hand(
        table_key="top_left",
        table_id="HL3048",
        hand_number=2,
        start_ts=10.0,
        end_ts=50.0,
        blinds="0.05/0.10/0.20(0.05)",
        hero_seat="seat_1",
        hero_cards=["2s", "6h"],   # sem suits detectadas — serão placeholder
        winner="Hamster813",
        winner_label="Hamster813",
        pot_peak=113.8,   # em BB (113.8 × 0.10 = $11.38)
    )
    h.players = {
        "seat_1": {"name": "dLzinN",     "stack_start": 207.0, "stack_end": 200.0},
        "seat_2": {"name": "Hamster813", "stack_start": 329.0, "stack_end": 443.8},
        "seat_3": {"name": "ancomthit",  "stack_start": 580.0, "stack_end": 575.5},
        "seat_4": {"name": "能能2",      "stack_start": 100.0, "stack_end":  95.5},
        "seat_5": {"name": "GongFuBoy",  "stack_start": 846.0, "stack_end": 840.5},
        "seat_6": {"name": "你懂个嗨",  "stack_start": 169.0, "stack_end": 163.5},
        "seat_7": {"name": "Andylau408", "stack_start": 245.0, "stack_end": 239.5},
        "seat_8": {"name": "FishGeorge", "stack_start": 502.0, "stack_end": 463.5},
    }
    h.positions = {
        "seat_3": "BTN",
        "seat_5": "SB",
        "seat_6": "BB",
        "seat_7": "STR",
    }

    # Cartas comunitárias: flop com suits reais, turn card
    flop_frame  = {"ts": 20.0, "pot": 63.9, "community_cards": ["Kd", "Ad", "9d"], "bets": {}, "seats": {}}
    turn_frame  = {"ts": 30.0, "pot": 89.7, "community_cards": ["Kd", "Ad", "9d", "8d"], "bets": {}, "seats": {}}
    h.streets["preflop"] = [{"ts": 10.0, "pot": 35.0, "community_cards": [], "bets": {}, "seats": {}}]
    h.streets["flop"]    = [flop_frame]
    h.streets["turn"]    = [turn_frame]

    # Ações mínimas para exercitar o writer
    h.actions = [
        Action("seat_8", "FishGeorge", "",  "call",  2.0, "preflop", 11.0, total_bb=2.0),
        Action("seat_1", "dLzinN",     "CO", "fold", 0.0, "preflop", 11.5, total_bb=0.0),
        Action("seat_2", "Hamster813", "",  "raise", 5.5, "preflop", 12.0, total_bb=7.5),
        Action("seat_7", "Andylau408", "STR", "call", 5.5, "preflop", 13.0, total_bb=7.5),
        Action("seat_8", "FishGeorge", "",  "raise", 13.8, "preflop", 14.0, total_bb=21.3),
        Action("seat_2", "Hamster813", "",  "call",  13.8, "preflop", 14.5, total_bb=21.3),
        Action("seat_7", "Andylau408", "STR", "call", 13.8, "preflop", 15.0, total_bb=21.3),
        Action("seat_7", "Andylau408", "STR", "check", 0.0, "flop",   21.0, total_bb=0.0),
        Action("seat_8", "FishGeorge", "",  "check", 0.0, "flop",    21.5, total_bb=0.0),
        Action("seat_2", "Hamster813", "",  "bet",   22.7, "flop",   22.0, total_bb=22.7),
        Action("seat_7", "Andylau408", "STR", "fold", 0.0, "flop",   22.5, total_bb=0.0),
        Action("seat_8", "FishGeorge", "",  "call",  22.7, "flop",   23.0, total_bb=22.7),
        Action("seat_8", "FishGeorge", "",  "check", 0.0, "turn",   31.0, total_bb=0.0),
        Action("seat_2", "Hamster813", "",  "bet",   57.2, "turn",   32.0, total_bb=57.2),
        Action("seat_8", "FishGeorge", "",  "fold",  0.0, "turn",   33.0, total_bb=0.0),
    ]

    return h


# ── testes unitários (sem vídeo) ──────────────────────────────────────────────

class TestHHWriterGabaritoFields(unittest.TestCase):

    def setUp(self):
        self.hand = _make_gabarito_hand()
        self.output = _hand_to_ps(self.hand)

    # ── issue #1: título com ante ─────────────────────────────────────────────
    def test_title_contains_ante(self):
        """Header deve incluir (0.05) representando o ante."""
        self.assertIn("$0.05/$0.10/$0.20(0.05)", self.output,
                      f"Ante ausente no header.\nSaída:\n{self.output[:200]}")

    # ── issue #2: stack de FishGeorge ─────────────────────────────────────────
    def test_fish_george_stack_approx(self):
        """FishGeorge deve aparecer com stack ≈ $50.20 (±$0.10)."""
        m = re.search(r"FishGeorge \(\$([0-9.]+) in chips\)", self.output)
        self.assertIsNotNone(m, "Linha 'FishGeorge ($ in chips)' não encontrada")
        stack = float(m.group(1))
        self.assertAlmostEqual(stack, 50.20, delta=0.10,
                               msg=f"Stack FishGeorge={stack:.2f}, esperado ≈ 50.20")

    # ── issues #4-6: suits das cartas comunitárias ────────────────────────────
    def test_flop_all_diamonds(self):
        """Flop deve ser [Kd Ad 9d] — todos diamonds."""
        self.assertIn("*** FLOP *** [Kd Ad 9d]", self.output,
                      f"Flop incorreto.\nSaída:\n{self.output}")

    def test_turn_card_diamond(self):
        """Turn card deve ser 8d."""
        self.assertIn("[8d]", self.output,
                      f"Turn card 8d ausente.\nSaída:\n{self.output}")

    def test_board_in_summary(self):
        """Board no SUMMARY deve ser [Kd Ad 9d 8d]."""
        self.assertIn("Board [Kd Ad 9d 8d]", self.output,
                      f"Board incorreto no SUMMARY.\nSaída:\n{self.output}")

    # ── parse_blinds ──────────────────────────────────────────────────────────
    def test_parse_blinds_with_explicit_ante(self):
        """parse_blinds("0.05/0.10/0.20(0.05)") → ante=0.05, str=0.20."""
        b = parse_blinds("0.05/0.10/0.20(0.05)")
        self.assertAlmostEqual(b["ante"], 0.05)
        self.assertAlmostEqual(b["str"],  0.20)

    def test_parse_blinds_implicit_ante(self):
        """parse_blinds("0.5/1/2") → ante=0.5 (igual ao SB)."""
        b = parse_blinds("0.5/1/2")
        self.assertAlmostEqual(b["ante"], 0.5)

    # ── issue #1 regressão: winner collect ───────────────────────────────────
    def test_winner_hamster_collected(self):
        self.assertIn("Hamster813 collected", self.output)


# ── teste de arquivo (só roda se existe output recente) ───────────────────────

class TestOutputFileGabarito(unittest.TestCase):
    """Compara campos específicos do arquivo de saída mais recente contra o gabarito."""

    @classmethod
    def setUpClass(cls):
        pattern = os.path.join("output", "hands_video_teste_reduzido_*.txt")
        files = sorted(glob.glob(pattern), reverse=True)
        cls.output_text = None
        if files:
            with open(files[0], encoding="utf-8") as f:
                cls.output_text = f.read()
        cls.gabarito_section = cls._extract_fish_hand(cls.output_text) if cls.output_text else None

    @staticmethod
    def _extract_fish_hand(text: str) -> str | None:
        """Extrai o bloco da mão onde FishGeorge aparece."""
        blocks = re.split(r"\n(?=PokerStars Hand #)", text)
        for block in blocks:
            if "FishGeorge" in block and "HL3048" in block:
                return block
        return None

    def _skip_if_no_file(self):
        if self.gabarito_section is None:
            self.skipTest("Arquivo de output com mão HL3048/FishGeorge não encontrado")

    def test_file_title_has_ante(self):
        self._skip_if_no_file()
        self.assertIn("(0.05)", self.gabarito_section,
                      "Ante '(0.05)' ausente no título do arquivo de saída")

    def test_file_flop_suits(self):
        self._skip_if_no_file()
        self.assertIn("[Kd Ad 9d]", self.gabarito_section,
                      f"Flop incorreto no arquivo. Encontrado:\n{self.gabarito_section[:500]}")

    def test_file_board(self):
        self._skip_if_no_file()
        self.assertIn("Board [Kd Ad 9d 8d]", self.gabarito_section,
                      "Board incorreto no arquivo de saída")

    def test_file_fish_george_stack(self):
        self._skip_if_no_file()
        m = re.search(r"FishGeorge \(\$([0-9.]+) in chips\)", self.gabarito_section)
        if m:
            stack = float(m.group(1))
            self.assertAlmostEqual(stack, 49.70, delta=0.10,
                                   msg=f"Stack FishGeorge={stack}, esperado ≈ 49.70")


if __name__ == "__main__":
    unittest.main()
