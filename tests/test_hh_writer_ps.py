import os
import tempfile
import unittest

from engine.hand_tracker import Hand, Action
from output.hh_writer_ps import (
    _assign_placeholder_suits,
    _hand_to_ps,
    parse_blinds,
    write_hands_ps,
)


# ── helpers de construção ─────────────────────────────────────────────────────

def _make_hand(
    blinds="0.05/0.1/0.2(0.05)",
    n_players=4,
    pot_peak=8.5,
    start_ts=2.0,
    end_ts=30.0,
    winner="Bob",
    hero_cards=None,
    actions=None,
    streets=None,
):
    h = Hand(
        table_key="top_left",
        table_id="HL5798",
        hand_number=1,
        start_ts=start_ts,
        end_ts=end_ts,
        pot_peak=pot_peak,
        blinds=blinds,
        winner=winner,
    )
    names = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Hank"]
    positions = ["BTN", "SB", "BB", "STR", "CO", "HJ", "MP", "UTG+1"]
    for i in range(min(n_players, len(names))):
        sk = f"seat_{i + 1}"
        h.players[sk] = {"name": names[i], "stack_start": 200.0, "stack_end": 200.0}
        h.positions[sk] = positions[i]

    if hero_cards is not None:
        h.hero_cards = hero_cards
    if actions is not None:
        h.actions = actions
    if streets is not None:
        h.streets = streets
    return h


# ── testes ────────────────────────────────────────────────────────────────────

class TestBlindsParsing(unittest.TestCase):

    def test_full_format_with_ante(self):
        r = parse_blinds("0.05/0.1/0.2(0.05)")
        self.assertAlmostEqual(r["sb"],   0.05)
        self.assertAlmostEqual(r["bb"],   0.10)
        self.assertAlmostEqual(r["str"],  0.20)
        self.assertAlmostEqual(r["ante"], 0.05)

    def test_no_ante_str_present(self):
        r = parse_blinds("0.5/1/2")
        self.assertAlmostEqual(r["sb"],   0.5)
        self.assertAlmostEqual(r["bb"],   1.0)
        self.assertAlmostEqual(r["str"],  2.0)
        self.assertAlmostEqual(r["ante"], 0.5)   # ante = SB

    def test_two_blinds_no_str(self):
        r = parse_blinds("5/10")
        self.assertAlmostEqual(r["sb"],  5.0)
        self.assertAlmostEqual(r["bb"], 10.0)
        self.assertIsNone(r["str"])
        self.assertAlmostEqual(r["ante"], 5.0)  # ante = SB

    def test_ocr_noise_o_as_zero(self):
        r = parse_blinds("0.05/O.1/0.2(O.05)")
        self.assertAlmostEqual(r["sb"],   0.05)
        self.assertAlmostEqual(r["bb"],   0.10)
        self.assertAlmostEqual(r["str"],  0.20)
        self.assertAlmostEqual(r["ante"], 0.05)


class TestBBToCurrencyConversion(unittest.TestCase):

    def test_200bb_at_010_gives_20(self):
        # blinds "0.05/0.1" → bb = $0.10; stack 200 BB → $20.00
        h = _make_hand(blinds="0.05/0.1", n_players=2, winner="Bob")
        h.players["seat_1"]["stack_start"] = 200.0
        output = _hand_to_ps(h)
        self.assertIn("$20.00 in chips", output)

    def test_header_has_correct_stakes(self):
        h = _make_hand(blinds="0.05/0.1/0.2(0.05)", n_players=4)
        output = _hand_to_ps(h)
        self.assertIn("($0.05/$0.10/$0.20)", output)


class TestSingleHandBasic(unittest.TestCase):

    def test_header_present(self):
        h = _make_hand()
        output = _hand_to_ps(h)
        self.assertIn("PokerStars Hand #", output)
        self.assertIn("Hold'em No Limit", output)

    def test_table_line_present(self):
        h = _make_hand()
        output = _hand_to_ps(h)
        self.assertIn("Table 'HL5798'", output)
        self.assertIn("8-max", output)

    def test_seat_list_present(self):
        h = _make_hand(n_players=2)
        output = _hand_to_ps(h)
        self.assertIn("Seat 1: Alice", output)
        self.assertIn("Seat 2: Bob", output)

    def test_summary_present(self):
        h = _make_hand()
        output = _hand_to_ps(h)
        self.assertIn("*** SUMMARY ***", output)
        self.assertIn("Total pot", output)


class TestHeroIdentification(unittest.TestCase):

    def test_dealt_to_hero_when_hero_cards_present(self):
        h = _make_hand(hero_cards=["A", "K"])
        output = _hand_to_ps(h)
        self.assertIn("Dealt to Hero", output)

    def test_no_dealt_to_hero_when_no_hero_cards(self):
        h = _make_hand(hero_cards=[])
        output = _hand_to_ps(h)
        self.assertNotIn("Dealt to Hero", output)

    def test_hero_cards_have_suits(self):
        h = _make_hand(hero_cards=["A", "K"])
        output = _hand_to_ps(h)
        # Should have exactly 2 cards with suits in the Dealt line
        import re
        m = re.search(r"Dealt to Hero \[([^\]]+)\]", output)
        self.assertIsNotNone(m)
        cards = m.group(1).split()
        self.assertEqual(len(cards), 2)
        for card in cards:
            self.assertRegex(card, r"^[2-9TJQKA][hdcs]$")


class TestFlopTurnRiverBoardAccumulation(unittest.TestCase):

    def _make_hand_with_streets(self):
        h = _make_hand(n_players=4)
        h.streets = {
            "preflop": [{"ts": 2, "pot": 3.5, "bets": {}, "community_cards": []}],
            "flop":    [{"ts": 4, "pot": 8.0, "bets": {}, "community_cards": ["A", "K", "2"]}],
            "turn":    [{"ts": 6, "pot": 12.0, "bets": {}, "community_cards": ["A", "K", "2", "J"]}],
            "river":   [{"ts": 8, "pot": 18.0, "bets": {}, "community_cards": ["A", "K", "2", "J", "3"]}],
        }
        return h

    def test_flop_present(self):
        output = _hand_to_ps(self._make_hand_with_streets())
        self.assertIn("*** FLOP ***", output)

    def test_turn_shows_flop_and_turn(self):
        output = _hand_to_ps(self._make_hand_with_streets())
        import re
        m = re.search(r"\*\*\* TURN \*\*\* \[([^\]]+)\] \[([^\]]+)\]", output)
        self.assertIsNotNone(m, "TURN line not found or wrong format")
        flop_part, turn_part = m.group(1).split(), m.group(2).split()
        self.assertEqual(len(flop_part), 3)
        self.assertEqual(len(turn_part), 1)

    def test_river_shows_flop_turn_river(self):
        output = _hand_to_ps(self._make_hand_with_streets())
        import re
        m = re.search(r"\*\*\* RIVER \*\*\* \[([^\]]+)\] \[([^\]]+)\] \[([^\]]+)\]", output)
        self.assertIsNotNone(m, "RIVER line not found or wrong format")
        flop_part = m.group(1).split()
        turn_part = m.group(2).split()
        river_part = m.group(3).split()
        self.assertEqual(len(flop_part), 3)
        self.assertEqual(len(turn_part), 1)
        self.assertEqual(len(river_part), 1)


class TestEmptyStreetsOmitted(unittest.TestCase):

    def test_no_turn_when_no_turn_cards(self):
        h = _make_hand(n_players=4)
        h.streets = {
            "preflop": [{"ts": 2, "pot": 3.5, "bets": {}, "community_cards": []}],
            "flop":    [{"ts": 4, "pot": 8.0, "bets": {}, "community_cards": ["A", "K", "2"]}],
            "turn":    [],
            "river":   [],
        }
        output = _hand_to_ps(h)
        self.assertIn("*** FLOP ***", output)
        self.assertNotIn("*** TURN ***", output)
        self.assertNotIn("*** RIVER ***", output)

    def test_no_flop_when_preflop_only(self):
        h = _make_hand(n_players=4)
        # streets default: all empty lists → no community cards
        output = _hand_to_ps(h)
        self.assertNotIn("*** FLOP ***", output)
        self.assertNotIn("*** TURN ***", output)
        self.assertNotIn("*** RIVER ***", output)


class TestRaiseToCalculation(unittest.TestCase):

    def test_raise_to_amount(self):
        # Alice bets 6BB, then raises another 30BB (total 36BB committed)
        # At bb=$0.10: bet=$0.60, raise=$3.00, to=$3.60
        h = _make_hand(blinds="0.05/0.1/0.2(0.05)", n_players=4, winner="Alice")
        h.actions = [
            Action("seat_1", "Alice", "BTN", "bet",   6.0,  "preflop", 3.0),
            Action("seat_2", "Bob",   "SB",  "raise", 18.0, "preflop", 4.0),
            Action("seat_1", "Alice", "BTN", "raise", 30.0, "preflop", 5.0),
        ]
        output = _hand_to_ps(h)
        # Alice's second action: prev committed=$0.60, raise $3.00 → to $3.60
        self.assertIn("Alice: raises $3.00 to $3.60", output)

    def test_first_bet_uses_bets_keyword(self):
        h = _make_hand(blinds="0.05/0.1/0.2(0.05)", n_players=4)
        h.actions = [
            Action("seat_1", "Alice", "BTN", "bet", 6.0, "preflop", 3.0),
        ]
        output = _hand_to_ps(h)
        self.assertIn("Alice: bets $0.60", output)


class TestMultiHandOutput(unittest.TestCase):

    def test_three_hands_three_blocks(self):
        hands = [
            _make_hand(start_ts=2.0,  end_ts=20.0, winner="Alice"),
            _make_hand(start_ts=22.0, end_ts=40.0, winner="Bob"),
            _make_hand(start_ts=42.0, end_ts=60.0, winner="Carol"),
        ]
        # Set different hand numbers
        for i, h in enumerate(hands, 1):
            h.hand_number = i

        with tempfile.TemporaryDirectory() as tmpdir:
            # Override output dir is not possible without patching, so
            # test _hand_to_ps output joined directly
            combined = "\n".join(_hand_to_ps(h) for h in hands)

        count = combined.count("PokerStars Hand #")
        self.assertEqual(count, 3)

    def test_blocks_separated_by_blank_line(self):
        h1 = _make_hand(start_ts=2.0,  winner="Alice")
        h2 = _make_hand(start_ts=22.0, winner="Bob")
        h2.hand_number = 2

        combined = "\n".join([_hand_to_ps(h1), _hand_to_ps(h2)])
        # Each block ends with a blank line; joining two gives a separator
        self.assertIn("\n\nPokerStars Hand #", combined)


class TestPlaceholderSuitsNoCollision(unittest.TestCase):

    def test_five_card_board_no_duplicate_card(self):
        used: set[str] = set()
        ranks = ["A", "K", "2", "J", "3"]
        cards = _assign_placeholder_suits(ranks, used)
        self.assertEqual(len(cards), 5)
        # No duplicates
        self.assertEqual(len(set(cards)), 5)
        # All have valid suit characters
        for card in cards:
            self.assertRegex(card, r"^[2-9TJQKA][hdcs]$")

    def test_same_rank_gets_different_suit(self):
        used: set[str] = set()
        # Force two aces — must get different suits
        cards = _assign_placeholder_suits(["A", "A"], used)
        self.assertEqual(len(cards), 2)
        self.assertNotEqual(cards[0], cards[1])

    def test_used_set_prevents_collision_across_calls(self):
        used: set[str] = set()
        flop  = _assign_placeholder_suits(["A", "K", "2"], used)
        turn  = _assign_placeholder_suits(["J"], used)
        river = _assign_placeholder_suits(["3"], used)
        all_cards = flop + turn + river
        self.assertEqual(len(set(all_cards)), 5)


class TestHeroNameInActionLines(unittest.TestCase):

    def test_hero_name_replaced_by_Hero_in_actions(self):
        h = _make_hand(hero_cards=["A", "K"])
        h.hero_seat = "seat_1"   # Alice é o hero
        h.actions = [
            Action("seat_1", "Alice", "BTN", "fold", 0.0, "preflop", 3.0),
            Action("seat_2", "Bob",   "SB",  "fold", 0.0, "preflop", 3.0),
        ]
        output = _hand_to_ps(h)
        self.assertIn("Hero: folds", output)
        self.assertNotIn("Alice: folds", output)
        self.assertIn("Bob: folds", output)

    def test_no_hero_substitution_without_hero_seat(self):
        h = _make_hand(hero_cards=[])
        h.actions = [
            Action("seat_1", "Alice", "BTN", "fold", 0.0, "preflop", 3.0),
        ]
        output = _hand_to_ps(h)
        self.assertIn("Alice: folds", output)
        self.assertNotIn("Hero: folds", output)


class TestSummaryLabelsOnlyForBlinds(unittest.TestCase):

    def test_btn_sb_bb_str_have_labels(self):
        h = _make_hand(n_players=5)
        h.positions = {
            "seat_1": "BTN",
            "seat_2": "SB",
            "seat_3": "BB",
            "seat_4": "STR",
            "seat_5": "CO",
        }
        output = _hand_to_ps(h)
        summary = output.split("*** SUMMARY ***")[1]
        self.assertIn("(button)", summary)
        self.assertIn("(small blind)", summary)
        self.assertIn("(big blind)", summary)
        self.assertIn("(straddle)", summary)

    def test_non_blind_position_has_no_label(self):
        h = _make_hand(n_players=5)
        h.positions = {
            "seat_1": "BTN",
            "seat_2": "SB",
            "seat_3": "BB",
            "seat_4": "STR",
            "seat_5": "CO",   # Eve é CO
        }
        output = _hand_to_ps(h)
        summary = output.split("*** SUMMARY ***")[1]
        # Eve (seat_5) não deve ter label de posição
        self.assertNotIn("Eve (", summary)
        self.assertNotIn("(CO)", summary)


if __name__ == "__main__":
    unittest.main()
