"""Debug the 6 spade card in hero_cards region."""
import json, sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from vision.ocr_reader import _ocr_table, _bbox_center, _VALID_CARDS, detect_suit_by_color

cfg       = json.loads(Path("vision/roi_config.json").read_text())
TABLE     = "bottom_right"
table_pos = cfg["table_positions"][TABLE]
regions   = cfg["regions"][TABLE]
hc_region = regions["hero_cards"]  # [441, 385, 78, 55]

tx, ty, tw, th = (int(round(table_pos[i])) for i in range(4))
rx = int(round(hc_region[0])); ry = int(round(hc_region[1]))
rw = int(round(hc_region[2])); rh = int(round(hc_region[3]))

frame = cv2.imread("key_frames/frame_00001s_1.17.png")
table_img = frame[ty:ty+th, tx:tx+tw]
ocr_results = _ocr_table(table_img)

print(f"HC region: rx={rx} ry={ry} rw={rw} rh={rh}")

# Find card tokens in region
card_xs = []
for bbox, text, conf in ocr_results:
    if conf < 0.4: continue
    cx, cy = _bbox_center(bbox)
    if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
        if any(c in _VALID_CARDS for c in text.upper()):
            card_xs.append((cx, text))
            print(f"  OCR token '{text}' at cx={cx:.1f}")

if not card_xs:
    print("  No card tokens found in HC region!")
    sys.exit()

card_xs.sort()
# Show the second card (6 = spade) crop analysis
if len(card_xs) >= 2:
    cx, tok = card_xs[1]  # second card
    half_w = max(rw // max(len(card_xs) * 2, 2), 20)
    x1 = max(0, int(cx) - half_w)
    x2 = min(table_img.shape[1], int(cx) + half_w)
    y1 = max(0, ry); y2 = min(table_img.shape[0], ry + rh)
    crop = table_img[y1:y2, x1:x2]

    print(f"\nCrop for '{tok}': x={x1}-{x2}, y={y1}-{y2}, size={crop.shape}")
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]

    print(f"  V distribution: <50={int(np.sum(V<50))}, 50-80={int(np.sum((V>=50)&(V<80)))}, 80-100={int(np.sum((V>=80)&(V<100)))}, >100={int(np.sum(V>=100))}")
    print(f"  S distribution: <30={int(np.sum(S<30))}, 30-80={int(np.sum((S>=30)&(S<80)))}, >80={int(np.sum(S>=80))}")

    # With various V thresholds
    for vt in [50, 60, 70, 80, 90, 100]:
        cm = (S > 30) & (V > vt) & (V < 235)
        n = int(cm.sum())
        if n > 0:
            h_vals = H[cm]
            d = int(np.sum((h_vals >= 90) & (h_vals <= 130)))
            c = int(np.sum((h_vals >= 35) & (h_vals <= 85)))
            h_c = int(np.sum((h_vals >= 160) | (h_vals <= 15)))
            print(f"  V>{vt}: n_colored={n:4d}  D(d)={d:4d}  C(c)={c:4d}  H(h)={h_c:4d}")

    # Save crop for visual inspection
    cv2.imwrite("debug_spade_crop.png", crop)
    print(f"\n  Saved: debug_spade_crop.png")

    # Full debug detection
    print(f"\n  detect_suit_by_color debug:")
    suit = detect_suit_by_color(crop, debug=True)
    print(f"  Final suit: '{suit}'")
