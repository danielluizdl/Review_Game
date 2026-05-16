"""
Lê texto das regiões da mesa usando RapidOCR (ONNX runtime).
Executa OCR uma vez por mesa inteira e mapeia detecções às regiões por coordenadas.
"""
import re
import numpy as np
from rapidocr_onnxruntime import RapidOCR

_reader = None


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
        if conf < 0.4:
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


def _is_timebank(name: str) -> bool:
    """Retorna True se o texto é um contador de timebank (só dígitos)."""
    return bool(name) and name.isdigit()


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


def _parse_cards(text: str) -> list[str]:
    """
    Extrai lista de cartas do texto OCR da região community_cards/hero_cards.
    Tokens válidos: A K Q J T 2-9 (e variante de OCR: "10"→"T").
    Retorna lista com até 5 elementos, ignorando ruído.
    """
    cards = []
    for token in re.findall(r"[A-Za-z0-9]{1,2}", text):
        token = token.upper()
        if token == "10":
            token = "T"
        if token in _VALID_CARDS:
            cards.append(token)
        if len(cards) == 5:
            break
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
    pot = _parse_bb(texts.get("pot", ""))

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

    # Action labels e winner labels: lidos somente se as regiões estão no config
    _LABEL_MAP = {
        "fold": "fold", "folds": "fold", "desistir": "fold",
        "call": "call", "calls": "call", "fazer call": "call",
        "check": "check", "checks": "check", "passar": "check",
        "raise": "raise", "raises": "raise", "aumentar": "raise",
        "bet": "bet", "bets": "bet", "apostar": "bet",
    }
    action_labels: dict[str, str] = {}
    for i in range(1, 9):
        key = f"action_label_seat_{i}"
        if key in regions:
            raw = texts.get(key, "").strip().lower()
            mapped = _LABEL_MAP.get(raw)
            if mapped:
                action_labels[f"seat_{i}"] = mapped

    winner_labels: dict[str, bool] = {}
    for i in range(1, 9):
        key = f"winner_label_seat_{i}"
        if key in regions:
            raw = texts.get(key, "").strip().lower()
            if "winner" in raw:
                winner_labels[f"seat_{i}"] = True

    return {"table_id": table_id, "blinds": blinds, "game_type": game_type,
            "pot": pot, "seats": seats, "bets": bets,
            "community_cards": community_cards, "hero_cards": hero_cards,
            "action_labels": action_labels, "winner_labels": winner_labels}


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
