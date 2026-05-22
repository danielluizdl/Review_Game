"""
Debug zone-based suit detection for HL3048 flop frames.
Shows per-zone HSV stats to diagnose why K/A are detected as spades.
"""
import json, sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from vision.ocr_reader import detect_suit_by_color

cfg       = json.loads(Path("vision/roi_config.json").read_text())
TABLE     = "bottom_right"
table_pos = cfg["table_positions"][TABLE]
regions   = cfg["regions"][TABLE]
cc_region = regions["community_cards"]

# Known flop frames from test_flop_suits output
TARGET_FRAMES = [
    "frame_00021s_21.70.png",
    "frame_00021s_21.75.png",
    "frame_00024s_24.75.png",
]

for fname in TARGET_FRAMES:
    fp = Path("key_frames") / fname
    if not fp.exists():
        print(f"MISSING: {fname}")
        continue

    frame = cv2.imread(str(fp))
    if frame is None:
        print(f"UNREADABLE: {fname}")
        continue

    h, w = frame.shape[:2]
    calib_w, calib_h = cfg.get("calibration_resolution", [w, h])
    sx, sy = w / calib_w, h / calib_h

    # Extract table sub-image
    tx = int(round(table_pos[0] * sx)); ty = int(round(table_pos[1] * sy))
    tw = int(round(table_pos[2] * sx)); th = int(round(table_pos[3] * sy))
    table_img = frame[ty:ty+th, tx:tx+tw]

    # CC region coords
    rx = int(round(cc_region[0]*sx)); ry = int(round(cc_region[1]*sy))
    rw = int(round(cc_region[2]*sx)); rh = int(round(cc_region[3]*sy))
    y1 = max(0, ry); y2 = min(table_img.shape[0], ry + rh)

    n_cards = 3
    zone_w = rw / n_cards

    print(f"\n{'='*60}")
    print(f"Frame: {fname}")
    print(f"CC region: x={rx} y={ry} w={rw} h={rh}")
    print(f"Table img shape: {table_img.shape}")

    for i in range(n_cards):
        x1 = max(0, rx + int(round(i * zone_w)))
        x2 = min(table_img.shape[1], rx + int(round((i + 1) * zone_w)))
        crop = table_img[y1:y2, x1:x2]

        if crop.size == 0:
            print(f"  Zone {i}: EMPTY crop")
            continue

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        colored_mask = (S > 30) & (V > 80) & (V < 235)
        colored_h = H[colored_mask]
        n_colored = int(colored_h.size)
        dark_count = int(np.sum((V < 80) & (S < 60)))

        diamond = int(np.sum((colored_h >= 90) & (colored_h <= 130)))
        club    = int(np.sum((colored_h >= 35) & (colored_h <= 85)))
        heart   = int(np.sum((colored_h >= 160) | (colored_h <= 15)))

        suit = detect_suit_by_color(crop)

        print(f"  Zone {i} (x={x1}..{x2}, crop={crop.shape}): "
              f"n_colored={n_colored:4d}  dark={dark_count:4d}  "
              f"d={diamond:4d} c={club:4d} h={heart:4d}  -> '{suit}'")

        # Show hue histogram for colored pixels
        if n_colored > 0:
            hist, _ = np.histogram(colored_h, bins=18, range=(0, 180))
            hue_ranges = [f"H{i*10}-{(i+1)*10}:{hist[i]}" for i in range(18) if hist[i] > 0]
            print(f"    Hue dist: {' | '.join(hue_ranges[:8])}")

        # Save zone crop for visual inspection
        out_path = Path(f"debug_zone_{fname.replace('.png','')}_{i}.png")
        cv2.imwrite(str(out_path), crop)
        print(f"    Saved: {out_path}")
