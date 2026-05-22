"""
Test zone-based community card suit detection for HL3048 flop.
Scans frames 15-60s looking for the bottom_right table flop.
"""
import json, sys
from pathlib import Path
import cv2
sys.path.insert(0, str(Path(__file__).parent))
from vision.ocr_reader import read_table

cfg       = json.loads(Path("vision/roi_config.json").read_text())
TABLE     = "bottom_right"
table_pos = cfg["table_positions"][TABLE]
regions   = cfg["regions"][TABLE]

MAX_SHOW  = 8  # show first N frames with 3+ community cards

print("Scanning for flop frames (3+ community cards in CC region)...")
count = 0
for fp in sorted(Path("key_frames").glob("*.png")):
    # Only look at frames 5s-70s
    try:
        ts = float(fp.stem.split("_")[-1])
    except Exception:
        continue
    if ts < 5 or ts > 70:
        continue

    frame = cv2.imread(str(fp))
    if frame is None:
        continue
    h, w = frame.shape[:2]
    calib_w, calib_h = cfg.get("calibration_resolution", [w, h])
    sx, sy = w / calib_w, h / calib_h

    result = read_table(frame, table_pos, regions, sx, sy)
    cc = result.get("community_cards", [])
    hc = result.get("hero_cards", [])

    if len(cc) >= 3:
        count += 1
        print(f"  {fp.name}: CC={cc}  HC={hc}")
        if count >= MAX_SHOW:
            break

if count == 0:
    print("  No frames found with 3+ community cards in 5-70s range")
