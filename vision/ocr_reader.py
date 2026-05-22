"""
Lê texto das regiões da mesa usando RapidOCR (ONNX runtime).
Executa OCR uma vez por mesa inteira e mapeia detecções às regiões por coordenadas.
"""
import re
import logging
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

_reader = None

_OCR_CONF_THRESHOLD = 0.4


def get_reader():
    global _reader
    if _reader is None:
        print("Inicializando RapidOCR...")
        _reader = RapidOCR()
    return _reader


# ── mapeamento de regiões ────────────────────────────────────────────────────

def _bbox_center(bbox):
    return sum(p[0] for p in bbox) / 4, sum(p[1] for p in bbox) / 4


def _ocr_table(table_img: np.ndarray) -> list:
    """Executa OCR na imagem da mesa completa."""
    if table_img is None or table_img.size == 0:
        return []
    result, _ = get_reader()(table_img)
    return result or []


def _map_to_regions(ocr_results: list, regions: dict, sx=1.0, sy=1.0) -> dict:
    """
    Atribui cada detecção OCR à região cujo bounding box contém seu centro.
    Retorna dict region_name -> texto acumulado (detecções concatenadas).
    """
    buckets = {}
    for bbox, text, conf in ocr_results:
        if conf < _OCR_CONF_THRESHOLD:
            logging.debug("OCR descartado conf=%.2f texto=%r", conf, text)
            continue
        cx, cy = _bbox_center(bbox)
        for rname, coords in regions.items():
            rx = int(round(coords[0] * sx))
            ry = int(round(coords[1] * sy))
            rw = int(round(coords[2] * sx))
            rh = int(round(coords[3] * sy))
            if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                buckets.setdefault(rname, []).append(text)
                break
    return {k: " ".join(v) for k, v in buckets.items()}


# ── parsers ──────────────────────────────────────────────────────────────────

# OCR confunde "BB" com: "88", "8B", "B8", "阳", "B", "8", "EB", "6B"
_BB_SUFFIX = r"(?:BB|88|8B|B8|阳|EB|6B|8|B)\b"
_NUMBER    = r"([\d][\d,\.]*)"
_BB_RE     = re.compile(_NUMBER + r"\s*" + _BB_SUFFIX, re.IGNORECASE)


def _normalize_number(raw: str) -> float | None:
    raw = raw.strip()
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "." in raw:
        parts = raw.split(".")
        if len(parts) == 2 and len(parts[1]) > 2:
            raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _fix_bb_suffix(text: str) -> str:
    """
    Corrige '3948B' ou '3948 B' → '394 BB'.
    Corrige 'OBB' → '0BB' (OCR lê zero como 'O' quando seguido de BB).
    """
    text = re.sub(r'(\d{3,})8\s*B\b', lambda m: m.group(1) + ' BB', text)
    text = re.sub(r'\bO\s*BB\b', '0BB', text)
    return text


def _parse_bb(text: str) -> float | None:
    text = _fix_bb_suffix(text)
    matches = list(_BB_RE.finditer(text))
    if not matches:
        return None
    return _normalize_number(matches[-1].group(1))


_SAFE_CHAR_MAP = str.maketrans({
    "?": "7",
    "!": "1",
    "|": "",
    "。": "",
})


def _clean_name(name: str) -> str:
    name = name.rstrip("。.").strip()
    name = re.sub(r"^[^a-zA-Z一-鿿\d]+", "", name).strip()
    return name.translate(_SAFE_CHAR_MAP)


_INVALID_NAMES = {
    "fora da mesa", "fora de mesa", "sitting out", "sit out",
    "empty seat", "open seat",
}

def _is_timebank(name: str) -> bool:
    """Retorna True se o texto é um contador de timebank (só dígitos) ou placeholder de assento vazio."""
    if bool(name) and name.isdigit():
        return True
    return name.lower() in _INVALID_NAMES


def parse_seat_text(text: str) -> tuple[str, float | None]:
    """
    Separa nome e stack do texto combinado de um assento.
    Ex: 'FrankFong 245 BB' → ('FrankFong', 245.0)
    Retorna nome vazio se o campo de nome for apenas dígitos (timebank).
    """
    text = _fix_bb_suffix(text)
    matches = list(_BB_RE.finditer(text))
    if matches:
        last  = matches[-1]
        stack = _normalize_number(last.group(1))
        name  = re.sub(r"^\d+\s*", "", text[:last.start()].strip()).strip()
        name  = _clean_name(name)
        if _is_timebank(name):
            name = ""
        return name, stack

    nums = list(re.finditer(r"\b\d[\d,.]*\b", text))
    if nums:
        last  = nums[-1]
        stack = _normalize_number(last.group())
        name  = re.sub(r"^\d+\s*", "", text[:last.start()].strip()).strip()
        name  = _clean_name(name)
        if _is_timebank(name):
            name = ""
        return name, stack

    name = _clean_name(text.strip())
    if _is_timebank(name):
        name = ""
    return name, None


def _fix_table_id(text: str) -> str:
    """
    Corrige erros comuns de OCR no ID da mesa.
    Ex: 'HLB61Gg' → 'HL6169'  |  'HL86169' → 'HL6169'
    """
    ocr_map = str.maketrans("BOGgIlSZoQ", "8069961520")
    match = re.search(r"(?:H|1)?L([0-9B][A-Z0-9a-z.]{2,7})", text, re.IGNORECASE)
    if match:
        raw_id = match.group(1).translate(ocr_map).replace(".", "")
        if len(raw_id) >= 5 and raw_id[0] == "8":
            raw_id = raw_id[1:]
        return f"HL{raw_id}"
    return text.split(" ")[0].strip()


_VALID_CARDS = frozenset({"A", "K", "Q", "J", "T", "2", "3", "4", "5", "6", "7", "8", "9"})


# ── suit color detection ──────────────────────────────────────────────────────

def detect_suit_by_color(crop: np.ndarray, debug: bool = False) -> str:
    """
    Detect GGPoker card suit from a BGR image crop.
      ♦ Diamond : Blue  H=90-130
      ♣ Club    : Green H=35-85
      ♥ Heart   : Red   H=0-15 or H=160-180
      ♠ Spade   : Black (few colored pixels + dark pixels present)

    Strategy: analyse only pixels with meaningful saturation (S>30, V>50)
    to ignore dark table background. Spade is detected when almost no
    colored pixels remain but dark pixels (V<80, S<60) are present.
    """
    if crop is None or crop.size == 0:
        return "?"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    # Colored pixels: enough saturation, not too dark (V>80 excludes dark felt), not white
    colored_mask = (S > 30) & (V > 80) & (V < 235)
    colored_h = H[colored_mask]
    n_colored = int(colored_h.size)

    # Dark pixels: true black/dark (low value AND low saturation)
    dark_count = int(np.sum((V < 80) & (S < 60)))

    if debug:
        print(f"  n_colored(S>30,V>50)={n_colored:5d}  dark(V<80,S<60)={dark_count:5d}")

    if n_colored < 15:
        if dark_count >= 30:
            if debug:
                print(f"  -> s (spade: few colored, many dark)")
            return "s"
        if debug:
            print(f"  -> NO DETECTION")
        return "?"

    diamond = int(np.sum((colored_h >= 90) & (colored_h <= 130)))
    club    = int(np.sum((colored_h >= 35) & (colored_h <= 85)))
    heart   = int(np.sum((colored_h >= 160) | (colored_h <= 15)))

    best_count = max(diamond, club, heart)

    if debug:
        print(f"  BLUE(d):{diamond:5d}  GREEN(c):{club:5d}  RED(h):{heart:5d}")

    if best_count < 10:
        if debug:
            print(f"  -> s (spade: colored but no dominant hue)")
        return "s"

    if diamond == best_count:
        if debug:
            print(f"  -> d (count: {diamond})")
        return "d"
    if club == best_count:
        if debug:
            print(f"  -> c (count: {club})")
        return "c"
    if debug:
        print(f"  -> h (count: {heart})")
    return "h"


def _detect_card_suits_in_region(
    table_img: np.ndarray,
    ocr_results: list,
    region: list,
    sx: float = 1.0,
    sy: float = 1.0,
    n_cards: int = 0,
    region_capacity: int = 0,
) -> list[str]:
    """
    Detect suits for n_cards cards in `region`.

    If n_cards>0: divides the region into n_cards equal non-overlapping zones
    and detects the dominant suit colour in each zone — independent of OCR
    bounding-box positions, so adjacent cards never contaminate each other.

    If n_cards==0: falls back to OCR-position-based detection (legacy).
    """
    if not region or table_img is None or table_img.size == 0:
        return []

    rx = int(round(region[0] * sx))
    ry = int(round(region[1] * sy))
    rw = int(round(region[2] * sx))
    rh = int(round(region[3] * sy))

    if rw <= 0 or rh <= 0:
        return []

    y1 = max(0, ry)
    y2 = min(table_img.shape[0], ry + rh)

    if n_cards > 0:
        # Divide por region_capacity (total de slots na região), não por n_cards.
        # Isso garante alinhamento correto: community_cards cobre 5 slots fixos;
        # dividir por n_cards=3 (flop) cria zonas que abarcam 2 cartas por zona.
        cap = region_capacity if region_capacity > 0 else n_cards
        zone_w = rw / cap
        suits: list[str] = []
        for i in range(n_cards):
            x1 = max(0, rx + int(round(i * zone_w)))
            x2 = min(table_img.shape[1], rx + int(round((i + 1) * zone_w)))
            crop = table_img[y1:y2, x1:x2]
            suits.append(detect_suit_by_color(crop))
        return suits

    # ── Legacy: OCR-position-based ────────────────────────────────────────────
    card_xs: list[float] = []
    for bbox, text, conf in ocr_results:
        if conf < _OCR_CONF_THRESHOLD:
            continue
        cx, cy = _bbox_center(bbox)
        if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
            if any(c in _VALID_CARDS for c in text.upper()):
                card_xs.append(cx)

    if not card_xs:
        return []

    card_xs.sort()
    merge_thr = max(rw * 0.06, 8.0)
    merged_xs: list[float] = []
    for x in card_xs:
        if not merged_xs or x - merged_xs[-1] > merge_thr:
            merged_xs.append(x)

    half_w = max(rw // max(len(merged_xs) * 2, 2), 20)
    suits = []
    for cx in merged_xs[:5]:
        x1 = max(0, int(cx) - half_w)
        x2 = min(table_img.shape[1], int(cx) + half_w)
        crop = table_img[y1:y2, x1:x2]
        suits.append(detect_suit_by_color(crop))

    return suits


def _parse_cards(text: str) -> list[str]:
    """
    Extrai lista de cartas do texto OCR da região community_cards/hero_cards.
    Tokens válidos: A K Q J T 2-9 (e variante de OCR: "10"→"T").
    Retorna lista com até 5 elementos, ignorando ruído.
    Processa por token separado por espaço: tokens com ≥2 chars de carta válidos
    são expandidos char-a-char ("KA9" → K,A,9); tokens com 1 char válido e ≤2
    chars totais são aceitos como carta única ("Kd" → K); demais são ruído.
    """
    cards = []
    for token in text.split():
        token_up = re.sub(r"[^A-Za-z0-9]", "", token).upper()
        if not token_up:
            continue
        # Handle "10" prefix → "T"
        if token_up.startswith("10"):
            cards.append("T")
            if len(cards) == 5:
                return cards
            token_up = token_up[2:]
            if not token_up:
                continue
        valid = [c for c in token_up if c in _VALID_CARDS]
        # Multi-card merged token: ≥2 valid chars AND ≥2/3 of all chars are valid cards
        if len(valid) >= 2 and len(valid) * 3 >= len(token_up) * 2:
            for c in valid:
                cards.append(c)
                if len(cards) == 5:
                    return cards
        elif len(valid) == 1 and len(token_up) <= 2:
            cards.append(valid[0])
            if len(cards) == 5:
                return cards
    return cards


def _parse_title(text: str) -> tuple[str, str, str]:
    """
    Extrai table_id, blinds e game_type do título completo da mesa.
    Ex: 'HL5798 - 0.05/0.1/0.2(0.05) - NLHE' → ('HL5798', '0.05/0.1/0.2(0.05)', 'NLHE')
    """
    table_id = _fix_table_id(text)
    parts = re.split(r"\s*-\s*", text)
    blinds    = parts[1].strip() if len(parts) > 1 else ""
    game_type = parts[2].strip() if len(parts) > 2 else ""
    return table_id, blinds, game_type


# ── sanitização de resultado ─────────────────────────────────────────────────

def _sanitize_table_result(result: dict) -> dict:
    """Valida e corrige valores implausíveis antes de enviá-los ao HandTracker."""
    pot = result.get("pot")
    pot_ante = result.get("pot_ante")

    if pot is not None and pot < 0:
        logging.warning("OCR: pot negativo (%.2f) descartado", pot)
        result["pot"] = None
        pot = None

    if pot_ante is not None and pot is not None and pot_ante > pot:
        result["pot_ante"] = None

    cc = result.get("community_cards", [])
    if len(cc) > 5:
        logging.warning("OCR: %d cartas comunitárias (> 5) — truncando", len(cc))
        result["community_cards"] = cc[:5]

    for sk, info in result.get("seats", {}).items():
        stack = info.get("stack")
        if stack is not None and stack < 0:
            info["stack"] = None

    return result


# ── leitura principal ────────────────────────────────────────────────────────

def read_table(frame: np.ndarray, table_pos: list, regions: dict,
               sx=1.0, sy=1.0) -> dict:
    """
    Lê todos os dados de uma mesa com uma única chamada de OCR.

    Returns:
        {"table_id": str, "pot": float|None, "seats": {seat_key: {"name": str, "stack": float|None}}}
    """
    tx = int(round(table_pos[0] * sx))
    ty = int(round(table_pos[1] * sy))
    tw = int(round(table_pos[2] * sx))
    th = int(round(table_pos[3] * sy))
    table_img = frame[ty:ty + th, tx:tx + tw]

    ocr_results = _ocr_table(table_img)
    texts = _map_to_regions(ocr_results, regions, sx, sy)

    table_id, blinds, game_type = _parse_title(texts.get("title", ""))
    # pot_total = pot acumulado durante a mão; fallback para "pot" (config antigo)
    pot      = _parse_bb(texts.get("pot_total", "") or texts.get("pot", ""))
    pot_ante = _parse_bb(texts.get("pot_ante", ""))

    seats = {}
    for i in range(1, 9):
        sk = f"seat_{i}"
        if sk not in texts:
            continue
        name, stack = parse_seat_text(texts[sk])
        if name:
            seats[sk] = {"name": name, "stack": stack}

    bets = {}
    for i in range(1, 9):
        bk = f"bet_seat_{i}"
        if bk in texts:
            val = _parse_bb(texts[bk])
            if val and val > 0:
                bets[f"seat_{i}"] = val

    community_cards = _parse_cards(texts.get("community_cards", ""))
    hero_cards      = _parse_cards(texts.get("hero_cards", ""))

    # Suit detection for community cards.
    # Runs colour detection on all 5 fixed slots so the hand tracker can correct
    # suits at stable post-animation frames even when OCR misses a card rank.
    cc_region = regions.get("community_cards")
    community_zone_suits: list[str] = []
    if cc_region is not None:
        rx   = int(round(cc_region[0] * sx))
        ry   = int(round(cc_region[1] * sy))
        rw   = int(round(cc_region[2] * sx))
        rh   = int(round(cc_region[3] * sy))
        zone_w = rw // 5
        y1, y2 = max(0, ry), min(table_img.shape[0], ry + rh)
        for i in range(5):
            x1 = max(0, rx + i * zone_w)
            x2 = min(table_img.shape[1], x1 + zone_w)
            community_zone_suits.append(detect_suit_by_color(table_img[y1:y2, x1:x2]))
        # Apply detected suits to OCR-detected rank characters
        for i in range(len(community_cards)):
            if len(community_cards[i]) == 1 and i < len(community_zone_suits):
                suit = community_zone_suits[i]
                if suit != "?":
                    community_cards[i] += suit

    # Hero card suit detection skipped: GGPoker's gold highlight makes all hero
    # cards appear green regardless of suit, so color detection is unreliable.

    # Rótulos de ação e vencedor lidos das regiões winner_label_seat_N
    # O mesmo ROI mostra a última ação do jogador (ex: "Desistir") e "WINNER" ao final
    _LABEL_MAP = {
        # Português GGPoker
        "desistir":  "fold",
        "pagar":     "call",
        "passar":    "check",
        "aposta":    "bet",
        "aumentar":  "raise",
        "all in":    "allin",
        "allin":     "allin",
        "straddle":  "straddle",
        "postar":    "post",
        # Inglês (fallback)
        "fold":      "fold",
        "call":      "call",
        "check":     "check",
        "bet":       "bet",
        "raise":     "raise",
    }
    action_labels: dict[str, str] = {}
    winner_labels: dict[str, bool] = {}

    for i in range(1, 9):
        seat_key = f"seat_{i}"
        # Lê de winner_label_seat_N (rótulo de ação + vencedor no mesmo ROI)
        wkey = f"winner_label_seat_{i}"
        if wkey in regions:
            raw = texts.get(wkey, "").strip().lower()
            if "winner" in raw:
                winner_labels[seat_key] = True
            else:
                for pt, action in _LABEL_MAP.items():
                    if pt in raw:
                        action_labels[seat_key] = action
                        break
        # Lê de action_label_seat_N se existir como região separada
        akey = f"action_label_seat_{i}"
        if akey in regions and seat_key not in action_labels:
            raw = texts.get(akey, "").strip().lower()
            for pt, action in _LABEL_MAP.items():
                if pt in raw:
                    action_labels[seat_key] = action
                    break

    # Botão de dealer: chip tem pixel muito mais brilhante que o fundo (limiar=150)
    # Usa threshold relativo: max(_DEALER_THRESHOLD, mean_brightness + 40) para
    # evitar falsos positivos em regiões naturalmente claras e falsos negativos em escuras.
    _DEALER_THRESHOLD = 150
    dealer_seat = ""
    best_max = 0
    all_pmaxes: list[tuple[int, str]] = []   # (pmax, seat_key) — para fallback
    for i in range(1, 9):
        key = f"dealer_seat_{i}"
        if key not in regions:
            continue
        rx = int(round(regions[key][0] * sx))
        ry = int(round(regions[key][1] * sy))
        rw = int(round(regions[key][2] * sx))
        rh = int(round(regions[key][3] * sy))
        crop = table_img[ry:ry + rh, rx:rx + rw]
        if crop.size == 0:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        pmax = int(gray.max())
        mean_brightness = int(gray.mean())
        dynamic_threshold = max(_DEALER_THRESHOLD, mean_brightness + 40)
        all_pmaxes.append((pmax, f"seat_{i}"))
        if pmax > dynamic_threshold and pmax > best_max:
            best_max = pmax
            dealer_seat = f"seat_{i}"

    # Fallback: se nenhum assento passou o threshold mas todos têm pmax > 100,
    # escolhe o de maior pmax (sem log — pode ser vídeo com brilho reduzido).
    if not dealer_seat and all_pmaxes and all(p > 100 for p, _ in all_pmaxes):
        best_fallback = max(all_pmaxes, key=lambda x: x[0])
        dealer_seat = best_fallback[1]

    result = {"table_id": table_id, "blinds": blinds, "game_type": game_type,
              "pot": pot, "pot_ante": pot_ante, "seats": seats, "bets": bets,
              "community_cards": community_cards, "hero_cards": hero_cards,
              "community_zone_suits": community_zone_suits,
              "action_labels": action_labels, "winner_labels": winner_labels,
              "dealer_seat": dealer_seat}
    return _sanitize_table_result(result)


# ── APIs de compatibilidade (usadas por test_ocr.py) ────────────────────────

def _read_region(image: np.ndarray) -> str:
    result, _ = get_reader()(image)
    if not result:
        return ""
    return " ".join(r[1] for r in result)


def read_pot(image: np.ndarray) -> float | None:
    return _parse_bb(_read_region(image))


def read_stack(image: np.ndarray) -> float | None:
    _, stack = parse_seat_text(_read_region(image))
    return stack


def read_player_name(image: np.ndarray) -> str:
    name, _ = parse_seat_text(_read_region(image))
    return name


def read_table_id(image: np.ndarray) -> str:
    return _fix_table_id(_read_region(image))
