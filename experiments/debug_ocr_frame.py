import sys, cv2, json
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

for target_sec in [1.17, 1.25, 1.87, 2.00, 2.50, 2.57, 3.00, 3.27, 4.67]:
    cap = cv2.VideoCapture(VIDEO)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(target_sec * fps))
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print(f"t={target_sec}: FAILED to read")
        continue

    data = read_table(frame, tpos, regions, sx, sy)
    print(f"\n================ t={target_sec:.2f}s ================")
    print("table_id:", data.get("table_id"))
    print("pot:", data.get("pot"), "| pot_ante:", data.get("pot_ante"))
    print("dealer_seat:", data.get("dealer_seat"))
    print("bets:", data.get("bets"))
    print("seats:")
    for i in range(1, 9):
        sk = f"seat_{i}"
        sinfo = data.get("seats", {}).get(sk, {})
        print(f"  {sk}: name={sinfo.get('name')} | stack={sinfo.get('stack')}")
