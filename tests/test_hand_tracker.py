import unittest
from dataclasses import field
from engine.hand_tracker import (
    HandTracker, Hand, Action, StreetState,
    validate_hands, _infer_actions, _is_antes_frame,
)


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
    # Provide minimal positions so the SB/BB validation passes
    h.positions = {"seat_1": "BTN", "seat_2": "SB", "seat_3": "BB"}
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


# ── helpers compartilhados para testes de _infer_actions ────────────────────

def _players_from_seats(seats_dict):
    return {sk: {"name": info["name"], "stack_start": info["stack"], "stack_end": None}
            for sk, info in seats_dict.items()}


def _make_frame(ts, pot, bets, seats=None):
    if seats is None:
        seats = dict(_SEATS)
    return {"ts": ts, "pot": pot, "bets": bets, "seats": seats, "community_cards": []}


# ── testes de inferência de ações ─────────────────────────────────────────────

class TestInferActions(unittest.TestCase):

    def _positions(self):
        return {"seat_1": "CO", "seat_2": "SB", "seat_3": "BB", "seat_4": "STR", "seat_5": "BTN"}

    def _blind_state(self):
        return StreetState(street="preflop", max_bet=2.0,
                           invested={"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0})

    def test_limp_detected_as_call(self):
        # seat_1 coloca bet=2.0 quando STR já tem 2.0 → é limp (call), não bet
        prev = _make_frame(3.0, 3.5, {"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0})
        curr = _make_frame(5.0, 5.5, {"seat_2": 0.5, "seat_3": 1.0,
                                       "seat_4": 2.0, "seat_1": 2.0})
        actions, _ = _infer_actions(prev, curr, self._positions(),
                                    _players_from_seats(_SEATS), "preflop",
                                    self._blind_state())
        a1 = [a for a in actions if a.seat == "seat_1"]
        self.assertEqual(len(a1), 1)
        self.assertEqual(a1[0].action, "call")

    def test_bet_detected_as_raise(self):
        # seat_1 abre para 6BB com STR em 2BB → deve ser "raise" (supera o máximo)
        prev = _make_frame(3.0, 3.5, {"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0})
        curr = _make_frame(5.0, 9.5, {"seat_2": 0.5, "seat_3": 1.0,
                                       "seat_4": 2.0, "seat_1": 6.0})
        actions, _ = _infer_actions(prev, curr, self._positions(),
                                    _players_from_seats(_SEATS), "preflop",
                                    self._blind_state())
        a1 = [a for a in actions if a.seat == "seat_1"]
        self.assertEqual(len(a1), 1)
        self.assertEqual(a1[0].action, "raise")

    def test_first_bet_on_flop_is_bet(self):
        # No flop, sem apostas anteriores, seat_1 abre → "bet"
        prev = _make_frame(5.0, 10.0, {})
        curr = _make_frame(7.0, 15.0, {"seat_1": 5.0})
        actions, _ = _infer_actions(prev, curr, self._positions(),
                                    _players_from_seats(_SEATS), "flop",
                                    StreetState(street="flop"))
        a1 = [a for a in actions if a.seat == "seat_1"]
        self.assertEqual(len(a1), 1)
        self.assertEqual(a1[0].action, "bet")

    def test_ambiguous_multi_action_omitted(self):
        # pot_delta = 12.0 >> prev_bet * 2.5 = 5.0 → múltiplas ações → omitir
        prev = _make_frame(3.0, 4.0, {"seat_1": 2.0})
        curr = _make_frame(5.0, 16.0, {})
        actions, _ = _infer_actions(prev, curr, self._positions(),
                                    _players_from_seats(_SEATS), "preflop",
                                    StreetState(street="preflop", max_bet=2.0,
                                                invested={"seat_1": 2.0}))
        a1 = [a for a in actions if a.seat == "seat_1"]
        self.assertEqual(len(a1), 0)

    def test_state_max_bet_updated_after_raise(self):
        # Após raise de seat_1, state.max_bet deve refletir a nova aposta
        prev = _make_frame(3.0, 3.5, {"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0})
        curr = _make_frame(5.0, 9.5, {"seat_2": 0.5, "seat_3": 1.0,
                                       "seat_4": 2.0, "seat_1": 6.0})
        _, new_state = _infer_actions(prev, curr, self._positions(),
                                      _players_from_seats(_SEATS), "preflop",
                                      self._blind_state())
        self.assertAlmostEqual(new_state.max_bet, 6.0)
        self.assertEqual(new_state.voluntary_raises, 1)
        self.assertEqual(new_state.last_aggressor, "seat_1")

    def test_total_bb_equals_curr_bet_on_raise(self):
        # total_bb de um raise deve ser igual ao curr_bet (total na mesa)
        prev = _make_frame(3.0, 3.5, {"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0})
        curr = _make_frame(5.0, 9.5, {"seat_2": 0.5, "seat_3": 1.0,
                                       "seat_4": 2.0, "seat_1": 6.0})
        actions, _ = _infer_actions(prev, curr, self._positions(),
                                    _players_from_seats(_SEATS), "preflop",
                                    self._blind_state())
        a1 = [a for a in actions if a.seat == "seat_1"]
        self.assertEqual(len(a1), 1)
        self.assertAlmostEqual(a1[0].total_bb, 6.0)


class TestWinnerLabel(unittest.TestCase):

    def test_winner_label_overrides_stack_delta(self):
        # Alice tem maior stack delta, mas winner_label diz que Carol ganhou
        seq = [
            {"timestamp": 2.0, "tables": {"top_left": {
                "table_id": "HL0001", "blinds": "0.5/1/2", "game_type": "NLHE",
                "pot": 3.5,
                "seats": {"seat_1": {"name": "Alice", "stack": 200.0},
                          "seat_2": {"name": "Bob",   "stack": 190.0},
                          "seat_3": {"name": "Carol", "stack": 195.0}},
                "bets": {"seat_2": 0.5, "seat_3": 1.0},
                "community_cards": [], "hero_cards": [],
                "winner_labels": {}, "_from_cache": False,
            }}},
            {"timestamp": 10.0, "tables": {"top_left": {
                "table_id": "HL0001", "blinds": "0.5/1/2", "game_type": "NLHE",
                "pot": 12.0,
                "seats": {"seat_1": {"name": "Alice", "stack": 200.0},
                          "seat_2": {"name": "Bob",   "stack": 190.0},
                          "seat_3": {"name": "Carol", "stack": 195.0}},
                "bets": {},
                "community_cards": [], "hero_cards": [],
                "winner_labels": {"seat_3": True},   # Carol ganhou
                "_from_cache": False,
            }}},
            {"timestamp": 20.0, "tables": {"top_left": {
                "table_id": "HL0001", "blinds": "0.5/1/2", "game_type": "NLHE",
                "pot": 0,
                "seats": {"seat_1": {"name": "Alice", "stack": 220.0},   # Alice +20 (delta maior)
                          "seat_2": {"name": "Bob",   "stack": 183.0},
                          "seat_3": {"name": "Carol", "stack": 205.0}},  # Carol +10
                "bets": {},
                "community_cards": [], "hero_cards": [],
                "winner_labels": {}, "_from_cache": False,
            }}},
        ]
        hands = HandTracker().process_sequence(seq)
        self.assertEqual(len(hands), 1)
        self.assertEqual(hands[0].winner_label, "Carol")


class TestIsAntesFrame(unittest.TestCase):
    """Testa _is_antes_frame com os quatro cenários críticos."""

    _CFG    = {"ante_fraction": 0.5, "ante_tolerance_bb": 1.0}
    _SEATS8 = {f"seat_{i}": {"name": f"P{i}", "stack": 200.0} for i in range(1, 9)}
    _SEATS2 = {"seat_1": {"name": "Alice", "stack": 200.0},
               "seat_2": {"name": "Bob",   "stack": 200.0}}

    def test_antes_exatas_8_jogadores(self):
        # 8 jogadores × 0.5 BB = 4.0 BB exatos, bets vazio → detectado
        self.assertTrue(_is_antes_frame(4.0, {}, self._SEATS8, self._CFG))

    def test_antes_com_novo_jogador(self):
        # Novo jogador paga 2BB de penalidade → pot = 0.5×8 + 2.0 = 6.0
        # Tolerância padrão (1.0) não cobre; tolerância ampliada (2.5) cobre
        cfg_wide = {"ante_fraction": 0.5, "ante_tolerance_bb": 2.5}
        self.assertFalse(_is_antes_frame(6.0, {}, self._SEATS8, self._CFG))   # fora do padrão
        self.assertTrue(_is_antes_frame(6.0, {}, self._SEATS8, cfg_wide))     # dentro com tolerância maior

    def test_blinds_postados_nao_e_antes(self):
        # bets não vazio → blinds já foram postados, não é frame de antes
        bets = {"seat_2": 0.5, "seat_3": 1.0, "seat_4": 2.0}
        self.assertFalse(_is_antes_frame(7.5, bets, self._SEATS8, self._CFG))

    def test_heads_up_pot_1bb(self):
        # 2 jogadores × 0.5 = 1.0 BB de antes, bets vazio → detectado
        self.assertTrue(_is_antes_frame(1.0, {}, self._SEATS2, self._CFG))


if __name__ == "__main__":
    unittest.main()
