import json, sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

checkpoint_path = "output/.checkpoint_video_teste_reduzido.json"
if not os.path.exists(checkpoint_path):
    print("Checkpoint file not found")
    sys.exit(0)

with open(checkpoint_path, encoding='utf-8') as f:
    raw = json.load(f)

print(f"Total frames in checkpoint: {len(raw)}")
# Cada frame e um dict com "timestamp", "tables" (contem mesa -> dados OCR)
# Vamos filtrar frames que contem table_id com "HL3048"
table_frames = []
for frame in raw:
    tables = frame.get("tables", {})
    for tk, data in tables.items():
        if 'HL3048' in str(data.get('table_id', '')):
            table_frames.append({
                "ts": frame.get("timestamp"),
                "tk": tk,
                "data": data
            })

print(f"HL3048 frames: {len(table_frames)}")
for i, f in enumerate(table_frames[:15]):
    d = f["data"]
    print(f"[{i}] t={f['ts']:.1f}s | blinds={d.get('blinds')} | pot={d.get('pot')} | bets={d.get('bets')}")
    print(f"    seats: { {k: v['name'] for k, v in d.get('seats', {}).items()} }")
    print(f"    dealer_seat: '{d.get('dealer_seat')}'")
    print(f"    action_labels: {d.get('action_labels')}")
