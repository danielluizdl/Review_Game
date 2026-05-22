"""
Debug script: targeted analysis of suit detection for the HL3048 hand.
Looks at bottom_right table community_cards and hero_cards regions.
Only processes frames where OCR finds card tokens in those regions.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from vision.ocr_reader import detect_suit_by_color, _ocr_table, _bbox_center, _VALID_CARDS

CFG_PATH = Path("vision/roi_config.json")
FRAMES   = Path("key_frames")
MAX_FRAMES_WITH_CARDS = 20   # stop after finding this many frames with real cards
MIN_CARDS_IN_REGION   = 2    # require at least this many valid tokens for CC (flop=3)

cfg       = json.loads(CFG_PATH.read_text())
positions = cfg["table_positions"]
all_regs  = cfg["regions"]

TABLE    = "bottom_right"
table_pos = positions[TABLE]
regions   = all_regs[TABLE]

tx, ty, tw, th = (int(round(table_pos[i])) for i in range(4))

cc_region = regions.get("community_cards")
hc_region = regions.get("hero_cards")

def analyse_region(table_img, ocr_results, region, label, max_cards=5):
    if not region:
        return
    rx = int(round(region[0])); ry = int(round(region[1]))
    rw = int(round(region[2])); rh = int(round(region[3]))

    card_xs = []
    for bbox, text, conf in ocr_results:
        if conf < 0.4:
            continue
        cx, cy = _bbox_center(bbox)
        if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
            if any(c in _VALID_CARDS for c in text.upper()):
                card_xs.append((cx, text))

    if not card_xs:
        return

    card_xs.sort()
    merge_thr = max(rw * 0.12, 10.0)
    merged = []
    for x, t in card_xs:
        if not merged or x - merged[-1][0] > merge_thr:
            merged.append((x, t))

    half_w = max(rw // max(len(merged) * 2, 2), 20)
    suits = []
    print(f"  [{label}] tokens={[t for _, t in merged]}")
    for cx, tok in merged[:max_cards]:
        x1 = max(0, int(cx) - half_w)
        x2 = min(table_img.shape[1], int(cx) + half_w)
        y1 = max(0, ry); y2 = min(table_img.shape[0], ry + rh)
        crop = table_img[y1:y2, x1:x2]
        suit = detect_suit_by_color(crop, debug=True)
        suits.append(f"{tok[0]}{suit}")
        print(f"    '{tok}' -> '{tok[0]}{suit}'")
    print(f"  [{label}] RESULT: {suits}")

print("=" * 60)
print(f"Table: {TABLE}  Analysing community+hero card suits")
print(f"CC region: {cc_region}")
print(f"HC region: {hc_region}")
print("=" * 60)

frames_with_cards = 0
frames = sorted(FRAMES.glob("*.png"))

for fp in frames:
    frame = cv2.imread(str(fp))
    if frame is None:
        continue
    table_img = frame[ty:ty + th, tx:tx + tw]
    if table_img.size == 0:
        continue

    ocr_results = _ocr_table(table_img)

    # Check if any card tokens in cc or hc region
    def count_cards(region):
        if not region:
            return 0
        rx = int(round(region[0])); ry = int(round(region[1]))
        rw = int(round(region[2])); rh = int(round(region[3]))
        xs = []
        for bbox, text, conf in ocr_results:
            if conf < 0.4:
                continue
            cx, cy = _bbox_center(bbox)
            if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                if any(c in _VALID_CARDS for c in text.upper()):
                    xs.append(cx)
        if not xs:
            return 0
        # Merge nearby x positions to count distinct cards
        xs.sort()
        merge_thr = max(rw * 0.12, 10.0)
        merged_count = 1
        prev = xs[0]
        for x in xs[1:]:
            if x - prev > merge_thr:
                merged_count += 1
            prev = x
        return merged_count

    cc_count = count_cards(cc_region)
    hc_count = count_cards(hc_region)
    # Require 3+ distinct cards in CC to see real flop/turn/river
    if cc_count >= 3 or hc_count >= 1:
        print(f"\n--- {fp.name} ---")
        analyse_region(table_img, ocr_results, cc_region, "CC", 5)
        analyse_region(table_img, ocr_results, hc_region, "HC", 2)
        frames_with_cards += 1
        if frames_with_cards >= MAX_FRAMES_WITH_CARDS:
            print(f"\n[Stopped after {MAX_FRAMES_WITH_CARDS} frames with cards]")
            break

print("\n" + "=" * 60)
print("EXPECTED: CC [Kd Ad 9d] turn [8d], HC [2c 6s]")
print("=" * 60)
