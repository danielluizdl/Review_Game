# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtualenv (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Process a video (main workflow)
python main.py video.mp4

# Process a video without checkpoint resumption
python main.py video.mp4 --no-checkpoint

# Analyze a single screenshot
python main.py --screenshot frame.png

# Print player stats from output JSON(s)
python main.py --stats output/hands_video_20240101_120000.json

# Run all tests
python -m pytest tests/

# Run a single test file
python -m pytest tests/test_hand_tracker.py

# Run a single test
python -m pytest tests/test_hand_tracker.py::TestProcessSequence::test_single_hand_detected

# Debug OCR on a saved frame
python test_ocr.py

# Recalibrate ROI coordinates interactively
python calibrate_interactive.py
```

## Architecture

The pipeline has four sequential stages, each in its own module:

### 1. `capture/` — Frame extraction without OCR

`change_detector.py` scans the entire video at 2 fps using **pixel-diff only** (no OCR). It computes a per-table signature (grayscale 32×16 thumbnail of watched regions, with `pot` and `community_cards` weighted 2×) and emits a key frame only when the pixel diff exceeds `diff_threshold`. The output is a list of dicts with `{timestamp, path, changed_tables}` — crucially, `changed_tables` names only the tables that actually changed, enabling selective OCR downstream.

`checkpoint.py` persists the accumulated OCR results to `output/.checkpoint_<stem>.json` every 50 frames so interrupted runs can resume without reprocessing from the start.

### 2. `vision/` — OCR and region parsing

`ocr_reader.py` runs **one RapidOCR call per table per key frame** (not per region). The ONNX model returns bounding boxes for all detected text; `_map_to_regions()` routes each detection to its ROI by checking whether the bounding box center falls inside the region rectangle. This whole-table approach is ~18× faster than calling OCR per region.

Parsers in the same file handle GGPoker-specific OCR noise:
- `_parse_bb()` / `_fix_bb_suffix()`: fixes OCR confusions of "BB" with "88", "8B", "B8", "阳", etc.
- `_fix_table_id()`: fixes character substitutions in the "HL\d+" table ID.
- `parse_seat_text()`: splits name + stack from a combined text field; detects timebank countdowns (pure digits) and suppresses them so the cached name is preserved.

`roi_map.py` holds the static fallback coordinates (for calibration reference). The **authoritative coordinates at runtime** come from `vision/roi_config.json`, which is loaded by both `main.py` and `change_detector.py`. When ROIs need adjustment, edit `roi_config.json` directly (or use `calibrate_interactive.py`).

### 3. `engine/` — Hand tracking and stats

`hand_tracker.py` consumes the sequence of OCR results and reconstructs poker hands:
- **Hand start**: pot transitions from 0/None → positive (blinds posted).
- **Street**: inferred from the count of community cards (0=preflop, 3=flop, 4=turn, 5=river).
- **Hand end**: pot returns to 0/None after being positive.
- **Positions**: inferred from the `bets` dict at hand start — smallest bet = SB, second = BB, third (if ≥4 players) = STR (mandatory straddle). BTN = seat immediately before SB in clockwise order.
- **Actions**: `_infer_actions()` compares consecutive frames — bet increase → raise/bet; bet disappears + pot rose → call; bet disappears + pot didn't rise → fold.
- **Winner**: player with the largest positive stack delta at hand end.

`validate_hands()` filters out false positives: hands with <2 named players, duration <5s, pot_peak <1 BB, or <2 captured frames.

`stats.py` aggregates VPIP, PFR, AF, and net BB per player from the output JSON files.

### 4. `output/` — Persistence

`json_writer.py` serializes completed `Hand` objects to `output/hands_<stem>_<timestamp>.json`. The checkpoint file is deleted on successful completion.

## Key data flow

```
video.mp4
  → capture/change_detector.py  (pixel diff, no OCR)     → key_frames/
  → vision/ocr_reader.py        (1 OCR call/table/frame)  → list[dict] (raw OCR results)
  → engine/hand_tracker.py      (state machine per table) → list[Hand]
  → output/json_writer.py       (serialize)               → output/hands_*.json
  → engine/stats.py             (aggregate)               → terminal stats table
```

## ROI calibration

All region coordinates in `roi_config.json` are relative to each table's bounding box, calibrated at `1920×1080`. When the video resolution differs, `sx/sy` scale factors are applied automatically. The four table positions (`top_left`, `top_right`, `bottom_left`, `bottom_right`) are absolute pixel coordinates within the full frame.

To adjust ROIs after a layout change: run `python calibrate_interactive.py` against a representative frame, then update `roi_config.json`.
