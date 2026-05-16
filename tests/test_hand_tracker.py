import unittest
from dataclasses import field
from engine.hand_tracker import HandTracker, Hand, validate_hands


# ── helpers ───────────────────────────────────────────────────────────────────

_SEATS = {
    "seat_1": {"name": "Alice",  "stack": 200.0},
    "seat_2": {"name": "Bob",    "stack": 200.0},
    "seat_3": {"name": "Carol",  "stack": 200.0},
    "seat_4": {"name": "Dave",   "stack": 200.0},
    "seat_5": {"name": "Eve",    "stack": 200.0},
}

def _frame(ts, pot, bets=None, community=None):
    """Constrói um entry de ocr_results com uma única mesa 'top_left'."""
    return {
        "timestamp": float(ts),
        "tables": {
            "top_left": {
                "table_id":       "HL0001",
                "blinds":         "0.5/1/2",
                "game_type":      "NLHE",
                "pot":            pot,
                "seats":          dict(_SEATS),
                "bets":           bets or {},
                "community_cards": community or [],
                "hero_cards":     [],
                "_from_cache":    False,
            }
        }
    }


# ── testes de processo de sequência ──────────────────────────────────────────

class TestProcessSequence(unittest.TestCase):

    def _sequence(self):
        """Sequência sintética de uma mão completa conforme spec."""
        return [
            _frame( 2.0, 3.5,  {"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0}),
            _frame( 4.0, 8.0,  {"seat_5": 4.5}),
            _frame( 6.0, 12.5, {}),
            _frame( 8.0, 18.0, {"seat_2": 5.5}),
            _frame(10.0, 23.5, {}, ["A", "K", "2"]),
            _frame(12.0, 23.5, {}, ["A", "K", "2"]),
            _frame(14.0, 0,    {}),
        ]

    def test_single_hand_detected(self):
        hands = HandTracker().process_sequence(self._sequence())
        self.assertEqual(len(hands), 1)

    def test_start_and_end_timestamps(self):
        hands = HandTracker().process_sequence(self._sequence())
        self.assertEqual(hands[0].start_ts, 2.0)
        self.assertEqual(hands[0].end_ts,   14.0)

    def test_flop_detected(self):
        hands = HandTracker().process_sequence(self._sequence())
        streets_with_frames = [s for s, f in hands[0].streets.items() if f]
        self.assertIn("flop", streets_with_frames)

    def test_pot_peak(self):
        hands = HandTracker().process_sequence(self._sequence())
        self.assertEqual(hands[0].pot_peak, 23.5)

    def test_two_consecutive_hands(self):
        seq = [
            _frame( 2.0, 3.5),
            _frame( 8.0, 15.0),
            _frame(14.0, 0),     # fim da mão 1
            _frame(16.0, 3.5),
            _frame(22.0, 15.0),
            _frame(28.0, 0),     # fim da mão 2
        ]
        hands = HandTracker().process_sequence(seq)
        self.assertEqual(len(hands), 2)
        self.assertLess(hands[0].start_ts, hands[1].start_ts)


# ── testes de validação ───────────────────────────────────────────────────────

def _make_hand(n_frames=3, duration=30.0, pot_peak=10.0, n_named=2):
    h = Hand(
        table_key="top_left",
        table_id="HL0001",
        hand_number=1,
        start_ts=0.0,
        end_ts=duration,
        pot_peak=pot_peak,
    )
    for i in range(1, n_named + 1):
        h.players[f"seat_{i}"] = {
            "name": f"Player{i}",
            "stack_start": 200.0,
            "stack_end": 200.0,
        }
    frames_per_street = max(0, n_frames)
    h.streets["preflop"] = [{"ts": i, "pot": pot_peak} for i in range(frames_per_street)]
    return h


class TestValidateHands(unittest.TestCase):

    def test_valid_hand_passes(self):
        h = _make_hand(n_frames=4, duration=30.0, pot_peak=10.0, n_named=3)
        valid, rejected = validate_hands([h])
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(rejected), 0)

    def test_single_frame_rejected(self):
        h = _make_hand(n_frames=1, duration=30.0, pot_peak=10.0, n_named=3)
        valid, rejected = validate_hands([h])
        self.assertEqual(len(valid), 0)
        self.assertIn("1 frame", rejected[0]["reason"])

    def test_short_duration_rejected(self):
        h = _make_hand(n_frames=4, duration=2.0, pot_peak=10.0, n_named=3)
        valid, rejected = validate_hands([h])
        self.assertEqual(len(valid), 0)
        self.assertIn("curta", rejected[0]["reason"])

    def test_too_few_named_players_rejected(self):
        h = _make_hand(n_frames=4, duration=30.0, pot_peak=10.0, n_named=1)
        valid, rejected = validate_hands([h])
        self.assertEqual(len(valid), 0)
        self.assertIn("jogadores", rejected[0]["reason"])

    def test_low_pot_peak_rejected(self):
        h = _make_hand(n_frames=4, duration=30.0, pot_peak=0.5, n_named=3)
        valid, rejected = validate_hands([h])
        self.assertEqual(len(valid), 0)
        self.assertIn("pot_peak", rejected[0]["reason"])


if __name__ == "__main__":
    unittest.main()
