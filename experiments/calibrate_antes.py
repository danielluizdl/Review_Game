"""
Calibra ante_fraction e ante_tolerance_bb para detecção do frame de antes.

Para cada frame onde bets={} e pot>0 com pelo menos 2 jogadores ativos, calcula
pot/n_active e exibe um histograma para ajudar a escolher os parâmetros corretos.

Uso:
  python calibrate_antes.py --frames               # usa key_frames/ (mais rápido)
  python calibrate_antes.py --frames key_frames/   # diretório alternativo
  python calibrate_antes.py video.mp4              # reprocessa o vídeo completo
  python calibrate_antes.py --json output/.checkpoint_<video>.json
"""
import io
import json
import os
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)

from collections import Counter

CONFIG_PATH = "vision/roi_config.json"


def _load_from_json(path: str) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"Esperado checkpoint (lista de frames), mas '{path}' contém {type(data).__name__}.\n"
            "Use o arquivo .checkpoint_<video>.json gerado durante o processamento."
        )
    return data


def _load_from_frames_dir(frames_dir: str) -> list[dict]:
    """Lê PNGs já extraídos de key_frames/ e roda OCR em todas as mesas."""
    import glob
    import cv2
    from vision.ocr_reader import read_table

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    calib_w, calib_h  = cfg.get("calibration_resolution", [1920, 1080])
    table_positions   = cfg["table_positions"]
    all_table_keys    = list(table_positions.keys())

    pattern = os.path.join(frames_dir, "frame_*.png")
    paths   = sorted(glob.glob(pattern))
    if not paths:
        print(f"Nenhum PNG encontrado em '{frames_dir}'.")
        return []

    print(f"Processando {len(paths)} frames de '{frames_dir}'...")
    results = []

    for i, path in enumerate(paths, 1):
        base  = os.path.basename(path).replace(".png", "")
        parts = base.split("_")
        try:
            ts = float(parts[-1])
        except (ValueError, IndexError):
            ts = float(i)

        frame = cv2.imread(path)
        if frame is None:
            continue
        h, w = frame.shape[:2]
        sx, sy = w / calib_w, h / calib_h

        tables = {}
        for tk in all_table_keys:
            state = read_table(frame, table_positions[tk],
                               cfg["regions"][tk], sx, sy)
            tables[tk] = {**state, "_from_cache": False}

        results.append({"timestamp": ts, "tables": tables})

        if i % 10 == 0 or i == len(paths):
            print(f"  {i}/{len(paths)}", end="\r")

    print()
    return results


def _load_from_video(video_path: str) -> list[dict]:
    """Extrai key frames e roda OCR para análise de calibração."""
    import cv2
    from capture.change_detector import extract_key_frames
    from vision.ocr_reader import read_table

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    calib_w, calib_h = cfg.get("calibration_resolution", [1920, 1080])
    all_table_keys   = list(cfg["table_positions"].keys())

    print(f"Extraindo key frames de '{video_path}'...")
    key_frames = extract_key_frames(video_path, output_dir="key_frames")
    if not key_frames:
        print("Nenhum key frame encontrado.")
        return []

    print(f"Rodando OCR em {len(key_frames)} key frames...")
    results = []
    table_cache: dict = {}

    for i, kf in enumerate(key_frames, 1):
        frame = cv2.imread(kf["path"])
        if frame is None:
            continue
        h, w = frame.shape[:2]
        sx, sy = w / calib_w, h / calib_h

        tables = {}
        changed = set(kf.get("changed_tables", all_table_keys))
        for tk in all_table_keys:
            if tk in changed:
                state = read_table(frame, cfg["table_positions"][tk],
                                   cfg["regions"][tk], sx, sy)
                table_cache[tk] = state
                tables[tk] = {**state, "_from_cache": False}
            else:
                tables[tk] = {**(table_cache.get(tk) or {}), "_from_cache": True}

        results.append({"timestamp": kf["timestamp"], "tables": tables})

        if i % 10 == 0 or i == len(key_frames):
            print(f"  {i}/{len(key_frames)}", end="\r")

    print()
    return results


def _analyze(ocr_results: list[dict], ante_fraction: float, tolerance: float) -> None:
    matches: list[tuple] = []
    ratios:  list[float] = []

    for entry in ocr_results:
        ts = entry["timestamp"]
        for tk, data in entry["tables"].items():
            if data.get("_from_cache"):
                continue
            pot   = data.get("pot")
            bets  = data.get("bets", {})
            seats = data.get("seats", {})
            if not pot or pot <= 0 or bets:
                continue
            n_active = sum(1 for s in seats.values() if s.get("name") or s.get("stack"))
            if n_active < 2:
                continue
            ratio = round(pot / n_active, 3)
            ratios.append(ratio)
            matches.append((ts, tk, pot, n_active, ratio))

    if not matches:
        print("Nenhum frame candidato encontrado (bets={}, pot>0, ≥2 jogadores ativos).")
        return

    # Histograma
    rounded = [round(r, 2) for r in ratios]
    counter = Counter(rounded)
    mode    = counter.most_common(1)[0][0]
    deviations   = [abs(r - mode) for r in rounded]
    suggested_tol = round(max(deviations) + 0.1, 2) if deviations else 1.0

    print(f"\n{'='*69}")
    print(f"{'t':>8}  {'mesa':<14}  {'pot':>6}  {'n':>4}  {'pot/n':>6}  status")
    print(f"{'-'*69}")
    for ts, tk, pot, n_active, ratio in matches:
        status = "MATCH" if abs(ratio - ante_fraction) <= tolerance else "FORA "
        print(f"{ts:>8.1f}s  {tk:<14}  {pot:>6.2f}  {n_active:>4}  {ratio:>6.3f}  ← {status}")

    print(f"\nHistograma de pot/n_active  (moda esperada = ante_fraction):")
    for val, count in sorted(counter.items()):
        bar = "█" * min(count, 50)
        tag = " ← moda" if val == mode else ""
        print(f"  {val:.2f}  {bar} ({count}){tag}")

    print(f"\n{'-'*69}")
    print(f"Configuração atual:   ante_fraction={ante_fraction}  ante_tolerance_bb={tolerance}")
    print(f"Sugestão automática:  ante_fraction={mode}  ante_tolerance_bb={suggested_tol}")
    print(f"\nPara aplicar, edite 'ante_config' em vision/roi_config.json:")
    print(f'  "ante_config": {{')
    print(f'    "ante_fraction":     {mode},')
    print(f'    "ante_tolerance_bb": {suggested_tol}')
    print(f'  }}')
    print(f"\n({len(matches)} frames analisados de {len(ocr_results)} key frames)")


def main():
    if len(sys.argv) < 2:
        print("Uso: python calibrate_antes.py --frames [key_frames/]")
        print("     python calibrate_antes.py --json output/.checkpoint_<video>.json")
        print("     python calibrate_antes.py video.mp4")
        sys.exit(1)

    if sys.argv[1] == "--frames":
        frames_dir = sys.argv[2] if len(sys.argv) >= 3 else "key_frames"
        data = _load_from_frames_dir(frames_dir)
    elif sys.argv[1] == "--json":
        if len(sys.argv) < 3:
            print("Erro: informe o caminho do arquivo JSON após --json")
            sys.exit(1)
        data = _load_from_json(sys.argv[2])
    else:
        data = _load_from_video(sys.argv[1])

    if not data:
        sys.exit(1)

    # Lê parâmetros atuais do roi_config para comparação
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        ante_cfg   = cfg.get("ante_config", {})
        ante_frac  = ante_cfg.get("ante_fraction", 0.5)
        ante_tol   = ante_cfg.get("ante_tolerance_bb", 1.0)
    except FileNotFoundError:
        ante_frac, ante_tol = 0.5, 1.0

    _analyze(data, ante_frac, ante_tol)


if __name__ == "__main__":
    main()
