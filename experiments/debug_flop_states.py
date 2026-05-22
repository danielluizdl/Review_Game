import cv2, json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from vision.ocr_reader import read_table

VIDEO = "video_teste_reduzido.mp4"
CONFIG_PATH = "vision/roi_config.json"
TABLE_KEY = "bottom_right"

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

tpos = cfg["table_positions"][TABLE_KEY]
regions = cfg["regions"][TABLE_KEY]
calib_w, calib_h = cfg.get("calibration_resolution", [1920, 1080])

cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()
sx = frame_w / calib_w
sy = frame_h / calib_h

# Timestamps correspondentes aos key frames em torno do flop (t = 21s ate 44s)
timestamps = [21.23, 21.70, 22.75, 22.87, 23.25, 23.75, 23.80, 24.25, 24.50, 24.75, 25.25, 25.43, 25.75, 26.37, 26.50, 27.50, 27.53, 28.00, 28.23, 28.50, 29.17, 29.25, 30.10, 30.25, 30.33, 30.50, 30.75, 30.80, 31.25, 31.50, 31.75, 32.20, 32.25, 32.43, 32.75, 32.90, 33.25, 33.37, 33.60, 33.75, 34.25, 34.75, 34.77, 35.47, 35.50, 35.70, 35.75, 36.00, 36.17, 36.50, 36.87, 37.00, 37.50, 37.57, 37.75, 37.80, 38.00, 38.73, 38.75, 39.25, 39.43, 39.75, 40.37, 40.50, 41.00, 41.75, 41.77, 42.25, 42.70, 42.75, 43.25, 43.75]

for ts in timestamps:
    cap = cv2.VideoCapture(VIDEO)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
    ret, frame = cap.read()
    cap.release()
    if not ret:
        continue
    data = read_table(frame, tpos, regions, sx, sy)
    bets = data.get("bets", {})
    action_labels = data.get("action_labels", {})
    pot = data.get("pot")
    if bets or action_labels or pot:
        print(f"t={ts:5.2f}s | pot={pot} | bets={bets} | action_labels={action_labels}")
