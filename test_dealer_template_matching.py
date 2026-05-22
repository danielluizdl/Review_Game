import cv2, json
import numpy as np

VIDEO = "video_teste_reduzido.mp4"
CONFIG_PATH = "vision/roi_config.json"
TABLE_KEY = "bottom_right"
TEMPLATE_PATH = "vision/dealer_template.png"

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

tpos = cfg["table_positions"][TABLE_KEY]
regions = cfg["regions"][TABLE_KEY]

template = cv2.imread(TEMPLATE_PATH)
if template is None:
    print("Template nao encontrado")
    sys.exit(1)

cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.set(cv2.CAP_PROP_POS_FRAMES, int(1.17 * fps))
ret, frame = cap.read()
cap.release()

tx, ty, tw, th = tpos
table_img = frame[ty:ty+th, tx:tx+tw]

print("=== TEMPLATE MATCHING ANALYSIS (t = 1.17s) ===")
for i in range(1, 9):
    key = f"dealer_seat_{i}"
    if key not in regions:
        continue
    rx, ry, rw, rh = regions[key]
    crop = table_img[ry:ry+rh, rx:rx+rw]
    
    # Executa matchTemplate
    res = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    print(f"Seat {i}: max_score = {max_val:.4f} at {max_loc}")
