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
_WATCH = ["pot", "community_cards",
          "seat_1", "seat_2", "seat_3", "seat_4",
          "seat_5", "seat_6", "seat_7", "seat_8"]

# Regiões críticas recebem peso 2 no vetor de assinatura
_CRITICAL = {"pot", "community_cards"}


def _load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _scale(coords, sx, sy):
    x, y, w, h = coords
    return int(round(x * sx)), int(round(y * sy)), int(round(w * sx)), int(round(h * sy))


def _signature(frame, table_positions, regions, sx, sy) -> dict:
    """
    Retorna dict[table_key -> np.ndarray], uma assinatura por mesa.
    Regiões críticas (pot, community_cards, action_buttons) têm peso 2
    — qualquer mudança nelas aparece com o dobro da força no diff.
    """
    result = {}
    for tk, tpos in table_positions.items():
        tx, ty, _, _ = _scale(tpos, sx, sy)
        parts = []
        for rname in _WATCH:
            if rname not in regions.get(tk, {}):
                continue
            rx, ry, rw, rh = _scale(regions[tk][rname], sx, sy)
            x1, y1 = tx + rx, ty + ry
            x2, y2 = x1 + rw, y1 + rh
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            gray  = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (32, 16), interpolation=cv2.INTER_AREA)
            vec   = small.flatten().astype(np.float32)
            repeats = 2 if rname in _CRITICAL else 1
            for _ in range(repeats):
                parts.append(vec)
        result[tk] = np.concatenate(parts) if parts else None
    return result


def extract_key_frames(video_path, output_dir=None,
                       sample_fps=2.0, diff_threshold=4.0,
                       min_interval_sec=1.0):
    """
    Varre o vídeo e retorna os key frames onde o estado de pelo menos uma mesa mudou.

    Args:
        video_path:       caminho para o arquivo de vídeo
        output_dir:       se informado, salva os frames como PNG nesse diretório
        sample_fps:       quantos frames por segundo analisar
        diff_threshold:   diferença média mínima (0-255) para considerar mudança
        min_interval_sec: intervalo mínimo entre key frames consecutivos

    Returns:
        Lista de dicts: [{timestamp, frame_idx, diff, path, changed_tables}]
        changed_tables: lista das mesas que mudaram (ex: ["top_left", "bottom_right"])
    """
    cfg              = _load_config()
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
        print(f"Escalonando ROIs: {calib_w}x{calib_h} → {frame_w}x{frame_h} "
              f"(sx={sx:.3f}, sy={sy:.3f})")

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    key_frames     = []
    prev_sigs      = {}          # tk -> np.ndarray da assinatura anterior
    last_saved_sec = -min_interval_sec
    frame_idx      = 0
    sampled        = 0

    while frame_idx < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_idx / video_fps
        sigs      = _signature(frame, table_positions, regions, sx, sy)

        # Calcula diff por mesa individualmente
        changed_tables = []
        max_diff       = 0.0
        for tk, sig in sigs.items():
            prev = prev_sigs.get(tk)
            if prev is not None and sig is not None:
                diff = float(np.mean(np.abs(sig - prev)))
                if diff >= diff_threshold:
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

        # Atualiza assinaturas anteriores para cada mesa
        for tk, sig in sigs.items():
            if sig is not None:
                prev_sigs[tk] = sig

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
