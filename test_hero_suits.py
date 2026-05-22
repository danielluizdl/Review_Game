"""
Direct test: what does read_table() return for hero_cards in early frames?
"""
import json, sys
from pathlib import Path
import cv2
sys.path.insert(0, str(Path(__file__).parent))
from vision.ocr_reader import read_table

cfg       = json.loads(Path("vision/roi_config.json").read_text())
TABLE     = "bottom_right"
table_pos = cfg["table_positions"][TABLE]
regions   = cfg["regions"][TABLE]

TEST_FRAMES = [
    "key_frames/frame_00001s_1.17.png",
    "key_frames/frame_00001s_1.25.png",
    "key_frames/frame_00001s_1.87.png",
    "key_frames/frame_00002s_2.00.png",
]

print("Testing read_table() hero_cards with color detection...")
for fp in TEST_FRAMES:
    frame = cv2.imread(fp)
    if frame is None:
        print(f"  SKIP {fp}")
        continue
    h, w = frame.shape[:2]
    calib_w, calib_h = cfg.get("calibration_resolution", [w, h])
    sx, sy = w / calib_w, h / calib_h
    result = read_table(frame, table_pos, regions, sx, sy)
    hc = result.get("hero_cards", [])
    cc = result.get("community_cards", [])
    print(f"  {fp}: hero_cards={hc}  community_cards={cc}")
