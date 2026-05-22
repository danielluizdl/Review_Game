"""
Targeted debug: analyse specific frame(s) for the HL3048 flop.
Prints pixel-level stats for each card crop in the community_cards region.
"""
import json
import sys
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from vision.ocr_reader import detect_suit_by_color, _ocr_table, _bbox_center, _VALID_CARDS

cfg       = json.loads(Path("vision/roi_config.json").read_text())
table_pos = cfg["table_positions"]["bottom_right"]
regions   = cfg["regions"]["bottom_right"]
cc_region = regions["community_cards"]  # [328, 219, 305, 89]
hc_region = regions.get("hero_cards")

tx, ty, tw, th = (int(round(table_pos[i])) for i in range(4))

TARGET_FRAMES = [
    "key_frames/frame_00013s_13.00.png",
    "key_frames/frame_00013s_13.53.png",
    "key_frames/frame_00013s_13.75.png",
    "key_frames/frame_00013s_13.77.png",
    "key_frames/frame_00014s_14.25.png",
    "key_frames/frame_00014s_14.47.png",
    "key_frames/frame_00014s_14.75.png",
    "key_frames/frame_00019s_19.13.png",
    "key_frames/frame_00019s_19.25.png",
    "key_frames/frame_00020s_20.00.png",
    "key_frames/frame_00020s_20.07.png",
    "key_frames/frame_00020s_20.50.png",
]

print("Initializing RapidOCR...")
# Warm up
_ocr_table(np.zeros((10,10,3), dtype=np.uint8))

for fp in TARGET_FRAMES:
    frame = cv2.imread(fp)
    if frame is None:
        print(f"  SKIP: {fp}")
        continue
    table_img = frame[ty:ty + th, tx:tx + tw]
    ocr_results = _ocr_table(table_img)

    for region_name, region in [("CC", cc_region), ("HC", hc_region or [])]:
        if not region:
            continue
        rx = int(round(region[0])); ry = int(round(region[1]))
        rw = int(round(region[2])); rh = int(round(region[3]))

        card_xs = []
        for bbox, text, conf in ocr_results:
            if conf < 0.4: continue
            cx, cy = _bbox_center(bbox)
            if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                if any(c in _VALID_CARDS for c in text.upper()):
                    card_xs.append((cx, text))
        if not card_xs:
            continue

        card_xs.sort()
        merge_thr = max(rw * 0.12, 10.0)
        merged = []
        for x, t in card_xs:
            if not merged or x - merged[-1][0] > merge_thr:
                merged.append((x, t))

        if region_name == "CC" and len(merged) < 2:
            continue

        half_w = max(rw // max(len(merged) * 2, 2), 20)
        print(f"\n=== {fp}  [{region_name}] ===")
        print(f"    tokens: {[t for _,t in merged]}  half_w={half_w}")
        for cx, tok in merged:
            x1 = max(0, int(cx) - half_w)
            x2 = min(table_img.shape[1], int(cx) + half_w)
            y1 = max(0, ry); y2 = min(table_img.shape[0], ry + rh)
            crop = table_img[y1:y2, x1:x2]
            h_sz, w_sz = crop.shape[:2]

            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            H, S, V = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]
            # Stats
            sat_mask = S > 30
            n_sat = int(sat_mask.sum())
            mean_h = float(H[sat_mask].mean()) if n_sat > 0 else -1
            mean_s = float(S[sat_mask].mean()) if n_sat > 0 else -1
            mean_v = float(V[sat_mask].mean()) if n_sat > 0 else -1

            suit = detect_suit_by_color(crop, debug=True)
            print(f"    '{tok}' -> '{tok[0]}{suit}'  crop={w_sz}x{h_sz}"
                  f"  n_sat(S>30)={n_sat}  mean_H={mean_h:.1f}  mean_S={mean_s:.1f}  mean_V={mean_v:.1f}")
