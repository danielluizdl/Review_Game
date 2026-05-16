"""
Ponto de entrada principal.
Uso: python main.py <video.mp4>
      python main.py --screenshot <frame.png>
"""
import sys
import cv2
import json

CONFIG_PATH = "vision/roi_config.json"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def analyze_frame(frame, cfg):
    """Modo screenshot: OCR em todas as mesas sem cache."""
    from vision.ocr_reader import read_table

    h, w = frame.shape[:2]
    calib_w, calib_h = cfg.get("calibration_resolution", [w, h])
    sx, sy = w / calib_w, h / calib_h

    return {
        tk: read_table(frame, tpos, cfg["regions"][tk], sx, sy)
        for tk, tpos in cfg["table_positions"].items()
    }


def print_results(results):
    for table_key, data in results.items():
        print(f"\n{'='*40}")
        print(f"Mesa: {table_key} | ID: {data['table_id']} | "
              f"{data['blinds']} | {data['game_type']} | Pot: {data['pot']} BB")
        print(f"{'='*40}")
        for seat, info in data["seats"].items():
            print(f"  {seat}: {info['name']:<20} {info['stack']} BB")


def _process_video(video_path, cfg):
    from vision.ocr_reader import read_table
    from capture.change_detector import extract_key_frames
    from engine.hand_tracker import HandTracker, print_summary
    from output.json_writer import write_hands

    output_dir = "key_frames"
    key_frames = extract_key_frames(video_path, output_dir=output_dir)

    if not key_frames:
        print("Nenhuma mudança detectada no vídeo.")
        return

    all_table_keys = list(cfg["table_positions"].keys())
    print(f"\nAnalisando {len(key_frames)} key frames com OCR seletivo...\n")

    table_state_cache: dict = {}
    ocr_calls  = 0
    cache_hits = 0
    all_results: list[dict] = []

    for i, kf in enumerate(key_frames, 1):
        frame = cv2.imread(kf["path"])
        if frame is None:
            continue

        h, w = frame.shape[:2]
        calib_w, calib_h = cfg.get("calibration_resolution", [w, h])
        sx, sy = w / calib_w, h / calib_h

        # Mesas que mudaram neste frame (fallback: todas)
        changed = set(kf.get("changed_tables", all_table_keys))

        frame_results = {}
        for tk in all_table_keys:
            if tk in changed or tk not in table_state_cache:
                state = read_table(frame, cfg["table_positions"][tk],
                                   cfg["regions"][tk], sx, sy)
                table_state_cache[tk] = state
                frame_results[tk] = {**state, "_from_cache": False}
                ocr_calls += 1
            else:
                frame_results[tk] = {**table_state_cache[tk], "_from_cache": True}
                cache_hits += 1

        all_results.append({"timestamp": kf["timestamp"], "tables": frame_results})

        # Progresso — destaca mesas que rodaram OCR com *
        line = f"[{i}/{len(key_frames)}] t={kf['timestamp']:.1f}s  "
        for tk, data in frame_results.items():
            marker = "" if data["_from_cache"] else "*"
            line += f"{marker}{tk[:2].upper()}→{data['table_id']} pot={data['pot']}  "
        print(line)

    # Estatísticas de cache
    total    = ocr_calls + cache_hits
    economy  = 100 * cache_hits / total if total > 0 else 0
    print(f"\nOCR calls: {ocr_calls} | cache hits: {cache_hits} | economia: {economy:.0f}%")

    # Rastreamento de mãos
    hands = HandTracker(cfg).process_sequence(all_results)
    print_summary(hands)

    out_path = write_hands(hands, video_path)
    print(f"\nResultado salvo em: {out_path}")
    print(f"Processamento concluído: {len(all_results)} frames | {len(hands)} mãos detectadas.")


def main():
    if len(sys.argv) < 2:
        print("Uso: python main.py <video.mp4>")
        print("      python main.py --screenshot <frame.png>")
        sys.exit(1)

    cfg = load_config()

    if sys.argv[1] == "--screenshot":
        path = sys.argv[2]
        frame = cv2.imread(path)
        if frame is None:
            print(f"Erro: não conseguiu abrir '{path}'")
            sys.exit(1)
        print(f"Analisando screenshot: {path}")
        print_results(analyze_frame(frame, cfg))
    else:
        _process_video(sys.argv[1], cfg)


if __name__ == "__main__":
    main()
