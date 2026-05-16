"""
Coordenadas das regiões de interesse (ROI) para cada elemento da mesa.
Baseado em resolução de gravação 1820x1080, grid 2x2 de mesas.
Todas as coordenadas são relativas ao canto superior esquerdo de cada mesa.
"""

# Posição de cada mesa no frame completo (x, y, largura, altura)
TABLE_POSITIONS = {
    "top_left":     (0,    0,   910, 510),
    "top_right":    (910,  0,   910, 510),
    "bottom_left":  (0,    510, 910, 510),
    "bottom_right": (910,  510, 910, 510),
}

TABLE_KEYS = ["top_left", "top_right", "bottom_left", "bottom_right"]

# Regiões relativas dentro de cada mesa (x, y, largura, altura)
# Valores aproximados — calibrar com calibrate.py após confirmar no vídeo real
REGIONS = {
    "title":     (0,   0,  600, 30),   # título da janela: "HL5798 - 0.05/0.1 - NLHE"
    "pot":       (180, 155, 300, 35),  # "Pote Total: X BB"

    # 8 assentos: (x, y, w, h) da área de nome+stack de cada jogador
    "seat_1":    (260, 55,  180, 45),  # topo centro-esquerda
    "seat_2":    (370, 30,  180, 45),  # topo centro
    "seat_3":    (530, 55,  180, 45),  # topo centro-direita
    "seat_4":    (680, 150, 180, 45),  # direita
    "seat_5":    (620, 310, 180, 45),  # baixo direita
    "seat_6":    (370, 380, 180, 45),  # baixo centro (hero)
    "seat_7":    (80,  310, 180, 45),  # baixo esquerda
    "seat_8":    (20,  150, 180, 45),  # esquerda

    # Cartas comunitárias (flop/turn/river)
    "community_cards": (250, 195, 360, 90),

    # Cartas do hero (hole cards)
    "hero_cards":      (310, 330, 180, 90),

    # Aposta de cada assento (chip + valor)
    "bet_seat_1": (280, 100, 100, 30),
    "bet_seat_2": (370,  90, 100, 30),
    "bet_seat_3": (510, 100, 100, 30),
    "bet_seat_4": (600, 175, 100, 30),
    "bet_seat_5": (540, 275, 100, 30),
    "bet_seat_6": (370, 300, 100, 30),
    "bet_seat_7": (150, 275, 100, 30),
    "bet_seat_8": (100, 175, 100, 30),

    # Cartas dos oponentes no showdown — seat_2 a seat_8 (seat_1 = hero)
    "cards_seat_2": (370, 30,  80, 45),
    "cards_seat_3": (530, 55,  80, 45),
    "cards_seat_4": (680, 150, 80, 45),
    "cards_seat_5": (620, 310, 80, 45),
    "cards_seat_6": (370, 380, 80, 45),
    "cards_seat_7": (80,  310, 80, 45),
    "cards_seat_8": (20,  150, 80, 45),

    # Label "Winner." exibido junto ao seat vencedor ao fim de cada mão.
    # Coordenadas placeholder — calibrar com calibrate_interactive.py.
    # Posicionados ligeiramente abaixo (seats 1-4) ou acima (seats 5-8) do box de stack.
    "winner_label_seat_1": (260, 102, 140, 18),
    "winner_label_seat_2": (370,  77, 140, 18),
    "winner_label_seat_3": (530, 102, 140, 18),
    "winner_label_seat_4": (680, 197, 140, 18),
    "winner_label_seat_5": (620, 290, 140, 18),
    "winner_label_seat_6": (370, 360, 140, 18),
    "winner_label_seat_7": ( 80, 290, 140, 18),
    "winner_label_seat_8": ( 20, 197, 140, 18),

}

# Posição do dealer (BTN) é inferida a partir do SB/BB:
# SB = menor bet postado no início da mão
# BB = segundo bet postado
# BTN = seat imediatamente antes do SB na ordem horária


def get_table_roi(frame, table_key: str):
    """Recorta a região de uma mesa específica do frame completo."""
    x, y, w, h = TABLE_POSITIONS[table_key]
    return frame[y:y+h, x:x+w]


def get_region(table_frame, region_key: str):
    """Recorta uma região específica dentro do frame de uma mesa."""
    x, y, w, h = REGIONS[region_key]
    return table_frame[y:y+h, x:x+w]
