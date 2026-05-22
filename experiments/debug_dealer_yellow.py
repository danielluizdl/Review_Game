import cv2, json
import numpy as np

VIDEO = "video_teste_reduzido.mp4"
CONFIG_PATH = "vision/roi_config.json"
TABLE_KEY = "bottom_right"

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

tpos = cfg["table_positions"][TABLE_KEY]
regions = cfg["regions"][TABLE_KEY]

cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.set(cv2.CAP_PROP_POS_FRAMES, int(1.17 * fps))
ret, frame = cap.read()
cap.release()

tx, ty, tw, th = tpos
table_img = frame[ty:ty+th, tx:tx+tw]

print("=== YELLOW PIXELS ANALYSIS (t = 1.17s) ===")
# Filtro para amarelo/ouro no HSV
lower_yellow = np.array([10, 80, 120])
upper_yellow = np.array([40, 255, 255])

for i in range(1, 9):
    key = f"dealer_seat_{i}"
    if key not in regions:
        continue
    rx, ry, rw, rh = regions[key]
    crop = table_img[ry:ry+rh, rx:rx+rw]
    
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    num_yellow = np.sum(mask > 0)
    pct_yellow = num_yellow / mask.size
    
    print(f"Seat {i}:")
    print(f"  Yellow pixels: {num_yellow} ({pct_yellow*100:.1f}%)")
