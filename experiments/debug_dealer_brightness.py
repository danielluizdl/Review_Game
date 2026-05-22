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

print("=== BRIGHT PIXELS ANALYSIS (t = 1.17s) ===")
for i in range(1, 9):
    key = f"dealer_seat_{i}"
    if key not in regions:
        continue
    rx, ry, rw, rh = regions[key]
    crop = table_img[ry:ry+rh, rx:rx+rw]
    
    # Converte para cinza
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # Conta pixels brilhantes (ex: > 180)
    bright_180 = np.sum(gray > 180)
    bright_200 = np.sum(gray > 200)
    bright_220 = np.sum(gray > 220)
    pct_180 = bright_180 / gray.size
    
    print(f"Seat {i}:")
    print(f"  Gray min={np.min(gray)}, max={np.max(gray)}, mean={np.mean(gray):.1f}, std={np.std(gray):.1f}")
    print(f"  Bright pixels (>180): {bright_180} ({pct_180*100:.1f}%) | (>200): {bright_200} | (>220): {bright_220}")
