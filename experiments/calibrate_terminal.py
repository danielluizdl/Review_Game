"""
Visualizador de ROIs via terminal (sem GUI mouse).
Mostra cada região configurada em uma tabela formatada.
"""
import json
from vision.roi_map import REGIONS

def print_roi_config():
    """Mostra todas as ROIs em formato tabular."""

    config_path = "vision/roi_config.json"
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}

    print("\n" + "="*100)
    print("📍 ROI CONFIGURATION — vision/roi_config.json")
    print("="*100)

    # Tabelas (4 mesas)
    print("\n🎯 TABLE POSITIONS (mesas no grid 2x2):")
    print("-" * 100)
    print(f"{'Table':<15} {'X':<10} {'Y':<10} {'Width':<10} {'Height':<10} {'Description':<40}")
    print("-" * 100)

    table_keys = ["top_left", "top_right", "bottom_left", "bottom_right"]
    for tk in table_keys:
        if tk in config:
            x, y, w, h = config[tk]
            desc = f"Mesa {tk.replace('_', ' ').title()}"
            print(f"{tk:<15} {x:<10.0f} {y:<10.0f} {w:<10.0f} {h:<10.0f} {desc:<40}")

    # Regiões (dentro de cada mesa)
    print("\n\n🎲 REGIONS (dentro de cada mesa) — coordenadas relativas ao tamanho da mesa:")
    print("-" * 100)
    print(f"{'Region':<25} {'X':<10} {'Y':<10} {'Width':<10} {'Height':<10} {'Purpose':<30}")
    print("-" * 100)

    region_purposes = {
        "title": "Mesa ID (HL1234)",
        "pot_total": "Valor total do pot",
        "pot_ante": "Antes coletados",
        "community_cards": "[Kd Ad 9d] etc",
        "hero_cards": "Suas cartas",
        "action_buttons": "Fold/Check/Call/Raise",
        "seat_1": "Posição 1 — nome+stack",
        "seat_2": "Posição 2 — nome+stack",
        "seat_3": "Posição 3 — nome+stack",
        "seat_4": "Posição 4 — nome+stack",
        "seat_5": "Posição 5 — nome+stack",
        "seat_6": "Posição 6 — nome+stack",
        "seat_7": "Posição 7 — nome+stack",
        "seat_8": "Posição 8 — nome+stack",
        "bet_1": "Aposta jogador 1",
        "bet_2": "Aposta jogador 2",
        "bet_3": "Aposta jogador 3",
        "bet_4": "Aposta jogador 4",
        "bet_5": "Aposta jogador 5",
        "bet_6": "Aposta jogador 6",
        "bet_7": "Aposta jogador 7",
        "bet_8": "Aposta jogador 8",
        "dealer_seat_1": "Botão dealer (seat 1)",
        "dealer_seat_2": "Botão dealer (seat 2)",
        "dealer_seat_3": "Botão dealer (seat 3)",
        "dealer_seat_4": "Botão dealer (seat 4)",
        "dealer_seat_5": "Botão dealer (seat 5)",
        "dealer_seat_6": "Botão dealer (seat 6)",
        "dealer_seat_7": "Botão dealer (seat 7)",
        "dealer_seat_8": "Botão dealer (seat 8)",
        "winner_label_seat_1": "Label vencedor (seat 1)",
        "winner_label_seat_2": "Label vencedor (seat 2)",
        "winner_label_seat_3": "Label vencedor (seat 3)",
        "winner_label_seat_4": "Label vencedor (seat 4)",
        "winner_label_seat_5": "Label vencedor (seat 5)",
        "winner_label_seat_6": "Label vencedor (seat 6)",
        "winner_label_seat_7": "Label vencedor (seat 7)",
        "winner_label_seat_8": "Label vencedor (seat 8)",
    }

    for region_name, (x, y, w, h) in REGIONS.items():
        purpose = region_purposes.get(region_name, "")
        print(f"{region_name:<25} {x:<10.1f} {y:<10.1f} {w:<10.1f} {h:<10.1f} {purpose:<30}")

    print("\n" + "="*100)
    print("\n💡 COMO AJUSTAR ROIs:")
    print("-" * 100)
    print("1. Abra a GUI: python calibrate_interactive.py <frame.png>")
    print("   - Espaço: navega regiões")
    print("   - Setas: move ROI")
    print("   - +/- : redimensiona")
    print("   - S: salva em vision/roi_config.json")
    print("")
    print("2. Ou edite manualmente em vision/roi_config.json")
    print("")
    print("3. Valores são relativos ao tamanho da mesa (0.0 = top-left, 1.0 = bottom-right)")
    print("="*100 + "\n")

def compare_with_default():
    """Compara config atual com padrão."""
    print("\n🔍 COMPARING WITH DEFAULTS:")
    print("-" * 100)

    config_path = "vision/roi_config.json"
    try:
        with open(config_path, "r") as f:
            current = json.load(f)
    except FileNotFoundError:
        print("⚠️  vision/roi_config.json não encontrado!")
        return

    print(f"✓ vision/roi_config.json carregado ({len(current)} configurações)")
    print(f"✓ Padrão embutido: {len(REGIONS)} regiões")

    # Diferenças
    only_in_current = set(current.keys()) - set(REGIONS.keys())
    only_in_default = set(REGIONS.keys()) - set(current.keys())

    if only_in_current:
        print(f"\n⚠️  Apenas em config (não em padrão): {list(only_in_current)[:5]}...")
    if only_in_default:
        print(f"\n⚠️  Faltando em config: {list(only_in_default)[:5]}...")

    print("\n" + "="*100 + "\n")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--compare":
        compare_with_default()
    else:
        print_roi_config()
        compare_with_default()
