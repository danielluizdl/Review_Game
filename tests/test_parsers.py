import unittest
from vision.ocr_reader import _parse_bb, parse_seat_text, _parse_cards


class TestParseBB(unittest.TestCase):

    def test_plain_bb(self):
        self.assertEqual(_parse_bb("245 BB"), 245.0)

    def test_ocr_88(self):
        self.assertEqual(_parse_bb("245 88"), 245.0)

    def test_ocr_8b(self):
        self.assertEqual(_parse_bb("245 8B"), 245.0)

    def test_stuck_suffix(self):
        # OCR cola o 8 do BB no número: 3948B → 394 BB
        self.assertEqual(_parse_bb("3948B"), 394.0)

    def test_zero_as_o(self):
        # OCR lê zero como O quando seguido de BB
        self.assertEqual(_parse_bb("OBB"), 0.0)

    def test_comma_thousands(self):
        self.assertEqual(_parse_bb("1,234 BB"), 1234.0)

    def test_dot_thousands(self):
        self.assertEqual(_parse_bb("1.234 BB"), 1234.0)

    def test_decimal(self):
        self.assertEqual(_parse_bb("12.5 BB"), 12.5)

    def test_empty(self):
        self.assertIsNone(_parse_bb(""))

    def test_no_number(self):
        self.assertIsNone(_parse_bb("texto puro"))


class TestParseSeatText(unittest.TestCase):

    def test_normal(self):
        name, stack = parse_seat_text("FrankFong 245 BB")
        self.assertEqual(name, "FrankFong")
        self.assertEqual(stack, 245.0)

    def test_name_with_number(self):
        name, stack = parse_seat_text("szh99 548 BB")
        self.assertEqual(name, "szh99")
        self.assertEqual(stack, 548.0)

    def test_timebank_two_digits(self):
        # "13" é timebank — nome deve vir vazio
        name, stack = parse_seat_text("13 415 BB")
        self.assertEqual(name, "")
        self.assertEqual(stack, 415.0)

    def test_timebank_single_digit(self):
        name, stack = parse_seat_text("9 415 BB")
        self.assertEqual(name, "")
        self.assertEqual(stack, 415.0)

    def test_hero_name(self):
        name, stack = parse_seat_text("dLzinN 284 BB")
        self.assertEqual(name, "dLzinN")
        self.assertEqual(stack, 284.0)

    def test_cjk_name(self):
        name, stack = parse_seat_text("又支付了 538 BB")
        self.assertEqual(name, "又支付了")
        self.assertEqual(stack, 538.0)


class TestParseCards(unittest.TestCase):

    def test_three_cards(self):
        self.assertEqual(_parse_cards("A K Q"), ["A", "K", "Q"])

    def test_four_cards(self):
        self.assertEqual(_parse_cards("A K 2 J"), ["A", "K", "2", "J"])

    def test_ten_to_t(self):
        self.assertEqual(_parse_cards("10 K A"), ["T", "K", "A"])

    def test_empty(self):
        self.assertEqual(_parse_cards(""), [])

    def test_noise(self):
        self.assertEqual(_parse_cards("Pote Total"), [])


if __name__ == "__main__":
    unittest.main()
