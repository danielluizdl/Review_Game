import cv2, json
import numpy as np

VIDEO = "video_teste_reduzido.mp4"
CONFIG_PATH = "vision/roi_config.json"
TABLE_KEY = "bottom_right"

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

tpos = cfg["table_positions"][TABLE_KEY]
regions = cfg["regions"][TABLE_KEY]

# Abre o frame em t = 1.17s
cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.set(cv2.CAP_PROP_POS_FRAMES, int(1.17 * fps))
ret, frame = cap.read()
cap.release()

if not ret:
    print("Erro ao carregar o frame")
    sys.exit(1)

tx, ty, tw, th = tpos
table_img = frame[ty:ty+th, tx:tx+tw]

print("=== ANALISE VISUAL DOS DEALER SEAT REGIONS (t = 1.17s) ===")
for i in range(1, 9):
    key = f"dealer_seat_{i}"
    if key not in regions:
        continue
    rx, ry, rw, rh = regions[key]
    crop = table_img[ry:ry+rh, rx:rx+rw]
    
    # Converte para HSV para analise de cor
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mean_bgr = np.mean(crop, axis=(0, 1))
    mean_hsv = np.mean(hsv, axis=(0, 1))
    std_bgr = np.std(crop, axis=(0, 1))
    
    # Salva o crop para inspecao se necessario
    cv2.imwrite(f"debug_dealer_seat_{i}.png", crop)
    
    print(f"Seat {i}:")
    print(f"  Mean BGR: B={mean_bgr[0]:.1f}, G={mean_bgr[1]:.1f}, R={mean_bgr[2]:.1f}")
    print(f"  Mean HSV: H={mean_hsv[0]:.1f}, S={mean_hsv[1]:.1f}, V={mean_hsv[2]:.1f}")
    print(f"  Std BGR:  B={std_bgr[0]:.1f}, G={std_bgr[1]:.1f}, R={std_bgr[2]:.1f}")
