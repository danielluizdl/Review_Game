"""
Detector de mudança de estado das mesas.

Varre o vídeo sem OCR (só comparação de pixels) e extrai apenas os frames
onde o estado do jogo mudou. Retorna quais mesas específicas mudaram para
que o OCR só processe o que é necessário.
"""
import cv2
import json
import os
import numpy as np

CONFIG_PATH = "vision/roi_config.json"

# Regiões monitoradas — onde mudanças de jogo acontecem
_WATCH = [
    "pot_total", "pot_ante", "community_cards", "hero_cards",
    "seat_1", "seat_2", "seat_3", "seat_4",
    "seat_5", "seat_6", "seat_7", "seat_8",
    # apostas individuais — detecta ação de cada jogador
    "bet_seat_1", "bet_seat_2", "bet_seat_3", "bet_seat_4",
    "bet_seat_5", "bet_seat_6", "bet_seat_7", "bet_seat_8",
    # botão de dealer — movimento sinaliza início de nova mão
    "dealer_seat_1", "dealer_seat_2", "dealer_seat_3", "dealer_seat_4",
    "dealer_seat_5", "dealer_seat_6", "dealer_seat_7", "dealer_seat_8",
    # rótulos de ação/vencedor — mudam a cada ação do jogador
    "winner_label_seat_1", "winner_label_seat_2", "winner_label_seat_3", "winner_label_seat_4",
    "winner_label_seat_5", "winner_label_seat_6", "winner_label_seat_7", "winner_label_seat_8",
]

# Regiões críticas recebem peso 2 no vetor de assinatura
_CRITICAL = {
    "pot_total", "pot_ante", "community_cards", "hero_cards",
    "dealer_seat_1", "dealer_seat_2", "dealer_seat_3", "dealer_seat_4",
    "dealer_seat_5", "dealer_seat_6", "dealer_seat_7", "dealer_seat_8",
    "winner_label_seat_1", "winner_label_seat_2", "winner_label_seat_3", "winner_label_seat_4",
    "winner_label_seat_5", "winner_label_seat_6", "winner_label_seat_7", "winner_label_seat_8",
}

# Regiões de ação verificadas individualmente (evita diluição pelo mean global)
_ACTION_REGIONS = [
    "community_cards",
    "winner_label_seat_1", "winner_label_seat_2", "winner_label_seat_3", "winner_label_seat_4",
    "winner_label_seat_5", "winner_label_seat_6", "winner_label_seat_7", "winner_label_seat_8",
]
# Diff mínimo numa região de ação individual para disparar key frame
_ACTION_REGION_THRESHOLD = 8.0


def _load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _scale(coords, sx, sy):
    x, y, w, h = coords
    return int(round(x * sx)), int(round(y * sy)), int(round(w * sx)), int(round(h * sy))


def _signature(frame, table_positions, regions, sx, sy) -> tuple[dict, dict]:
    """
    Retorna (sigs, action_sigs).
    sigs: dict[table_key -> np.ndarray] — assinatura global por mesa.
    action_sigs: dict[table_key -> dict[rname -> np.ndarray]] — por região de ação.
    """
    # Converte todo o frame para grayscale uma única vez (evita 112 conversões por frame)
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sigs = {}
    action_sigs = {}
    for tk, tpos in table_positions.items():
        tx, ty, _, _ = _scale(tpos, sx, sy)
        parts = []
        per_region = {}
        for rname in _WATCH:
            if rname not in regions.get(tk, {}):
                continue
            rx, ry, rw, rh = _scale(regions[tk][rname], sx, sy)
            x1, y1 = tx + rx, ty + ry
            x2, y2 = x1 + rw, y1 + rh
            gray = frame_gray[y1:y2, x1:x2]
            if gray.size == 0:
                continue
            small = cv2.resize(gray, (32, 16), interpolation=cv2.INTER_AREA)
            vec   = small.flatten().astype(np.float32)
            repeats = 2 if rname in _CRITICAL else 1
            for _ in range(repeats):
                parts.append(vec)
            if rname in _ACTION_REGIONS:
                per_region[rname] = vec
        sigs[tk] = np.concatenate(parts) if parts else None
        action_sigs[tk] = per_region
    return sigs, action_sigs


def extract_key_frames(video_path, output_dir=None,
                       sample_fps=4.0, diff_threshold=2.5,
                       min_interval_sec=0.5, cfg: dict = None):
    """
    Varre o vídeo e retorna os key frames onde o estado de pelo menos uma mesa mudou.

    Args:
        video_path:       caminho para o arquivo de vídeo
        output_dir:       se informado, salva os frames como PNG nesse diretório
        sample_fps:       quantos frames por segundo analisar
        diff_threshold:   diferença média mínima (0-255) para considerar mudança
        min_interval_sec: intervalo mínimo entre key frames consecutivos
        cfg:              configuração já carregada (dict); se None, carrega do disco

    Returns:
        Lista de dicts: [{timestamp, frame_idx, diff, path, changed_tables}]
        changed_tables: lista das mesas que mudaram (ex: ["top_left", "bottom_right"])
    """
    if cfg is None:
        cfg = _load_config()
    table_positions  = cfg["table_positions"]
    regions          = cfg["regions"]
    calib_w, calib_h = cfg.get("calibration_resolution", [1920, 1080])

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Não conseguiu abrir: {video_path}")

    video_fps    = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration     = total_frames / video_fps if video_fps else 0

    sx   = frame_w / calib_w
    sy   = frame_h / calib_h
    step = max(1, int(video_fps / sample_fps))

    print(f"Vídeo: {frame_w}x{frame_h}  {video_fps:.1f}fps  "
          f"{duration/60:.1f}min ({total_frames} frames)")
    print(f"Amostrando 1 a cada {step} frames  |  threshold={diff_threshold}")
    if abs(sx - 1.0) > 0.005:
        print(f"Escalonando ROIs: {calib_w}x{calib_h} -> {frame_w}x{frame_h} "
              f"(sx={sx:.3f}, sy={sy:.3f})")

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    key_frames          = []
    prev_sigs           = {}   # tk -> np.ndarray da assinatura global anterior
    prev_action_sigs    = {}   # tk -> dict[rname -> np.ndarray] das regiões de ação
    key_sigs            = {}   # tk -> sig do último key frame salvo para essa mesa
    key_action_sigs     = {}   # tk -> per-region sigs do último key frame dessa mesa
    last_saved_sec      = -min_interval_sec
    frame_idx           = 0
    sampled             = 0

    while frame_idx < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_idx / video_fps
        sigs, action_sigs = _signature(frame, table_positions, regions, sx, sy)

        # Calcula diff por mesa — compara contra o último KEY FRAME (não o último
        # frame amostrado) para capturar animações graduais (ex: cartas sendo
        # distribuídas lentamente). Fallback para prev_sigs no primeiro frame.
        changed_tables = []
        max_diff       = 0.0
        for tk in sigs:
            sig     = sigs[tk]
            _ks     = key_sigs.get(tk)
            anchor  = _ks if _ks is not None else prev_sigs.get(tk)
            triggered = False
            diff = 0.0

            # 1) Check global médio (detector original)
            if anchor is not None and sig is not None:
                diff = float(np.mean(np.abs(sig - anchor)))
                if diff >= diff_threshold:
                    triggered = True

            # 2) Check individual por região de ação (evita diluição)
            if not triggered:
                _kas = key_action_sigs.get(tk)
                pa   = _kas if _kas is not None else prev_action_sigs.get(tk, {})
                ca = action_sigs.get(tk, {})
                for rname, vec in ca.items():
                    if rname in pa and pa[rname] is not None:
                        rdiff = float(np.mean(np.abs(vec - pa[rname])))
                        if rdiff >= _ACTION_REGION_THRESHOLD:
                            triggered = True
                            diff = max(diff, rdiff)
                            break

            if triggered:
                changed_tables.append(tk)
                max_diff = max(max_diff, diff)

        gap_ok = (timestamp - last_saved_sec) >= min_interval_sec

        if changed_tables and gap_ok:
            path = None
            if output_dir:
                name = f"frame_{int(timestamp):05d}s_{timestamp:.2f}.png"
                path = os.path.join(output_dir, name)
                cv2.imwrite(path, frame)

            key_frames.append({
                "timestamp":      round(timestamp, 2),
                "frame_idx":      frame_idx,
                "diff":           round(max_diff, 2),
                "path":           path,
                "changed_tables": changed_tables,
            })
            last_saved_sec = timestamp

            # Âncora atualizada por mesa apenas quando essa mesa disparou o key frame
            for tk in changed_tables:
                if sigs.get(tk) is not None:
                    key_sigs[tk] = sigs[tk]
                if action_sigs.get(tk):
                    key_action_sigs[tk] = action_sigs[tk]

        # Atualiza assinaturas anteriores para cada mesa (fallback/diagnóstico)
        for tk, sig in sigs.items():
            if sig is not None:
                prev_sigs[tk] = sig
        for tk, asig in action_sigs.items():
            prev_action_sigs[tk] = asig

        sampled   += 1
        frame_idx += step

        if sampled % 200 == 0:
            pct = 100 * frame_idx / total_frames
            print(f"  {pct:5.1f}%  t={timestamp/60:.1f}min  "
                  f"key frames={len(key_frames)}", end="\r")

    cap.release()

    total_sampled = total_frames // step
    print(f"\nPronto: {len(key_frames)} key frames "
          f"de {total_sampled} amostrados "
          f"({100*len(key_frames)/max(total_sampled,1):.1f}% do vídeo)")

    return key_frames
