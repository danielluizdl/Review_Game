"""Debug: all OCR (incl low-conf) at t=0 and t=60, plus cc parsing at flop."""
import sys, cv2, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from vision.ocr_reader import _bbox_center, get_reader

VIDEO = "video_teste_reduzido.mp4"
with open("vision/roi_config.json") as f:
    cfg = json.load(f)
tpos = cfg["table_positions"]["bottom_right"]
regions = cfg["regions"]["bottom_right"]

cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()

reader = get_reader()

# Check t=0s: show ALL detections near seat_3/4 area (no confidence filter)
print("=== t=0s: all detections near dealer_seat_3 area (x=200-320, y=140-300) ===")
cap = cv2.VideoCapture(VIDEO)
cap.set(cv2.CAP_PROP_POS_FRAMES, int(0 * fps))
ret, full_frame = cap.read()
cap.release()

tx, ty, tw, th = int(tpos[0]), int(tpos[1]), int(tpos[2]), int(tpos[3])
table_img = full_frame[ty:ty+th, tx:tx+tw]
raw, _ = reader(table_img)
raw = raw or []
for bbox, text, conf in raw:
    cx, cy = _bbox_center(bbox)
    if 100 <= cx <= 400 and 100 <= cy <= 350:
        print(f"  '{text}' conf={conf:.2f} center=({cx:.0f},{cy:.0f})")

# Check t=0s: dealer_seat_3 region specifically
ds3 = regions["dealer_seat_3"]  # [236, 229, 45, 36]
print(f"\ndealer_seat_3 ROI: x={ds3[0]}..{ds3[0]+ds3[2]}, y={ds3[1]}..{ds3[1]+ds3[3]}")
for bbox, text, conf in raw:
    cx, cy = _bbox_center(bbox)
    if ds3[0] <= cx <= ds3[0]+ds3[2] and ds3[1] <= cy <= ds3[1]+ds3[3]:
        print(f"  IN REGION: '{text}' conf={conf:.2f} center=({cx:.0f},{cy:.0f})")
print("  (nothing if empty)")

# cc parsing at t=21.7s
print("\n=== t=21.7s: community_cards region full OCR ===")
cap = cv2.VideoCapture(VIDEO)
cap.set(cv2.CAP_PROP_POS_FRAMES, int(21.7 * fps))
ret, full_frame = cap.read()
cap.release()
table_img = full_frame[ty:ty+th, tx:tx+tw]
raw21, _ = reader(table_img)
raw21 = raw21 or []
cc_roi = regions["community_cards"]  # [328, 219, 305, 89]
print(f"cc ROI: x={cc_roi[0]}..{cc_roi[0]+cc_roi[2]}, y={cc_roi[1]}..{cc_roi[1]+cc_roi[3]}")
for bbox, text, conf in raw21:
    cx, cy = _bbox_center(bbox)
    if cc_roi[0] <= cx <= cc_roi[0]+cc_roi[2] and cc_roi[1] <= cy <= cc_roi[1]+cc_roi[3]:
        print(f"  '{text}' conf={conf:.2f} center=({cx:.0f},{cy:.0f})")
