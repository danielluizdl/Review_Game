import unittest
from engine.hand_tracker import _find_positions


# Ordem horária fixa usada em todos os cenários
_ORDER = ["seat_1", "seat_2", "seat_3", "seat_4", "seat_5", "seat_6"]

def _seats(*keys):
    return {k: {"name": f"P{k[-1]}", "stack": 200.0} for k in keys}


class TestFindPositions(unittest.TestCase):

    def test_3_players_no_straddle(self):
        bets  = {"seat_2": 0.5, "seat_3": 1.0}
        seats = _seats("seat_1", "seat_2", "seat_3")
        pos   = _find_positions(bets, _ORDER, seats)
        self.assertEqual(pos["seat_1"], "BTN")
        self.assertEqual(pos["seat_2"], "SB")
        self.assertEqual(pos["seat_3"], "BB")
        self.assertNotIn("STR", pos.values())

    def test_4_players_with_straddle(self):
        bets  = {"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0}
        seats = _seats("seat_1", "seat_2", "seat_3", "seat_4")
        pos   = _find_positions(bets, _ORDER, seats)
        self.assertEqual(pos["seat_1"], "BTN")
        self.assertEqual(pos["seat_2"], "SB")
        self.assertEqual(pos["seat_3"], "BB")
        self.assertEqual(pos["seat_4"], "STR")

    def test_5_players_with_straddle(self):
        bets  = {"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0}
        seats = _seats("seat_1", "seat_2", "seat_3", "seat_4", "seat_5")
        pos   = _find_positions(bets, _ORDER, seats)
        self.assertEqual(pos["seat_1"], "BTN")
        self.assertEqual(pos["seat_2"], "SB")
        self.assertEqual(pos["seat_3"], "BB")
        self.assertEqual(pos["seat_4"], "STR")
        self.assertEqual(pos["seat_5"], "CO")

    def test_3_players_3_bets_no_straddle(self):
        # len(active) < 4 → straddle NÃO deve ser atribuído
        bets  = {"seat_2": 0.5, "seat_3": 1.0, "seat_1": 50.0}
        seats = _seats("seat_1", "seat_2", "seat_3")
        pos   = _find_positions(bets, _ORDER, seats)
        self.assertNotIn("STR", pos.values())
        self.assertEqual(len(pos), 3)


if __name__ == "__main__":
    unittest.main()
