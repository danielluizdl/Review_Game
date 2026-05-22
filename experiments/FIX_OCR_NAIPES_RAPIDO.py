"""
FIX RÁPIDO para OCR confundir naipes (Solução 2)

COPIE ISTO e COLE em vision/ocr_reader.py

Tempo: 5 minutos
Efetividade: 70%
Complexidade: ⭐ Fácil
"""

import re


def _fix_suit_ocr_errors(cards_text: str) -> str:
    """
    Corrige erros comuns de OCR em naipes.
    GGPoker frequentemente lê ◆ como 8.

    Exemplos:
        "K8 A8 9d 8h 2c" → "Kd Ad 9d 8h 2c"
        "KB A8 9d" → "Kd Ad 9d"
        "KO A8 9d" → "Kd Ad 9d"
    """
    if not cards_text:
        return cards_text

    cards_text = str(cards_text).upper()

    # PROBLEMA 1: OCR lê ◆ (diamond) como 8
    # Padrão: [RANK] seguido de 8 (onde 8 não faz sentido)
    # Exemplo: "K8" → "Kd" (king de diamond)
    # Regex: capture rank, depois 8 (não seguido de dígito)
    cards_text = re.sub(r'([AKQJT2-9])\s*8(?!\d)', r'\1D', cards_text)

    # PROBLEMA 2: OCR lê 8 como B (confunde visualmente)
    # Padrão: [RANK] seguido de B
    # Exemplo: "KB" → "Kd"
    cards_text = re.sub(r'([AKQJT2-9])\s*B(?!\d)', r'\1D', cards_text)

    # PROBLEMA 3: OCR lê 8 como O (zero)
    # Padrão: [RANK] seguido de O (letra O)
    # Exemplo: "KO" → "Kd"
    # Nota: Tomar cuidado pois 'O' pode ser legítimo em alguns idiomas
    cards_text = re.sub(r'([AKQJT2-9])\s*O\b', r'\1D', cards_text)

    # PROBLEMA 4: OCR lê ◆ como outros caracteres estranhos
    # "阳" (caractere asiático que o RapidOCR às vezes vê)
    cards_text = cards_text.replace('阳', 'D')  # Diamond

    # PROBLEMA 5: Substituir resultado normalizado
    # D = Diamond (d em lowercase)
    cards_text = cards_text.replace('D', 'd')

    return cards_text


def _normalize_cards_output(cards_list: list) -> list:
    """
    Normaliza lista de cartas lidas por OCR.
    Corrige naipes em cada carta.

    Input:  ["K8", "A8", "9d", "8h", "2c"]
    Output: ["Kd", "Ad", "9d", "8h", "2c"]
    """
    return [_fix_suit_ocr_errors(card) for card in cards_list]


# ────────────────────────────────────────────────────────────────────────────

# COMO USAR:
#
# Em vision/ocr_reader.py, encontre a função que parseia community_cards:
#
# def read_table(frame, table_pos, regions, sx, sy):
#     ...
#     community_cards = data.get("community_cards", [])
#     # ← ADICIONE AQUI:
#     community_cards = _normalize_cards_output(community_cards)
#     ...
#     return {..., "community_cards": community_cards, ...}
#
# OU em _parse_card(), use:
#
# def _parse_card(text: str) -> str:
#     text = _fix_suit_ocr_errors(text)  # ← ADICIONE
#     # ... resto do código


# ────────────────────────────────────────────────────────────────────────────

# TESTES (rode isto para validar):
if __name__ == "__main__":
    test_cases = [
        ("K8 A8 9d", "Kd Ad 9d"),
        ("KB A8 9d", "Kd Ad 9d"),
        ("KO A8 9d", "Kd Ad 9d"),
        ("K8", "Kd"),
        ("8h 2c", "8h 2c"),  # não deve mexer em apostas
        ("K8 A8 9d 8d 2h", "Kd Ad 9d 8d 2h"),  # 5 cartas do river
        ("8", "8"),  # solo 8 (não é rank com suit, deixa como está)
        ("T8 J8 Q8", "Td Jd Qd"),  # face cards
        ("2阳 3阳 4阳", "2d 3d 4d"),  # caractere asiático
    ]

    print("TESTANDO _fix_suit_ocr_errors():")
    print("─" * 60)

    passed = 0
    failed = 0

    for input_text, expected in test_cases:
        result = _fix_suit_ocr_errors(input_text)
        status = "✓ PASS" if result == expected else "✗ FAIL"

        if result == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status}")
        print(f"  Input:    {input_text}")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")
        print()

    print("─" * 60)
    print(f"Resultado: {passed} PASSED, {failed} FAILED")

    if failed == 0:
        print("✓ Todos os testes passaram!")
    else:
        print(f"✗ {failed} testes falharam. Ajuste as regexes se necessário.")
