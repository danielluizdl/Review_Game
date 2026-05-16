"""
Ponto de entrada principal.
Uso: python main.py <video.mp4> [--no-checkpoint]
      python main.py --screenshot <frame.png>
      python main.py --stats <arquivo.json> [arquivo2.json ...]
"""
import os
import sys
import cv2
import json
from pathlib import Path

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
        cc = data.get("community_cards", [])
        hc = data.get("hero_cards", [])
        if cc:
            print(f"  Comunitárias: {cc}")
        if hc:
            print(f"  Hero cards:   {hc}")
        print(f"{'='*40}")
        for seat, info in data["seats"].items():
            print(f"  {seat}: {info['name']:<20} {info['stack']} BB")


def _process_video(video_path, cfg, use_checkpoint=True):
    from vision.ocr_reader import read_table
    from capture.change_detector import extract_key_frames
    from capture.checkpoint import save_checkpoint, load_checkpoint
    from engine.hand_tracker import HandTracker, print_summary, validate_hands
    from output.json_writer import write_hands

    output_dir      = "key_frames"
    checkpoint_path = os.path.join("output", f".checkpoint_{Path(video_path).stem}.json")

    key_frames = extract_key_frames(video_path, output_dir=output_dir)
    if not key_frames:
        print("Nenhuma mudança detectada no vídeo.")
        return

    all_table_keys = list(cfg["table_positions"].keys())
    all_results: list[dict] = []

    # Retomada de checkpoint
    if use_checkpoint:
        existing = load_checkpoint(checkpoint_path)
        if existing:
            last_ts    = max(r["timestamp"] for r in existing)
            all_results = existing
            key_frames  = [kf for kf in key_frames if kf["timestamp"] > last_ts]
            print(f"Retomando de checkpoint: {len(existing)} frames já processados")
            print(f"Restam {len(key_frames)} key frames para processar")

    print(f"\nAnalisando {len(key_frames)} key frames com OCR seletivo...\n")

    table_state_cache: dict = {}
    ocr_calls  = 0
    cache_hits = 0

    for i, kf in enumerate(key_frames, 1):
        frame = cv2.imread(kf["path"])
        if frame is None:
            continue

        h, w = frame.shape[:2]
        calib_w, calib_h = cfg.get("calibration_resolution", [w, h])
        sx, sy = w / calib_w, h / calib_h

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

        # Progresso
        line = f"[{i}/{len(key_frames)}] t={kf['timestamp']:.1f}s  "
        for tk, data in frame_results.items():
            marker = "" if data["_from_cache"] else "*"
            line += f"{marker}{tk[:2].upper()}→{data['table_id']} pot={data['pot']}  "
        print(line)

        # Checkpoint periódico
        if use_checkpoint and i % 50 == 0:
            save_checkpoint(all_results, checkpoint_path)

    total   = ocr_calls + cache_hits
    economy = 100 * cache_hits / total if total > 0 else 0
    print(f"\nOCR calls: {ocr_calls} | cache hits: {cache_hits} | economia: {economy:.0f}%")

    # Rastreamento de mãos
    hands = HandTracker(cfg).process_sequence(all_results)
    hands, rejected = validate_hands(hands)

    if rejected:
        print(f"\nMãos rejeitadas ({len(rejected)}):")
        for r in rejected:
            print(f"  x {r['hand']} — {r['reason']}")

    print_summary(hands)

    out_path = write_hands(hands, video_path)

    # Remove checkpoint após conclusão bem-sucedida
    if use_checkpoint and os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
        print(f"Checkpoint removido. Resultado final: {out_path}")
    else:
        print(f"\nResultado salvo em: {out_path}")

    print(f"Processamento concluído: {len(all_results)} frames | {len(hands)} mãos detectadas.")


def main():
    if len(sys.argv) < 2:
        print("Uso: python main.py <video.mp4> [--no-checkpoint]")
        print("      python main.py --screenshot <frame.png>")
        print("      python main.py --stats <arquivo.json> [arquivo2.json ...]")
        sys.exit(1)

    if sys.argv[1] == "--screenshot":
        cfg  = load_config()
        path = sys.argv[2]
        frame = cv2.imread(path)
        if frame is None:
            print(f"Erro: não conseguiu abrir '{path}'")
            sys.exit(1)
        print(f"Analisando screenshot: {path}")
        print_results(analyze_frame(frame, cfg))

    elif sys.argv[1] == "--stats":
        from engine.stats import from_json, compute_player_stats, print_stats
        all_hands = []
        for path in sys.argv[2:]:
            all_hands.extend(from_json(path))
        stats = compute_player_stats(all_hands)
        print_stats(stats)

    else:
        cfg            = load_config()
        video_path     = sys.argv[1]
        use_checkpoint = "--no-checkpoint" not in sys.argv
        _process_video(video_path, cfg, use_checkpoint)


if __name__ == "__main__":
    main()
